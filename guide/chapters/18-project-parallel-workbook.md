# Chapter 18: Project Parallel Workbook

## Purpose

This chapter turns the book into a build plan. Each exercise pairs a concept with a concrete PEACE SME implementation task. Use it when you ask, "What should I build to understand this topic?" Work through the milestones in order — each one builds on the last.

---

## Architecture Overview

Before building anything, understand what you are building:

```
┌──────────────────────────────────────────────────────────────────┐
│                         sme_network                              │
│                                                                  │
│  ┌─────────────┐     ┌──────────────────────┐                   │
│  │  PostgreSQL  │◄────│    Go Backend        │◄── :8080          │
│  │  (port 5433) │     │  (sme_backend_app)   │                   │
│  └─────────────┘     └──────────┬───────────┘                   │
│                                 │                                │
│  ┌─────────────┐     ┌──────────▼───────────┐                   │
│  │   Redis 7    │◄────│    Go Worker         │                   │
│  │  (internal)  │     │  (emails + hfc jobs) │                   │
│  └─────────────┘     └──────────────────────┘                   │
│                                                                  │
│  ┌─────────────────────────────────────────┐                    │
│  │  nginx + Vue SPA          :3001          │                    │
│  │  /api/* → proxy → backend               │                    │
│  └─────────────────────────────────────────┘                    │
│                                                                  │
│  adminer :8082    pgAdmin :5051                                  │
└──────────────────────────────────────────────────────────────────┘

Request flow:
  Browser → nginx :3001
    └── GET /dashboard → Vue SPA (client-side routing)
    └── GET /api/updates → proxy → Go backend :8080
         └── query PostgreSQL
         └── check Redis cache
         └── return JSON
```

---

## Parallel Task Table

| Learning topic | Theory to study | Backend task | Vue task | Git task |
|---|---|---|---|---|
| HTTP routing | request methods, paths, status codes | implement `/health` and `/api/updates` | show updates on landing page | commit route and handler separately |
| JSON encoding | struct tags, request decoding | implement `ReadJSON` and `WriteJSON` | consume JSON with Axios | inspect diff for response names |
| Config | env vars, defaults, validation | parse `GRANT_APPLICATION_OPEN` | show registration closed page | add config tests before commit |
| Auth | JWT, bcrypt, bearer headers | implement `/api/login` | store `userToken` | branch `feature/user-login` |
| Admin auth | roles and permissions | implement `/api/admin/login` | store `adminToken` | commit admin claims tests |
| Middleware | chain of handlers | auth, geo-block, access slot middleware | redirect unauthenticated routes | diff middleware order |
| Database | schema, indexes, joins | migrate `users`, `businesses` | dashboard fetches profile | tag first DB milestone |
| Transactions | atomic multi-step writes | approve grant and log action | approval button | commit failing test then fix |
| JSONB | typed nested data | save `financed_items` | dynamic item rows | review JSON names |
| Validation | business rule enforcement | allowed districts, contribution rules | inline form errors | commit validation table tests |
| Uploads | presigned URLs, object keys | generate upload URL | document upload component | branch `feature/uploads` |
| Redis | TTL, cache, debounce | cache FAQs and updates | FAQ drawer consumes API | commit cache invalidation |
| Reports | pagination, filters, sorting | applicant report endpoint | admin table filters | compare query params diff |
| CSV | streaming, query tokens | full applicant export | export button | add token expiry test |
| HFC | deterministic scoring | calculate score and risk | HFC queue display | commit rule tests one by one |
| Workers | durable background jobs | enqueue HFC and email jobs | show pending state | tag async milestone |
| Bilingual UI | translation dictionaries, RTL | return language from login | language switcher | commit English/Urdu together |
| Deployment | containers, migrations | Dockerfile and migration runner | static frontend build | tag release candidate |

---

## Milestone 1: Skeleton That Teaches Go Basics

### Goal

Make the Go program feel understandable. Learn how Go organizes code before touching databases or auth.

### Theory to Study

- Go packages and the `main` package
- Exported vs unexported names (uppercase = exported)
- Functions with multiple return values
- Structs and struct literals
- Pointers (`*T` vs `T`)
- Error handling: `if err != nil { return err }`
- `http.HandleFunc` and `http.ListenAndServe`

### Build

```
backend-go/
├── cmd/server/main.go          entry point
├── internal/config/config.go   env var loading
├── internal/httpx/json.go      WriteJSON / ReadJSON helpers
├── internal/health/handler.go  /health endpoint
└── internal/content/handler.go /api/updates endpoint
```

### Starter Code

