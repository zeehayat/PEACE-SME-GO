# Chapter 10: Redis, Caching, Access Slots, and Background Jobs

## Purpose

Redis supports three separate concerns in the PEACE SME portal: JSON response caching (reduce DB load), concurrent applicant session slots (limit simultaneous users), and background job queuing (HFC scoring and email delivery). This chapter teaches each concern with full implementations using `go-redis/v9`.

---

## Redis Data Structures

Redis is not just a key-value store. It has multiple data structures, each suited to specific problems.

### Strings

The most basic type. Stores a single value (text, number, or serialized JSON).

```
SET peace_sme:cache:dashboard "{\"total\":500}" EX 60
GET peace_sme:cache:dashboard
DEL peace_sme:cache:dashboard
```

The PEACE SME portal uses strings for:
- Cached JSON responses (dashboard stats, filter options, announcements, FAQs)
- Session slot keys (`peace_sme:session:<session_id>`)
- HFC debounce keys (`peace_sme:hfc_debounce:<user_id>`)

### Sets

Unordered collections of unique strings.

```
SADD peace_sme:active_sessions session_abc session_def session_xyz
SCARD peace_sme:active_sessions   # count: 3
SISMEMBER peace_sme:active_sessions session_abc   # 1 = yes
SREM peace_sme:active_sessions session_abc
```

The portal uses a set to count active sessions (alternative to KEYS pattern scanning).

### Hash

A map of field-value pairs stored under one key.

```
HSET peace_sme:user:42 last_seen "2026-06-17T09:00:00Z" country "PK"
HGET peace_sme:user:42 last_seen
HGETALL peace_sme:user:42
```

### Sorted Sets

Like sets, but each member has a numeric score. Members are ranked by score.

```
ZADD peace_sme:hfc_queue 95 "user:42"   # score=95 (CRITICAL)
ZADD peace_sme:hfc_queue 30 "user:17"   # score=30 (MEDIUM)
ZRANGE peace_sme:hfc_queue 0 -1 WITHSCORES   # lowest score first
ZREVRANGE peace_sme:hfc_queue 0 9 WITHSCORES # top 10 highest risk
```

The portal could use sorted sets to maintain a priority queue of HFC evaluations ordered by risk score.

### Pub/Sub

Publisher-subscriber messaging. Used for real-time notifications.

```
SUBSCRIBE peace_sme:grant_approved
PUBLISH peace_sme:grant_approved "{\"user_id\":42,\"amount\":500000}"
```

---

## Go Redis Client Setup

Install `go-redis/v9`:

```bash
go get github.com/redis/go-redis/v9
```

```go
// internal/cache/client.go
package cache

import (
    "context"
    "fmt"

    "github.com/redis/go-redis/v9"
)

// NewClient creates a Redis client from a URL.
// URL format: redis://[:password@]host[:port][/db]
// Example:    redis://localhost:6379/0
func NewClient(redisURL string) (*redis.Client, error) {
    opts, err := redis.ParseURL(redisURL)
    if err != nil {
        return nil, fmt.Errorf("invalid Redis URL %q: %w", redisURL, err)
    }

    client := redis.NewClient(opts)

    // Verify connection at startup
    ctx := context.Background()
    if err := client.Ping(ctx).Err(); err != nil {
        return nil, fmt.Errorf("Redis ping failed: %w", err)
    }

    return client, nil
}
```

---

## The Cache Wrapper

Build a thin wrapper with JSON serialization, prefix management, and cache-aside helpers:

