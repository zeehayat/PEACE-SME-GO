# Chapter 21: Go Concurrency Patterns

## Purpose

Go's concurrency model is one of its defining features. The PEACE SME portal uses concurrency in several places: handling thousands of simultaneous HTTP requests, running HFC scoring jobs in background workers, limiting concurrent portal sessions with Redis, and generating reports in parallel. This chapter takes you from goroutine basics to production-grade patterns, applied directly to the portal's real problems.

---

## Part 1: Goroutines and the Go Scheduler

A goroutine is a lightweight thread managed by the Go runtime. The Go scheduler multiplexes goroutines onto OS threads using an M:N model (many goroutines, few OS threads).

```go
// The main goroutine
func main() {
    // Launch a new goroutine with the go keyword
    go func() {
        fmt.Println("hello from goroutine")
    }()

    // Main goroutine continues immediately — does not wait
    fmt.Println("hello from main")
    time.Sleep(10 * time.Millisecond) // crude wait — never do this in production
}
```

### Why Goroutines Are Cheap

A goroutine starts with a 2 KB stack (vs ~1 MB for an OS thread). The runtime grows and shrinks the stack as needed. You can have hundreds of thousands of goroutines without running out of memory.

Each incoming HTTP request in Go's `net/http` is served by its own goroutine automatically. This is why Go handles concurrency naturally without async/await.

### The Race Condition

Two goroutines reading and writing the same variable without synchronization is a race condition. It produces unpredictable results.

```go
// BROKEN — race condition
count := 0
var wg sync.WaitGroup
for i := 0; i < 1000; i++ {
    wg.Add(1)
    go func() {
        defer wg.Done()
        count++  // NOT safe — concurrent writes to count
    }()
}
wg.Wait()
fmt.Println(count) // prints something less than 1000, unpredictably
```

Run the race detector to catch this:

```bash
go run -race main.go
# or
go test -race ./...
```

Output:
```
WARNING: DATA RACE
Write at 0x00c0000b8000 by goroutine 7:
  main.main.func1()
        main.go:12 +0x30
Read at 0x00c0000b8000 by goroutine 8:
  main.main.func1()
        main.go:12 +0x28
```

---

## Part 2: Channels — Communicating Between Goroutines

Channels are typed conduits. Values sent into a channel can be received by another goroutine.

```
Go philosophy: "Do not communicate by sharing memory; share memory by communicating."
```

### Unbuffered Channel — Synchronous

An unbuffered channel blocks the sender until a receiver is ready, and blocks the receiver until a sender sends.

```go
ch := make(chan string)

go func() {
    ch <- "HFC score calculated"  // blocks until someone receives
}()

msg := <-ch  // blocks until sender sends
fmt.Println(msg)
```

### Buffered Channel — Asynchronous up to Capacity

A buffered channel holds values without blocking until the buffer is full.

```go
ch := make(chan string, 10)  // capacity of 10

ch <- "job 1"   // does not block — buffer has space
ch <- "job 2"
ch <- "job 3"

fmt.Println(<-ch) // "job 1"
fmt.Println(<-ch) // "job 2"
```

### Directional Channels

Functions can declare whether they send or receive:

```go
// send-only channel parameter
func producer(out chan<- string) {
    out <- "message"
}

// receive-only channel parameter
func consumer(in <-chan string) {
    msg := <-in
    fmt.Println(msg)
}
```

### Closing Channels and range

A closed channel returns the zero value immediately. Use `close` to signal "no more values":

```go
ch := make(chan int)

go func() {
    for i := 0; i < 5; i++ {
        ch <- i
    }
    close(ch)  // signal: no more values
}()

for v := range ch {  // range exits when channel is closed
    fmt.Println(v)
}
```

---

## Part 3: sync.WaitGroup — Wait for Multiple Goroutines

`WaitGroup` waits for a collection of goroutines to finish.