```go
// File: internal/httpx/json.go
package httpx

import (
    "encoding/json"
    "net/http"
)

// WriteJSON sends a JSON-encoded value with the given status code.
func WriteJSON(w http.ResponseWriter, status int, v any) error {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    return json.NewEncoder(w).Encode(v)
}

// ReadJSON decodes the request body into v.
func ReadJSON(r *http.Request, v any) error {
    return json.NewDecoder(r.Body).Decode(v)
}
```

```go
// File: internal/health/handler.go
package health

import (
    "net/http"

    "github.com/yourusername/peace-sme/internal/httpx"
)

type HealthResponse struct {
    Status  string `json:"status"`
    Service string `json:"service"`
}

func Handler(w http.ResponseWriter, r *http.Request) {
    httpx.WriteJSON(w, http.StatusOK, HealthResponse{
        Status:  "ok",
        Service: "peace-sme-backend",
    })
}
```

### Expected Output

```bash
$ curl http://localhost:8080/health
{"status":"ok","service":"peace-sme-backend"}

$ curl http://localhost:8080/api/updates
[]
```

### Vue Parallel

Create a landing page section that calls `/api/updates`:

```vue
<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const updates = ref([])

onMounted(async () => {
  const { data } = await axios.get('/api/updates')
  updates.value = data
})
</script>

<template>
  <div>
    <div v-for="update in updates" :key="update.update_id">
      <h3>{{ update.title }}</h3>
      <p>{{ update.body }}</p>
    </div>
    <p v-if="updates.length === 0">No announcements.</p>
  </div>
</template>
```

### Git

```bash
git checkout -b milestone-01-server-skeleton
git add internal/httpx/ internal/health/ cmd/server/main.go
git commit -m "Add Go server skeleton with health endpoint"
git add internal/content/
git commit -m "Add public updates endpoint"
```

### Done When

- `go test ./...` passes.
- `curl /health` returns `{"status":"ok"}`.
- `curl /api/updates` returns `[]` or seeded rows.
- Vue landing page shows updates.

---

## Milestone 2: Login Vertical Slice

### Goal

Understand web auth end to end. This is the most important milestone — every subsequent feature depends on authentication.

### Theory to Study

- SQL query result scanning with `pgx`
- Nullable values: `pgtype.Text`, `*string`
- Service layer errors vs HTTP errors
- JWT HS256 claims and expiry
- `localStorage` in the browser
- Axios default headers

### Build

```
internal/
├── user/
│   ├── model.go        User struct
│   ├── repo.go         FindByEmail
│   └── handler.go      POST /api/login
├── auth/
│   ├── jwt.go          GenerateUserToken, ParseUserToken
│   └── bcrypt.go       VerifyPassword
```

### Starter Code — User Repository

```go
// File: internal/user/repo.go
package user

import (
    "context"
    "errors"

    "github.com/jackc/pgx/v5"
    "github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("user not found")

type Repository struct {
    pool *pgxpool.Pool
}

func NewRepository(pool *pgxpool.Pool) *Repository {
    return &Repository{pool: pool}
}

func (r *Repository) FindByEmail(ctx context.Context, email string) (*User, error) {
    u := &User{}
    err := r.pool.QueryRow(ctx, `
        SELECT user_id, email_address, hashed_password,
               first_name, last_name, cnic, language, status
        FROM users
        WHERE email_address = $1
    `, email).Scan(
        &u.UserID, &u.EmailAddress, &u.HashedPassword,
        &u.FirstName, &u.LastName, &u.CNIC, &u.Language, &u.Status,
    )
    if errors.Is(err, pgx.ErrNoRows) {
        return nil, ErrNotFound
    }
    return u, err
}
```

### Starter Code — JWT

```go
// File: internal/auth/jwt.go
package auth

import (
    "fmt"
    "time"

    "github.com/golang-jwt/jwt/v5"
)

type UserClaims struct {
    UserID int `json:"user_id"`
    jwt.RegisteredClaims
}

func GenerateUserToken(userID int, secret string) (string, error) {
    claims := UserClaims{
        UserID: userID,
        RegisteredClaims: jwt.RegisteredClaims{
            ExpiresAt: jwt.NewNumericDate(time.Now().Add(24 * time.Hour)),
            IssuedAt:  jwt.NewNumericDate(time.Now()),
        },
    }
    return jwt.NewWithClaims(jwt.SigningMethodHS256, claims).
        SignedString([]byte(secret))
}

func ParseUserToken(tokenStr, secret string) (*UserClaims, error) {
    token, err := jwt.ParseWithClaims(tokenStr, &UserClaims{},
        func(t *jwt.Token) (any, error) {
            if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
                return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
            }
            return []byte(secret), nil
        },
    )
    if err != nil {
        return nil, err
    }
    claims, ok := token.Claims.(*UserClaims)
    if !ok || !token.Valid {
        return nil, fmt.Errorf("invalid token")
    }
    return claims, nil
}
```

