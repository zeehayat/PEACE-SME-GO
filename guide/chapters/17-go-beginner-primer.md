# Chapter 17: Go Beginner Primer Through Portal Features

## Purpose

This chapter is the missing beginner bridge. If you are new to Go, do not start by memorizing syntax. Start by asking: "Where will this Go concept appear in the PEACE SME portal?" Every concept below is paired with a real feature you will build.

## How Go Feels Different From Python or JavaScript

Go is compiled, statically typed, explicit, and intentionally small. That means:

- The compiler checks many mistakes before the program runs.
- You must say what shape data has.
- Errors are returned as values instead of thrown as exceptions.
- Packages are simple directories.
- Concurrency is built into the language through goroutines and channels, but web applications still need careful design.
- Formatting is standardized with `gofmt`.

In Flask, it is common to pass dictionaries around. In Go, you usually define structs. In JavaScript, a field can silently change type. In Go, `GrantRequired float64` cannot suddenly become `"five hundred thousand"` unless you explicitly parse it.

## Concept Map

| Go concept | Portal task | Why it matters |
|---|---|---|
| Variables and constants | allowed districts, status names, cache TTLs | Avoid magic strings scattered through handlers |
| Structs | `User`, `Business`, `Grant`, `AdminUser` | Model request, response, and database shapes |
| Pointers | services, repositories, large structs | Share dependencies without copying them |
| Methods | `UserService.Login`, `GrantRepository.FindByUserID` | Attach behavior to a type |
| Interfaces | `EmailQueue`, `Storage`, `TokenSigner` | Swap real services for test fakes |
| Slices | lists of documents, financed items, admins | Represent ordered collections |
| Maps | allowed country codes, translations, filter allow-lists | Fast lookup by key |
| Errors | config parsing, SQL failures, validation | Make failure explicit and testable |
| Context | request cancellation, identity, database queries | Carry request lifecycle through layers |
| Goroutines | background workers, email sending, HFC jobs | Run work outside the request path |
| Testing | auth rules, grant validation, reports | Protect compatibility while rewriting |

## Variables, Constants, and Types

Theory: A variable stores a value. A constant stores a value known at compile time. Go types are strict.

Application parallel: allowed districts should be constants or a package-level list:

```go
var AllowedDistricts = map[string]bool{
    "Swat":          true,
    "Shangla":       true,
    "Upper Dir":     true,
    "Upper Chitral": true,
    "Lower Chitral": true,
}
```

Beginner rule: use constants for stable single values and maps/slices for groups.

```go
const StatusBlocked = "blocked"
const StatusUnblocked = "unblocked"
```

Project task: create `internal/domain/constants.go` and put user statuses, grant statuses, HFC statuses, risk levels, and allowed districts there.

Git task:

```bash
git checkout -b chapter-17-domain-constants
git add internal/domain
git commit -m "Add domain constants for portal workflow"
```

## Structs

Theory: A struct groups named fields into one type. This is how Go represents application data.

Application parallel: the login response has a specific shape:

```json
{ "token": "jwt", "user_id": 42, "language": "urdu" }
```

Model it:

```go
type LoginResponse struct {
    Token    string `json:"token"`
    UserID   int64  `json:"user_id"`
    Language string `json:"language"`
}
```

The JSON tags are not optional decoration. They preserve the existing frontend contract. Without `json:"user_id"`, Go would output `UserID`, which would break code expecting `user_id`.

Project task: define request and response structs for:

- user login
- admin login
- business create/update
- grant create/update
- paginated report responses

Beginner mistake to avoid: do not use one giant struct for everything. A database row, a create request, and an API response often have different fields.

## Pointers

Theory: A pointer stores the address of a value. Go passes function arguments by value, so without pointers you copy values.

Application parallel: services hold dependencies:

```go
type UserService struct {
    users  *UserRepository
    tokens *TokenService
}
```

You pass pointers because:

- repositories may contain a database pool;
- services should share the same dependency instance;
- methods can avoid copying large values.

Project task: create constructors:

```go
func NewUserService(users *UserRepository, tokens *TokenService) *UserService {
    return &UserService{users: users, tokens: tokens}
}
```

Beginner rule: use values for small immutable data. Use pointers for services, repositories, large structs, and anything that must be modified.

## Methods

Theory: A method is a function attached to a type.

Application parallel: instead of a free function:

```go
func Login(service UserService, email string, password string) {}
```

write:

```go
func (s *UserService) Login(ctx context.Context, req LoginRequest) (*LoginResponse, error) {
    // login behavior
}
```

This reads naturally: "the user service logs in a user."

Project task: implement methods for:

- `UserService.Login`
- `BusinessService.SaveProfile`
- `GrantService.Apply`
- `AdminService.SetUserStatus`
- `HFCService.CalculateForUser`

## Interfaces

Theory: An interface describes behavior. In Go, a type satisfies an interface automatically if it has the required methods.

Application parallel: grant approval must enqueue emails. In tests, you do not want to send real Brevo emails.

```go
type EmailQueue interface {
    EnqueueGrantApproved(ctx context.Context, userID int64) error
    EnqueueApprovalNotification(ctx context.Context, userID int64) error
}
```

The real implementation writes to Redis. The test implementation records calls in memory.

Project task: define interfaces at the package that uses them. If `grant.Service` needs email queue behavior, define the small interface in `internal/grant`, not a giant global interface package.

Beginner rule: accept interfaces, return concrete types.

## Slices

Theory: A slice is a dynamic list.

Application parallel: a grant has financed items:

```go
type FinancedItem struct {
    Item          string  `json:"item"`
    Quantity      int     `json:"quantity"`
    EstimatedCost float64 `json:"estimated_cost"`
}

type GrantRequest struct {
    FinancedItems []FinancedItem `json:"financed_items"`
}
```

Project task: validate that each financed item has a name, positive quantity, and positive cost.

## Maps

Theory: A map is a key-value lookup table.

Application parallel: report sorting must be safe. Never put raw `sort_by` directly into SQL.

```go
var applicantSortColumns = map[string]string{
    "created_at": "u.created_at",
    "district":   "b.business_location_district",
    "status":     "u.status",
}
```

Project task: use map allow-lists for:

- report sort columns
- allowed countries
- allowed districts
- admin roles
- HFC risk bands if helpful

## Errors

Theory: Go functions return errors. You must check them.

Application parallel: login can fail because the request body is invalid, the user is missing, the password is wrong, the user is blocked, or token signing failed.

Do not collapse all errors too early. Inside the service, keep meaningful errors:

```go
var ErrInvalidCredentials = errors.New("invalid credentials")
var ErrUserBlocked = errors.New("user is blocked")
```

The handler converts them into HTTP responses:

```go
switch {
case errors.Is(err, ErrInvalidCredentials):
    httpx.WriteError(w, http.StatusUnauthorized, "invalid_credentials", "Invalid email or password")
case errors.Is(err, ErrUserBlocked):
    httpx.WriteError(w, http.StatusForbidden, "user_blocked", "Your account is blocked")
default:
    httpx.WriteError(w, http.StatusInternalServerError, "server_error", "Unexpected error")
}
```

Project task: define service-level errors for auth, validation, not found, forbidden, and conflict cases.

## Context

Theory: `context.Context` carries cancellation, timeouts, and request-scoped values.

Application parallel: when a browser cancels a report request, the Go handler's context is canceled. Database queries should receive that context so PostgreSQL work can stop too.

```go
func (r *ReportRepository) Applicants(ctx context.Context, filter ApplicantFilter) ([]ApplicantRow, error) {
    rows, err := r.db.Query(ctx, query, args...)
}
```

Project task: every handler should call service methods with `r.Context()`. Every repository method should accept `ctx context.Context`.

## Goroutines and Background Work

Theory: a goroutine is a lightweight concurrent function started with `go`.

Application parallel: HFC scoring and email sending should not block the applicant's grant submission response.

Beginner warning: do not casually start goroutines inside handlers for production-critical work. If the process crashes, the goroutine disappears. Use Redis-backed jobs or an outbox table for reliable work.

Good learning progression:

1. Start with synchronous fake implementations.
2. Add interfaces.
3. Add Redis queue implementation.
4. Add worker process.
5. Add retry and logging.

## Testing

Theory: Go tests live in files ending with `_test.go`.

Application parallel: write table-driven tests for grant validation:

```go
func TestValidateGrantRequest(t *testing.T) {
    tests := []struct {
        name    string
        req     GrantRequest
        wantErr bool
    }{
        {name: "missing amount", req: GrantRequest{}, wantErr: true},
        {name: "valid financed item", req: validGrant(), wantErr: false},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            err := ValidateGrantRequest(tt.req)
            if (err != nil) != tt.wantErr {
                t.Fatalf("expected error=%v, got %v", tt.wantErr, err)
            }
        })
    }
}
```

Project task: create tests for:

- configuration parsing
- JWT signing and verification
- blocked user login
- grant whitelist gate
- HFC risk scoring
- report sort allow-list

## `defer` Statements

Theory: `defer` schedules a function call to execute when the surrounding function returns — whether normally or due to an early `return` or `panic`.

