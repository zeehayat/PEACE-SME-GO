# Chapter 20: Error Handling and Observability

## Purpose

A Go backend that crashes silently is worse than one that crashes loudly. This chapter covers the complete observability stack for the PEACE SME portal: structured error handling, request tracing, structured logging, metrics, panic recovery, and debugging production issues. Observability is not optional — it is what separates a codebase you can operate from one you can only hope works.

---

## Part 1: Go Error Philosophy — Errors as Values

In Go, errors are ordinary values. There is no exception system. Every function that can fail returns an `error` as its last return value. The caller decides what to do.

```go
// Python/Flask style (exceptions)
def get_user(user_id):
    user = db.query("SELECT * FROM users WHERE user_id = ?", user_id)
    return user  # raises Exception if query fails

// Go style (errors as values)
func (r *Repository) GetUser(ctx context.Context, userID int) (*User, error) {
    var u User
    err := r.pool.QueryRow(ctx,
        "SELECT user_id, email_address FROM users WHERE user_id = $1",
        userID,
    ).Scan(&u.UserID, &u.EmailAddress)
    if err != nil {
        return nil, err  // caller handles this
    }
    return &u, nil
}
```

### Why Errors as Values?

1. **Explicit**: every function call that can fail is visible in the code.
2. **Composable**: you can wrap errors with context, inspect their type, and make decisions.
3. **No hidden control flow**: no surprise panics from uncaught exceptions.

### The Rule

```go
// WRONG: ignore errors
json.NewDecoder(r.Body).Decode(&req)
db.Exec("UPDATE grants SET status=$1", "Approved")

// RIGHT: handle every error
if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
    return fmt.Errorf("decode request: %w", err)
}
if _, err := db.Exec(ctx, "UPDATE grants SET status=$1", "Approved"); err != nil {
    return fmt.Errorf("update grant: %w", err)
}
```

---

## Part 2: Error Wrapping with %w

`fmt.Errorf` with `%w` wraps an error, adding context while preserving the original:

```go
func (s *GrantService) Approve(ctx context.Context, req ApprovalRequest) error {
    user, err := s.userRepo.FindByID(ctx, req.UserID)
    if err != nil {
        // Wrap with context — caller knows WHERE the error came from
        return fmt.Errorf("approve grant for user %d: find user: %w", req.UserID, err)
    }

    if err := s.grantRepo.SetApproved(ctx, req); err != nil {
        return fmt.Errorf("approve grant for user %d: set approved: %w", req.UserID, err)
    }

    if err := s.mailer.SendGrantApproved(user.EmailAddress, user.FirstName, req.Amount); err != nil {
        // Log but don't fail — email is best-effort
        slog.Error("failed to send approval email",
            "user_id", req.UserID,
            "error", err,
        )
    }

    return nil
}
```

The resulting error chain looks like:
```
approve grant for user 42: set approved: ERROR: duplicate key value violates unique constraint
```

### errors.Is and errors.As

```go
import (
    "errors"
    "github.com/jackc/pgx/v5"
)

var ErrNotFound = errors.New("not found")
var ErrBlocked = errors.New("account blocked")

func (r *UserRepository) FindByEmail(ctx context.Context, email string) (*User, error) {
    var u User
    err := r.pool.QueryRow(ctx, `SELECT ... FROM users WHERE email_address=$1`, email).
        Scan(&u.UserID, &u.EmailAddress, &u.Status, &u.HashedPassword)

    if errors.Is(err, pgx.ErrNoRows) {
        return nil, ErrNotFound  // wrap as domain error
    }
    if err != nil {
        return nil, fmt.Errorf("find by email: %w", err)
    }
    if u.Status == "blocked" {
        return nil, ErrBlocked
    }
    return &u, nil
}

// In the handler
func (h *Handler) Login(w http.ResponseWriter, r *http.Request) {
    // ...
    user, err := h.repo.FindByEmail(ctx, req.Email)
    if errors.Is(err, user.ErrNotFound) {
        writeError(w, http.StatusUnauthorized, "invalid credentials")
        return
    }
    if errors.Is(err, user.ErrBlocked) {
        writeError(w, http.StatusForbidden, "account has been blocked")
        return
    }
    if err != nil {
        // Unknown error — log it, return generic 500
        slog.Error("login: find user", "error", err, "email", req.Email)
        writeError(w, http.StatusInternalServerError, "internal error")
        return
    }
}
```

### errors.As — Inspect Error Types

```go
type ValidationError struct {
    Field   string
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation: %s: %s", e.Field, e.Message)
}

// In handler
var validErr *ValidationError
if errors.As(err, &validErr) {
    writeError(w, http.StatusUnprocessableEntity, validErr.Message)
    return
}
```