### Debugging Exercise: Fix the Broken Login Handler

The following handler has **three bugs**. Find and fix them:

```go
// BROKEN — do not use as-is
func (h *Handler) Login(w http.ResponseWriter, r *http.Request) {
    var req LoginRequest
    json.NewDecoder(r.Body).Decode(&req) // Bug 1

    user, err := h.repo.FindByEmail(r.Context(), req.Email)
    if err != nil {
        WriteJSON(w, 200, map[string]string{"error": "not found"}) // Bug 2
        return
    }

    if err := bcrypt.CompareHashAndPassword(
        []byte(req.Password), []byte(user.HashedPassword), // Bug 3
    ); err != nil {
        WriteJSON(w, 401, map[string]string{"error": "invalid password"})
        return
    }

    token, _ := auth.GenerateUserToken(user.UserID, h.secret)
    WriteJSON(w, 200, LoginResponse{Token: token, UserID: user.UserID})
}
```

Bug 1: Decode errors are ignored — the handler continues with a zero-value request.
Bug 2: Returns HTTP 200 for "not found" — should be 401.
Bug 3: Arguments to `CompareHashAndPassword` are swapped — first arg is the hash, second is the plain password.

### Git

```bash
git checkout -b feature/user-login
git commit -m "Add user repository with FindByEmail"
git commit -m "Add JWT token generation and parsing"
git commit -m "Implement POST /api/login endpoint"
git commit -m "Add Vue user login page"
```

### Done When

- Invalid password → 401.
- Blocked user → 403 with specific error.
- Valid login → `{token, user_id, language}`.
- Vue stores `userToken` and redirects to `/dashboard`.
- Authenticated request sends `Authorization: Bearer <token>`.

---

## Milestone 3: Business Profile

### Goal

Learn create/update workflows and validation. Every applicant has exactly one business profile — enforced by a UNIQUE constraint.

### Theory to Study

- One-to-one table relationships
- UNIQUE constraints and 409 Conflict responses
- Validation before database writes
- Vue `reactive` for form objects

### Validation Exercise

Write a function that validates the `CreateBusinessRequest` and returns all validation errors at once (not just the first one):

```go
// File: internal/business/dto.go
package business

import (
    "errors"
    "fmt"
    "strings"
)

var AllowedDistricts = []string{
    "Swat", "Shangla", "Upper Dir", "Upper Chitral", "Lower Chitral",
}

type CreateBusinessRequest struct {
    NameOfBusiness              string `json:"name_of_business"`
    BusinessLocationDistrict    string `json:"business_location_district"`
    BusinessSector              string `json:"business_sector"`
    MaleEmployees               int    `json:"male_employees"`
    FemaleEmployees             int    `json:"female_employees"`
    BusinessFullAddress         string `json:"business_full_address"`
}

// ValidationErrors collects multiple validation failures.
type ValidationErrors []string

func (ve ValidationErrors) Error() string {
    return strings.Join(ve, "; ")
}

func (req *CreateBusinessRequest) Validate() error {
    var errs ValidationErrors

    // YOUR TASK: implement the following validation rules
    // 1. NameOfBusiness must not be empty
    // 2. BusinessLocationDistrict must be in AllowedDistricts
    // 3. MaleEmployees and FemaleEmployees must be >= 0
    // 4. BusinessFullAddress must not be empty
    //
    // Collect ALL errors, return nil if none.

    // Example of rule 1:
    if strings.TrimSpace(req.NameOfBusiness) == "" {
        errs = append(errs, "business name is required")
    }

    // TODO: add remaining rules here

    if len(errs) > 0 {
        return errs
    }
    return nil
}

// isAllowedDistrict is a helper you can use in Validate.
func isAllowedDistrict(district string) bool {
    for _, d := range AllowedDistricts {
        if d == district {
            return true
        }
    }
    return false
}
```

Expected test output:

```
--- RUN   TestCreateBusinessRequest_Validate/valid_request
--- PASS
--- RUN   TestCreateBusinessRequest_Validate/invalid_district_Peshawar
--- PASS: error "district Peshawar is not in the allowed scope"
--- RUN   TestCreateBusinessRequest_Validate/negative_employees
--- PASS: error "employee counts cannot be negative"
```

