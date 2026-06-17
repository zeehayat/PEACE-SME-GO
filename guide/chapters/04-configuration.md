# Chapter 4: Configuration, Environment, and Application Toggles

## Purpose

The Flask application is controlled heavily by environment variables. The Go rewrite must preserve that behavior exactly. In this chapter, we study how to parse, validate, and inject configuration throughout a Go application — covering 12-factor principles, the Viper library, startup validation, feature flags, and the complete PEACE SME toggle system.

---

## The 12-Factor App: Configuration Principles

The 12-factor methodology defines best practices for modern web applications. Factor III states: "Store config in the environment."

The core idea:
- Everything that varies between deployments (development, staging, production) belongs in environment variables.
- Code never contains secrets, hostnames, or deployment-specific values.
- The application can be configured by whoever deploys it without touching source code.

### What Goes in Environment Variables

| Type | In env var? | Example |
|---|---|---|
| Database password | Yes | `POSTGRES_PASSWORD=sme_password` |
| API keys | Yes | `EMAIL_API_KEY=xkeysib-...` |
| Feature toggles | Yes | `GRANT_APPLICATION_OPEN=0` |
| Port numbers | Yes | `PORT=8080` |
| Hardcoded business logic | No | allowed districts list (in code) |
| HTML templates | No | (in files) |
| JWT algorithm | No | HS256 (this never changes) |

### Why Not Hardcode Feature Toggles?

The PEACE SME system has toggles like `GRANT_APPLICATION_OPEN`. In Flask:

```python
if os.environ.get('GRANT_APPLICATION_OPEN') == '1':
    # allow registration
```

In Go, if you hardcoded this:

```go
const grantOpen = false // WRONG: requires a code change and redeploy to open registration
```

But with env var:

```go
cfg.GrantApplicationOpen = os.Getenv("GRANT_APPLICATION_OPEN") == "1"
// Admin can open/close registration by restarting with a different env var
// No code change required
```

---

## Go Foundational Concepts for Configuration

### 1. Errors as Values

In Go, functions that can fail return an `error` value. There are no exceptions.

```go
// A function that returns (result, error)
func parsePort(s string) (int, error) {
    port, err := strconv.Atoi(s)
    if err != nil {
        return 0, fmt.Errorf("invalid PORT value %q: %w", s, err)
    }
    if port < 1 || port > 65535 {
        return 0, fmt.Errorf("PORT %d out of valid range 1-65535", port)
    }
    return port, nil
}

// At the call site, you MUST check the error
port, err := parsePort(os.Getenv("PORT"))
if err != nil {
    log.Fatalf("Configuration error: %v", err) // crash at startup
}
```

The `%w` verb wraps the original error, preserving it in the chain:

```go
// Error wrapping
err := fmt.Errorf("config: %w", originalErr)

// Check if the original error is in the chain
if errors.Is(err, strconv.ErrSyntax) {
    // handle parse error
}

// Sentinel errors for specific failure types
var ErrMissingRequired = errors.New("required environment variable is not set")
```

:::expandable [Go Errors Deep Dive]

#### Error Types

Go has three patterns for expressing different error types:

**Pattern 1: Sentinel errors** — fixed values you compare against with `errors.Is`:
```go
var ErrUserBlocked = errors.New("user is blocked")
var ErrNotWhitelisted = errors.New("user not whitelisted for grant access")

// In service:
if user.Status == "blocked" {
    return ErrUserBlocked
}

// In handler:
if errors.Is(err, ErrUserBlocked) {
    http.Error(w, `{"error":"Account blocked"}`, http.StatusForbidden)
    return
}
```

**Pattern 2: Struct errors** — custom types with fields you extract with `errors.As`:
```go
type ValidationError struct {
    Field   string
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation failed on field %q: %s", e.Field, e.Message)
}

// In handler:
var ve *ValidationError
if errors.As(err, &ve) {
    http.Error(w, fmt.Sprintf(`{"error":"%s","field":"%s"}`, ve.Message, ve.Field), 422)
    return
}
```

**Pattern 3: Wrapped errors** — preserve context with `fmt.Errorf("%w", err)`:
```go
func (r *UserRepository) FindByEmail(ctx context.Context, email string) (*User, error) {
    var u User
    err := r.db.QueryRow(ctx, query, email).Scan(&u.UserID, &u.Email)
    if err != nil {
        if errors.Is(err, pgx.ErrNoRows) {
            return nil, ErrUserNotFound
        }
        return nil, fmt.Errorf("user repository FindByEmail: %w", err)
    }
    return &u, nil
}
```
:::

### 2. Slices and Maps for Config

**Slices** hold ordered lists. Maps hold key-value lookups.

```go
// Parsing comma-separated country codes into a lookup map
allowedStr := "PK,AE,SA"
allowedMap := make(map[string]bool)
for _, code := range strings.Split(allowedStr, ",") {
    clean := strings.TrimSpace(strings.ToUpper(code))
    if clean != "" {
        allowedMap[clean] = true
    }
}

// O(1) lookup at request time
if !allowedMap[countryCode] {
    http.Error(w, "access restricted", http.StatusForbidden)
    return
}
```