```go
// internal/cache/cache.go
package cache

import (
    "context"
    "encoding/json"
    "errors"
    "fmt"
    "time"

    "github.com/redis/go-redis/v9"
)

// ErrCacheMiss is returned when a key is not found in the cache.
var ErrCacheMiss = errors.New("cache miss")

// Cache wraps a Redis client with JSON helpers and key prefix management.
type Cache struct {
    client *redis.Client
    prefix string
}

// New creates a Cache with the given Redis client and key prefix.
// In PEACE SME, prefix = "peace_sme" (from CACHE_PREFIX env var).
func New(client *redis.Client, prefix string) *Cache {
    return &Cache{client: client, prefix: prefix}
}

// key prefixes a cache key with the configured namespace.
func (c *Cache) key(k string) string {
    return fmt.Sprintf("%s:%s", c.prefix, k)
}

// GetJSON retrieves a JSON-encoded value and unmarshals it into dst.
// Returns ErrCacheMiss if the key does not exist.
func (c *Cache) GetJSON(ctx context.Context, k string, dst interface{}) error {
    data, err := c.client.Get(ctx, c.key(k)).Bytes()
    if err != nil {
        if errors.Is(err, redis.Nil) {
            return ErrCacheMiss
        }
        return fmt.Errorf("cache GetJSON %q: %w", k, err)
    }
    if err := json.Unmarshal(data, dst); err != nil {
        return fmt.Errorf("cache GetJSON %q: unmarshal: %w", k, err)
    }
    return nil
}

// SetJSON marshals value to JSON and stores it with a TTL.
func (c *Cache) SetJSON(ctx context.Context, k string, value interface{}, ttl time.Duration) error {
    data, err := json.Marshal(value)
    if err != nil {
        return fmt.Errorf("cache SetJSON %q: marshal: %w", k, err)
    }
    if err := c.client.Set(ctx, c.key(k), data, ttl).Err(); err != nil {
        return fmt.Errorf("cache SetJSON %q: %w", k, err)
    }
    return nil
}

// Delete removes a specific cache key.
func (c *Cache) Delete(ctx context.Context, k string) error {
    return c.client.Del(ctx, c.key(k)).Err()
}

// DeletePattern removes all keys matching a glob pattern.
// Use sparingly — SCAN is O(N) over the keyspace.
func (c *Cache) DeletePattern(ctx context.Context, pattern string) (int64, error) {
    fullPattern := c.key(pattern)
    var cursor uint64
    var deleted int64
    for {
        keys, nextCursor, err := c.client.Scan(ctx, cursor, fullPattern, 100).Result()
        if err != nil {
            return deleted, fmt.Errorf("cache DeletePattern %q: scan: %w", pattern, err)
        }
        if len(keys) > 0 {
            n, err := c.client.Del(ctx, keys...).Result()
            if err != nil {
                return deleted, fmt.Errorf("cache DeletePattern %q: del: %w", pattern, err)
            }
            deleted += n
        }
        cursor = nextCursor
        if cursor == 0 {
            break
        }
    }
    return deleted, nil
}

// SetNX sets a key only if it does not already exist. Returns true if set.
// Used for debouncing and distributed locking.
func (c *Cache) SetNX(ctx context.Context, k string, value string, ttl time.Duration) (bool, error) {
    return c.client.SetNX(ctx, c.key(k), value, ttl).Result()
}

// Exists checks if a key exists.
func (c *Cache) Exists(ctx context.Context, k string) (bool, error) {
    n, err := c.client.Exists(ctx, c.key(k)).Result()
    if err != nil {
        return false, err
    }
    return n > 0, nil
}
```

---

## The Cache-Aside Pattern

Cache-aside (lazy loading) is the pattern used by the Flask app for all caches:

```
1. Request arrives
2. Check cache for key
3. If hit: return cached value (fast)
4. If miss: query DB, store result in cache with TTL, return result
```

```go
// internal/content/service.go — using cache-aside for announcements
package content

import (
    "context"
    "errors"
    "time"

    "peace-sme-go/internal/cache"
)

type Update struct {
    UpdateID  int64  `json:"update_id"`
    Title     string `json:"title"`
    Body      string `json:"body"`
    Tag       string `json:"tag"`
    CreatedAt string `json:"created_at"`
}

type UpdateRepository interface {
    GetActiveUpdates(ctx context.Context) ([]Update, error)
    CreateUpdate(ctx context.Context, u Update) (int64, error)
    UpdateUpdate(ctx context.Context, u Update) error
    DeleteUpdate(ctx context.Context, id int64) error
}

type UpdateService struct {
    repo    UpdateRepository
    cache   *cache.Cache
    cacheTTL time.Duration
}

func NewUpdateService(repo UpdateRepository, cache *cache.Cache, cacheTTLSec int) *UpdateService {
    return &UpdateService{
        repo:    repo,
        cache:   cache,
        cacheTTL: time.Duration(cacheTTLSec) * time.Second,
    }
}

const updatesKey = "announcements"

// GetActiveUpdates returns all active announcements, from cache if available.
func (s *UpdateService) GetActiveUpdates(ctx context.Context) ([]Update, error) {
    // 1. Try cache first
    var updates []Update
    err := s.cache.GetJSON(ctx, updatesKey, &updates)
    if err == nil {
        return updates, nil   // Cache hit
    }
    if !errors.Is(err, cache.ErrCacheMiss) {
        // Cache error (Redis down?): log and fall through to DB
        // In production: log.Printf("cache error: %v", err)
    }

    // 2. Cache miss — query the database
    updates, err = s.repo.GetActiveUpdates(ctx)
    if err != nil {
        return nil, err
    }

    // 3. Store in cache for CACHE_TTL_UPDATES seconds (default 3600)
    _ = s.cache.SetJSON(ctx, updatesKey, updates, s.cacheTTL)

    return updates, nil
}

// CreateUpdate inserts a new announcement and invalidates the cache.
func (s *UpdateService) CreateUpdate(ctx context.Context, u Update) (int64, error) {
    id, err := s.repo.CreateUpdate(ctx, u)
    if err != nil {
        return 0, err
    }
    // Invalidate cache so next request reads fresh data from DB
    _ = s.cache.Delete(ctx, updatesKey)
    return id, nil
}

// DeleteUpdate removes an announcement and invalidates the cache.
func (s *UpdateService) DeleteUpdate(ctx context.Context, id int64) error {
    if err := s.repo.DeleteUpdate(ctx, id); err != nil {
        return err
    }
    _ = s.cache.Delete(ctx, updatesKey)
    return nil
}
```

### Cache Key Strategy

All cache keys used in the portal:

```go
// internal/cache/keys.go
package cache

import "fmt"

const (
    KeyAnnouncements   = "announcements"
    KeyFAQs            = "faqs"
    KeyFilterOptions   = "report:filter_options"
    KeyDashboardStats  = "admin:dashboard_stats"
)

// SessionKey returns the key for a specific session slot.
func SessionKey(sessionID string) string {
    return fmt.Sprintf("session:%s", sessionID)
}

// HFCDebounceKey returns the debounce key for a user's HFC scoring.
func HFCDebounceKey(userID int64) string {
    return fmt.Sprintf("hfc_debounce:%d", userID)
}
```