### Git

```bash
git checkout -b feature/business-profile
git commit -m "Add business profile schema migration"
git commit -m "Add allowed district validation"
git commit -m "Implement business profile CRUD endpoints"
git commit -m "Add Vue business profile form with validation"
```

---

## Milestone 4: Grant Form and Whitelist Gate

### Goal

Master larger payloads and workflow rules. This is the core of the portal.

### Theory to Study

- JSONB fields: encoding `[]FinancedItem` to and from `json.RawMessage`
- Conditional validation: in-kind fields required when `contribution_type` includes in-kind
- Workflow gates: HTTP 403 when not whitelisted, with a clear error body
- HTTP 403 vs 409 vs 422

### JSONB Exercise

Write the `FinancedItem` type and show how it round-trips through JSONB:

```go
// File: internal/grant/items.go
package grant

import (
    "encoding/json"
    "fmt"
)

type FinancedItem struct {
    Item          string  `json:"item"`
    Quantity      int     `json:"quantity"`
    EstimatedCost float64 `json:"estimated_cost"`
}

// EncodeFinancedItems converts a slice to JSON bytes for PostgreSQL JSONB storage.
func EncodeFinancedItems(items []FinancedItem) ([]byte, error) {
    if items == nil {
        return []byte("[]"), nil // never store null
    }
    return json.Marshal(items)
}

// DecodeFinancedItems parses JSONB bytes back into a slice.
func DecodeFinancedItems(raw []byte) ([]FinancedItem, error) {
    if len(raw) == 0 || string(raw) == "null" {
        return []FinancedItem{}, nil
    }
    var items []FinancedItem
    return items, json.Unmarshal(raw, &items)
}

// ValidateFinancedItems returns an error if any item row is invalid.
func ValidateFinancedItems(items []FinancedItem) error {
    for i, item := range items {
        if item.Item == "" {
            return fmt.Errorf("item[%d]: name is required", i)
        }
        if item.Quantity < 1 {
            return fmt.Errorf("item[%d]: quantity must be at least 1", i)
        }
        if item.EstimatedCost <= 0 {
            return fmt.Errorf("item[%d]: estimated cost must be positive", i)
        }
    }
    return nil
}
```

### Whitelist Gate Business Logic

The whitelist check logic with shadow mode awareness:

```go
// File: internal/grant/access.go
package grant

import (
    "context"
    "fmt"
)

// AccessState values match what the Vue frontend checks.
const (
    AccessStateSelected    = "selected"
    AccessStateNotSelected = "not_selected"
    AccessStateNotRequired = "not_required"
)

type AccessChecker struct {
    repo             WhitelistRepository
    requireSelection bool
}

func NewAccessChecker(repo WhitelistRepository, requireSelection bool) *AccessChecker {
    return &AccessChecker{repo: repo, requireSelection: requireSelection}
}

// GetAccessState returns the access state for a user.
// The Vue frontend uses this to show the whitelist gate message.
func (a *AccessChecker) GetAccessState(ctx context.Context, userID int) (string, error) {
    if !a.requireSelection {
        return AccessStateNotRequired, nil
    }

    selected, err := a.repo.IsSelected(ctx, userID)
    if err != nil {
        return "", fmt.Errorf("whitelist check: %w", err)
    }

    if selected {
        return AccessStateSelected, nil
    }
    return AccessStateNotSelected, nil
}

// CanSubmit returns true if the user is allowed to submit a grant.
func (a *AccessChecker) CanSubmit(ctx context.Context, userID int) (bool, error) {
    if !a.requireSelection {
        return true, nil
    }
    return a.repo.IsSelected(ctx, userID)
}
```

### Vue Parallel — Dynamic Financed Items

```vue
<script setup>
import { reactive } from 'vue'

const form = reactive({
  financed_items: [
    { item: '', quantity: 1, estimated_cost: null }
  ]
})

function addItem() {
  form.financed_items.push({ item: '', quantity: 1, estimated_cost: null })
}

function removeItem(index) {
  form.financed_items.splice(index, 1)
}
</script>

<template>
  <div>
    <div v-for="(item, i) in form.financed_items" :key="i" class="flex gap-2 mb-2">
      <input v-model="item.item" placeholder="Item name" class="border p-1 flex-1" />
      <input v-model.number="item.quantity" type="number" min="1" class="border p-1 w-20" />
      <input v-model.number="item.estimated_cost" type="number" min="0" class="border p-1 w-32" />
      <button @click="removeItem(i)" class="text-red-500">✕</button>
    </div>
    <button @click="addItem" class="text-blue-600 text-sm">+ Add Item</button>
  </div>
</template>
```