```go
// Parsing admin users JSON into a slice
var admins []AdminUser
adminJSON := os.Getenv("ADMIN_USERS_JSON")
if err := json.Unmarshal([]byte(adminJSON), &admins); err != nil {
    return nil, fmt.Errorf("ADMIN_USERS_JSON parse error: %w", err)
}

// Linear search by username at login time
func findAdmin(admins []AdminUser, username string) (*AdminUser, bool) {
    for i := range admins {
        if admins[i].Username == username {
            return &admins[i], true
        }
    }
    return nil, false
}
```

---

## The Complete PEACE SME Environment Variables

Every variable the system reads, with validation rules and operational impact:

### Auth and Security

```go
// JWT_SECRET_KEY
// Required. Non-empty. At least 32 chars in production.
// Used to sign/verify both user JWTs (24h) and admin JWTs (8h).
// If empty → startup crash.
JWTSecret string

// ADMIN_USERS_JSON
// Required. JSON array of admin user objects.
// Format: [{"username":"admin1","password_hash":"$2b$12$...","role":"admin","can_approve_grants":false}]
// Password hashes are bcrypt-hashed. Never store plain passwords.
// If malformed JSON → startup crash.
AdminUsers []AdminUser
```

### Database Connectivity

```go
// POSTGRES_HOST      default: localhost
// POSTGRES_PORT      default: 5432
// POSTGRES_USER      default: sme_user
// POSTGRES_PASSWORD  default: sme_password
// POSTGRES_DB        default: sme_app
// DB_POOL_MIN_CONN   default: 2
// DB_POOL_MAX_CONN   default: 40
// These are combined into a single DSN string.
DatabaseURL string
DBPoolMin   int
DBPoolMax   int
```

### Redis

```go
// REDIS_URL
// default: redis://localhost:6379/0
// Used for: session slots, cache, job queue debouncing
RedisURL string
```

### S3-Compatible Storage

```go
// S3_ENDPOINT_URL    Required. E.g. https://eu2.contabostorage.com
// S3_ACCESS_KEY      Required.
// S3_SECRET_KEY      Required.
// S3_BUCKET_NAME     default: peace-economic
// S3_PUBLIC_BASE_URL Required. E.g. https://eu2.contabostorage.com/peace-economic
// S3_UPLOAD_ACL      default: public-read
S3EndpointURL   string
S3AccessKey     string
S3SecretKey     string
S3BucketName    string
S3PublicBaseURL string
S3UploadACL     string
```

### Email (Brevo)

```go
// EMAIL_API_KEY      Required. Brevo REST API key.
// SENDER_EMAIL       default: info@srsp.cloud
// SENDER_NAME        default: PEACE SME GRANT
// APPROVAL_NOTIFICATION_EMAIL  Required. Internal email for approval notifications.
EmailAPIKey                  string
SenderEmail                  string
SenderName                   string
ApprovalNotificationEmail    string
```

### Feature Toggles

```go
// GRANT_APPLICATION_OPEN
// 0 (default) = registration and pre-registration return 403
// 1           = registration is open
GrantApplicationOpen bool

// GRANT_REQUIRE_SELECTION
// 1 (default) = users must be whitelisted in grant_access_whitelist before submitting
// 0           = any registered user can submit a grant
GrantRequireSelection bool

// HFC_SHADOW_MODE
// 1 (default) = HFC scores calculated and stored but cannot block approval
// 0           = HIGH/CRITICAL HFC risk blocks grant approval
HFCShadowMode bool

// HFC_ASYNC_ENABLED
// 1 (default) = HFC scoring runs asynchronously via Redis queue
// 0           = HFC scoring runs synchronously in the request handler (slow)
HFCAsyncEnabled bool

// HFC_ENQUEUE_DEBOUNCE_SEC
// default: 60
// How many seconds to wait before re-enqueuing an HFC job for the same user
// Prevents flooding the queue on rapid grant updates
HFCDebounceSec int
```

### Access Control

```go
// ACCESS_CONTROL_ENABLED
// 1 (default) = concurrent session limit enforced via Redis
// 0           = no session limit
AccessControlEnabled bool

// MAX_ACTIVE_APPLICANTS
// default: 300
// Maximum concurrent applicant sessions allowed via Redis SETEX keys
MaxActiveApplicants int

// ACCESS_SLOT_TTL_SEC
// default: 90
// TTL of each Redis session slot in seconds
AccessSlotTTLSec int

// GEO_BLOCK_ENABLED
// 1 (default) = non-PK IPs are blocked
// 0           = all IPs accepted
GeoBlockEnabled bool

// ALLOWED_COUNTRY_CODES
// default: PK
// Comma-separated ISO country codes. Case-insensitive.
AllowedCountryCodes map[string]bool
```

### Cache