---

## The Concurrent Session Slot System

The portal limits concurrent applicant sessions to `MAX_ACTIVE_APPLICANTS` (default 300). Each session occupies a Redis key that expires after `ACCESS_SLOT_TTL_SEC` (default 90 seconds).

### How It Works

```
Request arrives from user
  |
  └── Count SCAN keys matching peace_sme:session:* → currentCount
        |
        ├── currentCount >= MAX_ACTIVE_APPLICANTS?
        |     → 429 Too Many Requests (waiting room)
        |
        └── SET peace_sme:session:<session_id> "1" EX 90 NX
              |
              ├── SET returned false? (key already exists, user refreshing)
              |     → 200 OK (already has a slot)
              |
              └── SET returned true? (new slot allocated)
                    → 200 OK (slot granted)
```

```go
// internal/security/access_control.go
package security

import (
    "context"
    "crypto/rand"
    "encoding/hex"
    "fmt"
    "net/http"
    "time"

    "github.com/redis/go-redis/v9"
    "peace-sme-go/internal/config"
)

// AccessController manages concurrent applicant session slots.
type AccessController struct {
    redis  *redis.Client
    cfg    *config.Config
    prefix string
}

func NewAccessController(r *redis.Client, cfg *config.Config, prefix string) *AccessController {
    return &AccessController{redis: r, cfg: cfg, prefix: prefix}
}

// sessionKey returns the full Redis key for a session ID.
func (a *AccessController) sessionKey(sessionID string) string {
    return fmt.Sprintf("%s:session:%s", a.prefix, sessionID)
}

// sessionPattern returns the pattern for scanning all session keys.
func (a *AccessController) sessionPattern() string {
    return fmt.Sprintf("%s:session:*", a.prefix)
}

// CheckAndAllocate either allocates a new session slot or renews an existing one.
// Returns the session ID and whether the user is allowed in.
func (a *AccessController) CheckAndAllocate(ctx context.Context, existingSessionID string) (string, bool, error) {
    if !a.cfg.AccessControlEnabled {
        return "bypass", true, nil
    }

    ttl := time.Duration(a.cfg.AccessSlotTTLSec) * time.Second

    // 1. If user already has a session, try to renew it
    if existingSessionID != "" {
        key := a.sessionKey(existingSessionID)
        renewed, err := a.redis.Expire(ctx, key, ttl).Result()
        if err == nil && renewed {
            return existingSessionID, true, nil
        }
        // Key expired or doesn't exist — fall through to allocate a new slot
    }

    // 2. Count current active sessions
    count, err := a.countActiveSessions(ctx)
    if err != nil {
        // If Redis is unavailable, fail open (allow traffic) to prevent lockout
        return "", true, nil
    }

    if count >= int64(a.cfg.MaxActiveApplicants) {
        return "", false, nil // Waiting room
    }

    // 3. Allocate a new session slot
    newID, err := generateSessionID()
    if err != nil {
        return "", false, fmt.Errorf("failed to generate session ID: %w", err)
    }

    if err := a.redis.Set(ctx, a.sessionKey(newID), "1", ttl).Err(); err != nil {
        return "", false, fmt.Errorf("failed to allocate session slot: %w", err)
    }

    return newID, true, nil
}

// countActiveSessions scans Redis for all session keys matching the pattern.
func (a *AccessController) countActiveSessions(ctx context.Context) (int64, error) {
    var count int64
    var cursor uint64
    for {
        keys, nextCursor, err := a.redis.Scan(ctx, cursor, a.sessionPattern(), 100).Result()
        if err != nil {
            return 0, err
        }
        count += int64(len(keys))
        cursor = nextCursor
        if cursor == 0 {
            break
        }
    }
    return count, nil
}

// generateSessionID returns a random 16-byte hex string.
func generateSessionID() (string, error) {
    b := make([]byte, 16)
    if _, err := rand.Read(b); err != nil {
        return "", err
    }
    return hex.EncodeToString(b), nil
}

// Middleware returns an HTTP middleware that enforces the access slot system.
func (a *AccessController) Middleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        // Read existing session from cookie or header
        existingID := r.Header.Get("X-Session-ID")

        sessionID, allowed, err := a.CheckAndAllocate(r.Context(), existingID)
        if err != nil {
            // Log error, fail open
            next.ServeHTTP(w, r)
            return
        }

        if !allowed {
            w.Header().Set("Content-Type", "application/json")
            w.WriteHeader(http.StatusTooManyRequests)
            w.Write([]byte(`{"error":"server is at capacity, please try again later","in_queue":true}`))
            return
        }

        // Attach session ID to response so client can send it back
        w.Header().Set("X-Session-ID", sessionID)

        // Also expose via the access-status endpoint
        ctx := context.WithValue(r.Context(), contextKeySessionID, sessionID)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}

type contextKey string
const contextKeySessionID contextKey = "session_id"
```

### The Access Status Endpoint

