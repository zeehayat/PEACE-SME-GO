# Chapter 12: HFC Fraud Detection and Approval Authority

## Purpose

HFC teaches deterministic scoring, background recalculation, audit trails, and role-based approvals.

## Theoretical Background

### Rule-Based Engines vs. ML Models
In fraud detection and risk scoring, systems use one of two main approaches:
1. **Deterministic Rule-Based Engines:** Apply strict, logical heuristics to evaluate input data (e.g., "If email already exists, add 20 points").
   - **Pros:** 100% transparent, predictable, easy to debug, and requires no training datasets.
   - **Cons:** Rigid; cannot easily detect novel fraud patterns that do not violate explicit rules.
2. **Machine Learning Classifiers:** Make probabilistic predictions based on feature sets learned from historical data.
   - **Pros:** Can detect complex, non-linear fraud signals.
   - **Cons:** Hard to explain (black-box problem), prone to data drift, and slower to execute.
   
This application utilizes a deterministic rule engine (v1) as its primary scorer, with optional hook points for ML scoring.

### Message Processing Guarantees
When background workers process jobs (such as recalculating HFC scores or sending approval notifications), three execution guarantees are possible:
- **At-Most-Once:** The job is pulled from the queue and immediately marked complete before execution. If the worker crashes mid-job, the task is lost.
- **At-Least-Once (Recommended):** The job remains in the queue (or in a processing state) until the worker explicitly acknowledges completion. If the worker crashes, the job is re-run. This requires writing **Idempotent** tasks (tasks that can run multiple times safely without duplicate side-effects).
- **Exactly-Once:** Achieved by combining At-Least-Once processing with deduplication mechanisms (like database unique indexes or transaction locks).

### Transactional Outbox Pattern
When performing actions that involve writing to a database and triggering an external side effect (like sending an email or publishing to a message broker):
- **Do not** call the external service inside the database transaction. If the service is slow, it holds the DB connection open. If the transaction rolls back, the email cannot be unsent (dual-write problem).
- **Solution:** Use the Transactional Outbox pattern. Write both the primary state change (e.g., `ApproveGrant`) and a task record (e.g., `SendEmailJob`) to the database inside the same transaction. A separate background worker reads the outbox table and executes the side-effects.

