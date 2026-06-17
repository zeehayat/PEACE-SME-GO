# Chapter 8: Grant Applications and Workflow Rules

## Purpose

The grant workflow is the core applicant feature. It involves a large multi-section form, JSONB storage in PostgreSQL, a whitelist access gate, asynchronous HFC fraud scoring, and a multi-step approval process. This chapter teaches the complete implementation: handler, service, repository, and JSONB handling — using Go interfaces to keep each layer clean and testable.

---

## The Grant Workflow End to End

Before writing any code, understand the full lifecycle:

```
1. Admin whitelists applicant
   → INSERT/UPDATE grant_access_whitelist SET is_selected=true

2. Applicant submits grant (POST /api/grant)
   → Check whitelist if GRANT_REQUIRE_SELECTION=1
   → INSERT INTO grants (...)
   → Enqueue HFC scoring job → Redis → background worker

3. HFC worker runs
   → calculate_hfc_for_user(user_id)
   → INSERT INTO hfc_evaluations (...)
   → UPDATE grants SET hfc_score=N, hfc_risk_level='LOW'|'MEDIUM'|'HIGH'|'CRITICAL'

4. Applicant updates grant (PUT /api/grant)
   → UPDATE grants (...)
   → Re-enqueue HFC job (debounced 60s)

5. Admin reviews submitted grants
   → GET /api/admin/grants/submitted
   → GET /api/admin/grants/:user_id/approval-check (HFC score + checklist)

6. Approving authority approves
   → POST /api/admin/grants/:user_id/approve
   → UPDATE grants SET status='Approved', approved_amount=..., approved_by=...
   → INSERT INTO grant_approval_logs (...)
   → Enqueue approval emails (applicant + internal notification)
```

---

## The Grant Database Schema

Understanding the schema before writing any Go code:

```sql
CREATE TABLE grants (
  grant_id                  SERIAL PRIMARY KEY,
  user_id                   INTEGER UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

  -- Core fields
  expression_of_interest    TEXT,              -- stored as JSON: ["Purpose A", "Purpose B"]
  grant_required            REAL,
  application_date          DATE,
  status                    VARCHAR(50) DEFAULT 'Pending',
  how_did_you_hear          VARCHAR(255),

  -- Contribution section
  contribution_type         VARCHAR(100),
  financial_amount          REAL,
  financial_amount_words    TEXT,
  inkind_details            TEXT,
  inkind_value              REAL,
  contribution_utilization  TEXT,

  -- Grant narrative section
  grant_support_growth      TEXT,
  job_creation_details      TEXT,
  grant_amount_words        TEXT,
  other_purpose_text        TEXT,

  -- Approval fields (set by approving authority)
  approved_amount           REAL,
  approval_reason           TEXT,
  approved_at               TIMESTAMP,
  approved_by               VARCHAR(100),

  -- HFC fraud detection fields
  hfc_status                VARCHAR(30) DEFAULT 'HFC_Pending',
  hfc_score                 INTEGER DEFAULT 0,
  hfc_risk_level            VARCHAR(20) DEFAULT 'LOW',
  hfc_last_evaluated_at     TIMESTAMP,
  hfc_model_version         VARCHAR(50),

  -- JSONB fields (multi-value selections stored as arrays)
  domicile_district         TEXT,
  business_type             JSONB DEFAULT '[]',
  business_type_other       TEXT,
  tax_registration_status   JSONB DEFAULT '[]',
  ntn_registration_no       TEXT,
  tax_filer_status          VARCHAR(20),
  working_capital           BOOLEAN DEFAULT FALSE,
  financed_items            JSONB DEFAULT '[]',   -- [{item, quantity, estimated_cost}]
  expected_production_increase TEXT,
  employment_grid           JSONB DEFAULT '{}',   -- {before_male, before_female, after_male, after_female}
  declaration_accepted      BOOLEAN DEFAULT FALSE,
  declaration_name          TEXT,

  -- Disclaimer section
  has_srsp_relative         BOOLEAN DEFAULT FALSE,
  srsp_relatives            JSONB DEFAULT '[]'    -- [{name, position, office}]
);
```

Key observations:
- `user_id` is `UNIQUE` — one grant per user. POST creates, PUT updates.
- JSONB fields store arrays or objects as JSON strings in PostgreSQL.
- `status` transitions: `Pending` → `Approved` or `Rejected`
- `expression_of_interest` is a JSON array stored as TEXT (not JSONB).

---

## Go Data Structures for the Grant

### The Request Struct

This struct must exactly match the JSON payload the Vue frontend sends:

```go
// internal/grant/types.go
package grant

import "encoding/json"

// ApplyRequest maps directly to the JSON body from SmeGrantApplication.vue
type ApplyRequest struct {
    ExpressionOfInterest  []string           `json:"expression_of_interest"`
    OtherPurposeText      string             `json:"other_purpose_text"`
    GrantRequired         float64            `json:"grant_required"`
    GrantAmountWords      string             `json:"grant_amount_words"`
    ApplicationDate       string             `json:"application_date"`
    WorkingCapital        bool               `json:"working_capital"`
    FinancedItems         []FinancedItem     `json:"financed_items"`
    ContributionType      string             `json:"contribution_type"`
    FinancialAmount       *float64           `json:"financial_amount"`
    FinancialAmountWords  string             `json:"financial_amount_words"`
    InkindDetails         string             `json:"inkind_details"`
    InkindValue           *float64           `json:"inkind_value"`
    ContributionUtil      string             `json:"contribution_utilization"`
    GrantSupportGrowth    string             `json:"grant_support_growth"`
    JobCreationDetails    string             `json:"job_creation_details"`
    HowDidYouHear         string             `json:"how_did_you_hear"`
    DomicileDistrict      string             `json:"domicile_district"`
    BusinessType          []string           `json:"business_type"`
    BusinessTypeOther     string             `json:"business_type_other"`
    TaxRegistrationStatus []string           `json:"tax_registration_status"`
    NTNRegistrationNo     string             `json:"ntn_registration_no"`
    TaxFilerStatus        string             `json:"tax_filer_status"`
    ExpectedProdIncrease  string             `json:"expected_production_increase"`
    EmploymentGrid        EmploymentGrid     `json:"employment_grid"`
    DeclarationAccepted   bool               `json:"declaration_accepted"`
    DeclarationName       string             `json:"declaration_name"`
    HasSRSPRelative       bool               `json:"has_srsp_relative"`
    SRSPRelatives         []SRSPRelative     `json:"srsp_relatives"`
}

// FinancedItem represents one row in the "Items to be Financed" section.
type FinancedItem struct {
    Item          string  `json:"item"`
    Quantity      int     `json:"quantity"`
    EstimatedCost float64 `json:"estimated_cost"`
}

// EmploymentGrid stores before/after employment numbers.
type EmploymentGrid struct {
    BeforeMale   int `json:"before_male"`
    BeforeFemale int `json:"before_female"`
    AfterMale    int `json:"after_male"`
    AfterFemale  int `json:"after_female"`
}

// SRSPRelative represents one row in the SRSP relatives disclaimer table.
type SRSPRelative struct {
    Name     string `json:"name"`
    Position string `json:"position"`
    Office   string `json:"office"`
}

// Grant represents a row from the grants table.
type Grant struct {
    GrantID               int64
    UserID                int64
    Status                string
    ExpressionOfInterest  []string
    GrantRequired         *float64
    ApplicationDate       string
    WorkingCapital        bool
    FinancedItems         []FinancedItem
    ContributionType      string
    FinancialAmount       *float64
    FinancialAmountWords  string
    InkindDetails         string
    InkindValue           *float64
    ContributionUtil      string
    GrantSupportGrowth    string
    JobCreationDetails    string
    GrantAmountWords      string
    OtherPurposeText      string
    HowDidYouHear         string
    DomicileDistrict      string
    BusinessType          []string
    BusinessTypeOther     string
    TaxRegistrationStatus []string
    NTNRegistrationNo     string
    TaxFilerStatus        string
    ExpectedProdIncrease  string
    EmploymentGrid        EmploymentGrid
    DeclarationAccepted   bool
    DeclarationName       string
    HasSRSPRelative       bool
    SRSPRelatives         []SRSPRelative
    ApprovedAmount        *float64
    ApprovalReason        string
    ApprovedAt            *string
    ApprovedBy            string
    HFCStatus             string
    HFCScore              int
    HFCRiskLevel          string
}

// WhitelistEntry represents a row from grant_access_whitelist.
type WhitelistEntry struct {
    UserID        int64
    IsSelected    bool
    SelectionNote string
    SelectedBy    string
    SelectedAt    string
}
```

### JSONB Handling in Go with pgx

PostgreSQL JSONB fields require special handling when using `pgx`. The approach: marshal Go types to JSON bytes on write, unmarshal from JSON bytes on read.