### Git

```bash
git checkout -b feature/grant-application
git commit -m "Add grant schema and financed items JSONB type"
git commit -m "Implement grant access whitelist logic"
git commit -m "Implement POST and PUT /api/grant"
git commit -m "Add Vue multi-section grant form with dynamic items"
```

---

## Milestone 5: Admin Reports

### Goal

Learn real data querying with filters, sorting, and pagination. The admin report table is the most-used admin feature.

### Theory to Study

- SQL joins across multiple tables
- COUNT(*) OVER() for total without a second query
- Pagination: LIMIT/OFFSET
- SQL allow-list to prevent injection via sort fields
- Streaming CSV responses

### Pagination Implementation

```go
// File: internal/report/pagination.go
package report

import (
    "net/http"
    "strconv"
)

type Pagination struct {
    Page    int
    PerPage int
}

func (p Pagination) Offset() int {
    return (p.Page - 1) * p.PerPage
}

func ParsePagination(r *http.Request) Pagination {
    page := queryInt(r, "page", 1)
    perPage := queryInt(r, "per_page", 20)

    if page < 1 { page = 1 }
    if perPage < 1 { perPage = 20 }
    if perPage > 100 { perPage = 100 } // max page size

    return Pagination{Page: page, PerPage: perPage}
}

func queryInt(r *http.Request, key string, def int) int {
    v := r.URL.Query().Get(key)
    if v == "" { return def }
    n, err := strconv.Atoi(v)
    if err != nil { return def }
    return n
}
```

### SQL Injection Prevention for Sort Fields

```go
// File: internal/report/sort.go
package report

// AllowedSortFields maps safe frontend sort keys to SQL column expressions.
// Never interpolate sort fields directly from the request.
var AllowedSortFields = map[string]string{
    "created_at":   "u.created_at",
    "first_name":   "u.first_name",
    "last_name":    "u.last_name",
    "district":     "b.business_location_district",
    "sector":       "b.business_sector",
    "grant_status": "g.status",
}

func SafeSortField(key string) string {
    if col, ok := AllowedSortFields[key]; ok {
        return col
    }
    return "u.created_at" // default
}

func SafeSortDir(dir string) string {
    if dir == "asc" {
        return "ASC"
    }
    return "DESC" // default
}
```

### Paginated Response

```go
// File: internal/httpx/paginated.go
package httpx

// PaginatedResponse is the exact shape the Vue admin tables expect.
// All four fields must be present even for empty results.
type PaginatedResponse[T any] struct {
    Data    []T `json:"data"`
    Total   int `json:"total"`
    Page    int `json:"page"`
    PerPage int `json:"per_page"`
}

// NewPaginatedResponse ensures Data is [] not null when empty.
func NewPaginatedResponse[T any](data []T, total, page, perPage int) PaginatedResponse[T] {
    if data == nil {
        data = []T{}
    }
    return PaginatedResponse[T]{
        Data:    data,
        Total:   total,
        Page:    page,
        PerPage: perPage,
    }
}
```

### Debugging Exercise: Find the Pagination Bug

This endpoint returns the wrong total. Find the bug:

```go
// BROKEN
func (r *Repository) ApplicantReport(ctx context.Context, p Pagination) ([]ApplicantRow, int, error) {
    rows, err := r.pool.Query(ctx, `
        SELECT u.user_id, u.first_name, u.last_name, u.email_address,
               b.name_of_business, b.business_location_district
        FROM users u
        LEFT JOIN businesses b ON b.user_id = u.user_id
        ORDER BY u.created_at DESC
        LIMIT $1 OFFSET $2
    `, p.PerPage, p.Offset())
    if err != nil {
        return nil, 0, err
    }
    defer rows.Close()

    var result []ApplicantRow
    for rows.Next() {
        var row ApplicantRow
        rows.Scan(&row.UserID, &row.FirstName, &row.LastName,
                  &row.EmailAddress, &row.BusinessName, &row.District)
        result = append(result, row)
    }

    // Bug: this counts only the page results, not all rows
    total := len(result)
    return result, total, nil
}
```

Fix: run a separate `SELECT COUNT(*)` before the paginated query, or use `COUNT(*) OVER()` as a window function:

```sql
SELECT u.user_id, u.first_name, ...,
       COUNT(*) OVER() AS total_count
FROM users u
LEFT JOIN businesses b ON b.user_id = u.user_id
ORDER BY u.created_at DESC
LIMIT $1 OFFSET $2
```

---

## Milestone 6: HFC Scoring and Approval