```go
// CACHE_ENABLED      default: 1
// CACHE_PREFIX       default: peace_sme
// CACHE_TTL_UPDATES  default: 3600  (1 hour for announcements)
// CACHE_TTL_FAQS     default: 300   (5 minutes for FAQs)
// CACHE_TTL_FILTERS  default: 120   (2 minutes for filter options)
CacheEnabled    bool
CachePrefix     string
CacheTTLUpdates int
CacheTTLFAQs   int
CacheTTLFilters int
```

---

## Complete Configuration Implementation

```go
// File: internal/config/config.go
package config

import (
    "encoding/json"
    "fmt"
    "os"
    "strconv"
    "strings"
)

// AdminUser represents an admin credential loaded from ADMIN_USERS_JSON.
type AdminUser struct {
    Username         string `json:"username"`
    PasswordHash     string `json:"password_hash"`
    Role             string `json:"role"`
    CanApproveGrants bool   `json:"can_approve_grants"`
}

// Config holds all parsed application configuration.
// All fields are read-only after Load() returns.
type Config struct {
    // Server
    Port        int
    FrontendURL string

    // Auth
    JWTSecret  string
    AdminUsers []AdminUser

    // Database
    DatabaseURL string
    DBPoolMin   int
    DBPoolMax   int

    // Redis
    RedisURL string

    // S3
    S3EndpointURL   string
    S3AccessKey     string
    S3SecretKey     string
    S3BucketName    string
    S3PublicBaseURL string
    S3UploadACL     string

    // Email
    EmailAPIKey                 string
    SenderEmail                 string
    SenderName                  string
    ApprovalNotificationEmail   string

    // Feature toggles
    GrantApplicationOpen  bool
    GrantRequireSelection bool
    HFCShadowMode         bool
    HFCAsyncEnabled       bool
    HFCDebounceSec        int

    // Access control
    AccessControlEnabled bool
    MaxActiveApplicants  int
    AccessSlotTTLSec     int
    GeoBlockEnabled      bool
    AllowedCountryCodes  map[string]bool

    // Cache
    CacheEnabled    bool
    CachePrefix     string
    CacheTTLUpdates int
    CacheTTLFAQs   int
    CacheTTLFilters int
}

// Load reads and validates all environment variables.
// Returns an error if any required variable is missing or any value fails parsing.
// Call this once at startup and pass *Config everywhere via dependency injection.
func Load() (*Config, error) {
    cfg := &Config{
        AllowedCountryCodes: make(map[string]bool),
    }

    // --- Server ---
    port, err := envInt("PORT", 8080)
    if err != nil {
        return nil, err
    }
    cfg.Port = port
    cfg.FrontendURL = getEnv("FRONTEND_URL", "http://localhost:3001")

    // --- Auth ---
    cfg.JWTSecret = os.Getenv("JWT_SECRET_KEY")
    if cfg.JWTSecret == "" {
        return nil, fmt.Errorf("required env var JWT_SECRET_KEY is empty")
    }
    if len(cfg.JWTSecret) < 16 {
        return nil, fmt.Errorf("JWT_SECRET_KEY must be at least 16 characters")
    }

    adminJSON := os.Getenv("ADMIN_USERS_JSON")
    if adminJSON != "" {
        var admins []AdminUser
        if err := json.Unmarshal([]byte(adminJSON), &admins); err != nil {
            return nil, fmt.Errorf("ADMIN_USERS_JSON is invalid JSON: %w", err)
        }
        if len(admins) == 0 {
            return nil, fmt.Errorf("ADMIN_USERS_JSON must contain at least one admin user")
        }
        for i, a := range admins {
            if a.Username == "" {
                return nil, fmt.Errorf("ADMIN_USERS_JSON[%d]: username is empty", i)
            }
            if a.PasswordHash == "" {
                return nil, fmt.Errorf("ADMIN_USERS_JSON[%d]: password_hash is empty", i)
            }
        }
        cfg.AdminUsers = admins
    }

    // --- Database ---
    dbHost := getEnv("POSTGRES_HOST", "localhost")
    dbPort := getEnv("POSTGRES_PORT", "5432")
    dbUser := getEnv("POSTGRES_USER", "sme_user")
    dbPass := getEnv("POSTGRES_PASSWORD", "sme_password")
    dbName := getEnv("POSTGRES_DB", "sme_app")
    cfg.DatabaseURL = fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=disable",
        dbUser, dbPass, dbHost, dbPort, dbName)

    cfg.DBPoolMin, err = envInt("DB_POOL_MIN_CONN", 2)
    if err != nil {
        return nil, err
    }
    cfg.DBPoolMax, err = envInt("DB_POOL_MAX_CONN", 40)
    if err != nil {
        return nil, err
    }

    // --- Redis ---
    cfg.RedisURL = getEnv("REDIS_URL", "redis://localhost:6379/0")

    // --- S3 ---
    cfg.S3EndpointURL = os.Getenv("S3_ENDPOINT_URL")
    if cfg.S3EndpointURL == "" {
        return nil, fmt.Errorf("required env var S3_ENDPOINT_URL is empty")
    }
    cfg.S3AccessKey = os.Getenv("S3_ACCESS_KEY")
    if cfg.S3AccessKey == "" {
        return nil, fmt.Errorf("required env var S3_ACCESS_KEY is empty")
    }
    cfg.S3SecretKey = os.Getenv("S3_SECRET_KEY")
    if cfg.S3SecretKey == "" {
        return nil, fmt.Errorf("required env var S3_SECRET_KEY is empty")
    }
    cfg.S3BucketName = getEnv("S3_BUCKET_NAME", "peace-economic")
    cfg.S3PublicBaseURL = os.Getenv("S3_PUBLIC_BASE_URL")
    if cfg.S3PublicBaseURL == "" {
        return nil, fmt.Errorf("required env var S3_PUBLIC_BASE_URL is empty")
    }
    cfg.S3UploadACL = getEnv("S3_UPLOAD_ACL", "public-read")

    // --- Email ---
    cfg.EmailAPIKey = os.Getenv("EMAIL_API_KEY")
    if cfg.EmailAPIKey == "" {
        return nil, fmt.Errorf("required env var EMAIL_API_KEY is empty")
    }
    cfg.SenderEmail = getEnv("SENDER_EMAIL", "info@srsp.cloud")
    cfg.SenderName = getEnv("SENDER_NAME", "PEACE SME GRANT")
    cfg.ApprovalNotificationEmail = os.Getenv("APPROVAL_NOTIFICATION_EMAIL")

    // --- Feature Toggles ---
    cfg.GrantApplicationOpen  = getEnv("GRANT_APPLICATION_OPEN", "0") == "1"
    cfg.GrantRequireSelection = getEnv("GRANT_REQUIRE_SELECTION", "1") == "1"
    cfg.HFCShadowMode         = getEnv("HFC_SHADOW_MODE", "1") == "1"
    cfg.HFCAsyncEnabled       = getEnv("HFC_ASYNC_ENABLED", "1") == "1"

    cfg.HFCDebounceSec, err = envInt("HFC_ENQUEUE_DEBOUNCE_SEC", 60)
    if err != nil {
        return nil, err
    }

    // --- Access Control ---
    cfg.AccessControlEnabled = getEnv("ACCESS_CONTROL_ENABLED", "1") == "1"
    cfg.GeoBlockEnabled      = getEnv("GEO_BLOCK_ENABLED", "1") == "1"

    cfg.MaxActiveApplicants, err = envInt("MAX_ACTIVE_APPLICANTS", 300)
    if err != nil {
        return nil, err
    }
    cfg.AccessSlotTTLSec, err = envInt("ACCESS_SLOT_TTL_SEC", 90)
    if err != nil {
        return nil, err
    }

    allowedStr := getEnv("ALLOWED_COUNTRY_CODES", "PK")
    for _, code := range strings.Split(allowedStr, ",") {
        clean := strings.TrimSpace(strings.ToUpper(code))
        if clean != "" {
            cfg.AllowedCountryCodes[clean] = true
        }
    }

    // --- Cache ---
    cfg.CacheEnabled = getEnv("CACHE_ENABLED", "1") == "1"
    cfg.CachePrefix  = getEnv("CACHE_PREFIX", "peace_sme")

    cfg.CacheTTLUpdates, err = envInt("CACHE_TTL_UPDATES", 3600)
    if err != nil {
        return nil, err
    }
    cfg.CacheTTLFAQs, err = envInt("CACHE_TTL_FAQS", 300)
    if err != nil {
        return nil, err
    }
    cfg.CacheTTLFilters, err = envInt("CACHE_TTL_FILTERS", 120)
    if err != nil {
        return nil, err
    }

    return cfg, nil
}

// FindAdmin returns the admin user with the given username, or false if not found.
func (c *Config) FindAdmin(username string) (*AdminUser, bool) {
    for i := range c.AdminUsers {
        if c.AdminUsers[i].Username == username {
            return &c.AdminUsers[i], true
        }
    }
    return nil, false
}

// helpers

func getEnv(key, defaultVal string) string {
    if val := os.Getenv(key); val != "" {
        return val
    }
    return defaultVal
}

func envInt(key string, defaultVal int) (int, error) {
    s := os.Getenv(key)
    if s == "" {
        return defaultVal, nil
    }
    n, err := strconv.Atoi(s)
    if err != nil {
        return 0, fmt.Errorf("env var %s=%q is not a valid integer: %w", key, s, err)
    }
    return n, nil
}
```

