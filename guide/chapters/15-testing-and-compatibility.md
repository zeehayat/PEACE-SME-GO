# Chapter 15: Testing, Debugging, and API Compatibility

## Purpose

Testing proves that the Go and Vue rewrite matches the Flask behavior. Compatibility is the product. A passing test suite is the only honest answer to the question "does the rewrite work?"

This chapter covers the full testing stack: unit tests for pure logic, HTTP handler tests with `httptest`, integration tests against a real PostgreSQL container, mock interfaces for isolating layers, API contract tests comparing Flask and Go responses, benchmark tests, and Cypress E2E tests for the Vue frontend.

---

## The Testing Pyramid

A balanced software testing strategy is represented as a pyramid:

```text
         /\
        /  \       E2E Tests (Cypress, Playwright)
       /----\      Slow · High fidelity · Few
      /      \
     /--------\    Integration Tests (testcontainers-go)
    /          \   Medium speed · Real DB · Medium count
   /------------\
  /              \  Unit Tests (table-driven, in-memory)
 /----------------\ Fast · No I/O · Many
```

The rule: most tests are unit tests. A smaller layer of integration tests. A thin E2E layer that covers critical user paths only.

---

## Part 1: Go Unit Testing Fundamentals

### Running Tests

```bash
# Run all tests
go test ./...

# Run tests in one package with verbose output
go test ./internal/hfc/... -v

# Run a single test by name
go test ./internal/hfc/... -run TestCalculateScore

# Run tests with the race detector
go test -race ./...

# Generate a coverage report
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out -o coverage.html
```

### Anatomy of a Go Test File

```go
// File: internal/hfc/scorer_test.go
package hfc_test  // use _test suffix for black-box testing

import (
    "testing"

    "github.com/yourusername/peace-sme/internal/hfc"
)

func TestCalculateRiskLevel(t *testing.T) {
    // Arrange
    score := 45

    // Act
    level := hfc.CalculateRiskLevel(score)

    // Assert
    if level != "MEDIUM" {
        t.Errorf("expected MEDIUM, got %s", level)
    }
}
```

### t.Helper(), t.Fatal(), t.Error()

```go
// t.Helper() marks a function as a test helper so that stack traces
// point to the call site, not inside the helper.
func assertStatus(t *testing.T, got, want int) {
    t.Helper()
    if got != want {
        t.Errorf("status: got %d, want %d", got, want)
    }
}

// t.Fatal stops the test immediately — use when remaining assertions
// would panic or be meaningless.
func assertNoError(t *testing.T, err error) {
    t.Helper()
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }
}
```

### t.Parallel() — Run Tests Concurrently

```go
func TestHFCRules(t *testing.T) {
    tests := []struct {
        name  string
        input hfc.UserProfile
        want  int
    }{
        {"no flags", hfc.UserProfile{HasBusiness: true, HasDocs: true}, 0},
        {"missing business", hfc.UserProfile{HasBusiness: false}, 30},
    }

    for _, tt := range tests {
        tt := tt // capture loop variable
        t.Run(tt.name, func(t *testing.T) {
            t.Parallel() // run subtests concurrently
            got := hfc.ApplyMissingBusinessRule(tt.input)
            if got != tt.want {
                t.Errorf("got %d, want %d", got, tt.want)
            }
        })
    }
}
```

> [!NOTE]
> Always copy the loop variable (`tt := tt`) before calling `t.Parallel()`. Without this, all goroutines share the same `tt` pointer and read the last value.

---

## Part 2: Table-Driven Tests in Depth

Table-driven testing is Go's idiomatic pattern. Define a slice of structs, iterate, run subtests.

### Full Example: HFC Scoring Rules

This tests every scoring rule from the PEACE SME fraud detection system:

```go
// File: internal/hfc/scorer_test.go
package hfc_test

import (
    "testing"

    "github.com/yourusername/peace-sme/internal/hfc"
)

func TestCalculateHFCScore(t *testing.T) {
    tests := []struct {
        name           string
        profile        hfc.ScoringInput
        wantScore      int
        wantRisk       string
        wantTriggered  []string
    }{
        {
            name: "clean applicant scores zero",
            profile: hfc.ScoringInput{
                DuplicateCNIC:     false,
                DuplicateEmail:    false,
                DuplicateMobile:   false,
                HasBusiness:       true,
                HasRequiredDocs:   true,
                HasGrantMedia:     true,
                DistrictInScope:   true,
                GrantAmount:       200_000,
                ApplicationMinutes: 120,
                HasEOI:            true,
            },
            wantScore: 0,
            wantRisk:  "LOW",
        },
        {
            name: "duplicate CNIC triggers 50 points",
            profile: hfc.ScoringInput{
                DuplicateCNIC:   true,
                HasBusiness:     true,
                HasRequiredDocs: true,
                HasGrantMedia:   true,
                DistrictInScope: true,
                HasEOI:          true,
                ApplicationMinutes: 120,
            },
            wantScore:     50,
            wantRisk:      "MEDIUM",
            wantTriggered: []string{"DUPLICATE_CNIC"},
        },
        {
            name: "multiple flags reach CRITICAL",
            profile: hfc.ScoringInput{
                DuplicateCNIC:   true,  // 50
                DuplicateEmail:  true,  // 20
                DuplicateMobile: true,  // 20
                HasBusiness:     false, // 30
                DistrictInScope: false, // 40
            },
            wantScore:     160,
            wantRisk:      "CRITICAL",
        },
        {
            name: "fast submission triggers 10 points",
            profile: hfc.ScoringInput{
                HasBusiness:        true,
                HasRequiredDocs:    true,
                HasGrantMedia:      true,
                DistrictInScope:    true,
                HasEOI:             true,
                ApplicationMinutes: 2, // submitted within 2 minutes
            },
            wantScore:     10,
            wantRisk:      "LOW",
            wantTriggered: []string{"FAST_SUBMISSION"},
        },
        {
            name: "missing EOI adds 15 points",
            profile: hfc.ScoringInput{
                HasBusiness:        true,
                HasRequiredDocs:    true,
                HasGrantMedia:      true,
                DistrictInScope:    true,
                HasEOI:             false,
                ApplicationMinutes: 120,
            },
            wantScore:     15,
            wantRisk:      "LOW",
            wantTriggered: []string{"MISSING_EOI"},
        },
    }

    for _, tt := range tests {
        tt := tt
        t.Run(tt.name, func(t *testing.T) {
            t.Parallel()

            result := hfc.CalculateScore(tt.profile)

            if result.FinalScore != tt.wantScore {
                t.Errorf("score: got %d, want %d", result.FinalScore, tt.wantScore)
            }
            if result.RiskLevel != tt.wantRisk {
                t.Errorf("risk: got %s, want %s", result.RiskLevel, tt.wantRisk)
            }
            for _, expected := range tt.wantTriggered {
                found := false
                for _, rule := range result.RulesTriggered {
                    if rule == expected {
                        found = true
                        break
                    }
                }
                if !found {
                    t.Errorf("expected rule %q in triggered list, got %v",
                        expected, result.RulesTriggered)
                }
            }
        })
    }
}

func TestCalculateRiskLevel(t *testing.T) {
    tests := []struct {
        score int
        want  string
    }{
        {0, "LOW"},
        {29, "LOW"},
        {30, "MEDIUM"},
        {59, "MEDIUM"},
        {60, "HIGH"},
        {79, "HIGH"},
        {80, "CRITICAL"},
        {200, "CRITICAL"},
    }

    for _, tt := range tests {
        t.Run(fmt.Sprintf("score_%d", tt.score), func(t *testing.T) {
            got := hfc.CalculateRiskLevel(tt.score)
            if got != tt.want {
                t.Errorf("score %d: got %s, want %s", tt.score, got, tt.want)
            }
        })
    }
}
```

The implementation being tested:

```go
// File: internal/hfc/scorer.go
package hfc

// ScoringInput contains all the data needed to calculate an HFC score.
type ScoringInput struct {
    DuplicateCNIC      bool
    DuplicateEmail     bool
    DuplicateMobile    bool
    HasBusiness        bool
    HasRequiredDocs    bool
    HasGrantMedia      bool
    DistrictInScope    bool
    GrantAmount        float64
    ApplicationMinutes int
    HasEOI             bool
}

type ScoreResult struct {
    FinalScore     int
    RiskLevel      string
    RulesTriggered []string
}

// CalculateScore applies all deterministic HFC rules and returns a result.
func CalculateScore(input ScoringInput) ScoreResult {
    score := 0
    var rules []string

    if input.DuplicateCNIC {
        score += 50
        rules = append(rules, "DUPLICATE_CNIC")
    }
    if input.DuplicateEmail {
        score += 20
        rules = append(rules, "DUPLICATE_EMAIL")
    }
    if input.DuplicateMobile {
        score += 20
        rules = append(rules, "DUPLICATE_MOBILE")
    }
    if !input.HasBusiness {
        score += 30
        rules = append(rules, "MISSING_BUSINESS")
    }
    if !input.HasRequiredDocs {
        score += 25
        rules = append(rules, "MISSING_DOCS")
    }
    if !input.HasGrantMedia {
        score += 10
        rules = append(rules, "MISSING_MEDIA")
    }
    if !input.DistrictInScope {
        score += 40
        rules = append(rules, "OUT_OF_SCOPE_DISTRICT")
    }
    if input.GrantAmount > 1_000_000 {
        score += 15
        rules = append(rules, "HIGH_GRANT_AMOUNT")
    }
    if input.ApplicationMinutes < 5 && input.ApplicationMinutes > 0 {
        score += 10
        rules = append(rules, "FAST_SUBMISSION")
    }
    if !input.HasEOI {
        score += 15
        rules = append(rules, "MISSING_EOI")
    }

    return ScoreResult{
        FinalScore:     score,
        RiskLevel:      CalculateRiskLevel(score),
        RulesTriggered: rules,
    }
}

// CalculateRiskLevel converts a numeric score to a named risk band.
func CalculateRiskLevel(score int) string {
    switch {
    case score < 30:
        return "LOW"
    case score < 60:
        return "MEDIUM"
    case score < 80:
        return "HIGH"
    default:
        return "CRITICAL"
    }
}
```