### Goal

Learn deterministic business logic, auditability, and transactional side effects.

### Theory to Study

- Pure functions for business rules (no I/O, no randomness)
- Risk bands as a switch statement
- Audit logs: always write before and after state
- Database transactions for multi-table writes
- Interface injection for email side effects

### HFC Rule Implementation Exercise

Implement all 10 HFC rules from the specification:

```go
// File: internal/hfc/rules.go
package hfc

// Rule point values
const (
    PointsDuplicateCNIC    = 50
    PointsDuplicateEmail   = 20
    PointsDuplicateMobile  = 20
    PointsMissingBusiness  = 30
    PointsMissingDocs      = 25
    PointsMissingMedia     = 10
    PointsOutOfScope       = 40
    PointsHighAmount       = 15
    PointsFastSubmission   = 10
    PointsMissingEOI       = 15

    HighAmountThreshold       = 1_000_000
    FastSubmissionMinutes     = 5
)

type Rule struct {
    Code        string
    Points      int
    Description string
    Check       func(input ScoringInput) bool
}

// AllRules is the ordered list of HFC scoring rules.
// Each rule is a pure function — no database access, no side effects.
var AllRules = []Rule{
    {
        Code:        "DUPLICATE_CNIC",
        Points:      PointsDuplicateCNIC,
        Description: "Same CNIC appears on another user account",
        Check:       func(i ScoringInput) bool { return i.DuplicateCNIC },
    },
    {
        Code:        "DUPLICATE_EMAIL",
        Points:      PointsDuplicateEmail,
        Description: "Same email used on another account",
        Check:       func(i ScoringInput) bool { return i.DuplicateEmail },
    },
    // TODO: implement the remaining 8 rules following the same pattern
    // DUPLICATE_MOBILE, MISSING_BUSINESS, MISSING_DOCS, MISSING_MEDIA,
    // OUT_OF_SCOPE_DISTRICT, HIGH_GRANT_AMOUNT, FAST_SUBMISSION, MISSING_EOI
}

// CalculateScore applies all rules and returns a result.
func CalculateScore(input ScoringInput) ScoreResult {
    total := 0
    var triggered []string

    for _, rule := range AllRules {
        if rule.Check(input) {
            total += rule.Points
            triggered = append(triggered, rule.Code)
        }
    }

    return ScoreResult{
        FinalScore:     total,
        RiskLevel:      CalculateRiskLevel(total),
        RulesTriggered: triggered,
    }
}
```

### Approval Transaction

```go
// File: internal/grant/approval.go
package grant

import (
    "context"
    "fmt"
    "time"

    "github.com/jackc/pgx/v5"
)

type ApprovalRequest struct {
    UserID           int
    ApprovedAmount   float64
    ApprovalReason   string
    MissingFields    []string
    ConfirmationText string
    ApprovedBy       string
}

// Approve runs the grant approval as a single database transaction.
// Both the grant update and the approval log insert must succeed or both roll back.
func (r *GrantRepository) Approve(ctx context.Context, req ApprovalRequest) error {
    return r.pool.BeginTxFunc(ctx, pgx.TxOptions{}, func(tx pgx.Tx) error {
        // 1. Update the grant status
        _, err := tx.Exec(ctx, `
            UPDATE grants
            SET status = 'Approved',
                approved_amount = $1,
                approval_reason = $2,
                approved_by     = $3,
                approved_at     = $4
            WHERE user_id = $5
        `, req.ApprovedAmount, req.ApprovalReason, req.ApprovedBy,
           time.Now().UTC(), req.UserID)
        if err != nil {
            return fmt.Errorf("update grant: %w", err)
        }

        // 2. Insert the approval log
        _, err = tx.Exec(ctx, `
            INSERT INTO grant_approval_logs
                (grant_id, user_id, approving_authority, action, approved_amount,
                 approval_reason, confirmation_text)
            SELECT grant_id, user_id, $1, 'Approved', $2, $3, $4
            FROM grants WHERE user_id = $5
        `, req.ApprovedBy, req.ApprovedAmount, req.ApprovalReason,
           req.ConfirmationText, req.UserID)
        if err != nil {
            return fmt.Errorf("insert approval log: %w", err)
        }

        return nil
    })
}
```

### Git

```bash
git checkout -b feature/hfc-approval
git commit -m "Add deterministic HFC scoring rules (all 10)"
git commit -m "Store HFC evaluations in database"
git commit -m "Implement grant approval transaction with audit log"
git commit -m "Add approving_authority role check to approve endpoint"
git commit -m "Add HFC shadow mode — scores stored but cannot block approval"
```