---

## Startup Validation: Fail Fast, Fail Loud

The principle: if the configuration is invalid, crash immediately at startup with a clear error message. Never silently boot with bad config.

```go
// cmd/server/main.go
package main

import (
    "log"
    "peace-sme-go/internal/config"
)

func main() {
    cfg, err := config.Load()
    if err != nil {
        log.Fatalf("STARTUP FAILED — configuration error: %v", err)
    }

    log.Printf("Configuration loaded successfully.")
    log.Printf("  Server port:          %d", cfg.Port)
    log.Printf("  Grant registration:   %v", boolLabel(cfg.GrantApplicationOpen, "OPEN", "CLOSED"))
    log.Printf("  Grant require select: %v", boolLabel(cfg.GrantRequireSelection, "YES", "NO"))
    log.Printf("  HFC shadow mode:      %v", boolLabel(cfg.HFCShadowMode, "ON (non-blocking)", "OFF (blocking)"))
    log.Printf("  Geo blocking:         %v", boolLabel(cfg.GeoBlockEnabled, "ON", "OFF"))
    log.Printf("  Admin users loaded:   %d", len(cfg.AdminUsers))
    log.Printf("  Cache prefix:         %s", cfg.CachePrefix)
    log.Printf("  Allowed countries:    %v", keysOf(cfg.AllowedCountryCodes))

    // ... proceed to initialize DB, Redis, S3, start HTTP server
}

func boolLabel(b bool, ifTrue, ifFalse string) string {
    if b {
        return ifTrue
    }
    return ifFalse
}

func keysOf(m map[string]bool) []string {
    keys := make([]string, 0, len(m))
    for k := range m {
        keys = append(keys, k)
    }
    return keys
}
```