```go
var wg sync.WaitGroup

for i := 0; i < 5; i++ {
    wg.Add(1)  // increment before launching goroutine
    go func(id int) {
        defer wg.Done()  // decrement when done
        fmt.Printf("goroutine %d finished\n", id)
    }(i)
}

wg.Wait()  // blocks until counter reaches zero
fmt.Println("all goroutines done")
```

> [!WARNING]
> Always call `wg.Add(1)` before launching the goroutine, not inside it. If the goroutine starts and calls `Done` before the main goroutine calls `Add`, the counter can reach zero prematurely.

---

## Part 4: sync.Mutex and sync.RWMutex

A mutex protects shared state from concurrent access.

```go
// Thread-safe counter using Mutex
type SafeCounter struct {
    mu    sync.Mutex
    count int
}

func (c *SafeCounter) Increment() {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.count++
}

func (c *SafeCounter) Value() int {
    c.mu.Lock()
    defer c.mu.Unlock()
    return c.count
}
```

`RWMutex` allows multiple concurrent readers but only one writer at a time. Use it for read-heavy data:

```go
// Cache protected by RWMutex
type FilterCache struct {
    mu   sync.RWMutex
    data map[string][]string
}

func (c *FilterCache) Get(key string) ([]string, bool) {
    c.mu.RLock()         // multiple goroutines can read simultaneously
    defer c.mu.RUnlock()
    v, ok := c.data[key]
    return v, ok
}

func (c *FilterCache) Set(key string, val []string) {
    c.mu.Lock()          // exclusive write lock
    defer c.mu.Unlock()
    c.data[key] = val
}
```

---

## Part 5: context.Context — Cancellation and Timeouts

`context.Context` carries deadlines, cancellation signals, and request-scoped values across API boundaries. Every database query, HTTP call, and background job should accept a context.

```go
// Timeout: cancel after 5 seconds
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()

rows, err := pool.Query(ctx, "SELECT * FROM users") // cancelled after 5s
```

```go
// Cancellation: cancel when done
ctx, cancel := context.WithCancel(context.Background())

go func() {
    // Do work
    cancel() // signal other goroutines to stop
}()

select {
case <-ctx.Done():
    fmt.Println("cancelled:", ctx.Err())
}
```

### Context in HTTP Handlers

Every incoming HTTP request already has a context that is cancelled when the client disconnects:

```go
func (h *Handler) GetReport(w http.ResponseWriter, r *http.Request) {
    ctx := r.Context() // cancelled if client disconnects

    // Pass context to every downstream call
    data, err := h.repo.GetReport(ctx, filters)
    if err != nil {
        if errors.Is(err, context.Canceled) {
            // Client left — no need to send a response
            return
        }
        httpx.WriteError(w, 500, "report failed")
        return
    }

    httpx.WriteJSON(w, 200, data)
}
```

### Portal-Applied: Database Query with Timeout

```go
// Every repository method should have a query-level timeout
func (r *ReportRepository) GetApplicants(ctx context.Context, f Filter) ([]ApplicantRow, error) {
    // Add a 10-second deadline specifically for this query
    ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
    defer cancel()

    rows, err := r.pool.Query(ctx, buildApplicantSQL(f), buildApplicantArgs(f)...)
    if err != nil {
        return nil, fmt.Errorf("get applicants: %w", err)
    }
    defer rows.Close()

    var result []ApplicantRow
    for rows.Next() {
        var row ApplicantRow
        if err := rows.Scan(...); err != nil {
            return nil, fmt.Errorf("scan applicant row: %w", err)
        }
        result = append(result, row)
    }
    return result, rows.Err()
}
```

---

## Part 6: Worker Pool Pattern

The portal's HFC scoring and email sending are background jobs. A worker pool processes jobs concurrently with a fixed number of workers.