---

## Milestone 7: Production Readiness

### Goal

Make it runnable in Docker and maintainable in the field.

### Pre-Flight Checklist Exercise

Before tagging v0.1.0, verify each item:

```bash
# 1. All endpoints exist
curl http://localhost:5000/health
curl http://localhost:5000/api/updates
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"email_address":"test@example.com","password":"test"}'

# 2. Migrations applied
psql postgresql://sme_user:sme_password@localhost:5433/sme_app \
  -c "SELECT version FROM schema_migrations ORDER BY version;"

# 3. Redis working
docker exec sme_redis redis-cli ping
docker exec sme_redis redis-cli keys "peace_sme:*"

# 4. Tests pass
go test -race ./...

# 5. Build succeeds
docker compose build

# 6. Start cleanly
docker compose down -v
docker compose up -d
sleep 5
curl http://localhost:3001/health
```

### Git

```bash
git checkout -b release/v0.1.0
git commit -m "Add production Dockerfile for Go backend"
git commit -m "Add migration runner at server startup"
git commit -m "Add Redis caching for updates, FAQs, and filter options"
git commit -m "Add graceful shutdown on SIGTERM"
git commit -m "Add /health endpoint with PostgreSQL and Redis checks"
git checkout main
git merge release/v0.1.0
git tag -a v0.1.0 -m "First Go and Vue portal milestone"
git push origin main --tags
```

---

## Exercise Set: 20 Practical Challenges

Work through these in any order once the milestones are done.

### Group A: Go Backend

**A1.** Write a middleware that adds a `X-Request-ID` header to every response. The ID should be a UUID if none was provided in the request, or the incoming request ID if one was passed.

**A2.** The `GET /api/admin/reports/filter-options` endpoint should return distinct districts, sectors, and statuses. Implement it with a Redis cache that expires after 120 seconds. Write a test that verifies the cache is populated on first call and returned on second call without hitting the database.

**A3.** Implement the geo-block middleware. It should read `CF-IPCountry` header (set by Cloudflare) or `X-Country-Code` (for local testing), and return 403 if the country is not in `ALLOWED_COUNTRY_CODES`. Admin routes should bypass the check. Write tests for PK (allowed), US (blocked), and missing header (blocked when `GEO_BLOCK_ENABLED=1`).

**A4.** Implement the access slot system: Redis `SETEX` with a 90-second TTL, a UUID session key, and a check that the count of active keys does not exceed `MAX_ACTIVE_APPLICANTS` (300). Return 429 when the limit is reached. Hint: use `SCAN` with a pattern rather than `KEYS` to count slots.

**A5.** Write a function `GenerateQueryToken(adminUsername, secret string) (string, error)` that produces a short-lived (15-minute) JWT for CSV export URLs. Then write `ValidateQueryToken` and tests for both.

**A6.** Implement `POST /api/upload-document/:business_id` as a multipart form handler. It should accept `file` and `document_type` fields, upload to S3 using AWS SDK v2, and store the S3 URL in `business_documents`. Use an interface for the S3 client so you can test with a fake.

**A7.** The FAQ search uses fuzzy matching. Implement a simple trigram similarity function in Go that scores how similar two strings are (0.0–1.0). Use it to rank FAQ results for a query string. Write tests with known expected rankings.

**A8.** Implement the HFC debounce: when a grant is submitted or updated, the system should not immediately run HFC scoring but enqueue a job that runs after 60 seconds of inactivity. Implement this using Redis with a SETEX key named `hfc_debounce:<user_id>`. If the key already exists when a new submission arrives, reset it.

### Group B: Vue Frontend

**B1.** Build the `useLanguage` composable. It should read and write `localStorage.language`, expose `isUrdu` as a computed boolean, and provide a `setLanguage(lang)` function. Components should import this composable instead of reading `localStorage` directly.

```javascript
// Expected API:
const { isUrdu, setLanguage } = useLanguage()
// isUrdu.value === true when localStorage.language === 'urdu'
```

**B2.** Build the `usePagination` composable. It should track `page`, `perPage`, `total`, expose `totalPages`, `hasNext`, `hasPrev`, and `setPage(n)` functions. Show how the admin report table uses it.

**B3.** Add an Axios response interceptor that catches 401 responses, clears `localStorage.userToken`, and redirects to `/login`. Write a test using `vi.mock` (Vitest) to verify the interceptor fires.

**B4.** Build the bilingual grant application form. Create a `translations` object with `en` and `ur` keys for the Applicant Identification section. Use `useLanguage` to switch labels. Test that toggling language in `localStorage` and remounting the component changes the visible labels.