Application parallel: database rows must always be closed after a query, even if scanning fails halfway through:

```go
func (r *Repository) ListFAQs(ctx context.Context) ([]db.FAQ, error) {
    rows, err := r.pool.Query(ctx, "SELECT faq_id, question, answer FROM faqs")
    if err != nil {
        return nil, err
    }
    defer rows.Close() // guaranteed to run, even if Scan() fails below

    var faqs []db.FAQ
    for rows.Next() {
        var f db.FAQ
        if err := rows.Scan(&f.FAQID, &f.Question, &f.Answer); err != nil {
            return nil, err // rows.Close() still runs
        }
        faqs = append(faqs, f)
    }
    return faqs, rows.Err()
}
```

Transaction rollback pattern — defer makes it impossible to forget:

```go
tx, err := pool.Begin(ctx)
if err != nil {
    return err
}
defer tx.Rollback(ctx) // safe no-op if tx.Commit() already succeeded

// ... write to DB ...

return tx.Commit(ctx)
```

Multiple defers run in **LIFO** order (last-in, first-out). The last `defer` statement you write runs first when the function returns.

Project task: every repository method that opens rows must defer `rows.Close()`. Every service method that begins a transaction must defer `tx.Rollback(ctx)`.

---

## Type Assertions and Type Switches

Theory: Go interfaces store a concrete value plus its type. A type assertion extracts the concrete value.

Application parallel: pulling `Identity` from the request context requires a type assertion because `context.Value()` returns `interface{}`:

```go
// Safe form — never panics
func IdentityFromContext(ctx context.Context) (Identity, bool) {
    val, ok := ctx.Value(identityKey{}).(Identity)
    return val, ok
}

// Unsafe form — panics if the assertion fails
identity := ctx.Value(identityKey{}).(Identity) // do NOT use this
```

Always use the two-value form `val, ok := x.(T)` in production code. The panic form is only safe when you control both the set and get of the context value within the same package.

Type switches — when a handler needs to produce different error responses for different error types:

```go
func (h *Handler) Login(w http.ResponseWriter, r *http.Request) {
    resp, err := h.svc.Login(r.Context(), req)
    if err != nil {
        switch {
        case errors.Is(err, user.ErrInvalidCredentials):
            httpx.WriteError(w, 401, "Invalid email or password.")
        case errors.Is(err, user.ErrUserBlocked):
            httpx.WriteError(w, 403, "Account is blocked.")
        default:
            httpx.WriteError(w, 500, "Internal error.")
        }
        return
    }
    httpx.WriteJSON(w, 200, resp)
}
```

`errors.Is` traverses wrapped error chains — it works even if the error was wrapped with `fmt.Errorf("context: %w", ErrInvalidCredentials)`.

---

## Custom Error Types

Theory: `errors.New` creates a simple error. For errors that need to carry additional data (like field validation errors), define an error struct.

Application parallel: validation errors should tell the Vue frontend exactly which fields failed:

```go
// File: internal/httpx/errors.go

// ValidationError carries a map of field name -> error message.
type ValidationError struct {
    Fields map[string]string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation failed: %v", e.Fields)
}

// NewValidationError creates a ValidationError with initial fields.
func NewValidationError(fields map[string]string) *ValidationError {
    return &ValidationError{Fields: fields}
}
```

Service usage:
```go
func validateGrantRequest(req GrantRequest) error {
    errs := map[string]string{}
    if req.GrantRequired <= 0 {
        errs["grant_required"] = "Grant amount must be greater than zero."
    }
    if len(req.ExpressionOfInterest) == 0 && !req.WorkingCapital {
        errs["expression_of_interest"] = "Select at least one purpose or check working capital."
    }
    if req.ApplicationDate == "" {
        errs["application_date"] = "Application date is required."
    }
    if len(errs) > 0 {
        return httpx.NewValidationError(errs)
    }
    return nil
}
```

Handler extracts the specific error type:
```go
var ve *httpx.ValidationError
if errors.As(err, &ve) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusBadRequest)
    json.NewEncoder(w).Encode(map[string]interface{}{
        "message": "Validation failed.",
        "fields":  ve.Fields,
    })
    return
}
```

---

## Embedded Structs

Theory: Go has no classes or inheritance. Embedding lets one struct include another struct's fields and methods directly.

Application parallel: Admin and Committee tokens both carry `exp` and other JWT claims via embedding `jwt.RegisteredClaims`:

```go
type UserClaims struct {
    UserID int64 `json:"user_id"`
    jwt.RegisteredClaims // embedded — UserClaims gets .ExpiresAt, .IssuedAt, etc.
}

type AdminClaims struct {
    AdminUsername string `json:"admin_username"`
    Role          string `json:"role"`
    IsAdmin       bool   `json:"is_admin"`
    IsApprover    bool   `json:"is_approver"`
    jwt.RegisteredClaims // same embedding
}
```

Because of embedding, `UserClaims` automatically satisfies `jwt.Claims` interface — no explicit method implementations needed.

Field promotion: if you access `claims.ExpiresAt`, Go looks for `ExpiresAt` on `UserClaims` first, then on the embedded `RegisteredClaims`. You do not need `claims.RegisteredClaims.ExpiresAt`.

---

## Structured Logging with `log/slog`

Theory: `fmt.Println` and `log.Printf` produce unstructured text. In production, you need structured logs — JSON lines that monitoring systems can parse, filter, and alert on.

Go 1.21 introduced `log/slog` as the standard structured logger.

Application parallel: every HTTP request should log method, path, status, duration, and user identity when available:

```go
// File: internal/middleware/logging.go
package middleware

import (
    "log/slog"
    "net/http"
    "time"
)

func Logger(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        wrapped := &statusWriter{ResponseWriter: w, status: 200}

        next.ServeHTTP(wrapped, r)

        slog.Info("request",
            "method",   r.Method,
            "path",     r.URL.Path,
            "status",   wrapped.status,
            "duration", time.Since(start).Milliseconds(),
            "ip",       r.RemoteAddr,
        )
    })
}

// statusWriter wraps http.ResponseWriter to capture the status code.
type statusWriter struct {
    http.ResponseWriter
    status int
}

func (sw *statusWriter) WriteHeader(code int) {
    sw.status = code
    sw.ResponseWriter.WriteHeader(code)
}
```

Configure JSON output in `main.go`:
```go
slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
    Level: slog.LevelInfo,
})))
```

**What NOT to log:**
- Passwords or password hashes
- JWT token strings
- CNIC numbers (PII under Pakistani law)
- Full request bodies on auth endpoints

---

## Graceful Shutdown

Theory: when Docker Compose stops a container, it sends `SIGTERM` to PID 1. A server that does not handle this signal will be killed mid-request, potentially leaving in-flight grant submissions incomplete.

Application parallel: during a cutover deployment, the Go server gets `SIGTERM` — graceful shutdown lets the HFC scorer finish its current calculation and active applicants' form submissions complete before the process exits.

```go
// File: cmd/server/main.go

package main

import (
    "context"
    "fmt"
    "log/slog"
    "net/http"
    "os"
    "os/signal"
    "syscall"
    "time"

    "peace-sme-go/internal/app"
    "peace-sme-go/internal/config"
)

func main() {
    cfg, err := config.Load()
    if err != nil {
        slog.Error("config load failed", "error", err)
        os.Exit(1)
    }

    application, err := app.New(cfg)
    if err != nil {
        slog.Error("app init failed", "error", err)
        os.Exit(1)
    }

    server := &http.Server{
        Addr:         fmt.Sprintf("0.0.0.0:%d", cfg.Port),
        Handler:      application.Router(),
        ReadTimeout:  30 * time.Second,
        WriteTimeout: 120 * time.Second, // bulk HTML reports can take up to 30s
        IdleTimeout:  120 * time.Second,
    }

    // Start listening in a goroutine so main can block on signal
    go func() {
        slog.Info("server started", "addr", server.Addr)
        if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
            slog.Error("server listen failed", "error", err)
            os.Exit(1)
        }
    }()

    // Block until SIGINT or SIGTERM
    quit := make(chan os.Signal, 1)
    signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
    <-quit

    slog.Info("shutdown signal received, draining connections...")

    // Give in-flight requests up to 30 seconds to finish
    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()

    if err := server.Shutdown(ctx); err != nil {
        slog.Error("graceful shutdown failed", "error", err)
    }

    slog.Info("server stopped cleanly")
}
```

---

## `sync.Once` for One-Time Initialization

Theory: `sync.Once` guarantees a function runs exactly once, even under concurrent access. Unlike `init()`, it runs lazily — only when needed — and uses the `sync` package's safe initialization guarantee.

Application parallel: HFC rule weights are loaded from the `hfc_rule_config` database table. They do not change at runtime. Loading them once saves a database round-trip on every scoring calculation:

```go
// File: internal/hfc/config.go
package hfc

import (
    "context"
    "sync"
)

type RuleWeights struct {
    DuplicateCNIC      int
    DuplicateEmail     int
    MissingBusiness    int
    MissingDocuments   int
    OutOfScopeDistrict int
    // ... all rules
}

var (
    weights     RuleWeights
    weightsOnce sync.Once
)

// LoadWeights loads rule weights exactly once. Safe for concurrent callers.
func LoadWeights(ctx context.Context, repo *Repository) error {
    var loadErr error
    weightsOnce.Do(func() {
        w, err := repo.GetRuleWeights(ctx)
        if err != nil {
            loadErr = err
            return
        }
        weights = *w
    })
    return loadErr
}

func GetWeights() RuleWeights {
    return weights
}
```

---

## Complete Vertical Slice: User Profile

Here is every layer for `GET /api/user/profile` — from database to HTTP to test:

### Repository

```go
// internal/user/repository.go
func (r *Repository) FindByID(ctx context.Context, userID int64) (*db.User, error) {
    const q = `
        SELECT user_id, email_address, first_name, last_name,
               cnic, language, gender, mobile_no, status, created_at
        FROM users WHERE user_id = $1`
    row := r.pool.QueryRow(ctx, q, userID)
    var u db.User
    if err := row.Scan(&u.UserID, &u.EmailAddress, &u.FirstName, &u.LastName,
        &u.CNIC, &u.Language, &u.Gender, &u.MobileNo, &u.Status, &u.CreatedAt); err != nil {
        if err == pgx.ErrNoRows {
            return nil, nil
        }
        return nil, fmt.Errorf("FindByID: %w", err)
    }
    return &u, nil
}
```

### Service

```go
// internal/user/service.go
type ProfileResponse struct {
    UserID       int64  `json:"user_id"`
    EmailAddress string `json:"email_address"`
    FirstName    string `json:"first_name"`
    LastName     string `json:"last_name"`
    CNIC         string `json:"cnic"`
    Language     string `json:"language"`
    Status       string `json:"status"`
}

func (s *Service) GetProfile(ctx context.Context, userID int64) (*ProfileResponse, error) {
    u, err := s.repo.FindByID(ctx, userID)
    if err != nil {
        return nil, err
    }
    if u == nil {
        return nil, ErrUserNotFound
    }
    return &ProfileResponse{
        UserID:       u.UserID,
        EmailAddress: u.EmailAddress,
        FirstName:    u.FirstName.String,
        LastName:     u.LastName.String,
        CNIC:         u.CNIC.String,
        Language:     u.Language.String,
        Status:       u.Status,
    }, nil
}
```

### Handler

```go
// internal/user/handler.go
func (h *Handler) Profile(w http.ResponseWriter, r *http.Request) {
    identity, ok := middleware.IdentityFromContext(r.Context())
    if !ok {
        httpx.WriteError(w, http.StatusUnauthorized, "Not authenticated.")
        return
    }
    profile, err := h.svc.GetProfile(r.Context(), identity.UserID)
    if err != nil {
        if errors.Is(err, ErrUserNotFound) {
            httpx.WriteError(w, http.StatusNotFound, "User not found.")
            return
        }
        httpx.WriteError(w, http.StatusInternalServerError, "Internal error.")
        return
    }
    httpx.WriteJSON(w, http.StatusOK, profile)
}
```

### Test

```go
// internal/user/handler_test.go
func TestProfile_Success(t *testing.T) {
    // Stub service that returns a known profile
    svc := &stubUserService{
        profile: &ProfileResponse{UserID: 42, EmailAddress: "a@test.com", Status: "unblocked"},
    }
    h := NewHandler(svc)

    req := httptest.NewRequest(http.MethodGet, "/api/user/profile", nil)
    // Inject identity into context (simulating auth middleware)
    req = req.WithContext(middleware.WithIdentity(req.Context(), middleware.Identity{UserID: 42}))
    rr := httptest.NewRecorder()

    h.Profile(rr, req)

    if rr.Code != http.StatusOK {
        t.Fatalf("expected 200, got %d", rr.Code)
    }
    var resp ProfileResponse
    json.NewDecoder(rr.Body).Decode(&resp)
    if resp.UserID != 42 {
        t.Errorf("expected user_id 42, got %d", resp.UserID)
    }
}
```

When this complete slice works, you have practiced: structs, pointers, methods, interfaces, errors, context, type assertions, defer, SQL, httptest, and table-driven tests — all in a single feature.

---

## Capstone Exercise

Build a tiny vertical slice:

1. Define `LoginRequest` and `LoginResponse`.
2. Implement `UserRepository.FindByEmail`.
3. Implement `UserService.Login`.
4. Implement `POST /api/login`.
5. Add a Vue login form that stores `userToken`.
6. Commit each layer separately.

When this works, you have practiced structs, methods, pointers, interfaces, errors, context, JSON, SQL, Vue state, and Git.