```go
// GET /api/system/access-status
func (h *SecurityHandler) AccessStatus(w http.ResponseWriter, r *http.Request) {
    existingID := r.Header.Get("X-Session-ID")
    sessionID, allowed, _ := h.ac.CheckAndAllocate(r.Context(), existingID)

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(map[string]interface{}{
        "session_id":  sessionID,
        "server_time": time.Now().UTC().Format(time.RFC3339),
        "in_queue":    !allowed,
    })
}
```

---

## Redis-Based HFC Debouncing

When an applicant updates their grant quickly (e.g., saves multiple times), we don't want to flood the HFC queue with many jobs. The debounce pattern uses `SetNX` to prevent re-enqueueing within a time window.

```go
// internal/hfc/enqueuer.go
package hfc

import (
    "context"
    "encoding/json"
    "fmt"
    "time"

    "github.com/redis/go-redis/v9"
    "peace-sme-go/internal/config"
)

// HFCJob is the task payload stored in Redis for background processing.
type HFCJob struct {
    UserID            int64  `json:"user_id"`
    TriggeredByAdmin  bool   `json:"triggered_by_admin"`
    EnqueuedAt        string `json:"enqueued_at"`
}

// RedisEnqueuer enqueues HFC jobs into a Redis list (simple queue).
type RedisEnqueuer struct {
    redis     *redis.Client
    prefix    string
    queueKey  string
    debounceSec int
}

func NewRedisEnqueuer(r *redis.Client, cfg *config.Config) *RedisEnqueuer {
    return &RedisEnqueuer{
        redis:       r,
        prefix:      cfg.CachePrefix,
        queueKey:    cfg.CachePrefix + ":queue:hfc",
        debounceSec: cfg.HFCDebounceSec,
    }
}

// debounceKey returns the Redis key used to gate re-enqueuing for a user.
func (e *RedisEnqueuer) debounceKey(userID int64) string {
    return fmt.Sprintf("%s:hfc_debounce:%d", e.prefix, userID)
}

// EnqueueRecalculate enqueues an HFC scoring job for a user.
// If the same user was enqueued within the debounce window, this is a no-op.
func (e *RedisEnqueuer) EnqueueRecalculate(ctx context.Context, userID int64) error {
    // 1. Debounce: only enqueue if no key exists for this user
    debKey := e.debounceKey(userID)
    ttl := time.Duration(e.debounceSec) * time.Second

    set, err := e.redis.SetNX(ctx, debKey, "1", ttl).Result()
    if err != nil {
        return fmt.Errorf("HFC debounce check failed: %w", err)
    }
    if !set {
        // Key already exists — debounce in effect, skip enqueue
        return nil
    }

    // 2. Build the job payload
    job := HFCJob{
        UserID:           userID,
        TriggeredByAdmin: false,
        EnqueuedAt:       time.Now().UTC().Format(time.RFC3339),
    }
    data, err := json.Marshal(job)
    if err != nil {
        return fmt.Errorf("HFC job marshal: %w", err)
    }

    // 3. Push to queue (Redis list, RPUSH = push to the right = FIFO queue)
    if err := e.redis.RPush(ctx, e.queueKey, data).Err(); err != nil {
        return fmt.Errorf("HFC enqueue RPUSH: %w", err)
    }

    return nil
}

// EnqueueForAdmin bypasses the debounce (admin-triggered rescoring).
func (e *RedisEnqueuer) EnqueueForAdmin(ctx context.Context, userID int64) error {
    job := HFCJob{
        UserID:           userID,
        TriggeredByAdmin: true,
        EnqueuedAt:       time.Now().UTC().Format(time.RFC3339),
    }
    data, _ := json.Marshal(job)
    return e.redis.RPush(ctx, e.queueKey, data).Err()
}
```

---

## Background Workers with Goroutines

The portal needs workers to:
1. Process HFC scoring jobs from the Redis queue
2. Send approval notification emails via Brevo

Here is the full worker implementation using goroutines:

```go
// internal/worker/manager.go
package worker

import (
    "context"
    "encoding/json"
    "log"
    "sync"
    "time"

    "github.com/redis/go-redis/v9"
)

// Manager coordinates background workers.
type Manager struct {
    redis    *redis.Client
    hfcKey   string
    emailKey string
    hfcProc  HFCProcessor
    mailProc MailProcessor
    wg       sync.WaitGroup
}

// HFCProcessor executes the HFC scoring logic.
type HFCProcessor interface {
    ProcessJob(ctx context.Context, job HFCJob) error
}

// MailProcessor sends emails.
type MailProcessor interface {
    ProcessJob(ctx context.Context, job EmailJob) error
}

// HFCJob is the dequeued task payload.
type HFCJob struct {
    UserID           int64  `json:"user_id"`
    TriggeredByAdmin bool   `json:"triggered_by_admin"`
    EnqueuedAt       string `json:"enqueued_at"`
}

// EmailJob is the dequeued email task payload.
type EmailJob struct {
    RecipientEmail string `json:"recipient_email"`
    Subject        string `json:"subject"`
    Body           string `json:"body"`
    EmailType      string `json:"email_type"` // "welcome", "approval", "notification"
}

func NewManager(r *redis.Client, prefix string, hfcProc HFCProcessor, mailProc MailProcessor) *Manager {
    return &Manager{
        redis:    r,
        hfcKey:   prefix + ":queue:hfc",
        emailKey: prefix + ":queue:emails",
        hfcProc:  hfcProc,
        mailProc: mailProc,
    }
}

// Start launches background worker goroutines.
// Cancel the context to signal graceful shutdown.
func (m *Manager) Start(ctx context.Context, hfcWorkers, emailWorkers int) {
    for i := 0; i < hfcWorkers; i++ {
        m.wg.Add(1)
        go m.hfcWorkerLoop(ctx, i)
    }
    for i := 0; i < emailWorkers; i++ {
        m.wg.Add(1)
        go m.emailWorkerLoop(ctx, i)
    }
    log.Printf("Worker manager started: %d HFC workers, %d email workers", hfcWorkers, emailWorkers)
}

// Stop waits for all workers to finish their current jobs.
func (m *Manager) Stop() {
    log.Println("Worker manager: waiting for workers to drain...")
    m.wg.Wait()
    log.Println("Worker manager: all workers stopped.")
}

// hfcWorkerLoop is the blocking loop for one HFC worker goroutine.
func (m *Manager) hfcWorkerLoop(ctx context.Context, workerID int) {
    defer m.wg.Done()
    log.Printf("HFC worker %d started", workerID)

    for {
        // BLPOP blocks until a job is available or the context is cancelled
        // The timeout (5s) prevents deadlock if context cancellation is delayed
        result, err := m.redis.BLPop(ctx, 5*time.Second, m.hfcKey).Result()
        if err != nil {
            if ctx.Err() != nil {
                // Context was cancelled — normal shutdown
                log.Printf("HFC worker %d shutting down", workerID)
                return
            }
            if err == redis.Nil {
                // Timeout — no jobs available, loop and try again
                continue
            }
            log.Printf("HFC worker %d: BLPOP error: %v", workerID, err)
            time.Sleep(time.Second) // Back off on error
            continue
        }

        // result[0] = key name, result[1] = the job JSON
        var job HFCJob
        if err := json.Unmarshal([]byte(result[1]), &job); err != nil {
            log.Printf("HFC worker %d: failed to unmarshal job: %v", workerID, err)
            continue
        }

        log.Printf("HFC worker %d: processing user %d", workerID, job.UserID)
        if err := m.hfcProc.ProcessJob(ctx, job); err != nil {
            log.Printf("HFC worker %d: job failed for user %d: %v", workerID, job.UserID, err)
            // In production: push to a dead-letter queue or retry queue
        }
    }
}

// emailWorkerLoop is the blocking loop for one email worker goroutine.
func (m *Manager) emailWorkerLoop(ctx context.Context, workerID int) {
    defer m.wg.Done()
    log.Printf("Email worker %d started", workerID)

    for {
        result, err := m.redis.BLPop(ctx, 5*time.Second, m.emailKey).Result()
        if err != nil {
            if ctx.Err() != nil {
                log.Printf("Email worker %d shutting down", workerID)
                return
            }
            if err == redis.Nil {
                continue
            }
            log.Printf("Email worker %d: BLPOP error: %v", workerID, err)
            time.Sleep(time.Second)
            continue
        }

        var job EmailJob
        if err := json.Unmarshal([]byte(result[1]), &job); err != nil {
            log.Printf("Email worker %d: unmarshal error: %v", workerID, err)
            continue
        }

        log.Printf("Email worker %d: sending %s to %s", workerID, job.EmailType, job.RecipientEmail)
        if err := m.mailProc.ProcessJob(ctx, job); err != nil {
            log.Printf("Email worker %d: send failed: %v", workerID, err)
        }
    }
}
```

### Starting Workers in main.go

```go
// cmd/server/main.go
func main() {
    cfg, err := config.Load()
    if err != nil {
        log.Fatalf("config: %v", err)
    }

    redisClient, err := cache.NewClient(cfg.RedisURL)
    if err != nil {
        log.Fatalf("redis: %v", err)
    }
    defer redisClient.Close()

    db, err := db.NewPool(cfg.DatabaseURL, cfg.DBPoolMin, cfg.DBPoolMax)
    if err != nil {
        log.Fatalf("database: %v", err)
    }
    defer db.Close()

    // Build processors
    hfcProcessor := hfc.NewProcessor(db, redisClient, cfg)
    mailProcessor := mail.NewProcessor(cfg)

    // Start background workers
    workerMgr := worker.NewManager(redisClient, cfg.CachePrefix, hfcProcessor, mailProcessor)
    ctx, cancel := context.WithCancel(context.Background())

    workerMgr.Start(ctx,
        2, // 2 HFC workers
        1, // 1 email worker
    )

    // Start HTTP server
    srv := &http.Server{
        Addr:    fmt.Sprintf(":%d", cfg.Port),
        Handler: buildRouter(cfg, db, redisClient),
    }

    // Graceful shutdown on SIGINT/SIGTERM
    sigCh := make(chan os.Signal, 1)
    signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

    go func() {
        <-sigCh
        log.Println("Shutting down...")
        cancel()                              // signal workers to stop
        srv.Shutdown(context.Background())    // stop accepting new requests
    }()

    log.Printf("Server listening on :%d", cfg.Port)
    if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
        log.Fatalf("server: %v", err)
    }

    workerMgr.Stop() // wait for in-flight jobs to complete
    log.Println("Shutdown complete.")
}
```