```go
// File: internal/worker/pool.go
package worker

import (
    "context"
    "log/slog"
    "sync"
)

// Job is a unit of work the pool can execute.
type Job struct {
    UserID  int
    JobType string // "hfc" | "email"
    Payload any
}

// Pool runs jobs concurrently with a fixed number of workers.
type Pool struct {
    jobs    chan Job
    workers int
    wg      sync.WaitGroup
}

func NewPool(workers int, bufferSize int) *Pool {
    return &Pool{
        jobs:    make(chan Job, bufferSize),
        workers: workers,
    }
}

// Start launches the worker goroutines and returns when all are ready.
func (p *Pool) Start(ctx context.Context, handler func(context.Context, Job) error) {
    for i := 0; i < p.workers; i++ {
        p.wg.Add(1)
        go func(workerID int) {
            defer p.wg.Done()
            slog.Debug("worker started", "worker_id", workerID)

            for {
                select {
                case job, ok := <-p.jobs:
                    if !ok {
                        slog.Debug("worker stopping", "worker_id", workerID)
                        return
                    }
                    if err := handler(ctx, job); err != nil {
                        slog.Error("job failed",
                            "worker_id", workerID,
                            "job_type", job.JobType,
                            "user_id", job.UserID,
                            "error", err,
                        )
                    }
                case <-ctx.Done():
                    return
                }
            }
        }(i)
    }
}

// Submit adds a job to the queue. Returns false if the pool is full.
func (p *Pool) Submit(job Job) bool {
    select {
    case p.jobs <- job:
        return true
    default:
        return false // buffer full
    }
}

// Stop signals workers to stop and waits for them to finish.
func (p *Pool) Stop() {
    close(p.jobs)
    p.wg.Wait()
}
```

Usage in the portal:

```go
func main() {
    ctx, cancel := context.WithCancel(context.Background())
    defer cancel()

    pool := worker.NewPool(4, 100) // 4 workers, buffer of 100 jobs
    pool.Start(ctx, processJob)

    // In the HFC enqueue
    pool.Submit(worker.Job{
        UserID:  42,
        JobType: "hfc",
    })

    // Graceful shutdown
    signal.Notify(quit, syscall.SIGTERM)
    <-quit
    cancel()      // tell workers to stop accepting new context-dependent work
    pool.Stop()   // wait for in-flight jobs to complete
}

func processJob(ctx context.Context, job worker.Job) error {
    switch job.JobType {
    case "hfc":
        return hfc.CalculateAndStore(ctx, job.UserID, db)
    case "email":
        return mail.Send(ctx, job.Payload)
    default:
        return fmt.Errorf("unknown job type: %s", job.JobType)
    }
}
```

---

## Part 7: Fan-Out / Fan-In Pattern

Fan-out distributes work across multiple goroutines. Fan-in collects results.

### Applied to PEACE SME: Parallel Report Generation

The full applicant report must join data from several tables. Fan-out fetches them in parallel:

```go
// File: internal/report/parallel.go
package report

import (
    "context"
    "sync"
)

type FullApplicantData struct {
    User      *User
    Business  *Business
    Documents []Document
    Grant     *Grant
    HFCScore  *HFCEvaluation
    Error     error
}

// FetchApplicantDataParallel fetches all data for one applicant concurrently.
// Each fetch runs in its own goroutine, reducing total latency from the sum
// of all queries to the slowest individual query.
func FetchApplicantDataParallel(ctx context.Context, userID int, repos Repositories) FullApplicantData {
    var (
        result FullApplicantData
        wg     sync.WaitGroup
        mu     sync.Mutex
        errs   []error
    )

    addErr := func(err error) {
        if err != nil {
            mu.Lock()
            errs = append(errs, err)
            mu.Unlock()
        }
    }

    wg.Add(1)
    go func() {
        defer wg.Add(-1)
        u, err := repos.Users.FindByID(ctx, userID)
        addErr(err)
        mu.Lock()
        result.User = u
        mu.Unlock()
    }()

    wg.Add(1)
    go func() {
        defer wg.Done()
        b, err := repos.Businesses.FindByUserID(ctx, userID)
        addErr(err)
        mu.Lock()
        result.Business = b
        mu.Unlock()
    }()

    wg.Add(1)
    go func() {
        defer wg.Done()
        docs, err := repos.Documents.FindByUserID(ctx, userID)
        addErr(err)
        mu.Lock()
        result.Documents = docs
        mu.Unlock()
    }()

    wg.Add(1)
    go func() {
        defer wg.Done()
        g, err := repos.Grants.FindByUserID(ctx, userID)
        addErr(err)
        mu.Lock()
        result.Grant = g
        mu.Unlock()
    }()

    wg.Add(1)
    go func() {
        defer wg.Done()
        h, err := repos.HFC.LatestByUserID(ctx, userID)
        addErr(err)
        mu.Lock()
        result.HFCScore = h
        mu.Unlock()
    }()

    wg.Wait()

    if len(errs) > 0 {
        result.Error = errors.Join(errs...)
    }
    return result
}
```