---

## Part 3: HTTP Error Response Format

The Vue frontend expects a consistent JSON error shape. Always use this format:

```go
// File: internal/httpx/errors.go
package httpx

import (
    "encoding/json"
    "net/http"
)

// ErrorResponse is the JSON shape every error response uses.
// The Vue frontend checks err.response.data.error in Axios catch blocks.
type ErrorResponse struct {
    Error   string `json:"error"`
    Details any    `json:"details,omitempty"`
    Code    string `json:"code,omitempty"` // machine-readable error code
}

// WriteError sends a JSON error response.
func WriteError(w http.ResponseWriter, status int, message string) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    json.NewEncoder(w).Encode(ErrorResponse{Error: message})
}

// WriteValidationError sends a 422 with field-level details.
func WriteValidationError(w http.ResponseWriter, errors map[string]string) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusUnprocessableEntity)
    json.NewEncoder(w).Encode(ErrorResponse{
        Error:   "validation failed",
        Details: errors,
    })
}
```

### Consistent Status Codes

| Situation | Status | Body |
|---|---|---|
| Missing/bad auth token | 401 | `{"error": "authentication required"}` |
| Valid token, wrong role | 403 | `{"error": "access denied"}` |
| Blocked user login | 403 | `{"error": "account has been blocked"}` |
| Registration closed | 403 | `{"error": "registrations are currently closed"}` |
| Resource not found | 404 | `{"error": "not found"}` |
| Duplicate resource | 409 | `{"error": "resource already exists"}` |
| Invalid input | 422 | `{"error": "validation failed", "details": {...}}` |
| Too many sessions | 429 | `{"error": "portal is at capacity, please try again shortly"}` |
| Server error | 500 | `{"error": "internal server error"}` |

---

## Part 4: Panic Recovery Middleware

A panic in a Go HTTP handler crashes the goroutine serving that request. Without recovery middleware, other requests keep working but the panicking request leaks resources and leaves the client hanging.

```go
// File: internal/security/recovery.go
package security

import (
    "log/slog"
    "net/http"
    "runtime/debug"

    "github.com/yourusername/peace-sme/internal/httpx"
)

// RecoverMiddleware catches panics, logs the stack trace, and returns 500.
func RecoverMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        defer func() {
            if rec := recover(); rec != nil {
                stack := debug.Stack()

                slog.Error("panic recovered",
                    "panic", rec,
                    "method", r.Method,
                    "path", r.URL.Path,
                    "request_id", RequestIDFromContext(r.Context()),
                    "stack", string(stack),
                )

                // Do not write the stack trace to the client — it leaks internals
                httpx.WriteError(w, http.StatusInternalServerError,
                    "internal server error")
            }
        }()

        next.ServeHTTP(w, r)
    })
}
```

Register it as the outermost middleware:

```go
func buildRouter(cfg *config.Config, ...) http.Handler {
    mux := http.NewServeMux()
    // ... register routes

    // Middleware applied inside-out (last in = first executed)
    var handler http.Handler = mux
    handler = security.AuthMiddleware(cfg.JWTSecret)(handler)
    handler = security.AccessControlMiddleware(cfg)(handler)
    handler = security.GeoBlockMiddleware(cfg)(handler)
    handler = security.RequestIDMiddleware(handler)
    handler = security.RecoverMiddleware(handler)  // outermost
    return handler
}
```

---

## Part 5: Request ID Middleware

A request ID lets you correlate all log lines from a single HTTP request.

```go
// File: internal/security/request_id.go
package security

import (
    "context"
    "crypto/rand"
    "encoding/hex"
    "net/http"
)

type contextKey string

const requestIDKey contextKey = "request_id"

// RequestIDMiddleware adds a unique request ID to every request.
// It reads X-Request-ID from the client if present (useful for tracing across services),
// or generates a new one.
func RequestIDMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        id := r.Header.Get("X-Request-ID")
        if id == "" {
            id = generateRequestID()
        }

        // Add to context for downstream use
        ctx := context.WithValue(r.Context(), requestIDKey, id)
        // Add to response so the client can correlate
        w.Header().Set("X-Request-ID", id)

        next.ServeHTTP(w, r.WithContext(ctx))
    })
}

// RequestIDFromContext extracts the request ID from a context.
// Returns empty string if not set.
func RequestIDFromContext(ctx context.Context) string {
    if id, ok := ctx.Value(requestIDKey).(string); ok {
        return id
    }
    return ""
}

func generateRequestID() string {
    b := make([]byte, 8)
    rand.Read(b)
    return hex.EncodeToString(b)
}
```