---

## HFC Scoring Processor

The HFC processor implements the fraud detection rules:

```go
// internal/hfc/processor.go
package hfc

import (
    "context"
    "fmt"
    "log"
    "time"

    "github.com/jackc/pgx/v5/pgxpool"
    "peace-sme-go/internal/worker"
)

// RiskBand maps a score to a risk level.
func RiskBand(score int) string {
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

// Rule represents a single HFC scoring rule.
type Rule struct {
    Code        string
    Points      int
    Description string
}

// All rules with their point values.
var Rules = []Rule{
    {"DUPLICATE_CNIC",       50, "Duplicate CNIC detected"},
    {"DUPLICATE_EMAIL",      20, "Duplicate email address"},
    {"DUPLICATE_MOBILE",     20, "Duplicate mobile number"},
    {"MISSING_PROFILE",      30, "Business profile not completed"},
    {"MISSING_DOCUMENTS",    25, "Required documents not uploaded"},
    {"MISSING_MEDIA",        10, "Grant media not uploaded"},
    {"DISTRICT_OUT_OF_SCOPE",40, "Business district not in allowed list"},
    {"AMOUNT_EXCEEDS_LIMIT", 15, "Grant amount exceeds threshold"},
    {"FAST_SUBMISSION",      10, "Application submitted very quickly"},
    {"MISSING_EOI",          15, "Missing expression of interest"},
}

// Processor implements HFC scoring.
type Processor struct {
    db  *pgxpool.Pool
}

func NewProcessor(db *pgxpool.Pool) *Processor {
    return &Processor{db: db}
}

// ProcessJob is called by the worker goroutine when an HFC job is dequeued.
func (p *Processor) ProcessJob(ctx context.Context, job worker.HFCJob) error {
    return p.Calculate(ctx, job.UserID)
}

// Calculate runs all HFC rules for a user and stores the result.
func (p *Processor) Calculate(ctx context.Context, userID int64) error {
    // Gather data needed for rule evaluation
    data, err := p.gatherUserData(ctx, userID)
    if err != nil {
        return fmt.Errorf("HFC gather data: %w", err)
    }

    // Evaluate each rule
    var triggeredRules []string
    totalScore := 0

    for _, rule := range Rules {
        if triggered, points := p.evaluateRule(rule, data); triggered {
            triggeredRules = append(triggeredRules, rule.Code)
            totalScore += points
        }
    }

    riskLevel := RiskBand(totalScore)

    // Store evaluation result
    return p.storeEvaluation(ctx, userID, data.GrantID, totalScore, riskLevel, triggeredRules)
}

type UserData struct {
    GrantID          int64
    CNIC             string
    Email            string
    Mobile           string
    HasBusiness      bool
    DocumentCount    int
    HasGrantMedia    bool
    District         string
    GrantAmount      float64
    ApplicationDate  time.Time
    RegistrationDate time.Time
    HasEOI           bool

    // Duplicate check results
    DuplicateCNICs   int
    DuplicateEmails  int
    DuplicateMobiles int
}

// AllowedDistricts matches the business validation.
var AllowedDistricts = map[string]bool{
    "Swat": true, "Shangla": true, "Upper Dir": true,
    "Upper Chitral": true, "Lower Chitral": true,
}

// RequiredDocCount is the number of required document types.
const RequiredDocCount = 5

// MaxGrantAmount is the threshold for the amount rule.
const MaxGrantAmount = 1_000_000.0

// MinApplicationMinutes — faster than this is suspicious.
const MinApplicationMinutes = 10.0

func (p *Processor) evaluateRule(rule Rule, d *UserData) (bool, int) {
    switch rule.Code {
    case "DUPLICATE_CNIC":
        return d.DuplicateCNICs > 1, rule.Points
    case "DUPLICATE_EMAIL":
        return d.DuplicateEmails > 1, rule.Points
    case "DUPLICATE_MOBILE":
        return d.DuplicateMobiles > 1, rule.Points
    case "MISSING_PROFILE":
        return !d.HasBusiness, rule.Points
    case "MISSING_DOCUMENTS":
        return d.DocumentCount < RequiredDocCount, rule.Points
    case "MISSING_MEDIA":
        return !d.HasGrantMedia, rule.Points
    case "DISTRICT_OUT_OF_SCOPE":
        return !AllowedDistricts[d.District], rule.Points
    case "AMOUNT_EXCEEDS_LIMIT":
        return d.GrantAmount > MaxGrantAmount, rule.Points
    case "FAST_SUBMISSION":
        diff := d.ApplicationDate.Sub(d.RegistrationDate).Minutes()
        return diff < MinApplicationMinutes, rule.Points
    case "MISSING_EOI":
        return !d.HasEOI, rule.Points
    }
    return false, 0
}

func (p *Processor) gatherUserData(ctx context.Context, userID int64) (*UserData, error) {
    d := &UserData{}

    // Gather user basics
    err := p.db.QueryRow(ctx, `
        SELECT cnic, email_address, mobile_no, created_at
        FROM users WHERE user_id=$1
    `, userID).Scan(&d.CNIC, &d.Email, &d.Mobile, &d.RegistrationDate)
    if err != nil {
        return nil, fmt.Errorf("gather user: %w", err)
    }

    // Check for business profile
    var bizDistrict string
    err = p.db.QueryRow(ctx, `
        SELECT business_location_district FROM businesses WHERE user_id=$1
    `, userID).Scan(&bizDistrict)
    d.HasBusiness = err == nil
    d.District = bizDistrict

    // Get grant info
    var eoi string
    var amount float64
    var appDate time.Time
    err = p.db.QueryRow(ctx, `
        SELECT grant_id, grant_required, application_date, expression_of_interest
        FROM grants WHERE user_id=$1
    `, userID).Scan(&d.GrantID, &amount, &appDate, &eoi)
    if err == nil {
        d.GrantAmount = amount
        d.ApplicationDate = appDate
        d.HasEOI = eoi != "[]" && eoi != "" && eoi != "null"
    }

    // Count uploaded documents
    p.db.QueryRow(ctx, `
        SELECT COUNT(*) FROM business_documents
        WHERE user_id=$1 AND document_type IN (
            'CNIC (front)', 'CNIC (back)', 'Business registration certificate',
            'Tax certificate / NTN', 'Bank statement'
        )
    `, userID).Scan(&d.DocumentCount)

    // Check grant media
    var mediaCount int
    p.db.QueryRow(ctx, `SELECT COUNT(*) FROM grant_media WHERE user_id=$1`, userID).Scan(&mediaCount)
    d.HasGrantMedia = mediaCount > 0

    // Duplicate checks
    p.db.QueryRow(ctx, `SELECT COUNT(*) FROM users WHERE cnic=$1`, d.CNIC).Scan(&d.DuplicateCNICs)
    p.db.QueryRow(ctx, `SELECT COUNT(*) FROM users WHERE email_address=$1`, d.Email).Scan(&d.DuplicateEmails)
    p.db.QueryRow(ctx, `SELECT COUNT(*) FROM users WHERE mobile_no=$1 AND mobile_no != ''`, d.Mobile).Scan(&d.DuplicateMobiles)

    return d, nil
}

func (p *Processor) storeEvaluation(ctx context.Context, userID, grantID int64, score int, risk string, triggered []string) error {
    triggeredJSON := "[]"
    if len(triggered) > 0 {
        import_json, _ := json.Marshal(triggered)
        triggeredJSON = string(import_json)
    }

    _, err := p.db.Exec(ctx, `
        INSERT INTO hfc_evaluations (user_id, grant_id, final_score, risk_level, rules_triggered, evaluated_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
    `, userID, grantID, score, risk, triggeredJSON)
    if err != nil {
        return fmt.Errorf("store evaluation: %w", err)
    }

    _, err = p.db.Exec(ctx, `
        UPDATE grants SET
            hfc_score=$1, hfc_risk_level=$2, hfc_status='HFC_Complete', hfc_last_evaluated_at=NOW()
        WHERE user_id=$3
    `, score, risk, userID)
    if err != nil {
        return fmt.Errorf("update grant HFC fields: %w", err)
    }

    log.Printf("HFC complete: user=%d score=%d risk=%s rules=%v", userID, score, risk, triggered)
    return nil
}
```

---

## Dashboard Stats with Caching

```go
// internal/report/dashboard.go
package report

import (
    "context"
    "errors"
    "time"

    "peace-sme-go/internal/cache"
)

type DashboardStats struct {
    TotalUsers      int `json:"total_users"`
    TotalBusinesses int `json:"total_businesses"`
    TotalGrants     int `json:"total_grants"`
    TotalApproved   int `json:"total_approved"`
    HFCPending      int `json:"hfc_pending"`
}

type DashboardService struct {
    db    DBQuerier
    cache *cache.Cache
    ttl   time.Duration
}

func (s *DashboardService) GetStats(ctx context.Context) (*DashboardStats, error) {
    const cacheKey = "admin:dashboard_stats"

    // 1. Try cache
    var stats DashboardStats
    if err := s.cache.GetJSON(ctx, cacheKey, &stats); err == nil {
        return &stats, nil
    } else if !errors.Is(err, cache.ErrCacheMiss) {
        // Log cache error but continue to DB
    }

    // 2. Query DB
    err := s.db.QueryRow(ctx, `
        SELECT
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(*) FROM businesses) AS total_businesses,
            (SELECT COUNT(*) FROM grants) AS total_grants,
            (SELECT COUNT(*) FROM grants WHERE status='Approved') AS total_approved,
            (SELECT COUNT(*) FROM grants WHERE hfc_status='HFC_Pending') AS hfc_pending
    `).Scan(
        &stats.TotalUsers,
        &stats.TotalBusinesses,
        &stats.TotalGrants,
        &stats.TotalApproved,
        &stats.HFCPending,
    )
    if err != nil {
        return nil, err
    }

    // 3. Cache for 60 seconds (CACHE_TTL_UPDATES)
    _ = s.cache.SetJSON(ctx, cacheKey, stats, s.ttl)

    return &stats, nil
}
```