### Fan-In Pattern Using Channels

```go
// merge combines multiple channels into one
func merge(channels ...<-chan int) <-chan int {
    out := make(chan int)
    var wg sync.WaitGroup

    forward := func(ch <-chan int) {
        defer wg.Done()
        for v := range ch {
            out <- v
        }
    }

    wg.Add(len(channels))
    for _, ch := range channels {
        go forward(ch)
    }

    go func() {
        wg.Wait()
        close(out) // close output when all inputs are drained
    }()

    return out
}
```

---

## Part 8: The Access Slot System — Concurrent Session Limiting

The portal limits concurrent sessions to 300. This uses Redis as the coordination mechanism across multiple Go server instances.

```go
// File: internal/security/access_control.go
package security

import (
    "context"
    "crypto/rand"
    "encoding/hex"
    "fmt"
    "net/http"
    "time"

    "github.com/redis/go-redis/v9"
)

const (
    sessionPrefix   = "peace_sme:session:"
    sessionTTL      = 90 * time.Second
    maxSessions     = 300
)

type AccessController struct {
    rdb         *redis.Client
    maxSessions int
    ttl         time.Duration
}

func NewAccessController(rdb *redis.Client, max int, ttl time.Duration) *AccessController {
    return &AccessController{rdb: rdb, maxSessions: max, ttl: ttl}
}

// Acquire attempts to reserve a session slot.
// Returns (sessionID, true) if a slot was acquired, ("", false) if at capacity.
func (ac *AccessController) Acquire(ctx context.Context) (string, bool) {
    // Count active sessions using SCAN to avoid blocking KEYS on large datasets
    count, err := ac.countActiveSessions(ctx)
    if err != nil {
        // If Redis is down, allow the request through (fail open)
        return "", true
    }

    if count >= ac.maxSessions {
        return "", false
    }

    sessionID := ac.newSessionID()
    key := sessionPrefix + sessionID

    // SETEX: set with expiry. If the user navigates away, the slot expires automatically.
    err = ac.rdb.SetEx(ctx, key, "1", ac.ttl).Err()
    if err != nil {
        return "", true // Redis error — fail open
    }

    return sessionID, true
}

// Refresh extends the TTL of an active session.
func (ac *AccessController) Refresh(ctx context.Context, sessionID string) {
    key := sessionPrefix + sessionID
    ac.rdb.Expire(ctx, key, ac.ttl)
}

// Release removes a session slot immediately (on logout or disconnect).
func (ac *AccessController) Release(ctx context.Context, sessionID string) {
    ac.rdb.Del(ctx, sessionPrefix+sessionID)
}

func (ac *AccessController) countActiveSessions(ctx context.Context) (int, error) {
    var count int
    var cursor uint64
    pattern := sessionPrefix + "*"

    for {
        keys, nextCursor, err := ac.rdb.Scan(ctx, cursor, pattern, 100).Result()
        if err != nil {
            return 0, err
        }
        count += len(keys)
        cursor = nextCursor
        if cursor == 0 {
            break
        }
    }
    return count, nil
}

func (ac *AccessController) newSessionID() string {
    b := make([]byte, 16)
    rand.Read(b)
    return hex.EncodeToString(b)
}

// AccessControlMiddleware implements the session slot limit.
func AccessControlMiddleware(ac *AccessController) func(http.Handler) http.Handler {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            ctx := r.Context()

            // Check for existing session cookie
            cookie, err := r.Cookie("session_id")
            if err == nil && cookie.Value != "" {
                ac.Refresh(ctx, cookie.Value)
                next.ServeHTTP(w, r)
                return
            }

            // Try to acquire a new slot
            sessionID, ok := ac.Acquire(ctx)
            if !ok {
                w.Header().Set("Content-Type", "application/json")
                w.WriteHeader(http.StatusTooManyRequests)
                fmt.Fprint(w, `{"error":"portal is at capacity, please try again shortly"}`)
                return
            }

            // Set session cookie
            http.SetCookie(w, &http.Cookie{
                Name:     "session_id",
                Value:    sessionID,
                MaxAge:   int(ac.ttl.Seconds()),
                HttpOnly: true,
                SameSite: http.SameSiteStrictMode,
            })

            next.ServeHTTP(w, r)
        })
    }
}
```