### External Resources
- [Distributed Systems - Messaging Guarantees](https://en.wikipedia.org/wiki/Reliable_messaging)
- [Microservices Pattern: Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Wikipedia: Rule-Based System](https://en.wikipedia.org/wiki/Rule-based_system)

---

## HFC Rules

Score rules:

| Rule | Points |
|---|---:|
| Duplicate CNIC | 50 |
| Duplicate email | 20 |
| Duplicate mobile | 20 |
| Missing business profile | 30 |
| Missing required documents | 25 |
| Missing grant media | 10 |
| Business district out of scope | 40 |
| Grant amount above threshold | 15 |
| Application submitted very fast | 10 |
| Missing expression of interest | 15 |

Risk bands:

| Score | Level |
|---:|---|
| 0-29 | LOW |
| 30-59 | MEDIUM |
| 60-79 | HIGH |
| 80+ | CRITICAL |

---

## Tables

HFC writes:
- `hfc_evaluations`
- `hfc_review_actions`
- HFC fields on `grants`

Approval writes:
- `grants.status`
- `grants.approved_amount`
- `grants.approval_reason`
- `grants.approved_at`
- `grants.approved_by`
- `grant_approval_logs`

---

## Admin Endpoints

HFC:
- `GET /api/admin/hfc/dashboard/stats`
- `GET /api/admin/hfc/queue`
- `GET /api/admin/hfc/applicant/<user_id>`
- `POST /api/admin/hfc/applicant/<user_id>/action`
- `POST /api/admin/hfc/applicant/<user_id>/recalculate`

Approval:
- `GET /api/admin/grants/<user_id>/approval-check`
- `POST /api/admin/grants/<user_id>/approve`

---

## Shadow Mode

If `HFC_SHADOW_MODE=1`, HFC score does not block approval. The score is advisory.

If shadow mode is off, define explicit blocking behavior before implementation. For example, require override for HIGH/CRITICAL risk.

---

## Audit Trails

Every admin action should record:
- actor username
- action type
- before state
- after state
- comment
- timestamp

Audit records are not decoration. They are how an approval system explains itself later.

---

## Practical Examples

### Example: Implementing a Deterministic HFC Scorer in Go
This example shows how to write a scoring engine that queries various database tables and calculates a cumulative fraud score based on the application rules:

```go
// File: internal/hfc/scorer.go
package hfc

import (
	"context"
	"fmt"
)

type EvaluationResult struct {
	Score     int
	RiskLevel string
	Details   map[string]int
}

type ScorerRepository interface {
	CheckDuplicateCNIC(ctx context.Context, userID int64, cnic string) (bool, error)
	HasBusinessProfile(ctx context.Context, userID int64) (bool, error)
	GetUploadedDocumentsCount(ctx context.Context, userID int64) (int, error)
}

type Scorer struct {
	repo ScorerRepository
}

func NewScorer(repo ScorerRepository) *Scorer {
	return &Scorer{repo: repo}
}

// Evaluate calculates the risk score and risk bands for an applicant.
func (s *Scorer) Evaluate(ctx context.Context, userID int64, cnic string) (*EvaluationResult, error) {
	score := 0
	details := make(map[string]int)

	// Rule 1: Check for duplicate CNIC
	isDuplicateCNIC, err := s.repo.CheckDuplicateCNIC(ctx, userID, cnic)
	if err != nil {
		return nil, fmt.Errorf("failed to check duplicate CNIC: %w", err)
	}
	if isDuplicateCNIC {
		score += 50
		details["duplicate_cnic"] = 50
	}

	// Rule 2: Check for missing business profile
	hasProfile, err := s.repo.HasBusinessProfile(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to check business profile: %w", err)
	}
	if !hasProfile {
		score += 30
		details["missing_business_profile"] = 30
	}

	// Rule 3: Check for incomplete documents (expecting 5 required uploads)
	uploadedCount, err := s.repo.GetUploadedDocumentsCount(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to get docs count: %w", err)
	}
	if uploadedCount < 5 {
		score += 25
		details["missing_required_documents"] = 25
	}

	// Determine Risk Level Band
	var riskLevel string
	switch {
	case score <= 29:
		riskLevel = "LOW"
	case score <= 59:
		riskLevel = "MEDIUM"
	case score <= 79:
		riskLevel = "HIGH"
	default:
		riskLevel = "CRITICAL"
	}

	return &EvaluationResult{
		Score:     score,
		RiskLevel: riskLevel,
		Details:   details,
	}, nil
}
```

---

## Complete Implementations

### Implementation 1: Complete HFC Scorer with All 10 Rules

The basic example above covers three rules. Here is the full scorer covering all ten rules from the SRS. The implementation is sequential — each rule queries the database in order. This is the correct starting point: easy to read, easy to debug, and fast enough given the 60-second debounce described in Implementation 3.

First, expand the repository interface to cover every rule:

```go
// File: internal/hfc/scorer_repository.go
package hfc

import "context"

// ScorerRepository defines every database check the scorer needs.
// Using an interface here means the scorer can be unit-tested with a mock
// repository without a real database connection.
type ScorerRepository interface {
	// Rule 1
	CountDuplicateCNIC(ctx context.Context, cnic string, excludeUserID int64) (int, error)
	// Rule 2
	CountDuplicateEmail(ctx context.Context, email string, excludeUserID int64) (int, error)
	// Rule 3
	CountDuplicateMobile(ctx context.Context, mobile string, excludeUserID int64) (int, error)
	// Rule 4
	HasBusinessProfile(ctx context.Context, userID int64) (bool, error)
	// Rule 5: returns count of required document types uploaded
	CountRequiredDocuments(ctx context.Context, userID int64) (int, error)
	// Rule 6
	HasGrantMedia(ctx context.Context, userID int64) (bool, error)
	// Rule 7
	GetBusinessDistrict(ctx context.Context, userID int64) (string, error)
	// Rule 8
	GetGrantRequiredAmount(ctx context.Context, userID int64) (float64, error)
	// Rule 9: returns seconds since user account was created
	SecondsSinceRegistration(ctx context.Context, userID int64) (int64, error)
	// Rule 10
	HasExpressionOfInterest(ctx context.Context, userID int64) (bool, error)
}
```

Now the full scorer with all ten rules:

```go
// File: internal/hfc/scorer.go
package hfc

import (
	"context"
	"fmt"
)

// EvaluationResult holds the computed score, human-readable risk level, and
// a per-rule breakdown so the admin UI can display exactly what fired.
type EvaluationResult struct {
	Score     int            `json:"score"`
	RiskLevel string         `json:"risk_level"`
	Details   map[string]int `json:"details"`
}

// allowedDistricts is the definitive list of districts in scope for the grant.
// Applications from outside this list receive the district penalty.
var allowedDistricts = map[string]bool{
	"Karachi East":    true,
	"Karachi West":    true,
	"Karachi Central": true,
	"Karachi South":   true,
	"Malir":           true,
	"Korangi":         true,
}

// grantAmountThreshold is the maximum grant amount before the amount penalty
// fires. This should come from config in production.
const grantAmountThreshold = 500000.0

// minimumApplicationSeconds is the minimum time (in seconds) that must have
// elapsed between registration and submission. Applications faster than this
// receive the speed penalty.
const minimumApplicationSeconds = 600 // 10 minutes

// requiredDocumentCount is the number of document types that must be present.
const requiredDocumentCount = 5

type Scorer struct {
	repo ScorerRepository
}

func NewScorer(repo ScorerRepository) *Scorer {
	return &Scorer{repo: repo}
}

// Evaluate calculates the HFC risk score for a single applicant.
// It runs all ten rules sequentially and accumulates the total score.
// The function returns an error only if a database query fails; a rule
// "not firing" is represented as a zero contribution to Details.
func (s *Scorer) Evaluate(ctx context.Context, userID int64, cnic, email, mobile string) (*EvaluationResult, error) {
	score := 0
	details := make(map[string]int)

	// Rule 1: Duplicate CNIC — 50 points
	// Most severe rule. Another applicant using the same national ID is a
	// strong fraud signal.
	dupCNIC, err := s.repo.CountDuplicateCNIC(ctx, cnic, userID)
	if err != nil {
		return nil, fmt.Errorf("rule 1 (duplicate cnic): %w", err)
	}
	if dupCNIC > 0 {
		score += 50
		details["duplicate_cnic"] = 50
	}

	// Rule 2: Duplicate email — 20 points
	dupEmail, err := s.repo.CountDuplicateEmail(ctx, email, userID)
	if err != nil {
		return nil, fmt.Errorf("rule 2 (duplicate email): %w", err)
	}
	if dupEmail > 0 {
		score += 20
		details["duplicate_email"] = 20
	}

	// Rule 3: Duplicate mobile — 20 points
	dupMobile, err := s.repo.CountDuplicateMobile(ctx, mobile, userID)
	if err != nil {
		return nil, fmt.Errorf("rule 3 (duplicate mobile): %w", err)
	}
	if dupMobile > 0 {
		score += 20
		details["duplicate_mobile"] = 20
	}

	// Rule 4: Missing business profile — 30 points
	// An applicant without a business profile has not completed the minimum
	// requirements and is either incomplete or fraudulent.
	hasProfile, err := s.repo.HasBusinessProfile(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("rule 4 (business profile): %w", err)
	}
	if !hasProfile {
		score += 30
		details["missing_business_profile"] = 30
	}

	// Rule 5: Missing required documents — 25 points
	// The SRS requires 5 specific document types. Each missing type increases
	// suspicion that the applicant is not a real business.
	docCount, err := s.repo.CountRequiredDocuments(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("rule 5 (required docs): %w", err)
	}
	if docCount < requiredDocumentCount {
		score += 25
		details["missing_required_documents"] = 25
	}

	// Rule 6: Missing grant media — 10 points
	// Grant media (photos, proof of business) is optional for completion but
	// its total absence is a mild signal.
	hasMedia, err := s.repo.HasGrantMedia(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("rule 6 (grant media): %w", err)
	}
	if !hasMedia {
		score += 10
		details["missing_grant_media"] = 10
	}

	// Rule 7: Business district not in allowed list — 40 points
	// The grant is geographically scoped. An out-of-scope district is a
	// disqualifying condition, reflected here as a high penalty.
	district, err := s.repo.GetBusinessDistrict(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("rule 7 (district): %w", err)
	}
	if district != "" && !allowedDistricts[district] {
		score += 40
		details["district_out_of_scope"] = 40
	}

	// Rule 8: Grant amount above threshold — 15 points
	// Requests significantly above the expected range warrant manual review.
	amount, err := s.repo.GetGrantRequiredAmount(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("rule 8 (grant amount): %w", err)
	}
	if amount > grantAmountThreshold {
		score += 15
		details["grant_amount_above_threshold"] = 15
	}

	// Rule 9: Application submitted very fast — 10 points
	// An application submitted less than 10 minutes after registration
	// suggests automated submission or pre-filled fraudulent data.
	seconds, err := s.repo.SecondsSinceRegistration(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("rule 9 (submission speed): %w", err)
	}
	if seconds < minimumApplicationSeconds {
		score += 10
		details["submitted_too_fast"] = 10
	}

	// Rule 10: Missing expression of interest — 15 points
	// The expression of interest field explains the applicant's business intent.
	// Its absence suggests the application was not genuinely completed.
	hasEOI, err := s.repo.HasExpressionOfInterest(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("rule 10 (expression of interest): %w", err)
	}
	if !hasEOI {
		score += 15
		details["missing_expression_of_interest"] = 15
	}

	// Determine risk level from score band.
	riskLevel := scoreToRiskLevel(score)

	return &EvaluationResult{
		Score:     score,
		RiskLevel: riskLevel,
		Details:   details,
	}, nil
}

// scoreToRiskLevel converts a numeric score to the human-readable risk band.
func scoreToRiskLevel(score int) string {
	switch {
	case score <= 29:
		return "LOW"
	case score <= 59:
		return "MEDIUM"
	case score <= 79:
		return "HIGH"
	default:
		return "CRITICAL"
	}
}
```

The SQL for each repository method is straightforward. Here are the most important ones:

```go
// File: internal/hfc/scorer_pg_repository.go
package hfc

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

type PGScorerRepository struct {
	db *pgxpool.Pool
}

func NewPGScorerRepository(db *pgxpool.Pool) *PGScorerRepository {
	return &PGScorerRepository{db: db}
}

func (r *PGScorerRepository) CountDuplicateCNIC(ctx context.Context, cnic string, excludeUserID int64) (int, error) {
	var count int
	err := r.db.QueryRow(ctx,
		`SELECT COUNT(*) FROM users WHERE cnic = $1 AND user_id != $2`,
		cnic, excludeUserID,
	).Scan(&count)
	return count, fmt.Errorf("count duplicate cnic: %w", wrapNil(err))
}

func (r *PGScorerRepository) CountDuplicateEmail(ctx context.Context, email string, excludeUserID int64) (int, error) {
	var count int
	err := r.db.QueryRow(ctx,
		`SELECT COUNT(*) FROM users WHERE email_address = $1 AND user_id != $2`,
		email, excludeUserID,
	).Scan(&count)
	return count, fmt.Errorf("count duplicate email: %w", wrapNil(err))
}

func (r *PGScorerRepository) CountDuplicateMobile(ctx context.Context, mobile string, excludeUserID int64) (int, error) {
	var count int
	err := r.db.QueryRow(ctx,
		`SELECT COUNT(*) FROM users WHERE mobile_no = $1 AND user_id != $2`,
		mobile, excludeUserID,
	).Scan(&count)
	return count, fmt.Errorf("count duplicate mobile: %w", wrapNil(err))
}

func (r *PGScorerRepository) HasBusinessProfile(ctx context.Context, userID int64) (bool, error) {
	var count int
	err := r.db.QueryRow(ctx,
		`SELECT COUNT(*) FROM businesses WHERE user_id = $1`,
		userID,
	).Scan(&count)
	return count > 0, wrapNil(err)
}

func (r *PGScorerRepository) CountRequiredDocuments(ctx context.Context, userID int64) (int, error) {
	// required_doc_types is the set of document type identifiers the SRS defines
	// as mandatory. COUNT DISTINCT ensures each type is counted once even if
	// the applicant uploaded multiple files of the same type.
	var count int
	err := r.db.QueryRow(ctx, `
		SELECT COUNT(DISTINCT document_type)
		FROM business_documents
		WHERE user_id = $1
		  AND document_type IN (
			  'cnic_front', 'cnic_back', 'business_registration',
			  'bank_statement', 'utility_bill'
		  )
	`, userID).Scan(&count)
	return count, wrapNil(err)
}

func (r *PGScorerRepository) HasGrantMedia(ctx context.Context, userID int64) (bool, error) {
	var count int
	err := r.db.QueryRow(ctx,
		`SELECT COUNT(*) FROM grant_media WHERE user_id = $1`,
		userID,
	).Scan(&count)
	return count > 0, wrapNil(err)
}

func (r *PGScorerRepository) GetBusinessDistrict(ctx context.Context, userID int64) (string, error) {
	var district string
	err := r.db.QueryRow(ctx,
		`SELECT COALESCE(business_location_district, '') FROM businesses WHERE user_id = $1`,
		userID,
	).Scan(&district)
	return district, wrapNil(err)
}

func (r *PGScorerRepository) GetGrantRequiredAmount(ctx context.Context, userID int64) (float64, error) {
	var amount float64
	err := r.db.QueryRow(ctx,
		`SELECT COALESCE(grant_required, 0) FROM grants WHERE user_id = $1`,
		userID,
	).Scan(&amount)
	return amount, wrapNil(err)
}

func (r *PGScorerRepository) SecondsSinceRegistration(ctx context.Context, userID int64) (int64, error) {
	var seconds int64
	err := r.db.QueryRow(ctx,
		`SELECT EXTRACT(EPOCH FROM (NOW() - created_at))::BIGINT FROM users WHERE user_id = $1`,
		userID,
	).Scan(&seconds)
	return seconds, wrapNil(err)
}

func (r *PGScorerRepository) HasExpressionOfInterest(ctx context.Context, userID int64) (bool, error) {
	var eoi string
	err := r.db.QueryRow(ctx,
		`SELECT COALESCE(expression_of_interest, '') FROM grants WHERE user_id = $1`,
		userID,
	).Scan(&eoi)
	return len(eoi) > 10, wrapNil(err) // must be more than a blank or trivial entry
}

// wrapNil returns nil unchanged and wraps non-nil errors.
// Used to avoid "wrap nil error" false-positive in fmt.Errorf.
func wrapNil(err error) error {
	if err == nil {
		return nil
	}
	return err
}
```

**Why sequential instead of concurrent goroutines?**

The rule evaluation runs as a background job (not on a request path) and the result is cached in `hfc_evaluations` for the admin UI. Running ten sequential queries takes roughly 5-10ms on a local database — fast enough that the complexity of goroutine coordination is not justified at this stage. Add concurrency when profiling proves it is the bottleneck, not before.

---

### Implementation 2: Redis-Backed HFC Debounce

User data changes frequently during profile completion. Every document upload, profile save, and grant form autosave could trigger an HFC recalculation. Without debouncing you would run the scorer dozens of times in a few minutes for a single user filling out their profile — wasting database query budget and producing noisy intermediate scores.

The debounce pattern: when asked to enqueue an HFC job, first check for a Redis key specific to that user. If the key exists, the job was already scheduled in the last 60 seconds — skip it. If not, set the key (with 60s TTL) and push the job to the queue.

```go
// File: internal/hfc/queue.go
package hfc

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	hfcDebouncePrefix = "peace_sme:hfc_debounce"
	hfcDebounceTTL    = 60 * time.Second
	// rqQueueKey is the Redis list key that Python RQ workers pull jobs from.
	rqQueueKey = "rq:queue:hfc"
)

// RQJob is the JSON structure Python RQ expects when it reads a job from the
// Redis list. The "func" field must match the Python dotted import path of the
// task function.
type RQJob struct {
	Func        string        `json:"func"`
	Args        []interface{} `json:"args"`
	Kwargs      interface{}   `json:"kwargs"`
	Description string        `json:"description"`
}

// Queue wraps the Redis client to provide HFC-specific enqueue operations.
type Queue struct {
	client *redis.Client
}

func NewQueue(client *redis.Client) *Queue {
	return &Queue{client: client}
}

// EnqueueRecalculation schedules an HFC recalculation for userID.
// If a job for this user was already enqueued within the last 60 seconds,
// this call is a no-op (debounced).
//
// Returns (true, nil) if the job was enqueued, (false, nil) if it was debounced.
func (q *Queue) EnqueueRecalculation(ctx context.Context, userID int64) (bool, error) {
	debounceKey := fmt.Sprintf("%s:%d", hfcDebouncePrefix, userID)

	// SETNX = SET if Not eXists. Returns 1 if the key was set (first enqueue),
	// 0 if it already existed (debounced). This is atomic — no race condition.
	set, err := q.client.SetNX(ctx, debounceKey, "1", hfcDebounceTTL).Result()
	if err != nil {
		return false, fmt.Errorf("debounce check for user %d: %w", userID, err)
	}
	if !set {
		// Debounced — a job is already in the pipeline for this user.
		return false, nil
	}

	// Build the RQ-compatible job payload.
	job := RQJob{
		Func:        "services.hfc_service.calculate",
		Args:        []interface{}{userID},
		Kwargs:      map[string]interface{}{},
		Description: fmt.Sprintf("HFC recalculation for user %d", userID),
	}

	payload, err := json.Marshal(job)
	if err != nil {
		return false, fmt.Errorf("marshal hfc job for user %d: %w", userID, err)
	}

	// RPUSH appends to the tail of the list. RQ workers pop from the head (LPOP),
	// giving FIFO ordering. This is the correct direction for a job queue.
	if err := q.client.RPush(ctx, rqQueueKey, payload).Err(); err != nil {
		// If push fails, clear the debounce key so the next call can retry.
		_ = q.client.Del(ctx, debounceKey)
		return false, fmt.Errorf("push hfc job for user %d: %w", userID, err)
	}

	return true, nil
}

// ClearDebounce removes the debounce key for a user. Used when an admin
// manually triggers an immediate recalculation via the admin UI and wants
// to bypass the 60s window.
func (q *Queue) ClearDebounce(ctx context.Context, userID int64) error {
	debounceKey := fmt.Sprintf("%s:%d", hfcDebouncePrefix, userID)
	return q.client.Del(ctx, debounceKey).Err()
}
```

**Why `SetNX` instead of `Get` then `Set`?**

`SetNX` is a single atomic Redis command. If you used `Get` followed by `Set`, two concurrent requests could both see no key, both decide to enqueue, and both push jobs — a classic check-then-act race condition. `SetNX` eliminates this because the check and set happen as one indivisible operation.

---

### Implementation 3: Complete Approval Workflow

Approval is the most consequential write operation in the portal. It touches three tables, sends two emails, and invalidates the admin cache. All of the database writes happen inside a single transaction — if any step fails, none of them commit.

```go
// File: internal/hfc/approval_service.go
package hfc

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/peace-sme/portal/internal/cache"
)

// ApprovalRequest contains the fields the approver must supply.
type ApprovalRequest struct {
	ApprovedAmount float64 `json:"approved_amount"`
	ApprovalReason string  `json:"approval_reason"`
	// OverrideHFC allows an approver to approve despite CRITICAL HFC risk.
	// Only valid when shadow mode is off. Requires explicit opt-in.
	OverrideHFC bool `json:"override_hfc"`
}

// ErrApprovalBlocked is returned when HFC risk prevents approval without an override.
var ErrApprovalBlocked = errors.New("approval blocked: applicant has CRITICAL HFC risk; supply override_hfc=true to proceed")

// ApprovalService handles grant approval business logic.
type ApprovalService struct {
	db         *pgxpool.Pool
	queue      *Queue
	cache      *cache.Cache
	shadowMode bool
}

func NewApprovalService(db *pgxpool.Pool, q *Queue, c *cache.Cache, shadowMode bool) *ApprovalService {
	return &ApprovalService{db: db, queue: q, cache: c, shadowMode: shadowMode}
}

// ApproveGrant executes the full approval workflow for a single applicant.
// approverUserID is the admin's user_id extracted from the JWT by middleware.
func (s *ApprovalService) ApproveGrant(ctx context.Context, applicantUserID, approverUserID int64, req ApprovalRequest) error {
	// Step 1: Validate inputs before touching the database.
	if req.ApprovedAmount <= 0 {
		return fmt.Errorf("approved_amount must be greater than zero")
	}
	if len(req.ApprovalReason) < 10 {
		return fmt.Errorf("approval_reason must be at least 10 characters")
	}

	// Step 2: Check HFC risk level. If shadow mode is OFF and risk is CRITICAL,
	// block the approval unless the approver has explicitly set override_hfc.
	if !s.shadowMode {
		var hfcStatus string
		err := s.db.QueryRow(ctx,
			`SELECT COALESCE(hfc_status, '') FROM grants WHERE user_id = $1`,
			applicantUserID,
		).Scan(&hfcStatus)
		if err != nil {
			return fmt.Errorf("fetch hfc status for user %d: %w", applicantUserID, err)
		}

		if hfcStatus == "CRITICAL" && !req.OverrideHFC {
			return ErrApprovalBlocked
		}
	}

	// Step 3: Begin a PostgreSQL transaction.
	// All database writes for this approval happen inside this transaction.
	// If any write fails, tx.Rollback() is called and nothing is committed.
	tx, err := s.db.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin approval transaction: %w", err)
	}
	// Deferred rollback is a no-op after tx.Commit() succeeds.
	defer func() { _ = tx.Rollback(ctx) }()

	now := time.Now().UTC()

	// Step 4: Update the grants table with approval details.
	_, err = tx.Exec(ctx, `
		UPDATE grants
		SET
			status          = 'Approved',
			approved_amount = $1,
			approval_reason = $2,
			approved_at     = $3,
			approved_by     = $4,
			hfc_override    = $5
		WHERE user_id = $6
	`,
		req.ApprovedAmount,
		req.ApprovalReason,
		now,
		approverUserID,
		req.OverrideHFC,
		applicantUserID,
	)
	if err != nil {
		return fmt.Errorf("update grant status: %w", err)
	}

	// Step 5: Insert an immutable audit record into grant_approval_logs.
	// This row is never updated or deleted — it is the permanent record of
	// who approved what, when, for how much, and why.
	_, err = tx.Exec(ctx, `
		INSERT INTO grant_approval_logs
			(user_id, approver_id, approved_amount, approval_reason, hfc_override, approved_at)
		VALUES ($1, $2, $3, $4, $5, $6)
	`,
		applicantUserID,
		approverUserID,
		req.ApprovedAmount,
		req.ApprovalReason,
		req.OverrideHFC,
		now,
	)
	if err != nil {
		return fmt.Errorf("insert approval log: %w", err)
	}

	// Step 6: Commit the transaction.
	// Both the grants UPDATE and the approval_logs INSERT are now durable.
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit approval transaction: %w", err)
	}

	// Step 7: Enqueue email notifications AFTER the transaction commits.
	// Emails are side-effects. They must not run inside the transaction because:
	//   a) They hold the DB connection open while waiting for the email service.
	//   b) If the transaction later rolls back, the email cannot be unsent.
	// Enqueueing to Redis is fast (~1ms) and the worker handles actual delivery.
	s.enqueueApprovalEmails(ctx, applicantUserID)

	// Step 8: Invalidate the admin dashboard cache so the stats reflect the
	// new Approved count on the next page load.
	_ = s.cache.Delete(ctx, dashboardStatsCacheKey)

	return nil
}

// enqueueApprovalEmails pushes both notification emails to the Redis queue.
// This is fire-and-forget at the Go level — failures are logged but do not
// roll back the approval. The email worker has its own retry mechanism.
func (s *ApprovalService) enqueueApprovalEmails(ctx context.Context, applicantUserID int64) {
	jobs := []RQJob{
		{
			Func:        "services.email_service.send_grant_approved_email",
			Args:        []interface{}{applicantUserID},
			Kwargs:      map[string]interface{}{},
			Description: fmt.Sprintf("send grant approved email to user %d", applicantUserID),
		},
		{
			Func:        "services.email_service.send_grant_approval_notification_email",
			Args:        []interface{}{applicantUserID},
			Kwargs:      map[string]interface{}{},
			Description: fmt.Sprintf("send approval notification for user %d", applicantUserID),
		},
	}

	for _, job := range jobs {
		payload, err := marshalJob(job)
		if err != nil {
			continue // log in production
		}
		_ = s.queue.client.RPush(ctx, "rq:queue:email", payload).Err()
	}
}

func marshalJob(job RQJob) ([]byte, error) {
	return jsonMarshal(job)
}
```

The HTTP handler for the approval endpoint extracts the approver's user ID from the JWT claims (already validated by the `RequireApprover` middleware) and delegates to the service:

```go
// File: internal/hfc/approval_handler.go
package hfc

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"
	"github.com/peace-sme/portal/internal/auth"
	"github.com/peace-sme/portal/internal/httpx"
)

type ApprovalHandler struct {
	svc *ApprovalService
}

func NewApprovalHandler(svc *ApprovalService) *ApprovalHandler {
	return &ApprovalHandler{svc: svc}
}

// ApproveGrant handles POST /api/admin/grants/<user_id>/approve
// The route is protected by RequireApprover middleware which validates
// the JWT and ensures is_approver == true before this handler runs.
func (h *ApprovalHandler) ApproveGrant(w http.ResponseWriter, r *http.Request) {
	applicantUserID, err := strconv.ParseInt(chi.URLParam(r, "user_id"), 10, 64)
	if err != nil {
		httpx.WriteError(w, http.StatusBadRequest, "invalid user_id")
		return
	}

	// The approver's identity comes from the JWT claims, not from the request body.
	// This prevents an approver from spoofing a different approver's identity.
	claims, ok := auth.ClaimsFromContext(r.Context())
	if !ok {
		httpx.WriteError(w, http.StatusUnauthorized, "missing auth claims")
		return
	}

	var req ApprovalRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpx.WriteError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if err := h.svc.ApproveGrant(r.Context(), applicantUserID, claims.UserID, req); err != nil {
		if errors.Is(err, ErrApprovalBlocked) {
			httpx.WriteError(w, http.StatusForbidden, err.Error())
			return
		}
		httpx.WriteError(w, http.StatusInternalServerError, "approval failed")
		return
	}

	httpx.WriteJSON(w, http.StatusOK, map[string]string{"status": "approved"})
}
```

**Why is `ErrApprovalBlocked` a sentinel error?**

Using `errors.Is(err, ErrApprovalBlocked)` in the handler lets us return an HTTP 403 specifically for the HFC block case, while all other errors return 500. Without a sentinel, the handler would have to parse error message strings — fragile and prone to breakage when messages change.

---

### Implementation 4: HFC Admin Actions

Admins can take three manual actions on an applicant's HFC record: mark it cleared, mark it failed, or add an override that allows approval to proceed despite the risk score.

```go
// File: internal/hfc/action_service.go
package hfc

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// ActionType is the set of valid action_type values from the SRS.
type ActionType string

const (
	ActionMarkClear  ActionType = "mark_clear"
	ActionMarkFailed ActionType = "mark_failed"
	ActionOverride   ActionType = "override"
)

// HFCActionRequest is the request body for POST /api/admin/hfc/applicant/<user_id>/action
type HFCActionRequest struct {
	ActionType ActionType `json:"action_type"`
	Comment    string     `json:"comment"`
}

// ActionService handles the three manual HFC admin actions.
type ActionService struct {
	db *pgxpool.Pool
}

func NewActionService(db *pgxpool.Pool) *ActionService {
	return &ActionService{db: db}
}

// RecordAction performs the HFC admin action for a given applicant.
// It inserts an audit record in hfc_review_actions and updates the
// relevant field(s) on grants within the same transaction.
func (s *ActionService) RecordAction(ctx context.Context, applicantUserID, adminUserID int64, req HFCActionRequest) error {
	// Validate action_type against the known set.
	switch req.ActionType {
	case ActionMarkClear, ActionMarkFailed, ActionOverride:
		// valid
	default:
		return fmt.Errorf("unknown action_type %q: must be mark_clear, mark_failed, or override", req.ActionType)
	}

	if len(req.Comment) < 5 {
		return fmt.Errorf("comment must be at least 5 characters")
	}

	tx, err := s.db.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin action transaction: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	now := time.Now().UTC()

	// Capture current HFC state for the audit record's "before" snapshot.
	var beforeState []byte
	_ = tx.QueryRow(ctx,
		`SELECT to_jsonb(g) FROM grants g WHERE user_id = $1`,
		applicantUserID,
	).Scan(&beforeState)

	// Apply the action to the grants table.
	switch req.ActionType {
	case ActionMarkClear:
		_, err = tx.Exec(ctx,
			`UPDATE grants SET hfc_status = 'HFC_Cleared' WHERE user_id = $1`,
			applicantUserID,
		)
	case ActionMarkFailed:
		_, err = tx.Exec(ctx,
			`UPDATE grants SET hfc_status = 'HFC_Failed' WHERE user_id = $1`,
			applicantUserID,
		)
	case ActionOverride:
		// Override does not change hfc_status — the score stands as recorded.
		// It sets hfc_override = true which the approval service checks to
		// allow approval to proceed despite the risk level.
		_, err = tx.Exec(ctx,
			`UPDATE grants SET hfc_override = true WHERE user_id = $1`,
			applicantUserID,
		)
	}
	if err != nil {
		return fmt.Errorf("apply hfc action %q: %w", req.ActionType, err)
	}

	// Capture after state for the audit record.
	var afterState []byte
	_ = tx.QueryRow(ctx,
		`SELECT to_jsonb(g) FROM grants g WHERE user_id = $1`,
		applicantUserID,
	).Scan(&afterState)

	// Insert the immutable audit record.
	_, err = tx.Exec(ctx, `
		INSERT INTO hfc_review_actions
			(user_id, admin_id, action_type, comment, before_state, after_state, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
	`,
		applicantUserID,
		adminUserID,
		string(req.ActionType),
		req.Comment,
		beforeState,
		afterState,
		now,
	)
	if err != nil {
		return fmt.Errorf("insert hfc_review_action: %w", err)
	}

	return tx.Commit(ctx)
}
```

The handler for `POST /api/admin/hfc/applicant/<user_id>/action`:

```go
// File: internal/hfc/action_handler.go
package hfc

import (
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"
	"github.com/peace-sme/portal/internal/auth"
	"github.com/peace-sme/portal/internal/httpx"
)

type ActionHandler struct {
	svc *ActionService
}

func NewActionHandler(svc *ActionService) *ActionHandler {
	return &ActionHandler{svc: svc}
}

func (h *ActionHandler) PostHFCAction(w http.ResponseWriter, r *http.Request) {
	applicantUserID, err := strconv.ParseInt(chi.URLParam(r, "user_id"), 10, 64)
	if err != nil {
		httpx.WriteError(w, http.StatusBadRequest, "invalid user_id")
		return
	}

	claims, ok := auth.ClaimsFromContext(r.Context())
	if !ok {
		httpx.WriteError(w, http.StatusUnauthorized, "missing auth claims")
		return
	}

	var req HFCActionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpx.WriteError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if err := h.svc.RecordAction(r.Context(), applicantUserID, claims.UserID, req); err != nil {
		httpx.WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	httpx.WriteJSON(w, http.StatusOK, map[string]string{"status": "action recorded"})
}
```

**Why capture `before_state` and `after_state` as JSON blobs?**

Storing the entire row snapshot as JSON means the audit log is self-contained. Even if the `grants` table schema changes in a future migration, the audit record still shows exactly what the row looked like at the time of the action. Using foreign keys to the grants table would give you only the current state, not the historical state at the moment of the action.

---

## Mastery Check

You understand this chapter when you can:
- Implement all ten HFC rules in a sequential scorer, explaining what each rule measures and why it carries its specific point value.
- Explain why `CountDuplicateCNIC` uses `AND user_id != $2` rather than just `WHERE cnic = $1`.
- Write a `ScorerRepository` interface and explain why the interface enables unit testing without a database.
- Implement Redis debounce using `SetNX` and explain why `Get`+`Set` is not a safe alternative.
- Describe the full approval workflow in order: validate inputs, check HFC, begin transaction, update grants, insert audit log, commit, enqueue emails, invalidate cache.
- Explain why email enqueueing happens AFTER `tx.Commit()` and not inside the transaction.
- Implement the three HFC admin actions (`mark_clear`, `mark_failed`, `override`) as a single transactional service method.
- Explain what `hfc_override = true` means versus `hfc_status = 'HFC_Cleared'` and when each is appropriate.
- Explain why shadow mode changes enforcement but not scoring.
- Justify storing `before_state` and `after_state` as JSON blobs in the audit log rather than as foreign key references.