```go
// internal/grant/repository.go
package grant

import (
    "context"
    "encoding/json"
    "errors"
    "fmt"

    "github.com/jackc/pgx/v5"
    "github.com/jackc/pgx/v5/pgxpool"
)

var ErrGrantNotFound  = errors.New("grant not found")
var ErrGrantExists    = errors.New("grant already exists")
var ErrNotWhitelisted = errors.New("user is not whitelisted for grant access")

type Repository struct {
    db *pgxpool.Pool
}

func NewRepository(db *pgxpool.Pool) *Repository {
    return &Repository{db: db}
}

// FindByUserID returns the grant for a user, or ErrGrantNotFound.
func (r *Repository) FindByUserID(ctx context.Context, userID int64) (*Grant, error) {
    query := `
        SELECT
            grant_id, user_id, status,
            expression_of_interest, grant_required, application_date,
            working_capital, financed_items, contribution_type,
            financial_amount, financial_amount_words,
            inkind_details, inkind_value, contribution_utilization,
            grant_support_growth, job_creation_details, grant_amount_words,
            other_purpose_text, how_did_you_hear, domicile_district,
            business_type, business_type_other, tax_registration_status,
            ntn_registration_no, tax_filer_status, expected_production_increase,
            employment_grid, declaration_accepted, declaration_name,
            has_srsp_relative, srsp_relatives,
            approved_amount, approval_reason, approved_at, approved_by,
            hfc_status, hfc_score, hfc_risk_level
        FROM grants
        WHERE user_id = $1
    `

    g := &Grant{}
    // Temporary holders for JSONB fields
    var (
        exprJSON       []byte
        financedJSON   []byte
        bizTypeJSON    []byte
        taxStatusJSON  []byte
        empGridJSON    []byte
        relativesJSON  []byte
    )

    err := r.db.QueryRow(ctx, query, userID).Scan(
        &g.GrantID, &g.UserID, &g.Status,
        &exprJSON, &g.GrantRequired, &g.ApplicationDate,
        &g.WorkingCapital, &financedJSON, &g.ContributionType,
        &g.FinancialAmount, &g.FinancialAmountWords,
        &g.InkindDetails, &g.InkindValue, &g.ContributionUtil,
        &g.GrantSupportGrowth, &g.JobCreationDetails, &g.GrantAmountWords,
        &g.OtherPurposeText, &g.HowDidYouHear, &g.DomicileDistrict,
        &bizTypeJSON, &g.BusinessTypeOther, &taxStatusJSON,
        &g.NTNRegistrationNo, &g.TaxFilerStatus, &g.ExpectedProdIncrease,
        &empGridJSON, &g.DeclarationAccepted, &g.DeclarationName,
        &g.HasSRSPRelative, &relativesJSON,
        &g.ApprovedAmount, &g.ApprovalReason, &g.ApprovedAt, &g.ApprovedBy,
        &g.HFCStatus, &g.HFCScore, &g.HFCRiskLevel,
    )
    if err != nil {
        if errors.Is(err, pgx.ErrNoRows) {
            return nil, ErrGrantNotFound
        }
        return nil, fmt.Errorf("grant FindByUserID: %w", err)
    }

    // Unmarshal JSONB fields from bytes into Go types
    if len(exprJSON) > 0 {
        _ = json.Unmarshal(exprJSON, &g.ExpressionOfInterest)
    }
    if len(financedJSON) > 0 {
        _ = json.Unmarshal(financedJSON, &g.FinancedItems)
    }
    if len(bizTypeJSON) > 0 {
        _ = json.Unmarshal(bizTypeJSON, &g.BusinessType)
    }
    if len(taxStatusJSON) > 0 {
        _ = json.Unmarshal(taxStatusJSON, &g.TaxRegistrationStatus)
    }
    if len(empGridJSON) > 0 {
        _ = json.Unmarshal(empGridJSON, &g.EmploymentGrid)
    }
    if len(relativesJSON) > 0 {
        _ = json.Unmarshal(relativesJSON, &g.SRSPRelatives)
    }

    return g, nil
}

// Create inserts a new grant row.
func (r *Repository) Create(ctx context.Context, g *Grant) (int64, error) {
    // Marshal JSONB fields to bytes
    exprJSON, _      := json.Marshal(g.ExpressionOfInterest)
    financedJSON, _  := json.Marshal(g.FinancedItems)
    bizTypeJSON, _   := json.Marshal(g.BusinessType)
    taxStatusJSON, _ := json.Marshal(g.TaxRegistrationStatus)
    empGridJSON, _   := json.Marshal(g.EmploymentGrid)
    relativesJSON, _ := json.Marshal(g.SRSPRelatives)

    query := `
        INSERT INTO grants (
            user_id, status,
            expression_of_interest, grant_required, application_date,
            working_capital, financed_items, contribution_type,
            financial_amount, financial_amount_words,
            inkind_details, inkind_value, contribution_utilization,
            grant_support_growth, job_creation_details, grant_amount_words,
            other_purpose_text, how_did_you_hear, domicile_district,
            business_type, business_type_other, tax_registration_status,
            ntn_registration_no, tax_filer_status, expected_production_increase,
            employment_grid, declaration_accepted, declaration_name,
            has_srsp_relative, srsp_relatives
        ) VALUES (
            $1, 'Pending',
            $2, $3, $4,
            $5, $6, $7,
            $8, $9,
            $10, $11, $12,
            $13, $14, $15,
            $16, $17, $18,
            $19, $20, $21,
            $22, $23, $24,
            $25, $26, $27,
            $28, $29
        )
        RETURNING grant_id
    `

    var grantID int64
    err := r.db.QueryRow(ctx, query,
        g.UserID,
        exprJSON, g.GrantRequired, g.ApplicationDate,
        g.WorkingCapital, financedJSON, g.ContributionType,
        g.FinancialAmount, g.FinancialAmountWords,
        g.InkindDetails, g.InkindValue, g.ContributionUtil,
        g.GrantSupportGrowth, g.JobCreationDetails, g.GrantAmountWords,
        g.OtherPurposeText, g.HowDidYouHear, g.DomicileDistrict,
        bizTypeJSON, g.BusinessTypeOther, taxStatusJSON,
        g.NTNRegistrationNo, g.TaxFilerStatus, g.ExpectedProdIncrease,
        empGridJSON, g.DeclarationAccepted, g.DeclarationName,
        g.HasSRSPRelative, relativesJSON,
    ).Scan(&grantID)
    if err != nil {
        return 0, fmt.Errorf("grant Create: %w", err)
    }
    return grantID, nil
}

// GetWhitelistEntry returns the whitelist row for a user.
func (r *Repository) GetWhitelistEntry(ctx context.Context, userID int64) (*WhitelistEntry, error) {
    query := `
        SELECT user_id, is_selected, selection_note, selected_by, selected_at
        FROM grant_access_whitelist
        WHERE user_id = $1
    `
    e := &WhitelistEntry{}
    err := r.db.QueryRow(ctx, query, userID).Scan(
        &e.UserID, &e.IsSelected, &e.SelectionNote, &e.SelectedBy, &e.SelectedAt,
    )
    if err != nil {
        if errors.Is(err, pgx.ErrNoRows) {
            return &WhitelistEntry{IsSelected: false}, nil
        }
        return nil, fmt.Errorf("GetWhitelistEntry: %w", err)
    }
    return e, nil
}

// UpsertWhitelist inserts or updates a whitelist entry.
func (r *Repository) UpsertWhitelist(ctx context.Context, userID int64, isSelected bool, note, selectedBy string) error {
    query := `
        INSERT INTO grant_access_whitelist (user_id, is_selected, selection_note, selected_by)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id)
        DO UPDATE SET
            is_selected = EXCLUDED.is_selected,
            selection_note = EXCLUDED.selection_note,
            selected_by = EXCLUDED.selected_by,
            updated_at = NOW()
    `
    _, err := r.db.Exec(ctx, query, userID, isSelected, note, selectedBy)
    if err != nil {
        return fmt.Errorf("UpsertWhitelist: %w", err)
    }
    return nil
}
```

---

## Validation: The 9-Section Grant Form

The grant form has 9 sections. Validate them all before inserting:

```go
// internal/grant/validation.go
package grant

import (
    "fmt"
    "strings"
)

// AllowedDistricts matches the Flask implementation.
var AllowedDistricts = map[string]bool{
    "Swat":           true,
    "Shangla":        true,
    "Upper Dir":      true,
    "Upper Chitral":  true,
    "Lower Chitral":  true,
}

// ValidContributionTypes matches the dropdown values in SmeGrantApplication.vue.
var ValidContributionTypes = map[string]bool{
    "Cash/Financial":                        true,
    "In-kind (materials, equipment, services)": true,
    "Both":                                  true,
}

// ValidTaxFilerStatus matches the radio values.
var ValidTaxFilerStatus = map[string]bool{
    "Active":   true,
    "Inactive": true,
    "N/A":      true,
}

// Validate checks all required fields and business rules for a grant application.
// Returns a slice of validation errors (one per failed field).
func Validate(req ApplyRequest) []ValidationError {
    var errs []ValidationError

    // Section 1: Applicant Identification
    if req.DomicileDistrict == "" {
        errs = append(errs, ValidationError{Field: "domicile_district", Message: "Domicile district is required"})
    } else if !AllowedDistricts[req.DomicileDistrict] {
        errs = append(errs, ValidationError{
            Field:   "domicile_district",
            Message: fmt.Sprintf("District %q is not in the allowed list", req.DomicileDistrict),
        })
    }

    // Section 2: Business Details
    if len(req.BusinessType) == 0 {
        errs = append(errs, ValidationError{Field: "business_type", Message: "At least one business type must be selected"})
    }
    // If "Other" is selected, the free-text field is required
    for _, bt := range req.BusinessType {
        if strings.ToLower(bt) == "other" && strings.TrimSpace(req.BusinessTypeOther) == "" {
            errs = append(errs, ValidationError{Field: "business_type_other", Message: "Please describe the other business type"})
            break
        }
    }
    if req.TaxFilerStatus != "" && !ValidTaxFilerStatus[req.TaxFilerStatus] {
        errs = append(errs, ValidationError{Field: "tax_filer_status", Message: "Invalid tax filer status"})
    }

    // Section 3: Purpose of Grant
    if len(req.ExpressionOfInterest) == 0 {
        errs = append(errs, ValidationError{Field: "expression_of_interest", Message: "At least one purpose must be selected"})
    }

    // Section 4: Items to be Financed
    if len(req.FinancedItems) == 0 {
        errs = append(errs, ValidationError{Field: "financed_items", Message: "At least one financed item is required"})
    }
    for i, item := range req.FinancedItems {
        if strings.TrimSpace(item.Item) == "" {
            errs = append(errs, ValidationError{
                Field:   fmt.Sprintf("financed_items[%d].item", i),
                Message: "Item name is required",
            })
        }
        if item.Quantity <= 0 {
            errs = append(errs, ValidationError{
                Field:   fmt.Sprintf("financed_items[%d].quantity", i),
                Message: "Quantity must be greater than zero",
            })
        }
        if item.EstimatedCost <= 0 {
            errs = append(errs, ValidationError{
                Field:   fmt.Sprintf("financed_items[%d].estimated_cost", i),
                Message: "Estimated cost must be greater than zero",
            })
        }
    }

    // Section 5: Grant Amount
    if req.GrantRequired <= 0 {
        errs = append(errs, ValidationError{Field: "grant_required", Message: "Grant amount must be greater than zero"})
    }
    if strings.TrimSpace(req.GrantAmountWords) == "" {
        errs = append(errs, ValidationError{Field: "grant_amount_words", Message: "Grant amount in words is required"})
    }

    // Section 5: Contribution
    if !ValidContributionTypes[req.ContributionType] {
        errs = append(errs, ValidationError{Field: "contribution_type", Message: "Invalid contribution type"})
    }
    if (req.ContributionType == "Cash/Financial" || req.ContributionType == "Both") {
        if req.FinancialAmount == nil || *req.FinancialAmount <= 0 {
            errs = append(errs, ValidationError{Field: "financial_amount", Message: "Financial contribution amount is required"})
        }
        if strings.TrimSpace(req.FinancialAmountWords) == "" {
            errs = append(errs, ValidationError{Field: "financial_amount_words", Message: "Financial amount in words is required"})
        }
    }

    // Section 8: Declaration
    if !req.DeclarationAccepted {
        errs = append(errs, ValidationError{Field: "declaration_accepted", Message: "Declaration must be accepted"})
    }
    if strings.TrimSpace(req.DeclarationName) == "" {
        errs = append(errs, ValidationError{Field: "declaration_name", Message: "Declarant name is required"})
    }

    // Section 7: Disclaimer — relatives table validation
    if req.HasSRSPRelative && len(req.SRSPRelatives) == 0 {
        errs = append(errs, ValidationError{Field: "srsp_relatives", Message: "If you have an SRSP relative, please add their details"})
    }
    for i, rel := range req.SRSPRelatives {
        if strings.TrimSpace(rel.Name) == "" {
            errs = append(errs, ValidationError{
                Field:   fmt.Sprintf("srsp_relatives[%d].name", i),
                Message: "Relative name is required",
            })
        }
    }

    return errs
}

// ValidationError represents a single field validation failure.
type ValidationError struct {
    Field   string `json:"field"`
    Message string `json:"message"`
}
```

---

## The Grant Service

The service coordinates the business logic — validation, whitelist gate, DB write, and HFC enqueue:

```go
// internal/grant/service.go
package grant

import (
    "context"
    "fmt"
    "peace-sme-go/internal/config"
)

// HFCEnqueuer is the interface for enqueueing HFC scoring jobs.
type HFCEnqueuer interface {
    EnqueueRecalculate(ctx context.Context, userID int64) error
}

// GrantRepository is the interface for grant data access.
type GrantRepository interface {
    FindByUserID(ctx context.Context, userID int64) (*Grant, error)
    Create(ctx context.Context, g *Grant) (int64, error)
    Update(ctx context.Context, g *Grant) error
    UpdateStatus(ctx context.Context, userID int64, status string) error
    GetWhitelistEntry(ctx context.Context, userID int64) (*WhitelistEntry, error)
    UpsertWhitelist(ctx context.Context, userID int64, isSelected bool, note, selectedBy string) error
}

type Service struct {
    cfg  *config.Config
    repo GrantRepository
    hfc  HFCEnqueuer
}

func NewService(cfg *config.Config, repo GrantRepository, hfc HFCEnqueuer) *Service {
    return &Service{cfg: cfg, repo: repo, hfc: hfc}
}

// GetGrantForUser returns the grant for a user, with access state for the whitelist.
func (s *Service) GetGrantForUser(ctx context.Context, userID int64) (*Grant, string, error) {
    var accessState string

    if s.cfg.GrantRequireSelection {
        entry, err := s.repo.GetWhitelistEntry(ctx, userID)
        if err != nil {
            return nil, "", fmt.Errorf("GetGrantForUser whitelist check: %w", err)
        }
        if entry.IsSelected {
            accessState = "selected"
        } else {
            accessState = "not_selected"
        }
    } else {
        accessState = "open"
    }

    grant, err := s.repo.FindByUserID(ctx, userID)
    if err != nil {
        if err == ErrGrantNotFound {
            return nil, accessState, ErrGrantNotFound
        }
        return nil, "", err
    }

    return grant, accessState, nil
}

// Apply creates a new grant application.
func (s *Service) Apply(ctx context.Context, userID int64, req ApplyRequest) (int64, error) {
    // 1. Whitelist gate
    if s.cfg.GrantRequireSelection {
        entry, err := s.repo.GetWhitelistEntry(ctx, userID)
        if err != nil {
            return 0, fmt.Errorf("whitelist check failed: %w", err)
        }
        if !entry.IsSelected {
            return 0, ErrNotWhitelisted
        }
    }

    // 2. Validate all form sections
    if errs := Validate(req); len(errs) > 0 {
        return 0, &FormValidationError{Errors: errs}
    }

    // 3. Check if grant already exists (one per user)
    _, err := s.repo.FindByUserID(ctx, userID)
    if err == nil {
        return 0, ErrGrantExists
    }
    if err != ErrGrantNotFound {
        return 0, fmt.Errorf("apply: unexpected error checking existing grant: %w", err)
    }

    // 4. Build the Grant model from the request
    g := buildGrantFromRequest(userID, req)

    // 5. Insert into database
    grantID, err := s.repo.Create(ctx, g)
    if err != nil {
        return 0, fmt.Errorf("apply: create grant: %w", err)
    }

    // 6. Enqueue HFC scoring (non-blocking — log warning if fails)
    if err := s.hfc.EnqueueRecalculate(ctx, userID); err != nil {
        // Log but don't fail the user's request
        fmt.Printf("WARNING: failed to enqueue HFC for user %d: %v\n", userID, err)
    }

    return grantID, nil
}

// Update modifies an existing grant application.
func (s *Service) Update(ctx context.Context, userID int64, req ApplyRequest) error {
    // 1. Validate
    if errs := Validate(req); len(errs) > 0 {
        return &FormValidationError{Errors: errs}
    }

    // 2. Ensure grant exists
    existing, err := s.repo.FindByUserID(ctx, userID)
    if err != nil {
        return fmt.Errorf("update: grant not found for user %d: %w", userID, err)
    }

    // 3. Build updated model
    g := buildGrantFromRequest(userID, req)
    g.GrantID = existing.GrantID

    // 4. Update in database
    if err := s.repo.Update(ctx, g); err != nil {
        return fmt.Errorf("update: %w", err)
    }

    // 5. Re-enqueue HFC (debounced in the HFC layer)
    if err := s.hfc.EnqueueRecalculate(ctx, userID); err != nil {
        fmt.Printf("WARNING: failed to re-enqueue HFC for user %d: %v\n", userID, err)
    }

    return nil
}

// SetWhitelistEntry updates the whitelist for an admin action.
func (s *Service) SetWhitelistEntry(ctx context.Context, userID int64, isSelected bool, note, adminUsername string) error {
    return s.repo.UpsertWhitelist(ctx, userID, isSelected, note, adminUsername)
}

// buildGrantFromRequest maps an ApplyRequest into a Grant model.
func buildGrantFromRequest(userID int64, req ApplyRequest) *Grant {
    return &Grant{
        UserID:                userID,
        ExpressionOfInterest:  req.ExpressionOfInterest,
        OtherPurposeText:      req.OtherPurposeText,
        GrantRequired:         &req.GrantRequired,
        GrantAmountWords:      req.GrantAmountWords,
        ApplicationDate:       req.ApplicationDate,
        WorkingCapital:        req.WorkingCapital,
        FinancedItems:         req.FinancedItems,
        ContributionType:      req.ContributionType,
        FinancialAmount:       req.FinancialAmount,
        FinancialAmountWords:  req.FinancialAmountWords,
        InkindDetails:         req.InkindDetails,
        InkindValue:           req.InkindValue,
        ContributionUtil:      req.ContributionUtil,
        GrantSupportGrowth:    req.GrantSupportGrowth,
        JobCreationDetails:    req.JobCreationDetails,
        HowDidYouHear:         req.HowDidYouHear,
        DomicileDistrict:      req.DomicileDistrict,
        BusinessType:          req.BusinessType,
        BusinessTypeOther:     req.BusinessTypeOther,
        TaxRegistrationStatus: req.TaxRegistrationStatus,
        NTNRegistrationNo:     req.NTNRegistrationNo,
        TaxFilerStatus:        req.TaxFilerStatus,
        ExpectedProdIncrease:  req.ExpectedProdIncrease,
        EmploymentGrid:        req.EmploymentGrid,
        DeclarationAccepted:   req.DeclarationAccepted,
        DeclarationName:       req.DeclarationName,
        HasSRSPRelative:       req.HasSRSPRelative,
        SRSPRelatives:         req.SRSPRelatives,
    }
}

// FormValidationError wraps multiple field-level validation errors.
type FormValidationError struct {
    Errors []ValidationError
}

func (e *FormValidationError) Error() string {
    return fmt.Sprintf("form validation failed: %d error(s)", len(e.Errors))
}
```