---

## Part 9: HFC Debounce with Redis

The HFC job should not run immediately on every grant form save — users may make several saves in quick succession. A 60-second debounce ensures the job only runs after the user has stopped editing.

```go
// File: internal/hfc/debounce.go
package hfc

import (
    "context"
    "fmt"
    "log/slog"
    "time"

    "github.com/redis/go-redis/v9"
)

const (
    debouncePrefix = "peace_sme:hfc_debounce:"
    debounceTTL    = 60 * time.Second
)

type Debouncer struct {
    rdb    *redis.Client
    enqueue func(ctx context.Context, userID int) error
}

func NewDebouncer(rdb *redis.Client, enqueue func(context.Context, int) error) *Debouncer {
    return &Debouncer{rdb: rdb, enqueue: enqueue}
}

// Schedule queues an HFC recalculation for userID with a 60-second delay.
// If called again before the delay expires, the timer resets.
// This means the job runs 60 seconds AFTER THE LAST submission or edit.
func (d *Debouncer) Schedule(ctx context.Context, userID int) error {
    key := fmt.Sprintf("%s%d", debouncePrefix, userID)

    // Check if a debounce key already exists
    exists, err := d.rdb.Exists(ctx, key).Result()
    if err != nil {
        slog.Warn("hfc debounce: redis check failed",
            "user_id", userID, "error", err)
        // Fall through — enqueue anyway
    }

    if exists == 1 {
        // Reset the timer — user is still editing
        d.rdb.Expire(ctx, key, debounceTTL)
        slog.Debug("hfc debounce: timer reset", "user_id", userID)
        return nil
    }

    // First submission — set the debounce key and enqueue after TTL
    // The key expiry is our signal: we enqueue in a background goroutine
    // that polls expired keys, or use Redis keyspace notifications.
    if err := d.rdb.SetEx(ctx, key, "1", debounceTTL).Err(); err != nil {
        slog.Error("hfc debounce: set key failed", "user_id", userID, "error", err)
    }

    // Enqueue the job to run after the debounce period
    // In production, a separate scheduler checks for expired debounce keys
    // and enqueues the actual HFC job. For simplicity here, we launch
    // a goroutine with a timer.
    go func() {
        select {
        case <-time.After(debounceTTL):
            // Check if the key still exists (it won't if the timer was reset)
            exists, _ := d.rdb.Exists(context.Background(), key).Result()
            if exists == 0 {
                return // was reset, another goroutine will fire
            }
            d.rdb.Del(context.Background(), key)
            if err := d.enqueue(context.Background(), userID); err != nil {
                slog.Error("hfc debounce: enqueue failed",
                    "user_id", userID, "error", err)
            }
        }
    }()

    slog.Debug("hfc debounce: scheduled", "user_id", userID,
        "delay_seconds", debounceTTL.Seconds())
    return nil
}
```

---

## Part 10: Background Email Sending

Emails must not block the HTTP response. Enqueue them into a buffered channel; a pool of workers sends them.