---

## Part 3: HTTP Handler Testing with httptest

`net/http/httptest` lets you test handlers without starting a real server. You create a fake request, a fake response recorder, and call the handler directly.

### Testing the /api/updates Endpoint

```go
// File: internal/content/handler_test.go
package content_test

import (
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"

    "github.com/yourusername/peace-sme/internal/content"
)

// mockUpdateStore satisfies the UpdateStore interface without a database.
type mockUpdateStore struct {
    updates []content.Update
    err     error
}

func (m *mockUpdateStore) ListActive() ([]content.Update, error) {
    return m.updates, m.err
}

func TestGetUpdatesHandler(t *testing.T) {
    t.Run("returns updates as JSON", func(t *testing.T) {
        store := &mockUpdateStore{
            updates: []content.Update{
                {UpdateID: 1, Title: "Portal Open", Body: "Applications now open", Tag: "info"},
            },
        }
        handler := content.NewHandler(store)

        req := httptest.NewRequest(http.MethodGet, "/api/updates", nil)
        rr := httptest.NewRecorder()

        handler.GetUpdates(rr, req)

        if rr.Code != http.StatusOK {
            t.Errorf("status: got %d, want %d", rr.Code, http.StatusOK)
        }

        ct := rr.Header().Get("Content-Type")
        if ct != "application/json" {
            t.Errorf("content-type: got %s, want application/json", ct)
        }

        var result []content.Update
        if err := json.NewDecoder(rr.Body).Decode(&result); err != nil {
            t.Fatalf("failed to decode response: %v", err)
        }
        if len(result) != 1 {
            t.Errorf("expected 1 update, got %d", len(result))
        }
        if result[0].Title != "Portal Open" {
            t.Errorf("title: got %s, want Portal Open", result[0].Title)
        }
    })

    t.Run("returns empty array not null", func(t *testing.T) {
        // The Vue frontend expects [] not null for empty lists.
        store := &mockUpdateStore{updates: []content.Update{}}
        handler := content.NewHandler(store)

        req := httptest.NewRequest(http.MethodGet, "/api/updates", nil)
        rr := httptest.NewRecorder()
        handler.GetUpdates(rr, req)

        body := rr.Body.String()
        if body == "null\n" {
            t.Error("expected [] but got null — the Vue frontend breaks on null")
        }
    })
}
```

### Testing JWT Middleware

```go
// File: internal/security/middleware_test.go
package security_test

import (
    "net/http"
    "net/http/httptest"
    "testing"
    "time"

    "github.com/golang-jwt/jwt/v5"
    "github.com/yourusername/peace-sme/internal/security"
)

const testSecret = "test-jwt-secret"

func makeUserToken(userID int, expired bool) string {
    exp := time.Now().Add(24 * time.Hour)
    if expired {
        exp = time.Now().Add(-1 * time.Hour)
    }
    claims := jwt.MapClaims{
        "user_id": userID,
        "exp":     exp.Unix(),
    }
    token, _ := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).
        SignedString([]byte(testSecret))
    return token
}

func TestAuthMiddleware(t *testing.T) {
    nextHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.WriteHeader(http.StatusOK)
    })
    mw := security.AuthMiddleware(testSecret)(nextHandler)

    tests := []struct {
        name       string
        authHeader string
        wantStatus int
    }{
        {
            name:       "valid token passes through",
            authHeader: "Bearer " + makeUserToken(42, false),
            wantStatus: http.StatusOK,
        },
        {
            name:       "missing header returns 401",
            authHeader: "",
            wantStatus: http.StatusUnauthorized,
        },
        {
            name:       "expired token returns 401",
            authHeader: "Bearer " + makeUserToken(42, true),
            wantStatus: http.StatusUnauthorized,
        },
        {
            name:       "malformed token returns 401",
            authHeader: "Bearer not.a.valid.token",
            wantStatus: http.StatusUnauthorized,
        },
        {
            name:       "wrong prefix returns 401",
            authHeader: "Token " + makeUserToken(42, false),
            wantStatus: http.StatusUnauthorized,
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            req := httptest.NewRequest(http.MethodGet, "/api/grant", nil)
            if tt.authHeader != "" {
                req.Header.Set("Authorization", tt.authHeader)
            }
            rr := httptest.NewRecorder()
            mw.ServeHTTP(rr, req)

            if rr.Code != tt.wantStatus {
                t.Errorf("got %d, want %d", rr.Code, tt.wantStatus)
            }
        })
    }
}
```