---

## The Grant Handler

The handler translates between HTTP and the service layer:

```go
// internal/grant/handler.go
package grant

import (
    "encoding/json"
    "errors"
    "net/http"

    "peace-sme-go/internal/middleware"
)

type Handler struct {
    svc *Service
}

func NewHandler(svc *Service) *Handler {
    return &Handler{svc: svc}
}

// Get handles GET /api/grant
func (h *Handler) Get(w http.ResponseWriter, r *http.Request) {
    userID := middleware.MustUserID(r.Context())

    grant, accessState, err := h.svc.GetGrantForUser(r.Context(), userID)
    if err != nil && err != ErrGrantNotFound {
        http.Error(w, `{"error":"internal server error"}`, http.StatusInternalServerError)
        return
    }

    // Build response — include access_state field the Vue frontend reads
    resp := map[string]interface{}{
        "access_state": accessState,
    }
    if grant != nil {
        resp["grant"] = grant
    }

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(resp)
}

// Apply handles POST /api/grant
func (h *Handler) Apply(w http.ResponseWriter, r *http.Request) {
    userID := middleware.MustUserID(r.Context())

    var req ApplyRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        w.Header().Set("Content-Type", "application/json")
        w.WriteHeader(http.StatusBadRequest)
        json.NewEncoder(w).Encode(map[string]string{"error": "invalid request body"})
        return
    }

    grantID, err := h.svc.Apply(r.Context(), userID, req)
    if err != nil {
        h.handleError(w, err)
        return
    }

    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusCreated)
    json.NewEncoder(w).Encode(map[string]interface{}{
        "message":  "Grant application submitted successfully",
        "grant_id": grantID,
    })
}

// Update handles PUT /api/grant
func (h *Handler) Update(w http.ResponseWriter, r *http.Request) {
    userID := middleware.MustUserID(r.Context())

    var req ApplyRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        w.Header().Set("Content-Type", "application/json")
        w.WriteHeader(http.StatusBadRequest)
        json.NewEncoder(w).Encode(map[string]string{"error": "invalid request body"})
        return
    }

    if err := h.svc.Update(r.Context(), userID, req); err != nil {
        h.handleError(w, err)
        return
    }

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(map[string]string{"message": "Grant application updated successfully"})
}

// handleError maps service errors to HTTP responses.
func (h *Handler) handleError(w http.ResponseWriter, err error) {
    w.Header().Set("Content-Type", "application/json")

    switch {
    case errors.Is(err, ErrNotWhitelisted):
        w.WriteHeader(http.StatusForbidden)
        json.NewEncoder(w).Encode(map[string]string{
            "error":        "You have not been selected to apply for a grant.",
            "access_state": "not_selected",
        })

    case errors.Is(err, ErrGrantExists):
        w.WriteHeader(http.StatusConflict)
        json.NewEncoder(w).Encode(map[string]string{
            "error": "A grant application already exists for this user.",
        })

    case errors.Is(err, ErrGrantNotFound):
        w.WriteHeader(http.StatusNotFound)
        json.NewEncoder(w).Encode(map[string]string{
            "error": "No grant application found.",
        })

    default:
        var ve *FormValidationError
        if errors.As(err, &ve) {
            w.WriteHeader(http.StatusUnprocessableEntity)
            json.NewEncoder(w).Encode(map[string]interface{}{
                "error":  "Validation failed",
                "errors": ve.Errors,
            })
            return
        }
        w.WriteHeader(http.StatusInternalServerError)
        json.NewEncoder(w).Encode(map[string]string{"error": "internal server error"})
    }
}
```

---

## Grant Status Transitions

```go
// internal/grant/status.go
package grant

import "fmt"

// GrantStatus represents a valid grant workflow state.
type GrantStatus string

const (
    StatusPending     GrantStatus = "Pending"
    StatusApproved    GrantStatus = "Approved"
    StatusRejected    GrantStatus = "Rejected"
    StatusUnderReview GrantStatus = "Under Review"
)

// CanTransitionTo checks if a transition from the current status is valid.
func (current GrantStatus) CanTransitionTo(next GrantStatus) error {
    validTransitions := map[GrantStatus][]GrantStatus{
        StatusPending:     {StatusApproved, StatusRejected, StatusUnderReview},
        StatusUnderReview: {StatusApproved, StatusRejected},
        StatusApproved:    {},  // terminal state
        StatusRejected:    {},  // terminal state
    }

    allowed := validTransitions[current]
    for _, s := range allowed {
        if s == next {
            return nil
        }
    }
    return fmt.Errorf("invalid transition from %q to %q", current, next)
}
```

---

## Grant Approval (Admin)