---

## Go Concurrency Concepts Applied

### Goroutines

```go
// Starting a goroutine — prefixing a function call with "go"
go m.hfcWorkerLoop(ctx, workerID)
// Returns immediately; hfcWorkerLoop runs concurrently
```

The Go scheduler multiplexes goroutines onto OS threads (M:N scheduling). Goroutines start with ~2KB stack (vs ~1MB for OS threads), so you can run thousands.

### sync.WaitGroup

```go
var wg sync.WaitGroup

// Before launching a goroutine:
wg.Add(1)
go func() {
    defer wg.Done()  // called when goroutine exits
    // ... work ...
}()

// Block until all goroutines call Done():
wg.Wait()
```

Used in `Manager.Stop()` to ensure all in-flight jobs complete before the process exits.

### Channels

```go
// Unbuffered: sender blocks until receiver reads
ch := make(chan string)

// Buffered: sender blocks only if buffer is full
ch := make(chan string, 10)

// Sending
ch <- "value"

// Receiving
val := <-ch

// Closing signals "no more values"
close(ch)

// Range over channel (exits when channel is closed and drained)
for val := range ch {
    fmt.Println(val)
}
```

The worker uses Redis `BLPOP` instead of Go channels for queuing because:
- Redis queues persist across process restarts
- Redis queues allow multiple workers on different machines
- Channels are in-memory only — jobs are lost if the process crashes