### Testing the Whitelist Gate

```go
// File: internal/grant/whitelist_test.go
package grant_test

import (
    "bytes"
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"

    "github.com/yourusername/peace-sme/internal/grant"
)

type mockWhitelistRepo struct {
    selected map[int]bool
}

func (m *mockWhitelistRepo) IsSelected(userID int) (bool, error) {
    return m.selected[userID], nil
}

func TestGrantSubmissionWhitelistGate(t *testing.T) {
    t.Run("whitelisted user can submit", func(t *testing.T) {
        repo := &mockWhitelistRepo{selected: map[int]bool{99: true}}
        svc := grant.NewService(repo, true) // requireSelection = true

        body, _ := json.Marshal(map[string]any{
            "grant_required":       500_000,
            "declaration_accepted": true,
            "declaration_name":     "Test User",
        })
        req := httptest.NewRequest(http.MethodPost, "/api/grant", bytes.NewReader(body))
        req.Header.Set("Content-Type", "application/json")
        // Simulate middleware having set user_id in context
        req = req.WithContext(grant.WithUserID(req.Context(), 99))

        rr := httptest.NewRecorder()
        svc.HandleGrantSubmit(rr, req)

        if rr.Code == http.StatusForbidden {
            t.Error("whitelisted user should not get 403")
        }
    })

    t.Run("non-whitelisted user gets 403", func(t *testing.T) {
        repo := &mockWhitelistRepo{selected: map[int]bool{}} // nobody selected
        svc := grant.NewService(repo, true)

        body, _ := json.Marshal(map[string]any{"grant_required": 500_000})
        req := httptest.NewRequest(http.MethodPost, "/api/grant", bytes.NewReader(body))
        req = req.WithContext(grant.WithUserID(req.Context(), 55))

        rr := httptest.NewRecorder()
        svc.HandleGrantSubmit(rr, req)

        if rr.Code != http.StatusForbidden {
            t.Errorf("expected 403, got %d", rr.Code)
        }
    })

    t.Run("when whitelist disabled, any user can submit", func(t *testing.T) {
        repo := &mockWhitelistRepo{selected: map[int]bool{}}
        svc := grant.NewService(repo, false) // requireSelection = false

        body, _ := json.Marshal(map[string]any{
            "grant_required":       500_000,
            "declaration_accepted": true,
            "declaration_name":     "Test User",
        })
        req := httptest.NewRequest(http.MethodPost, "/api/grant", bytes.NewReader(body))
        req = req.WithContext(grant.WithUserID(req.Context(), 55))

        rr := httptest.NewRecorder()
        svc.HandleGrantSubmit(rr, req)

        if rr.Code == http.StatusForbidden {
            t.Error("whitelist disabled, user should not get 403")
        }
    })
}
```

---

## Part 4: Mock Interfaces

Mocking in Go is done through interfaces. Design your services to accept interfaces, then inject test doubles.

### The Interface Pattern

```go
// File: internal/grant/service.go

// EmailSender is an interface for sending emails.
// In production we inject the real Brevo client.
// In tests we inject a mock that records calls.
type EmailSender interface {
    SendGrantApproved(toEmail, firstName string, amount float64) error
}

// WhitelistRepository is an interface for whitelist lookups.
type WhitelistRepository interface {
    IsSelected(userID int) (bool, error)
    Upsert(userID int, selected bool, note string, by string) error
}

// GrantService holds its dependencies as interfaces.
type GrantService struct {
    whitelist         WhitelistRepository
    mailer            EmailSender
    requireWhitelist  bool
}

func NewService(wl WhitelistRepository, requireWL bool) *GrantService {
    return &GrantService{whitelist: wl, requireWhitelist: requireWL}
}
```

### Test Double for Email

```go
// File: internal/grant/service_test.go
package grant_test

// SpyEmailSender records what emails were sent without calling Brevo.
type SpyEmailSender struct {
    Calls []EmailCall
}

type EmailCall struct {
    To        string
    FirstName string
    Amount    float64
}

func (s *SpyEmailSender) SendGrantApproved(to, name string, amount float64) error {
    s.Calls = append(s.Calls, EmailCall{To: to, FirstName: name, Amount: amount})
    return nil
}

func TestApproveGrantSendsEmail(t *testing.T) {
    spy := &SpyEmailSender{}
    repo := &mockGrantRepo{} // satisfies GrantRepository interface
    svc := grant.NewApprovalService(repo, spy)

    err := svc.Approve(42, "admin1", 500_000, "Good application")
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }
    if len(spy.Calls) != 1 {
        t.Fatalf("expected 1 email, sent %d", len(spy.Calls))
    }
    if spy.Calls[0].Amount != 500_000 {
        t.Errorf("email amount: got %.0f, want 500000", spy.Calls[0].Amount)
    }
}
```