```go
// internal/grant/approval.go
package grant

import (
    "context"
    "fmt"
    "time"

    "peace-sme-go/internal/config"
)

type ApproveRequest struct {
    ApprovedAmount   float64  `json:"approved_amount"`
    ApprovalReason   string   `json:"approval_reason"`
    MissingFields    []string `json:"missing_fields"`
    ConfirmationText string   `json:"confirmation_text"`
}

// ApprovalRepository handles approval-related DB operations.
type ApprovalRepository interface {
    FindByUserID(ctx context.Context, userID int64) (*Grant, error)
    SetApproved(ctx context.Context, userID int64, approvedBy string, amount float64, reason string, at time.Time) error
    InsertApprovalLog(ctx context.Context, log ApprovalLog) error
}

// MailEnqueuer enqueues approval notification emails.
type MailEnqueuer interface {
    EnqueueApprovalEmail(ctx context.Context, userID int64, approvedAmount float64) error
    EnqueueNotificationEmail(ctx context.Context, approvedAmount float64) error
}

type ApprovalService struct {
    cfg  *config.Config
    repo ApprovalRepository
    mail MailEnqueuer
}

func NewApprovalService(cfg *config.Config, repo ApprovalRepository, mail MailEnqueuer) *ApprovalService {
    return &ApprovalService{cfg: cfg, repo: repo, mail: mail}
}

// ApproveGrant performs the approval workflow.
func (s *ApprovalService) ApproveGrant(ctx context.Context, adminUsername string, userID int64, req ApproveRequest) error {
    grant, err := s.repo.FindByUserID(ctx, userID)
    if err != nil {
        return fmt.Errorf("approve: %w", err)
    }

    // Validate state transition
    if err := GrantStatus(grant.Status).CanTransitionTo(StatusApproved); err != nil {
        return fmt.Errorf("approve: %w", err)
    }

    // HFC shadow mode check
    if !s.cfg.HFCShadowMode {
        if grant.HFCRiskLevel == "HIGH" || grant.HFCRiskLevel == "CRITICAL" {
            return fmt.Errorf("cannot approve: HFC risk level is %s and shadow mode is OFF", grant.HFCRiskLevel)
        }
    }

    now := time.Now().UTC()

    // Update grant status
    if err := s.repo.SetApproved(ctx, userID, adminUsername, req.ApprovedAmount, req.ApprovalReason, now); err != nil {
        return fmt.Errorf("approve: set approved: %w", err)
    }

    // Insert approval log
    log := ApprovalLog{
        GrantID:             grant.GrantID,
        UserID:              userID,
        ApprovingAuthority:  adminUsername,
        Action:              "approve",
        ApprovedAmount:      req.ApprovedAmount,
        ApprovalReason:      req.ApprovalReason,
        MissingFields:       req.MissingFields,
        ConfirmationText:    req.ConfirmationText,
    }
    if err := s.repo.InsertApprovalLog(ctx, log); err != nil {
        // Log but don't fail — approval already recorded
        fmt.Printf("WARNING: failed to insert approval log for user %d: %v\n", userID, err)
    }

    // Enqueue notification emails
    _ = s.mail.EnqueueApprovalEmail(ctx, userID, req.ApprovedAmount)
    _ = s.mail.EnqueueNotificationEmail(ctx, req.ApprovedAmount)

    return nil
}

// ApprovalLog represents a row in grant_approval_logs.
type ApprovalLog struct {
    GrantID            int64
    UserID             int64
    ApprovingAuthority string
    Action             string
    ApprovedAmount     float64
    ApprovalReason     string
    MissingFields      []string
    ConfirmationText   string
}
```

---

## Registering Grant Routes

```go
// In your router setup (e.g., internal/app/app.go)
func (a *App) registerGrantRoutes(r chi.Router) {
    grantRepo := grant.NewRepository(a.db)
    grantSvc  := grant.NewService(a.cfg, grantRepo, a.hfcEnqueuer)
    grantH    := grant.NewHandler(grantSvc)

    approvalSvc := grant.NewApprovalService(a.cfg, grantRepo, a.mailEnqueuer)
    approvalH   := grant.NewApprovalHandler(approvalSvc)

    // Applicant routes (user JWT required)
    r.With(middleware.AuthRequired(a.cfg)).Route("/api", func(r chi.Router) {
        r.Get("/grant", grantH.Get)
        r.Post("/grant", grantH.Apply)
        r.Put("/grant", grantH.Update)
        r.Get("/grant-status", grantH.GetStatus)
    })

    // Admin routes (admin JWT required)
    r.With(middleware.AdminRequired(a.cfg)).Route("/api/admin", func(r chi.Router) {
        r.Post("/grants/access", approvalH.SetWhitelist)
        r.Get("/grants/access/{user_id}", approvalH.GetWhitelist)
        r.Get("/grants/{user_id}/approval-check", approvalH.ApprovalCheck)
        // Approver-only routes
        r.With(middleware.ApproverRequired(a.cfg)).Post("/grants/{user_id}/approve", approvalH.Approve)
    })
}
```

---

## Testing the Grant Service