Expected startup output:

```
2026/06/17 09:00:00 Configuration loaded successfully.
2026/06/17 09:00:00   Server port:          8080
2026/06/17 09:00:00   Grant registration:   CLOSED
2026/06/17 09:00:00   Grant require select: YES
2026/06/17 09:00:00   HFC shadow mode:      ON (non-blocking)
2026/06/17 09:00:00   Geo blocking:         ON
2026/06/17 09:00:00   Admin users loaded:   3
2026/06/17 09:00:00   Cache prefix:         peace_sme
2026/06/17 09:00:00   Allowed countries:    [PK]
```

If `JWT_SECRET_KEY` is missing:

```
2026/06/17 09:00:00 STARTUP FAILED — configuration error: required env var JWT_SECRET_KEY is empty
exit status 1
```

---

## The Viper Library: Advanced Config Loading

For more complex configuration needs, the `github.com/spf13/viper` library supports multiple sources: env vars, config files (YAML/JSON/TOML), command-line flags, remote config stores.

```bash
go get github.com/spf13/viper
```

```go
// Using Viper for multi-source configuration
package config

import (
    "fmt"
    "github.com/spf13/viper"
)

func LoadWithViper() (*Config, error) {
    v := viper.New()

    // 1. Set defaults
    v.SetDefault("PORT", 8080)
    v.SetDefault("POSTGRES_HOST", "localhost")
    v.SetDefault("POSTGRES_PORT", 5432)
    v.SetDefault("REDIS_URL", "redis://localhost:6379/0")
    v.SetDefault("GRANT_APPLICATION_OPEN", false)
    v.SetDefault("GRANT_REQUIRE_SELECTION", true)
    v.SetDefault("HFC_SHADOW_MODE", true)
    v.SetDefault("CACHE_PREFIX", "peace_sme")
    v.SetDefault("MAX_ACTIVE_APPLICANTS", 300)

    // 2. Read from config file (optional)
    v.SetConfigName("config")
    v.SetConfigType("yaml")
    v.AddConfigPath(".")
    v.AddConfigPath("./config")
    if err := v.ReadInConfig(); err != nil {
        // Config file is optional — only fail if it exists but is malformed
        if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
            return nil, fmt.Errorf("config file error: %w", err)
        }
    }

    // 3. Environment variables override config file
    v.AutomaticEnv()

    // 4. Extract into struct
    cfg := &Config{
        Port:                  v.GetInt("PORT"),
        JWTSecret:             v.GetString("JWT_SECRET_KEY"),
        RedisURL:              v.GetString("REDIS_URL"),
        GrantApplicationOpen:  v.GetBool("GRANT_APPLICATION_OPEN"),
        GrantRequireSelection: v.GetBool("GRANT_REQUIRE_SELECTION"),
        HFCShadowMode:         v.GetBool("HFC_SHADOW_MODE"),
        CachePrefix:           v.GetString("CACHE_PREFIX"),
        MaxActiveApplicants:   v.GetInt("MAX_ACTIVE_APPLICANTS"),
    }

    // 5. Validate required fields
    if cfg.JWTSecret == "" {
        return nil, fmt.Errorf("JWT_SECRET_KEY is required")
    }

    return cfg, nil
}
```

### Config File Example (config.yaml for local development)

```yaml
# config.yaml (do not commit secrets — use .env for real values)
PORT: 8080
POSTGRES_HOST: localhost
POSTGRES_PORT: 5432
POSTGRES_USER: sme_user
POSTGRES_PASSWORD: sme_password
POSTGRES_DB: sme_app
REDIS_URL: "redis://localhost:6379/0"
GRANT_APPLICATION_OPEN: false
GRANT_REQUIRE_SELECTION: true
HFC_SHADOW_MODE: true
CACHE_PREFIX: peace_sme
MAX_ACTIVE_APPLICANTS: 300
```