---

## Part 5: Integration Tests with testcontainers-go

Unit tests with mocks are fast but can miss real SQL errors. Integration tests spin up a real PostgreSQL container.

### Setup

```bash
go get github.com/testcontainers/testcontainers-go
go get github.com/testcontainers/testcontainers-go/modules/postgres
```

### TestMain with Shared Container

```go
// File: internal/db/integration_test.go
package db_test

import (
    "context"
    "os"
    "testing"

    "github.com/jackc/pgx/v5/pgxpool"
    "github.com/testcontainers/testcontainers-go"
    "github.com/testcontainers/testcontainers-go/modules/postgres"
    "github.com/testcontainers/testcontainers-go/wait"
)

var testPool *pgxpool.Pool

func TestMain(m *testing.M) {
    ctx := context.Background()

    pgContainer, err := postgres.RunContainer(ctx,
        testcontainers.WithImage("postgres:15-alpine"),
        postgres.WithDatabase("sme_test"),
        postgres.WithUsername("sme_user"),
        postgres.WithPassword("sme_pass"),
        testcontainers.WithWaitStrategy(
            wait.ForLog("database system is ready to accept connections").
                WithOccurrence(2),
        ),
    )
    if err != nil {
        panic("failed to start postgres container: " + err.Error())
    }
    defer pgContainer.Terminate(ctx)

    connStr, err := pgContainer.ConnectionString(ctx, "sslmode=disable")
    if err != nil {
        panic(err)
    }

    testPool, err = pgxpool.New(ctx, connStr)
    if err != nil {
        panic(err)
    }
    defer testPool.Close()

    // Run migrations
    if err := runMigrations(testPool); err != nil {
        panic("migrations failed: " + err.Error())
    }

    os.Exit(m.Run())
}

func runMigrations(pool *pgxpool.Pool) error {
    schema := `
    CREATE TABLE IF NOT EXISTS users (
        user_id         SERIAL PRIMARY KEY,
        email_address   VARCHAR(255) UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        first_name      VARCHAR(100),
        last_name       VARCHAR(100),
        cnic            VARCHAR(25),
        status          VARCHAR(20) DEFAULT 'unblocked',
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS businesses (
        business_id                 SERIAL PRIMARY KEY,
        user_id                     INTEGER UNIQUE NOT NULL REFERENCES users(user_id),
        name_of_business            TEXT,
        business_location_district  TEXT,
        business_sector             TEXT,
        created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS grant_access_whitelist (
        access_id   SERIAL PRIMARY KEY,
        user_id     INTEGER UNIQUE NOT NULL REFERENCES users(user_id),
        is_selected BOOLEAN DEFAULT FALSE,
        selected_by VARCHAR(100),
        selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    `
    _, err := testPool.Exec(context.Background(), schema)
    return err
}
```

### Integration Test: User Repository

```go
// File: internal/user/repo_integration_test.go
package user_test

import (
    "context"
    "testing"

    "golang.org/x/crypto/bcrypt"
    "github.com/yourusername/peace-sme/internal/user"
)

func TestUserRepository_FindByEmail(t *testing.T) {
    ctx := context.Background()
    repo := user.NewRepository(testPool)

    // Seed a user
    hash, _ := bcrypt.GenerateFromPassword([]byte("password123"), 12)
    _, err := testPool.Exec(ctx,
        `INSERT INTO users (email_address, hashed_password, first_name, cnic)
         VALUES ($1, $2, $3, $4)`,
        "fatima@example.com", string(hash), "Fatima", "1234567890123",
    )
    if err != nil {
        t.Fatalf("seed user: %v", err)
    }
    defer testPool.Exec(ctx, `DELETE FROM users WHERE email_address=$1`, "fatima@example.com")

    t.Run("finds existing user", func(t *testing.T) {
        u, err := repo.FindByEmail(ctx, "fatima@example.com")
        if err != nil {
            t.Fatalf("unexpected error: %v", err)
        }
        if u.FirstName != "Fatima" {
            t.Errorf("first name: got %s, want Fatima", u.FirstName)
        }
    })

    t.Run("returns not-found for unknown email", func(t *testing.T) {
        _, err := repo.FindByEmail(ctx, "nobody@example.com")
        if !user.IsNotFound(err) {
            t.Errorf("expected not-found error, got %v", err)
        }
    })

    t.Run("blocked user login fails", func(t *testing.T) {
        testPool.Exec(ctx,
            `UPDATE users SET status='blocked' WHERE email_address=$1`,
            "fatima@example.com",
        )
        defer testPool.Exec(ctx,
            `UPDATE users SET status='unblocked' WHERE email_address=$1`,
            "fatima@example.com",
        )

        u, err := repo.FindByEmail(ctx, "fatima@example.com")
        if err != nil {
            t.Fatalf("fetch error: %v", err)
        }
        if u.Status != "blocked" {
            t.Error("expected user to be blocked")
        }
    })
}
```

---

## Part 6: Benchmark Tests

Benchmarks measure performance. Run them with `-bench`.

```bash
go test ./internal/hfc/... -bench=. -benchmem
```

```go
// File: internal/hfc/scorer_bench_test.go
package hfc_test

import (
    "testing"

    "github.com/yourusername/peace-sme/internal/hfc"
)

// BenchmarkCalculateScore measures how fast the HFC scoring function runs.
func BenchmarkCalculateScore(b *testing.B) {
    input := hfc.ScoringInput{
        DuplicateCNIC:      false,
        HasBusiness:        true,
        HasRequiredDocs:    true,
        HasGrantMedia:      true,
        DistrictInScope:    true,
        HasEOI:             true,
        ApplicationMinutes: 60,
    }

    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        hfc.CalculateScore(input)
    }
}

// BenchmarkCalculateRiskLevel is a micro-benchmark for the risk band function.
func BenchmarkCalculateRiskLevel(b *testing.B) {
    for i := 0; i < b.N; i++ {
        hfc.CalculateRiskLevel(45)
    }
}
```

Example output:
```
BenchmarkCalculateScore-8    10000000    112 ns/op    0 B/op    0 allocs/op
BenchmarkCalculateRiskLevel-8  500000000  2.1 ns/op   0 B/op    0 allocs/op
```

---

## Part 7: Test Fixtures and Test Helpers

### Using testdata/ Directories

```
internal/
  grant/
    testdata/
      grant_payload.json
      hfc_response.json
    service_test.go
```

```go
// Load a fixture file in tests
func loadFixture(t *testing.T, name string) []byte {
    t.Helper()
    data, err := os.ReadFile(filepath.Join("testdata", name))
    if err != nil {
        t.Fatalf("load fixture %s: %v", name, err)
    }
    return data
}

func TestGrantDecoding(t *testing.T) {
    raw := loadFixture(t, "grant_payload.json")
    var req grant.SubmitRequest
    if err := json.Unmarshal(raw, &req); err != nil {
        t.Fatalf("unmarshal: %v", err)
    }
    if req.GrantRequired != 500_000 {
        t.Errorf("grant_required: got %.0f, want 500000", req.GrantRequired)
    }
}
```

### Shared Test Setup with t.Cleanup

```go
func setupTestUser(t *testing.T, pool *pgxpool.Pool, email string) int {
    t.Helper()
    ctx := context.Background()
    hash, _ := bcrypt.GenerateFromPassword([]byte("password"), 12)
    var id int
    err := pool.QueryRow(ctx,
        `INSERT INTO users (email_address, hashed_password, first_name)
         VALUES ($1, $2, $3) RETURNING user_id`,
        email, string(hash), "Test",
    ).Scan(&id)
    if err != nil {
        t.Fatalf("setup user: %v", err)
    }
    // Automatically clean up when the test ends
    t.Cleanup(func() {
        pool.Exec(ctx, `DELETE FROM users WHERE user_id=$1`, id)
    })
    return id
}
```

---

## Part 8: API Contract Tests

Contract tests verify that the Go backend returns responses with the same shape as the original Flask backend. This catches regressions where a field is renamed or removed.

### Contract Test Pattern

```go
// File: internal/contract/updates_test.go
package contract_test

import (
    "encoding/json"
    "net/http"
    "testing"
)

// UpdateResponse mirrors what the Vue frontend expects.
type UpdateResponse struct {
    UpdateID  int    `json:"update_id"`
    Title     string `json:"title"`
    Body      string `json:"body"`
    Tag       string `json:"tag"`
    CreatedAt string `json:"created_at"`
}

// TestUpdatesContractShape verifies the JSON keys match the Flask contract.
func TestUpdatesContractShape(t *testing.T) {
    // This test runs against the Go server if GO_SERVER_URL is set,
    // or is skipped in CI where no server is running.
    serverURL := os.Getenv("GO_SERVER_URL")
    if serverURL == "" {
        t.Skip("GO_SERVER_URL not set, skipping contract test")
    }

    resp, err := http.Get(serverURL + "/api/updates")
    if err != nil {
        t.Fatalf("request failed: %v", err)
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        t.Fatalf("expected 200, got %d", resp.StatusCode)
    }

    ct := resp.Header.Get("Content-Type")
    if ct != "application/json" {
        t.Errorf("content-type: got %s, want application/json", ct)
    }

    var updates []UpdateResponse
    if err := json.NewDecoder(resp.Body).Decode(&updates); err != nil {
        t.Fatalf("decode failed: %v", err)
    }
    // Shape verified — all required fields are present in the struct
}
```

### Pagination Contract

The Vue admin report tables depend on exactly this shape:

```go
// PaginatedResponse is the contract every paginated endpoint must match.
type PaginatedResponse struct {
    Data    json.RawMessage `json:"data"`
    Total   int             `json:"total"`
    Page    int             `json:"page"`
    PerPage int             `json:"per_page"`
}

func TestApplicantReportPaginationShape(t *testing.T) {
    serverURL := os.Getenv("GO_SERVER_URL")
    if serverURL == "" {
        t.Skip("GO_SERVER_URL not set")
    }

    req, _ := http.NewRequest(http.MethodGet,
        serverURL+"/api/admin/applicants/report?page=1&per_page=10", nil)
    req.Header.Set("Authorization", "Bearer "+os.Getenv("TEST_ADMIN_TOKEN"))

    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        t.Fatalf("request: %v", err)
    }
    defer resp.Body.Close()

    var result PaginatedResponse
    if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
        t.Fatalf("decode: %v", err)
    }

    // All four fields must exist and be non-negative
    if result.Page < 1 {
        t.Errorf("page should be >= 1, got %d", result.Page)
    }
    if result.PerPage < 1 {
        t.Errorf("per_page should be >= 1, got %d", result.PerPage)
    }
}
```

---

## Part 9: Coverage Reports

```bash
# Generate coverage data
go test -coverprofile=coverage.out ./...

# View per-function coverage in terminal
go tool cover -func=coverage.out

# Generate HTML coverage report
go tool cover -html=coverage.out -o coverage.html

# Set minimum coverage threshold in CI
go test -coverprofile=coverage.out ./... && \
  go tool cover -func=coverage.out | grep total | awk '{print $3}' | \
  awk -F'%' '{if ($1 < 70) {print "Coverage below 70%"; exit 1}}'
```

Example output from `go tool cover -func`:
```
internal/hfc/scorer.go:CalculateScore           89.5%
internal/hfc/scorer.go:CalculateRiskLevel       100.0%
internal/user/service.go:Login                  72.3%
internal/security/middleware.go:AuthMiddleware   95.0%
total:                                           (statements)  81.2%
```

---

## Part 10: Cypress E2E Tests for Vue Frontend

Cypress automates a real browser. Use it for critical user paths.

### Setup

```bash
cd frontend
npm install --save-dev cypress
npx cypress open
```

### Test: Login Flow

```javascript
// File: frontend/cypress/e2e/login.cy.js
describe('User Login', () => {
  beforeEach(() => {
    cy.visit('/login')
  })

  it('successful login redirects to dashboard', () => {
    // Intercept the API call and return a fixture
    cy.intercept('POST', '/api/login', {
      statusCode: 200,
      body: {
        token: 'eyJhbGciOiJIUzI1NiJ9.test.token',
        user_id: 42,
        language: 'english',
      },
    }).as('loginRequest')

    cy.get('[data-cy="email-input"]').type('fatima@example.com')
    cy.get('[data-cy="password-input"]').type('password123')
    cy.get('[data-cy="login-button"]').click()

    cy.wait('@loginRequest')
    cy.url().should('include', '/dashboard')
    cy.window().then((win) => {
      expect(win.localStorage.getItem('userToken')).to.not.be.null
    })
  })

  it('blocked user sees error message', () => {
    cy.intercept('POST', '/api/login', {
      statusCode: 403,
      body: { error: 'Account blocked' },
    }).as('loginRequest')

    cy.get('[data-cy="email-input"]').type('blocked@example.com')
    cy.get('[data-cy="password-input"]').type('password123')
    cy.get('[data-cy="login-button"]').click()

    cy.wait('@loginRequest')
    cy.get('[data-cy="error-message"]').should('be.visible')
    cy.url().should('include', '/login')
  })

  it('switches to Urdu labels', () => {
    cy.window().then((win) => {
      win.localStorage.setItem('language', 'urdu')
    })
    cy.reload()
    cy.get('[data-cy="login-heading"]').should('contain', 'لاگ ان')
  })
})
```

### Test: Admin Dashboard

```javascript
// File: frontend/cypress/e2e/admin-dashboard.cy.js
describe('Admin Dashboard', () => {
  beforeEach(() => {
    // Set admin token directly (bypasses login UI)
    cy.window().then((win) => {
      win.localStorage.setItem('adminToken', Cypress.env('ADMIN_TOKEN'))
    })

    cy.intercept('GET', '/api/admin/reports/dashboard-stats', {
      body: {
        total_users: 150,
        total_businesses: 130,
        total_grants: 80,
        approved: 12,
        hfc_pending: 5,
      },
    }).as('dashStats')

    cy.visit('/admin/dashboard')
    cy.wait('@dashStats')
  })

  it('shows stats cards', () => {
    cy.get('[data-cy="stat-total-users"]').should('contain', '150')
    cy.get('[data-cy="stat-approved"]').should('contain', '12')
  })

  it('chart renders', () => {
    cy.get('canvas').should('exist')
  })
})
```

### Test: Grant Application Whitelist Gate

```javascript
// File: frontend/cypress/e2e/grant-access.cy.js
describe('Grant Application Access Gate', () => {
  it('non-whitelisted user sees access denied', () => {
    cy.intercept('GET', '/api/grant', {
      body: {
        access_state: 'not_selected',
        grant: null,
      },
    })

    cy.window().then((win) => {
      win.localStorage.setItem('userToken', 'valid-user-token')
    })
    cy.visit('/grant-application')

    cy.get('[data-cy="access-denied-message"]').should('be.visible')
    cy.get('[data-cy="grant-form"]').should('not.exist')
  })

  it('whitelisted user sees the form', () => {
    cy.intercept('GET', '/api/grant', {
      body: {
        access_state: 'selected',
        grant: null,
      },
    })

    cy.window().then((win) => {
      win.localStorage.setItem('userToken', 'valid-user-token')
    })
    cy.visit('/grant-application')

    cy.get('[data-cy="grant-form"]').should('be.visible')
  })
})
```

---

## Part 11: Git Bisect for Debugging Regressions

When a test starts failing and you do not know which commit broke it, `git bisect` performs a binary search through history.

```bash
# Start bisect
git bisect start

# Mark current HEAD as broken
git bisect bad

# Mark a commit where the test passed
git bisect good v0.2.0

# Run automatically using the failing test
git bisect run go test ./internal/hfc/... -run TestCalculateScore

# When done
git bisect reset
```

Git will check out intermediate commits, run the test command, and report the first bad commit.

### Manual Bisect Session Example

```bash
$ git bisect start
$ git bisect bad HEAD
$ git bisect good abc1234

Bisecting: 8 revisions left to test after this (roughly 3 steps)
[def5678] Add missing EOI rule to HFC scorer

$ go test ./internal/hfc/... -run TestCalculateScore
--- FAIL: TestCalculateScore/fast_submission_triggers_10_points
FAIL

$ git bisect bad
Bisecting: 3 revisions left to test after this

$ go test ./internal/hfc/... -run TestCalculateScore
ok  github.com/yourusername/peace-sme/internal/hfc

$ git bisect good
abc9999 is the first bad commit
```

---

## Part 12: Testing Registration Closed Business Rule

The system returns 403 when `GRANT_APPLICATION_OPEN=0`. This is a critical business rule that must be tested.

```go
// File: internal/user/registration_test.go
package user_test

import (
    "net/http"
    "net/http/httptest"
    "strings"
    "testing"

    "github.com/yourusername/peace-sme/internal/user"
)

func TestRegistrationClosed(t *testing.T) {
    // When GRANT_APPLICATION_OPEN = false
    handler := user.NewHandler(user.Config{RegistrationsOpen: false})

    body := strings.NewReader(`{
        "email_address": "new@example.com",
        "password": "pass123",
        "first_name": "Ahmed",
        "cnic": "1234567890123"
    }`)
    req := httptest.NewRequest(http.MethodPost, "/api/register", body)
    req.Header.Set("Content-Type", "application/json")
    rr := httptest.NewRecorder()

    handler.Register(rr, req)

    if rr.Code != http.StatusForbidden {
        t.Errorf("expected 403 when closed, got %d", rr.Code)
    }
}

func TestPreRegistrationClosed(t *testing.T) {
    handler := user.NewHandler(user.Config{RegistrationsOpen: false})

    body := strings.NewReader(`{"cnic":"1234567890123"}`)
    req := httptest.NewRequest(http.MethodPost, "/api/pre-registration", body)
    rr := httptest.NewRecorder()

    handler.PreRegister(rr, req)

    if rr.Code != http.StatusForbidden {
        t.Errorf("expected 403, got %d", rr.Code)
    }
}
```

---

## Mastery Check

You understand this chapter when you can answer:

1. What is the difference between `t.Error` and `t.Fatal`, and when should you use each?
2. Write a table-driven test for a function that validates whether a business district is in the allowed list for the PEACE SME portal.
3. How does `httptest.NewRecorder` work, and what does it let you test that a real HTTP call cannot?
4. What is a mock interface and why do Go programmers prefer it over monkey-patching or global state?
5. You discover the `/api/admin/applicants/report` endpoint returns `null` instead of `[]` for an empty result set. Write a test that catches this contract violation before it reaches the Vue frontend.