```go
// internal/grant/service_test.go
package grant_test

import (
    "context"
    "testing"

    "peace-sme-go/internal/config"
    "peace-sme-go/internal/grant"
)

// MockRepository implements GrantRepository in memory.
type MockRepository struct {
    grants     map[int64]*grant.Grant
    whitelist  map[int64]*grant.WhitelistEntry
    nextID     int64
}

func NewMockRepository() *MockRepository {
    return &MockRepository{
        grants:    make(map[int64]*grant.Grant),
        whitelist: make(map[int64]*grant.WhitelistEntry),
        nextID:    1,
    }
}

func (m *MockRepository) FindByUserID(ctx context.Context, userID int64) (*grant.Grant, error) {
    g, ok := m.grants[userID]
    if !ok {
        return nil, grant.ErrGrantNotFound
    }
    return g, nil
}

func (m *MockRepository) Create(ctx context.Context, g *grant.Grant) (int64, error) {
    id := m.nextID
    m.nextID++
    g.GrantID = id
    m.grants[g.UserID] = g
    return id, nil
}

func (m *MockRepository) Update(ctx context.Context, g *grant.Grant) error {
    m.grants[g.UserID] = g
    return nil
}

func (m *MockRepository) UpdateStatus(ctx context.Context, userID int64, status string) error {
    if g, ok := m.grants[userID]; ok {
        g.Status = status
    }
    return nil
}

func (m *MockRepository) GetWhitelistEntry(ctx context.Context, userID int64) (*grant.WhitelistEntry, error) {
    e, ok := m.whitelist[userID]
    if !ok {
        return &grant.WhitelistEntry{IsSelected: false}, nil
    }
    return e, nil
}

func (m *MockRepository) UpsertWhitelist(ctx context.Context, userID int64, isSelected bool, note, selectedBy string) error {
    m.whitelist[userID] = &grant.WhitelistEntry{
        UserID:     userID,
        IsSelected: isSelected,
        SelectionNote: note,
        SelectedBy: selectedBy,
    }
    return nil
}

// MockHFC implements HFCEnqueuer.
type MockHFC struct {
    enqueuedUsers []int64
}

func (m *MockHFC) EnqueueRecalculate(ctx context.Context, userID int64) error {
    m.enqueuedUsers = append(m.enqueuedUsers, userID)
    return nil
}

func validApplyRequest() grant.ApplyRequest {
    cost := 150000.0
    return grant.ApplyRequest{
        DomicileDistrict:    "Swat",
        BusinessType:        []string{"Manufacturing"},
        ExpressionOfInterest: []string{"Purchase equipment"},
        FinancedItems: []grant.FinancedItem{
            {Item: "Loom", Quantity: 1, EstimatedCost: cost},
        },
        GrantRequired:      500000,
        GrantAmountWords:   "Five Hundred Thousand",
        ContributionType:   "Cash/Financial",
        FinancialAmount:    &cost,
        FinancialAmountWords: "One Hundred Fifty Thousand",
        DeclarationAccepted: true,
        DeclarationName:    "Muhammad Ali",
    }
}

func TestApply_WhitelistGate(t *testing.T) {
    repo := NewMockRepository()
    hfc  := &MockHFC{}
    cfg  := &config.Config{GrantRequireSelection: true}
    svc  := grant.NewService(cfg, repo, hfc)

    // Not whitelisted
    _, err := svc.Apply(context.Background(), 42, validApplyRequest())
    if err != grant.ErrNotWhitelisted {
        t.Errorf("expected ErrNotWhitelisted, got %v", err)
    }

    // Whitelist the user
    repo.whitelist[42] = &grant.WhitelistEntry{UserID: 42, IsSelected: true}

    grantID, err := svc.Apply(context.Background(), 42, validApplyRequest())
    if err != nil {
        t.Errorf("expected success after whitelist, got %v", err)
    }
    if grantID == 0 {
        t.Error("expected non-zero grant ID")
    }
    if len(hfc.enqueuedUsers) != 1 || hfc.enqueuedUsers[0] != 42 {
        t.Error("expected HFC to be enqueued for user 42")
    }
}

func TestApply_DuplicateGrant(t *testing.T) {
    repo := NewMockRepository()
    hfc  := &MockHFC{}
    cfg  := &config.Config{GrantRequireSelection: false}
    svc  := grant.NewService(cfg, repo, hfc)

    req := validApplyRequest()
    _, err := svc.Apply(context.Background(), 42, req)
    if err != nil {
        t.Fatalf("first apply failed: %v", err)
    }

    _, err = svc.Apply(context.Background(), 42, req)
    if err != grant.ErrGrantExists {
        t.Errorf("expected ErrGrantExists on second apply, got %v", err)
    }
}

func TestApply_ValidationFailure(t *testing.T) {
    repo := NewMockRepository()
    hfc  := &MockHFC{}
    cfg  := &config.Config{GrantRequireSelection: false}
    svc  := grant.NewService(cfg, repo, hfc)

    // Empty request should fail validation
    _, err := svc.Apply(context.Background(), 42, grant.ApplyRequest{})
    if err == nil {
        t.Fatal("expected validation error, got nil")
    }

    var ve *grant.FormValidationError
    if !errors.As(err, &ve) {
        t.Errorf("expected FormValidationError, got %T: %v", err, err)
    }
    if len(ve.Errors) == 0 {
        t.Error("expected at least one validation error")
    }
}
```

Run the tests:

```bash
go test ./internal/grant/... -v

# Expected:
# --- PASS: TestApply_WhitelistGate (0.00s)
# --- PASS: TestApply_DuplicateGrant (0.00s)
# --- PASS: TestApply_ValidationFailure (0.00s)
```

---

## Mastery Check

You understand this chapter when you can:

1. Describe the full grant lifecycle from whitelist entry to approval, including which database tables are touched at each step and what side effects (Redis, email) occur.
2. Explain why `user_id` is `UNIQUE` on the `grants` table, what that means for POST vs PUT behavior, and how to handle the `ErrGrantExists` error in the handler.
3. Write a `Repository.Create()` method that marshals Go slice/struct fields to JSON bytes before passing them as `$N` parameters to a pgx `INSERT` query, and a `Repository.FindByUserID()` that scans and unmarshals them back.
4. Implement the whitelist gate in the service layer using the `GrantRequireSelection` config flag, returning `ErrNotWhitelisted` (which maps to 403 + `access_state:"not_selected"` in the handler).
5. Write a table-driven test that uses a mock repository and mock HFC enqueuer to verify the whitelist gate, duplicate grant, and validation failure scenarios — without touching a real database or Redis.