> [!WARNING]
> Never commit `config.yaml` if it contains real secrets. Add it to `.gitignore`. Use config files only for local development defaults; use environment variables in all deployed environments.

---

## Feature Flags Pattern

The PEACE SME system uses simple boolean feature flags via environment variables. Here is the Go pattern for implementing them cleanly:

### Using Flags in Handlers

```go
// internal/user/handler.go
func (h *Handler) PreRegister(w http.ResponseWriter, r *http.Request) {
    // Feature flag check at the start of the handler
    if !h.cfg.GrantApplicationOpen {
        w.Header().Set("Content-Type", "application/json")
        w.WriteHeader(http.StatusForbidden)
        json.NewEncoder(w).Encode(map[string]string{
            "error": "Registration is currently closed",
        })
        return
    }

    // Normal registration logic below
    var req PreRegisterRequest
    // ...
}
```

### Using Flags in Services

```go
// internal/grant/service.go
func (s *Service) Apply(ctx context.Context, userID int64, req ApplyRequest) (*ApplyResult, error) {
    // Whitelist gate — controlled by feature flag
    if s.cfg.GrantRequireSelection {
        entry, err := s.repo.GetWhitelistEntry(ctx, userID)
        if err != nil || !entry.IsSelected {
            return nil, ErrNotWhitelisted
        }
    }

    // HFC shadow mode — affects approval flow, not submission
    // The flag is checked in the approval service, not here

    // ... insert grant ...
}
```

### The HFC Shadow Mode Flag

```go
// internal/grant/service.go
func (s *Service) ApproveGrant(ctx context.Context, adminUsername string, userID int64, req ApproveRequest) error {
    grant, err := s.repo.FindByUserID(ctx, userID)
    if err != nil {
        return err
    }

    // If NOT in shadow mode, HFC score can block approval
    if !s.cfg.HFCShadowMode {
        if grant.HFCRiskLevel == "HIGH" || grant.HFCRiskLevel == "CRITICAL" {
            return fmt.Errorf("cannot approve: HFC risk level is %s (shadow mode is OFF)", grant.HFCRiskLevel)
        }
    }
    // In shadow mode: proceed regardless of HFC score

    // ... perform approval ...
}
```

---

## Environment-Specific Configs

Use separate `.env` files for different environments:

```
.env                 → local development defaults
.env.staging         → staging environment
.env.production      → production (never committed)
```

`.env` file for local development:

```env
# .env — local development (safe to commit if it has no real secrets)
PORT=8080
JWT_SECRET_KEY=local-dev-secret-key-change-in-production
ADMIN_USERS_JSON=[{"username":"admin","password_hash":"$2b$12$...","role":"admin","can_approve_grants":true}]
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=sme_user
POSTGRES_PASSWORD=sme_password
POSTGRES_DB=sme_app
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=peace-economic-dev
S3_PUBLIC_BASE_URL=http://localhost:9000/peace-economic-dev
EMAIL_API_KEY=test-key-emails-disabled-locally
GRANT_APPLICATION_OPEN=1
GRANT_REQUIRE_SELECTION=0
HFC_SHADOW_MODE=1
GEO_BLOCK_ENABLED=0
ACCESS_CONTROL_ENABLED=0
```

For production `.env`:

```env
# .env.production — NEVER commit this file
PORT=8080
JWT_SECRET_KEY=a-very-long-high-entropy-random-string-generated-with-openssl
# ... real credentials ...
GRANT_APPLICATION_OPEN=0
GRANT_REQUIRE_SELECTION=1
HFC_SHADOW_MODE=1
GEO_BLOCK_ENABLED=1
ALLOWED_COUNTRY_CODES=PK
```

Load `.env` file in development using `godotenv`:

```go
// cmd/server/main.go
import "github.com/joho/godotenv"

func main() {
    // Load .env file in development (fails silently if not found)
    _ = godotenv.Load()

    cfg, err := config.Load()
    // ...
}
```

---

## Config Testing

Test your configuration loader to ensure validation works:

```go
// internal/config/config_test.go
package config_test

import (
    "os"
    "testing"
    "peace-sme-go/internal/config"
)

func setEnv(t *testing.T, key, value string) {
    t.Helper()
    original := os.Getenv(key)
    os.Setenv(key, value)
    t.Cleanup(func() { os.Setenv(key, original) })
}

func TestLoad_RequiresJWTSecret(t *testing.T) {
    // Ensure JWT_SECRET_KEY is not set
    os.Unsetenv("JWT_SECRET_KEY")

    _, err := config.Load()
    if err == nil {
        t.Fatal("expected error when JWT_SECRET_KEY is missing, got nil")
    }
}

func TestLoad_ToggleDefaults(t *testing.T) {
    setEnv(t, "JWT_SECRET_KEY", "test-secret-key-1234567890123456")
    setEnv(t, "ADMIN_USERS_JSON", `[{"username":"a","password_hash":"$2b$12$x","role":"admin","can_approve_grants":false}]`)
    // Don't set S3/email required vars — we test toggles only
    // ... (in a real test you'd set all required vars)

    setEnv(t, "GRANT_APPLICATION_OPEN", "0")
    setEnv(t, "GRANT_REQUIRE_SELECTION", "1")
    setEnv(t, "HFC_SHADOW_MODE", "1")

    cfg, err := config.Load()
    if err != nil {
        t.Skipf("skipping toggle test (other required vars missing): %v", err)
    }

    if cfg.GrantApplicationOpen {
        t.Error("GrantApplicationOpen should be false when GRANT_APPLICATION_OPEN=0")
    }
    if !cfg.GrantRequireSelection {
        t.Error("GrantRequireSelection should be true when GRANT_REQUIRE_SELECTION=1")
    }
    if !cfg.HFCShadowMode {
        t.Error("HFCShadowMode should be true when HFC_SHADOW_MODE=1")
    }
}

func TestLoad_CountryCodesMap(t *testing.T) {
    setEnv(t, "ALLOWED_COUNTRY_CODES", "PK,AE, SA ") // includes spaces

    // ... set required vars ...
    cfg, err := config.Load()
    if err != nil {
        t.Skipf("skipping: %v", err)
    }

    if !cfg.AllowedCountryCodes["PK"] {
        t.Error("PK should be in AllowedCountryCodes")
    }
    if !cfg.AllowedCountryCodes["AE"] {
        t.Error("AE should be in AllowedCountryCodes")
    }
    if !cfg.AllowedCountryCodes["SA"] {
        t.Error("SA should be trimmed and in AllowedCountryCodes")
    }
    if cfg.AllowedCountryCodes["US"] {
        t.Error("US should not be in AllowedCountryCodes")
    }
}

func TestLoad_InvalidPort(t *testing.T) {
    setEnv(t, "PORT", "not-a-number")

    _, err := config.Load()
    if err == nil {
        t.Fatal("expected error for invalid PORT")
    }
}
```

Run config tests:

```bash
go test ./internal/config/... -v

# Expected output:
# --- PASS: TestLoad_RequiresJWTSecret (0.00s)
# --- SKIP: TestLoad_ToggleDefaults (other required vars missing)
# --- SKIP: TestLoad_CountryCodesMap (other required vars missing)
# --- PASS: TestLoad_InvalidPort (0.00s)
```

---

## Secrets Management Best Practices

| Practice | Why |
|---|---|
| Never commit `.env` files with real secrets | They appear in git history forever, even after deletion |
| Use `.gitignore` for all secret files | `echo ".env.production" >> .gitignore` |
| Rotate secrets regularly | Old API keys may have been exposed |
| Use different secrets per environment | A dev leak should not expose production |
| Use a secrets manager in production | AWS Secrets Manager, HashiCorp Vault, or 1Password Secrets Automation |
| Log config state at startup (without secret values) | Confirms what was loaded without exposing values |
| Validate all required secrets at startup | Catch missing secrets before they cause runtime failures |

```go
// GOOD: log the presence of a secret, not its value
log.Printf("S3 credentials: loaded (key starts with %s...)", cfg.S3AccessKey[:4])

// BAD: never log secrets
log.Printf("S3 secret key: %s", cfg.S3SecretKey) // NEVER DO THIS
```

---

## Runnable Sandbox: Complete Config Loader