```go
// File: internal/mail/async.go
package mail

import (
    "context"
    "log/slog"
    "sync"
)

type EmailJob struct {
    Type      string // "welcome" | "approved" | "approval_notification"
    ToEmail   string
    ToName    string
    Amount    float64
}

type AsyncMailer struct {
    jobs    chan EmailJob
    sender  Sender
    workers int
    wg      sync.WaitGroup
}

func NewAsyncMailer(sender Sender, workers, bufferSize int) *AsyncMailer {
    m := &AsyncMailer{
        jobs:    make(chan EmailJob, bufferSize),
        sender:  sender,
        workers: workers,
    }
    return m
}

func (m *AsyncMailer) Start(ctx context.Context) {
    for i := 0; i < m.workers; i++ {
        m.wg.Add(1)
        go func() {
            defer m.wg.Done()
            for {
                select {
                case job, ok := <-m.jobs:
                    if !ok {
                        return
                    }
                    m.send(ctx, job)
                case <-ctx.Done():
                    return
                }
            }
        }()
    }
}

func (m *AsyncMailer) send(ctx context.Context, job EmailJob) {
    var err error
    switch job.Type {
    case "approved":
        err = m.sender.SendGrantApproved(job.ToEmail, job.ToName, job.Amount)
    case "welcome":
        err = m.sender.SendWelcome(job.ToEmail, job.ToName)
    }
    if err != nil {
        slog.Error("failed to send email",
            "type", job.Type,
            "to", job.ToEmail,
            "error", err,
        )
    }
}

// Enqueue adds an email job to the queue without blocking.
// Returns false if the buffer is full (email will be dropped and logged).
func (m *AsyncMailer) Enqueue(job EmailJob) bool {
    select {
    case m.jobs <- job:
        return true
    default:
        slog.Warn("email queue full, dropping email",
            "type", job.Type,
            "to", job.ToEmail,
        )
        return false
    }
}

func (m *AsyncMailer) Stop() {
    close(m.jobs)
    m.wg.Wait()
}
```

---

## Part 11: select — Multiplexing Channels

`select` waits on multiple channel operations simultaneously, executing whichever is ready:

```go
// Timeout a long-running job
func runWithTimeout(ctx context.Context, fn func() error) error {
    done := make(chan error, 1)

    go func() {
        done <- fn()
    }()

    select {
    case err := <-done:
        return err
    case <-time.After(30 * time.Second):
        return fmt.Errorf("operation timed out after 30 seconds")
    case <-ctx.Done():
        return ctx.Err()
    }
}
```

### Portal: Graceful Worker Shutdown

```go
func (w *Worker) Run(ctx context.Context) {
    ticker := time.NewTicker(5 * time.Second)
    defer ticker.Stop()

    for {
        select {
        case job := <-w.jobs:
            w.process(ctx, job)

        case <-ticker.C:
            // Periodic health check or queue drain
            w.checkPendingJobs(ctx)

        case <-ctx.Done():
            slog.Info("worker shutting down")
            // Drain remaining jobs before exiting
            for {
                select {
                case job := <-w.jobs:
                    w.process(context.Background(), job) // no timeout on shutdown drain
                default:
                    return
                }
            }
        }
    }
}
```

---

## Part 12: Race Condition Exercises

### Exercise 1: Fix the Cache Race

This cache has a race condition. Find it and fix it using `sync.RWMutex`:

```go
// BROKEN — concurrent map access is not safe
type UpdateCache struct {
    data map[string][]Update
    ttl  map[string]time.Time
}

func (c *UpdateCache) Get(key string) ([]Update, bool) {
    if t, ok := c.ttl[key]; ok && time.Now().Before(t) {
        return c.data[key], true
    }
    return nil, false
}

func (c *UpdateCache) Set(key string, updates []Update) {
    c.data[key] = updates
    c.ttl[key] = time.Now().Add(60 * time.Second)
}
```

Fix:

```go
type UpdateCache struct {
    mu   sync.RWMutex
    data map[string][]Update
    ttl  map[string]time.Time
}

func (c *UpdateCache) Get(key string) ([]Update, bool) {
    c.mu.RLock()
    defer c.mu.RUnlock()
    if t, ok := c.ttl[key]; ok && time.Now().Before(t) {
        return c.data[key], true
    }
    return nil, false
}

func (c *UpdateCache) Set(key string, updates []Update) {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.data[key] = updates
    c.ttl[key] = time.Now().Add(60 * time.Second)
}
```

### Exercise 2: Detect the Goroutine Leak

```go
// LEAKING GOROUTINE
func fetchWithTimeout(url string) ([]byte, error) {
    ch := make(chan []byte) // unbuffered!

    go func() {
        resp, _ := http.Get(url)
        body, _ := io.ReadAll(resp.Body)
        ch <- body // BLOCKS FOREVER if timeout fires first
    }()

    select {
    case body := <-ch:
        return body, nil
    case <-time.After(5 * time.Second):
        return nil, fmt.Errorf("timeout")
        // The goroutine is now stuck trying to send to ch with no receiver
    }
}
```

Fix: use a buffered channel so the goroutine can always send even if the receiver timed out:

```go
ch := make(chan []byte, 1) // buffer of 1 — goroutine never blocks
```

### Exercise 3: Write a Race Detector Test

```go
// File: internal/security/access_test.go
func TestAccessControllerRace(t *testing.T) {
    // Run with: go test -race ./internal/security/...
    ac := NewAccessController(mockRedis, 300, 90*time.Second)

    var wg sync.WaitGroup
    results := make([]bool, 50)

    for i := 0; i < 50; i++ {
        wg.Add(1)
        go func(idx int) {
            defer wg.Done()
            _, ok := ac.Acquire(context.Background())
            results[idx] = ok // concurrent write — is this safe?
        }(i)
    }

    wg.Wait()
    // Count successful acquisitions
    var count int
    for _, ok := range results {
        if ok { count++ }
    }
    t.Logf("acquired %d slots", count)
}
```

---

## Part 13: Concurrency Patterns Summary

| Pattern | When to use | Portal usage |
|---|---|---|
| `go func()` | Fire-and-forget background work | Email sending after approval |
| `sync.WaitGroup` | Wait for a fixed set of goroutines | Parallel applicant data fetch |
| `sync.Mutex` | Protect shared mutable state | In-memory caches |
| `sync.RWMutex` | Read-heavy shared state | Filter cache |
| Buffered channel | Job queue with backpressure | Email and HFC job queue |
| `context.WithTimeout` | Time-bound external calls | Database queries, S3 uploads |
| `context.WithCancel` | Cooperative cancellation | Graceful shutdown |
| `select` | Wait on multiple channels | Worker shutdown drain |
| Worker pool | Process jobs with bounded concurrency | HFC worker |
| Fan-out | Distribute work across goroutines | Parallel report generation |
| Fan-in | Collect results from goroutines | Admin applicant detail |
| Redis + SCAN | Distributed session counting | Access slot system |

---

## Mastery Check

You understand this chapter when you can answer:

1. What is the difference between a buffered channel with capacity 1 and an unbuffered channel? Describe a situation where using the wrong one causes a goroutine leak.
2. The access slot system uses `SCAN` instead of `KEYS` to count active sessions. Why? What problem does `KEYS peace_sme:session:*` cause on a production Redis with 10,000 keys?
3. Write a test that proves `sync.Mutex` prevents a race condition. The test should fail with `-race` if the mutex is removed, and pass with the mutex in place.
4. The email sending goroutine in `AsyncMailer` accepts a `context.Context`. If the server receives `SIGTERM` and cancels the context, what happens to emails that are already in the `jobs` channel but have not been sent yet? Write the shutdown code that ensures those emails are sent before the process exits.
5. Describe the HFC debounce in your own words. A user saves their grant form three times in 20 seconds. When does the HFC job actually run? What would happen without the debounce if 50 users all saved their forms simultaneously?