### Select

```go
select {
case job := <-hfcChan:
    processHFCJob(job)
case email := <-emailChan:
    sendEmail(email)
case <-ctx.Done():
    // Shutdown signal received
    return
case <-time.After(5 * time.Second):
    // No activity in 5 seconds — loop and try again
}
```

---

## Testing Cache Behavior

```go
// internal/cache/cache_test.go
package cache_test

import (
    "context"
    "errors"
    "testing"
    "time"

    "peace-sme-go/internal/cache"
)

// TestCacheSetAndGet verifies the round-trip of SetJSON/GetJSON.
func TestCacheSetAndGet(t *testing.T) {
    // In real tests, use a test Redis instance (e.g., via testcontainers or miniredis)
    // Here we illustrate with miniredis

    mr := miniredis.RunT(t) // Starts an in-memory fake Redis
    client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
    c := cache.New(client, "test")
    ctx := context.Background()

    type Data struct {
        Name  string `json:"name"`
        Count int    `json:"count"`
    }

    original := Data{Name: "Swat", Count: 42}
    if err := c.SetJSON(ctx, "districts:swat", original, time.Minute); err != nil {
        t.Fatalf("SetJSON failed: %v", err)
    }

    var retrieved Data
    if err := c.GetJSON(ctx, "districts:swat", &retrieved); err != nil {
        t.Fatalf("GetJSON failed: %v", err)
    }

    if retrieved.Name != original.Name || retrieved.Count != original.Count {
        t.Errorf("got %+v, want %+v", retrieved, original)
    }
}

// TestCacheMiss verifies ErrCacheMiss is returned for missing keys.
func TestCacheMiss(t *testing.T) {
    mr := miniredis.RunT(t)
    client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
    c := cache.New(client, "test")
    ctx := context.Background()

    var dst map[string]string
    err := c.GetJSON(ctx, "nonexistent:key", &dst)
    if !errors.Is(err, cache.ErrCacheMiss) {
        t.Errorf("expected ErrCacheMiss, got %v", err)
    }
}

// TestCacheTTLExpiry verifies that keys expire after the TTL.
func TestCacheTTLExpiry(t *testing.T) {
    mr := miniredis.RunT(t)
    client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
    c := cache.New(client, "test")
    ctx := context.Background()

    _ = c.SetJSON(ctx, "short_lived", "value", 100*time.Millisecond)

    var result string
    if err := c.GetJSON(ctx, "short_lived", &result); err != nil {
        t.Fatalf("should be cached: %v", err)
    }

    // Fast-forward time in miniredis
    mr.FastForward(200 * time.Millisecond)

    err := c.GetJSON(ctx, "short_lived", &result)
    if !errors.Is(err, cache.ErrCacheMiss) {
        t.Errorf("expected cache miss after TTL, got %v", err)
    }
}
```

Install miniredis for testing:

```bash
go get github.com/alicebob/miniredis/v2
```

---

## Mastery Check

You understand this chapter when you can:

1. Explain the three separate roles Redis plays in the PEACE SME portal (caching, session slots, job queuing), and give a concrete example of what would break if Redis became unavailable for each role.
2. Implement `cache.GetJSON` and `cache.SetJSON` using `go-redis/v9`, including handling `redis.Nil` as a cache miss (not an error), and explain why the prefix (`peace_sme`) must be consistent between the Flask and Go implementations.
3. Write the `CheckAndAllocate` method that: reads an existing session ID from the request header, tries to renew it with `Expire`, counts active sessions via `SCAN`, returns 429 if at capacity, or allocates a new slot with `Set` + TTL.
4. Implement `EnqueueRecalculate` with the `SetNX` debounce pattern — explain why `SetNX` prevents flooding the HFC queue when a user saves their grant multiple times in 60 seconds.
5. Write a `hfcWorkerLoop` goroutine that uses `redis.BLPop` with a 5-second timeout, unmarshals the job JSON, calls the processor, handles context cancellation for graceful shutdown, and uses `sync.WaitGroup` so `manager.Stop()` blocks until the goroutine exits.