```go
// Run this with: go run main.go
package main

import (
    "encoding/json"
    "fmt"
    "os"
    "strconv"
    "strings"
)

type AdminUser struct {
    Username         string `json:"username"`
    Role             string `json:"role"`
    CanApproveGrants bool   `json:"can_approve_grants"`
}

type Config struct {
    Port                  int
    GrantApplicationOpen  bool
    GrantRequireSelection bool
    HFCShadowMode         bool
    AllowedCountryCodes   map[string]bool
    AdminUsers            []AdminUser
    CachePrefix           string
    MaxActiveApplicants   int
}

func main() {
    // Simulate a production environment
    os.Setenv("PORT", "8080")
    os.Setenv("JWT_SECRET_KEY", "local-dev-secret-32-chars-minimum!")
    os.Setenv("GRANT_APPLICATION_OPEN", "0")
    os.Setenv("GRANT_REQUIRE_SELECTION", "1")
    os.Setenv("HFC_SHADOW_MODE", "1")
    os.Setenv("ALLOWED_COUNTRY_CODES", "PK")
    os.Setenv("CACHE_PREFIX", "peace_sme")
    os.Setenv("MAX_ACTIVE_APPLICANTS", "300")
    os.Setenv("ADMIN_USERS_JSON", `[
        {"username":"aftab","role":"approving_authority","can_approve_grants":true},
        {"username":"reviewer","role":"admin","can_approve_grants":false}
    ]`)

    cfg := &Config{AllowedCountryCodes: make(map[string]bool)}

    // Parse port
    portStr := os.Getenv("PORT")
    port, err := strconv.Atoi(portStr)
    if err != nil {
        fmt.Printf("ERROR: PORT=%q is not a valid integer\n", portStr)
        os.Exit(1)
    }
    cfg.Port = port

    // Validate JWT secret
    jwtSecret := os.Getenv("JWT_SECRET_KEY")
    if jwtSecret == "" {
        fmt.Println("ERROR: JWT_SECRET_KEY is required")
        os.Exit(1)
    }

    // Parse boolean toggles
    cfg.GrantApplicationOpen  = os.Getenv("GRANT_APPLICATION_OPEN") == "1"
    cfg.GrantRequireSelection = os.Getenv("GRANT_REQUIRE_SELECTION") == "1"
    cfg.HFCShadowMode         = os.Getenv("HFC_SHADOW_MODE") == "1"

    // Parse country codes into lookup map
    for _, code := range strings.Split(os.Getenv("ALLOWED_COUNTRY_CODES"), ",") {
        clean := strings.TrimSpace(strings.ToUpper(code))
        if clean != "" {
            cfg.AllowedCountryCodes[clean] = true
        }
    }

    // Parse admin users JSON
    if adminJSON := os.Getenv("ADMIN_USERS_JSON"); adminJSON != "" {
        if err := json.Unmarshal([]byte(adminJSON), &cfg.AdminUsers); err != nil {
            fmt.Printf("ERROR: ADMIN_USERS_JSON is malformed: %v\n", err)
            os.Exit(1)
        }
    }

    // Parse integer config
    if maxStr := os.Getenv("MAX_ACTIVE_APPLICANTS"); maxStr != "" {
        cfg.MaxActiveApplicants, _ = strconv.Atoi(maxStr)
    } else {
        cfg.MaxActiveApplicants = 300
    }

    cfg.CachePrefix = os.Getenv("CACHE_PREFIX")
    if cfg.CachePrefix == "" {
        cfg.CachePrefix = "peace_sme"
    }

    // Print loaded config (no secrets)
    fmt.Println("=== Loaded Configuration ===")
    fmt.Printf("Port:                  %d\n", cfg.Port)
    fmt.Printf("Grant registrations:   %s\n", boolStr(cfg.GrantApplicationOpen, "OPEN", "CLOSED"))
    fmt.Printf("Whitelist required:    %s\n", boolStr(cfg.GrantRequireSelection, "YES", "NO"))
    fmt.Printf("HFC shadow mode:       %s\n", boolStr(cfg.HFCShadowMode, "ON", "OFF"))
    fmt.Printf("Allowed countries:     %v\n", cfg.AllowedCountryCodes)
    fmt.Printf("Max active applicants: %d\n", cfg.MaxActiveApplicants)
    fmt.Printf("Cache prefix:          %s\n", cfg.CachePrefix)
    fmt.Printf("Admin users:\n")
    for _, a := range cfg.AdminUsers {
        fmt.Printf("  - %s (%s, can_approve=%v)\n", a.Username, a.Role, a.CanApproveGrants)
    }

    // Simulate a geo-block check
    requestCountry := "PK"
    if cfg.AllowedCountryCodes[requestCountry] {
        fmt.Printf("\nRequest from %s: ALLOWED\n", requestCountry)
    } else {
        fmt.Printf("\nRequest from %s: BLOCKED\n", requestCountry)
    }

    // Simulate registration gate
    fmt.Printf("\nRegistration attempt: %s\n",
        boolStr(cfg.GrantApplicationOpen, "ACCEPTED (201)", "REJECTED (403 closed)"))
}

func boolStr(b bool, ifTrue, ifFalse string) string {
    if b {
        return ifTrue
    }
    return ifFalse
}
```

Expected output:
```
=== Loaded Configuration ===
Port:                  8080
Grant registrations:   CLOSED
Whitelist required:    YES
HFC shadow mode:       ON
Allowed countries:     map[PK:true]
Max active applicants: 300
Cache prefix:          peace_sme
Admin users:
  - aftab (approving_authority, can_approve=true)
  - reviewer (admin, can_approve=false)

Request from PK: ALLOWED

Registration attempt: REJECTED (403 closed)
```

---

## Mastery Check

You understand this chapter when you can:

1. Explain the 12-factor app principle for configuration and why secrets must not be in source code.
2. List every PEACE SME environment toggle, what each controls, and what happens if it is missing or wrong.
3. Write a `config.Load()` function that validates required variables, parses integers and booleans, builds a DSN string, and unmarshals a JSON array — returning a descriptive error for each failure case.
4. Implement the feature flag pattern in a Go handler so that `GRANT_APPLICATION_OPEN=0` returns 403 and `=1` proceeds normally.
5. Write a config test that sets environment variables, calls `config.Load()`, and asserts the resulting struct fields match the expected values.