---

## Part 6: Structured Logging with slog

Go 1.21 added `log/slog` as the standard structured logger. Use it instead of `fmt.Println` or the `log` package.

### Setup

```go
// File: cmd/server/main.go
package main

import (
    "log/slog"
    "os"
)

func setupLogger(env string) {
    var handler slog.Handler

    if env == "production" {
        // JSON format for log aggregators (Loki, CloudWatch, etc.)
        handler = slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
            Level: slog.LevelInfo,
        })
    } else {
        // Human-readable format for development
        handler = slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
            Level: slog.LevelDebug,
        })
    }

    slog.SetDefault(slog.New(handler))
}
```

### Using slog Throughout the Application

```go
// Structured key-value pairs — much better than fmt.Sprintf
slog.Info("user logged in",
    "user_id", userID,
    "ip", r.RemoteAddr,
    "language", language,
)

slog.Warn("whitelist check: user not selected",
    "user_id", userID,
    "require_selection", true,
)

slog.Error("database query failed",
    "error", err,
    "query", "FindByEmail",
    "request_id", security.RequestIDFromContext(ctx),
)

slog.Debug("HFC score calculated",
    "user_id", userID,
    "final_score", result.FinalScore,
    "risk_level", result.RiskLevel,
    "rules_triggered", result.RulesTriggered,
)
```

### Request Logging Middleware

```go
// File: internal/security/logging.go
package security

import (
    "log/slog"
    "net/http"
    "time"
)

func RequestLoggingMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        rw := &responseRecorder{w, http.StatusOK, 0}

        next.ServeHTTP(rw, r)

        duration := time.Since(start)
        requestID := RequestIDFromContext(r.Context())

        level := slog.LevelInfo
        if rw.statusCode >= 500 {
            level = slog.LevelError
        } else if rw.statusCode >= 400 {
            level = slog.LevelWarn
        }

        slog.Log(r.Context(), level, "request",
            "method", r.Method,
            "path", r.URL.Path,
            "status", rw.statusCode,
            "duration_ms", duration.Milliseconds(),
            "request_id", requestID,
            "bytes", rw.bytesWritten,
        )
    })
}

type responseRecorder struct {
    http.ResponseWriter
    statusCode   int
    bytesWritten int
}

func (r *responseRecorder) WriteHeader(code int) {
    r.statusCode = code
    r.ResponseWriter.WriteHeader(code)
}

func (r *responseRecorder) Write(b []byte) (int, error) {
    n, err := r.ResponseWriter.Write(b)
    r.bytesWritten += n
    return n, err
}
```

Example JSON output in production:

```json
{"time":"2026-06-17T10:23:45Z","level":"INFO","msg":"request","method":"POST","path":"/api/login","status":200,"duration_ms":12,"request_id":"a3f7b2c1","bytes":185}
{"time":"2026-06-17T10:23:50Z","level":"WARN","msg":"request","method":"POST","path":"/api/grant","status":403,"duration_ms":3,"request_id":"d8e9a4b2","bytes":52}
{"time":"2026-06-17T10:23:55Z","level":"ERROR","msg":"database query failed","error":"connection refused","query":"FindByEmail","request_id":"c2f1a9d7"}
```

---

## Part 7: Audit Logging for Grant Approvals

The grant approval is a high-stakes action. Every approval must be logged with full before/after state.