**B5.** Implement the Chart.js admin dashboard. It should show a line chart of registrations per day using the `/api/admin/reports/dashboard-frequency` endpoint. The chart should update when the time range dropdown changes. Handle loading and error states.

### Group C: Architecture and Debugging

**C1.** Draw the complete request flow for `POST /api/grant` as an ASCII architecture diagram. Include: Vue form, Axios, nginx proxy, Go handler, middleware chain, business service, whitelist repository, PostgreSQL, HFC job enqueue, Redis. Show which steps can fail and what HTTP status each failure returns.

**C2.** The following SQL query is very slow on the admin applicant report with 5000 rows. Identify the problem and propose a fix:

```sql
SELECT u.user_id, u.first_name, u.last_name,
       (SELECT COUNT(*) FROM business_documents d WHERE d.user_id = u.user_id) AS doc_count
FROM users u
ORDER BY u.created_at DESC
LIMIT 20 OFFSET 0;
```

**C3.** A user reports that after submitting a grant, the HFC score shows as 0 for 10 minutes, then jumps to 45. Explain why this happens given the system architecture, and write the UI behavior that should handle this (polling or pending state).

**C4.** Code review this handler and identify all problems:

```go
func approveGrant(w http.ResponseWriter, r *http.Request) {
    userID := r.URL.Query().Get("user_id")
    amount := r.URL.Query().Get("amount")
    db.Exec("UPDATE grants SET status='Approved', approved_amount=" + amount +
        " WHERE user_id=" + userID)
    w.Write([]byte("ok"))
}
```

Problems: no auth check, SQL injection via string concatenation, no error handling, no Content-Type header, no transaction with approval log, `amount` and `userID` not validated as numbers.

**C5.** You tag v0.2.0 and deploy. Within 30 minutes, three admins report that the applicant report table shows no results. Walk through your debugging process step by step: logs, health endpoint, Redis, database query, browser network tab.

### Group D: Git

**D1.** Your `feature/hfc-scoring` branch has 12 commits. Before merging to `main`, use interactive rebase to squash the "fix typo" and "add missing import" commits into the commits they fix. Write the commands.

**D2.** A commit on `main` introduced a bug where HFC scores are always 0. You know it worked at tag `v0.1.0`. Use `git bisect` with an automated test to find the exact commit.

**D3.** Create a `.git/hooks/pre-commit` script that runs `go vet ./...` and fails the commit if vet finds issues. Test it by introducing a `go vet` error and verifying the commit is blocked.

---

## Code Review Checklist

Use this before every pull request:

```
Handler
  [ ] Input validated before reaching service layer
  [ ] Auth middleware applied (not checked manually inside handler)
  [ ] Error from service returned correctly (not swallowed)
  [ ] HTTP status code matches the failure type (401/403/404/409/422/500)
  [ ] Response body is JSON with Content-Type header

Service / Business Logic
  [ ] Pure functions are tested independently
  [ ] Business rules match the specification in CLAUDE.md
  [ ] Errors wrapped with context (%w)

Database
  [ ] No string interpolation in SQL — use $1 $2 placeholders
  [ ] Transactions used for multi-table writes
  [ ] Query uses available indexes
  [ ] NULL values handled explicitly

Tests
  [ ] Table-driven where multiple cases exist
  [ ] Mock interfaces, not global state
  [ ] Test covers the unhappy path
  [ ] No t.Skip() left in without a comment

Vue
  [ ] API field names match Go struct JSON tags exactly
  [ ] Empty array returned not null (frontend v-for breaks on null)
  [ ] Token sent as Bearer header on every protected call
  [ ] Error state visible to user (not silently swallowed)

Git
  [ ] One logical change per commit
  [ ] Commit message describes behavior, not file names
  [ ] No generated files committed (dist/, coverage.out)
  [ ] No secrets in diff
```

---

## Mastery Check

You understand this chapter when you can answer:

1. Walk through the complete request path for an admin approving a grant: from clicking the button in the Vue UI, through nginx, the Go handler, the database transaction, the email enqueue, and the response back to the browser.
2. The `financed_items` field is stored as JSONB. What happens if the Go struct and the database column get out of sync? How would you detect this in a test?
3. The admin report has a sort-field allow-list. What attack does this prevent, and why is `strings.Contains` not a safe alternative?
4. Why does the approval endpoint use a database transaction? What would happen if the grant UPDATE succeeded but the approval log INSERT failed without a transaction?
5. Describe the HFC debounce mechanism. Why is a 60-second debounce appropriate for grant form submissions?