```go
// File: internal/grant/audit.go
package grant

import (
    "context"
    "encoding/json"
    "log/slog"
    "time"
)

type AuditEntry struct {
    Action     string          `json:"action"`
    ActorName  string          `json:"actor_username"`
    UserID     int             `json:"user_id"`
    GrantID    int             `json:"grant_id"`
    BeforeState json.RawMessage `json:"before_state"`
    AfterState json.RawMessage `json:"after_state"`
    Timestamp  time.Time       `json:"timestamp"`
}

// LogApproval writes a structured audit log entry AND inserts a database record.
func (s *GrantService) LogApproval(ctx context.Context, entry AuditEntry) error {
    // 1. Structured log (goes to your log aggregator)
    slog.Info("grant approval action",
        "action", entry.Action,
        "actor", entry.ActorName,
        "user_id", entry.UserID,
        "grant_id", entry.GrantID,
        "timestamp", entry.Timestamp,
    )

    // 2. Database audit record (permanent, searchable)
    _, err := s.pool.Exec(ctx, `
        INSERT INTO grant_approval_logs
            (grant_id, user_id, approving_authority, action, before_state, after_state, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    `,
        entry.GrantID, entry.UserID, entry.ActorName,
        entry.Action, entry.BeforeState, entry.AfterState,
        entry.Timestamp,
    )
    return err
}
```

Usage in the approval flow:

```go
func (s *GrantService) Approve(ctx context.Context, req ApprovalRequest) error {
    // Capture before state
    before, _ := s.grantRepo.GetJSON(ctx, req.UserID)

    // Execute approval
    if err := s.grantRepo.Approve(ctx, req); err != nil {
        return fmt.Errorf("approve: %w", err)
    }

    // Capture after state
    after, _ := s.grantRepo.GetJSON(ctx, req.UserID)

    // Audit log
    s.LogApproval(ctx, AuditEntry{
        Action:      "Approved",
        ActorName:   req.ApprovedBy,
        UserID:      req.UserID,
        GrantID:     req.GrantID,
        BeforeState: before,
        AfterState:  after,
        Timestamp:   time.Now().UTC(),
    })

    return nil
}
```

---

## Part 8: HFC Scoring Observability

Log every HFC calculation with enough detail to reconstruct what happened:

```go
// File: internal/hfc/scorer.go

func CalculateAndStore(ctx context.Context, userID int, pool *pgxpool.Pool) error {
    input, err := buildScoringInput(ctx, userID, pool)
    if err != nil {
        return fmt.Errorf("build scoring input for user %d: %w", userID, err)
    }

    result := CalculateScore(input)

    // Structured log of every HFC calculation
    slog.Info("hfc score calculated",
        "user_id", userID,
        "final_score", result.FinalScore,
        "risk_level", result.RiskLevel,
        "rules_triggered", result.RulesTriggered,
        "rule_count", len(result.RulesTriggered),
    )

    if result.RiskLevel == "CRITICAL" {
        slog.Warn("hfc critical risk detected",
            "user_id", userID,
            "score", result.FinalScore,
            "rules", result.RulesTriggered,
        )
    }

    // Store in database
    if err := storeEvaluation(ctx, userID, result, pool); err != nil {
        return fmt.Errorf("store HFC evaluation for user %d: %w", userID, err)
    }

    return nil
}
```

---

## Part 9: S3 Error Observability

S3 failures should be logged with enough context to retry or diagnose:

```go
// File: internal/s3/client.go
package s3

import (
    "context"
    "fmt"
    "log/slog"

    "github.com/aws/aws-sdk-go-v2/service/s3"
)

type Client struct {
    s3     *s3.Client
    bucket string
}

func (c *Client) UploadDocument(ctx context.Context, key string, body []byte, mimeType string) (string, error) {
    _, err := c.s3.PutObject(ctx, &s3.PutObjectInput{
        Bucket:      &c.bucket,
        Key:         &key,
        Body:        bytes.NewReader(body),
        ContentType: &mimeType,
    })
    if err != nil {
        slog.Error("s3 upload failed",
            "bucket", c.bucket,
            "key", key,
            "mime_type", mimeType,
            "size_bytes", len(body),
            "error", err,
        )
        return "", fmt.Errorf("s3 upload %s: %w", key, err)
    }

    url := c.buildPublicURL(key)
    slog.Debug("s3 upload succeeded",
        "bucket", c.bucket,
        "key", key,
        "url", url,
    )
    return url, nil
}
```

---

## Part 10: Prometheus Metrics for the Portal

```go
// File: internal/metrics/portal.go
package metrics

import (
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promauto"
)

var (
    // How long HTTP requests take
    HTTPDuration = promauto.NewHistogramVec(
        prometheus.HistogramOpts{
            Name:    "peace_sme_http_duration_seconds",
            Help:    "HTTP request duration in seconds",
            Buckets: []float64{.005, .01, .025, .05, .1, .25, .5, 1, 2.5},
        },
        []string{"method", "path", "status"},
    )

    // Total requests by path and status
    HTTPRequests = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "peace_sme_http_requests_total",
            Help: "Total HTTP requests",
        },
        []string{"method", "path", "status"},
    )

    // HFC scores by risk level
    HFCScores = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "peace_sme_hfc_scores_total",
            Help: "HFC evaluations by risk level",
        },
        []string{"risk_level"},
    )

    // Active portal sessions
    ActiveSessions = promauto.NewGauge(prometheus.GaugeOpts{
        Name: "peace_sme_active_sessions",
        Help: "Current number of active portal sessions",
    })

    // S3 upload outcomes
    S3Uploads = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "peace_sme_s3_uploads_total",
            Help: "S3 document upload outcomes",
        },
        []string{"outcome"}, // "success" | "error"
    )

    // Grants approved
    GrantsApproved = promauto.NewCounter(prometheus.CounterOpts{
        Name: "peace_sme_grants_approved_total",
        Help: "Total grants approved",
    })

    // Email jobs queued
    EmailsQueued = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "peace_sme_emails_queued_total",
            Help: "Email jobs enqueued by type",
        },
        []string{"type"}, // "welcome" | "approved" | "approval_notification"
    )
)
```

Record metrics at the right places:

```go
// In the HFC scorer
result := hfc.CalculateScore(input)
metrics.HFCScores.WithLabelValues(result.RiskLevel).Inc()

// In the approval service
metrics.GrantsApproved.Inc()

// In the S3 client
if err != nil {
    metrics.S3Uploads.WithLabelValues("error").Inc()
} else {
    metrics.S3Uploads.WithLabelValues("success").Inc()
}
```

---

## Part 11: pprof Profiling

Go's `net/http/pprof` package exposes profiling endpoints. Use it to find slow functions or memory leaks.

```go
// File: cmd/server/main.go
import _ "net/http/pprof"

// In development only — never expose pprof publicly
if cfg.Env == "development" {
    go func() {
        log.Println("pprof listening on :6060")
        log.Println(http.ListenAndServe("localhost:6060", nil))
    }()
}
```

### Collecting a CPU Profile

```bash
# Collect 30 seconds of CPU profile while running a slow report
go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30

# View in browser
go tool pprof -http=:8081 cpu.prof
```

### Collecting a Memory Profile

```bash
go tool pprof http://localhost:6060/debug/pprof/heap

# In interactive mode
(pprof) top10
(pprof) list <function name>
```

### Reading a Go Stack Trace

When a panic or crash produces a stack trace, read it bottom-up:

```
goroutine 1 [running]:
main.main()
        /app/cmd/server/main.go:42 +0x1c4          ← entry point

runtime/debug.Stack()
        runtime/debug/stack.go:24 +0x5b

github.com/yourusername/peace-sme/internal/security.RecoverMiddleware.func1()
        internal/security/recovery.go:18 +0x6a      ← recovery middleware caught it

github.com/yourusername/peace-sme/internal/grant.(*Handler).Approve(...)
        internal/grant/handler.go:156 +0x3a8         ← the panic source
```

The panic source is at `internal/grant/handler.go:156`. Read the function, look for nil pointer dereference or out-of-bounds slice access.

---

## Part 12: Debugging Checklist for Production Issues

When something goes wrong in production:

```
Step 1: Check the health endpoint
  curl https://peace-grant.srsp.cloud/health
  → If unhealthy: which check failed? (postgres / redis)

Step 2: Check service logs
  docker compose logs --tail=100 backend
  docker compose logs --tail=100 worker
  → Look for ERROR level lines
  → Copy the request_id from a user complaint

Step 3: Search logs by request ID
  docker compose logs backend | grep "a3f7b2c1"
  → See all log lines for that specific request

Step 4: Check the database
  psql $DATABASE_URL
  SELECT * FROM grants WHERE user_id = 42 ORDER BY grant_id DESC LIMIT 1;
  SELECT * FROM hfc_evaluations WHERE user_id = 42 ORDER BY evaluated_at DESC LIMIT 5;
  SELECT * FROM grant_approval_logs WHERE user_id = 42 ORDER BY created_at DESC;

Step 5: Check Redis
  docker exec sme_redis redis-cli
  > KEYS peace_sme:*
  > GET peace_sme:stats
  > TTL peace_sme:faqs

Step 6: Check HFC worker
  → Is the worker container running?
  docker ps | grep worker
  → Are jobs stuck?
  docker exec sme_redis redis-cli LRANGE rq:queue:hfc 0 -1

Step 7: Reproduce with a test
  → Write a failing test that reproduces the bug
  → Fix the bug
  → Verify the test passes
  → Deploy
```

---

## Mastery Check

You understand this chapter when you can answer:

1. A function call returns `fmt.Errorf("grant approval for user %d: update grant: %w", userID, pgErr)`. Write the code that uses `errors.Is` to check if the underlying error is a PostgreSQL unique constraint violation, and send a 409 response if so.
2. What is the difference between logging at `slog.LevelError` vs `slog.LevelWarn`? Give a portal-specific example of each.
3. A user reports their grant submission "disappeared." You have the X-Request-ID from their browser network tab. Write the shell command to search the container logs for that request ID and describe what you would look for.
4. Why should pprof endpoints never be exposed on a public port in production? What is the safe way to use them?
5. Write a panic recovery middleware test that sends a request to a handler that panics, verifies the response is a 500 JSON error body, and verifies the server is still running (can accept a second request).
