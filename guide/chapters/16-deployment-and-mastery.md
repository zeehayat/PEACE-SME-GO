# Chapter 16: Deployment, Release Git, and Mastery Roadmap

## Purpose

The final stage is operating the rewritten application: build artifacts, containers, migrations, environment configuration, health checks, graceful shutdown, release tags, and rollback strategy. A working Go binary that no one can deploy is unfinished.

---

## Part 1: Docker Multi-Stage Builds for Go

### Why Multi-Stage?

A standard Go Docker build using `golang:1.22` produces a ~1.2 GB image because it includes the entire Go toolchain, build cache, and standard library source. The running application only needs the compiled binary.

Multi-stage builds solve this: compile in a heavy builder image, copy the binary into a minimal runtime image.

```
Stage 1 (builder): golang:1.22-alpine
  - Downloads modules
  - Compiles binary with CGO_ENABLED=0
  - Produces: /app/server (static binary, ~25 MB)

Stage 2 (runtime): alpine:3.19 or scratch
  - No Go toolchain
  - No compilers
  - Only the binary + TLS certificates
  - Final image: ~30 MB
```

### Production Dockerfile for the Go Backend

```dockerfile
# File: backend-go/Dockerfile

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM golang:1.22-alpine AS builder

# Install build dependencies
RUN apk add --no-cache git ca-certificates tzdata

WORKDIR /app

# Copy dependency manifests first to cache module downloads separately
# from source code. A source-only change will not re-download modules.
COPY go.mod go.sum ./
RUN go mod download

# Copy all source code
COPY . .

# Build a statically linked binary.
#   CGO_ENABLED=0  — no C dependencies, enables static linking
#   -ldflags "-w -s" — strip debug symbols (reduces binary size ~30%)
#   -trimpath — remove local filesystem paths from the binary
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -ldflags="-w -s" -trimpath \
    -o /app/server ./cmd/server

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM alpine:3.19

# Alpine needs these for TLS (HTTPS calls to Brevo, S3, etc.)
RUN apk add --no-cache ca-certificates tzdata

# Never run as root in production
RUN addgroup -S sme && adduser -S sme -G sme
USER sme

# Copy only what the binary needs
COPY --from=builder /app/server /usr/local/bin/server

EXPOSE 8080

# Use exec form (not shell form) so signals reach the Go process
ENTRYPOINT ["/usr/local/bin/server"]
```

### Using scratch Instead of Alpine

For a truly minimal image (no shell, no package manager), use `scratch`:

```dockerfile
FROM scratch

# scratch has no TLS store — copy it from the builder
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /usr/share/zoneinfo /usr/share/zoneinfo
COPY --from=builder /app/server /server

EXPOSE 8080
ENTRYPOINT ["/server"]
```

> [!WARNING]
> The `scratch` image has no shell. You cannot `docker exec` into it for debugging. Use Alpine in development, scratch only in locked-down production environments.

### Build and Inspect

```bash
# Build the image
docker build -t peace-sme-backend:v0.1.0 -f backend-go/Dockerfile backend-go/

# Check final image size
docker images peace-sme-backend

# Inspect layers
docker history peace-sme-backend:v0.1.0
```

---

## Part 2: Vue Frontend Dockerfile and Nginx

### Multi-Stage Vue Build

```dockerfile
# File: frontend/Dockerfile.frontend

# ── Stage 1: Node Build ───────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Cache node_modules separately from source
COPY package.json package-lock.json ./
RUN npm ci --silent

# Copy source and build
COPY . .
# Pass the API base URL at build time
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# ── Stage 2: Nginx ────────────────────────────────────────────────────────────
FROM nginx:1.25-alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Nginx Config for Vue SPA

```nginx
# File: frontend/nginx.conf
server {
    listen 80;
    server_name _;

    # Serve static assets with long cache headers
    location /assets/ {
        root /usr/share/nginx/html;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Proxy all API calls to Go backend
    # The container name in docker-compose is sme_backend_app
    location /api/ {
        proxy_pass         http://sme_backend_app:8080;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # Pass Cloudflare's country header through to the Go middleware
        proxy_set_header   CF-IPCountry $http_cf_ipcountry;

        proxy_connect_timeout 10s;
        proxy_read_timeout    120s;
    }

    # All other paths → Vue Router handles routing
    location / {
        root  /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header Referrer-Policy "strict-origin-when-cross-origin";
}
```

---

## Part 3: docker-compose.yml — All 7 Services

```yaml
# File: docker-compose.yml
version: '3.9'

networks:
  sme_network:
    driver: bridge

volumes:
  sme_postgres_data:
  sme_uploads:

services:

  # ── PostgreSQL 15 ────────────────────────────────────────────────────────────
  db:
    image: postgres:15-alpine
    container_name: sme_postgres_db
    restart: unless-stopped
    environment:
      POSTGRES_DB:       ${POSTGRES_DB:-sme_app}
      POSTGRES_USER:     ${POSTGRES_USER:-sme_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-sme_password}
    volumes:
      - sme_postgres_data:/var/lib/postgresql/data
    ports:
      - "5433:5432"      # exposed for local tooling (pgAdmin, psql)
    networks:
      - sme_network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ── Redis 7 ──────────────────────────────────────────────────────────────────
  redis:
    image: redis:7-alpine
    container_name: sme_redis
    restart: unless-stopped
    networks:
      - sme_network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

  # ── Go Backend ───────────────────────────────────────────────────────────────
  backend:
    build:
      context: ./backend-go
      dockerfile: Dockerfile
    container_name: sme_backend_app
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file:
      - .env
    environment:
      POSTGRES_HOST: db
      POSTGRES_PORT: 5432
    ports:
      - "5000:8080"
    networks:
      - sme_network
    volumes:
      - sme_uploads:/var/www/sme-uploads

  # ── Go Worker (background jobs) ──────────────────────────────────────────────
  worker:
    build:
      context: ./backend-go
      dockerfile: Dockerfile.worker
    container_name: sme_backend_worker
    restart: unless-stopped
    depends_on:
      - db
      - redis
    env_file:
      - .env
    environment:
      POSTGRES_HOST: db
    networks:
      - sme_network

  # ── Vue Frontend (nginx) ─────────────────────────────────────────────────────
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.frontend
      args:
        VITE_API_BASE_URL: /api
    container_name: sme_frontend
    restart: unless-stopped
    depends_on:
      - backend
    ports:
      - "3001:80"
    networks:
      - sme_network

  # ── Adminer (lightweight DB browser) ────────────────────────────────────────
  adminer:
    image: adminer:4
    container_name: sme_adminer
    restart: unless-stopped
    ports:
      - "8082:8080"
    networks:
      - sme_network

  # ── pgAdmin (full DB management) ─────────────────────────────────────────────
  pgadmin:
    image: dpage/pgadmin4:8
    container_name: sme_pgadmin
    restart: unless-stopped
    environment:
      PGADMIN_DEFAULT_EMAIL:    admin@peace.local
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5051:80"
    networks:
      - sme_network
```

### Starting and Managing Services

```bash
# First start: build all images
docker compose up --build

# Start in background
docker compose up -d

# View logs for a specific service
docker compose logs -f backend

# Restart only the backend after a code change
docker compose up --build backend -d

# Stop all services
docker compose down

# Stop and remove all volumes (DESTROYS DATA)
docker compose down -v
```

---

## Part 4: Database Migration Strategy

The Python `init_db.py` tracked schema versions in `schema_migrations`. The Go equivalent uses `golang-migrate`.

### Setup golang-migrate

```bash
go get github.com/golang-migrate/migrate/v4
go get github.com/golang-migrate/migrate/v4/database/postgres
go get github.com/golang-migrate/migrate/v4/source/file
```

### Migration Files

```
backend-go/
└── migrations/
    ├── 000001_init_schema.up.sql
    ├── 000001_init_schema.down.sql
    ├── 000002_add_grants.up.sql
    ├── 000002_add_grants.down.sql
    ...
    ├── 000021_grant_new_fields.up.sql
    ├── 000021_grant_new_fields.down.sql
    ├── 000023_grant_srsp_relative.up.sql
    └── 000023_grant_srsp_relative.down.sql
```

Example migration file:

```sql
-- File: migrations/000001_init_schema.up.sql
CREATE TABLE IF NOT EXISTS users (
    user_id           SERIAL PRIMARY KEY,
    email_address     VARCHAR(255) UNIQUE NOT NULL,
    hashed_password   TEXT NOT NULL,
    first_name        VARCHAR(100),
    last_name         VARCHAR(100),
    middle_name       VARCHAR(100),
    cnic              VARCHAR(25),
    language          VARCHAR(10),
    gender            VARCHAR(10),
    mobile_no         VARCHAR(20),
    whatsapp_number   VARCHAR(20),
    terms_accepted    BOOLEAN DEFAULT FALSE,
    status            VARCHAR(20) DEFAULT 'unblocked',
    last_login_ip     VARCHAR(64),
    device_fingerprint VARCHAR(255),
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_cnic       ON users (cnic);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at DESC);
```

```sql
-- File: migrations/000001_init_schema.down.sql
DROP TABLE IF EXISTS users;
```

### Running Migrations in Go

```go
// File: cmd/server/main.go
package main

import (
    "log"

    "github.com/golang-migrate/migrate/v4"
    _ "github.com/golang-migrate/migrate/v4/database/postgres"
    _ "github.com/golang-migrate/migrate/v4/source/file"
)

func runMigrations(databaseURL string) {
    m, err := migrate.New(
        "file://migrations",
        databaseURL,
    )
    if err != nil {
        log.Fatalf("migration init: %v", err)
    }
    defer m.Close()

    if err := m.Up(); err != nil && err != migrate.ErrNoChange {
        log.Fatalf("migration up: %v", err)
    }
    log.Println("migrations applied successfully")
}
```

```go
func main() {
    cfg := config.Load()
    runMigrations(cfg.DatabaseURL)
    // ... start server
}
```

### Migration CLI Tool

```bash
# Install the migrate CLI
go install github.com/golang-migrate/migrate/v4/cmd/migrate@latest

# Apply all pending migrations
migrate -path migrations -database "postgres://sme_user:sme_password@localhost:5433/sme_app?sslmode=disable" up

# Roll back one migration
migrate -path migrations -database "..." down 1

# Check current version
migrate -path migrations -database "..." version
```

---

## Part 5: Health Check Endpoints

A health check endpoint lets the orchestrator (Docker, Kubernetes, load balancer) know if the service is ready.

```go
// File: internal/health/handler.go
package health

import (
    "context"
    "encoding/json"
    "net/http"
    "time"

    "github.com/jackc/pgx/v5/pgxpool"
    "github.com/redis/go-redis/v9"
)

type HealthStatus struct {
    Status   string            `json:"status"`
    Checks   map[string]string `json:"checks"`
    Uptime   string            `json:"uptime"`
}

type Handler struct {
    db        *pgxpool.Pool
    cache     *redis.Client
    startTime time.Time
}

func NewHandler(db *pgxpool.Pool, cache *redis.Client) *Handler {
    return &Handler{db: db, cache: cache, startTime: time.Now()}
}

func (h *Handler) Health(w http.ResponseWriter, r *http.Request) {
    ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
    defer cancel()

    checks := map[string]string{}
    status := "ok"

    // Check PostgreSQL
    if err := h.db.Ping(ctx); err != nil {
        checks["postgres"] = "unhealthy: " + err.Error()
        status = "degraded"
    } else {
        checks["postgres"] = "ok"
    }

    // Check Redis
    if err := h.cache.Ping(ctx).Err(); err != nil {
        checks["redis"] = "unhealthy: " + err.Error()
        status = "degraded"
    } else {
        checks["redis"] = "ok"
    }

    resp := HealthStatus{
        Status: status,
        Checks: checks,
        Uptime: time.Since(h.startTime).Round(time.Second).String(),
    }

    code := http.StatusOK
    if status != "ok" {
        code = http.StatusServiceUnavailable
    }

    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(code)
    json.NewEncoder(w).Encode(resp)
}
```

Register the route:

```go
mux.HandleFunc("/health", healthHandler.Health)
mux.HandleFunc("/ready", healthHandler.Ready) // same logic, used by load balancer
```

In `docker-compose.yml`:

```yaml
backend:
  healthcheck:
    test: ["CMD", "wget", "-qO-", "http://localhost:8080/health"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 10s
```

---

## Part 6: Graceful Shutdown

Go servers must handle `SIGINT` (Ctrl+C) and `SIGTERM` (Docker stop) gracefully: stop accepting new requests, finish in-flight requests, close database connections.

```go
// File: cmd/server/main.go
package main

import (
    "context"
    "log"
    "net/http"
    "os"
    "os/signal"
    "syscall"
    "time"
)

func main() {
    cfg := config.Load()
    db  := database.Connect(cfg)
    rdb := cache.Connect(cfg)

    // Run migrations before starting
    runMigrations(cfg.DatabaseURL)

    // Build the router
    router := buildRouter(cfg, db, rdb)

    srv := &http.Server{
        Addr:         ":" + cfg.Port,
        Handler:      router,
        ReadTimeout:  15 * time.Second,
        WriteTimeout: 120 * time.Second,
        IdleTimeout:  60 * time.Second,
    }

    // Start server in a goroutine so shutdown logic can run
    go func() {
        log.Printf("server listening on %s", srv.Addr)
        if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
            log.Fatalf("server error: %v", err)
        }
    }()

    // Wait for shutdown signals
    quit := make(chan os.Signal, 1)
    signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
    <-quit
    log.Println("shutdown signal received")

    // Give in-flight requests up to 30 seconds to complete
    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()

    if err := srv.Shutdown(ctx); err != nil {
        log.Printf("forced shutdown: %v", err)
    }

    db.Close()
    rdb.Close()
    log.Println("server stopped cleanly")
}
```

> [!NOTE]
> `docker compose stop` sends `SIGTERM` and waits 10 seconds before sending `SIGKILL`. With graceful shutdown, your server finishes current requests before the container stops.

---

## Part 7: Environment-Specific Builds

Different environments need different configuration. Use build tags and `.env` files.

### .env Files Per Environment

```
.env              # committed defaults (no secrets)
.env.local        # local overrides (gitignored)
.env.staging      # staging secrets (never committed)
.env.production   # production secrets (never committed)
```

### Loading Config in Go

```go
// File: internal/config/config.go
package config

import (
    "os"
    "strconv"
)

type Config struct {
    Port                  string
    DatabaseURL           string
    RedisURL              string
    JWTSecret             string
    GrantApplicationOpen  bool
    GrantRequireSelection bool
    HFCShadowMode         bool
    GeoBlockEnabled       bool
    AllowedCountryCodes   []string
    MaxActiveApplicants   int
    AccessSlotTTLSec      int
}

func Load() *Config {
    return &Config{
        Port:                  getEnv("PORT", "8080"),
        DatabaseURL:           buildDatabaseURL(),
        RedisURL:              getEnv("REDIS_URL", "redis://localhost:6379/0"),
        JWTSecret:             requireEnv("JWT_SECRET_KEY"),
        GrantApplicationOpen:  getBool("GRANT_APPLICATION_OPEN", false),
        GrantRequireSelection: getBool("GRANT_REQUIRE_SELECTION", true),
        HFCShadowMode:         getBool("HFC_SHADOW_MODE", true),
        GeoBlockEnabled:       getBool("GEO_BLOCK_ENABLED", false),
        AllowedCountryCodes:   splitCSV(getEnv("ALLOWED_COUNTRY_CODES", "PK")),
        MaxActiveApplicants:   getInt("MAX_ACTIVE_APPLICANTS", 300),
        AccessSlotTTLSec:      getInt("ACCESS_SLOT_TTL_SEC", 90),
    }
}

func requireEnv(key string) string {
    v := os.Getenv(key)
    if v == "" {
        panic("required environment variable not set: " + key)
    }
    return v
}

func getBool(key string, def bool) bool {
    v := os.Getenv(key)
    if v == "" {
        return def
    }
    return v == "1" || v == "true"
}

func getInt(key string, def int) int {
    v := os.Getenv(key)
    if v == "" {
        return def
    }
    n, err := strconv.Atoi(v)
    if err != nil {
        return def
    }
    return n
}
```

---

## Part 8: Prometheus Metrics

Expose metrics so you can alert on latency and error rates.

```bash
go get github.com/prometheus/client_golang/prometheus
go get github.com/prometheus/client_golang/prometheus/promhttp
```

```go
// File: internal/metrics/metrics.go
package metrics

import (
    "net/http"
    "strconv"
    "time"

    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promauto"
)

var (
    RequestDuration = promauto.NewHistogramVec(
        prometheus.HistogramOpts{
            Name:    "http_request_duration_seconds",
            Help:    "HTTP request latency",
            Buckets: prometheus.DefBuckets,
        },
        []string{"method", "path", "status"},
    )

    HFCScoresCalculated = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "hfc_scores_calculated_total",
            Help: "Number of HFC scores calculated",
        },
        []string{"risk_level"},
    )

    GrantsApproved = promauto.NewCounter(prometheus.CounterOpts{
        Name: "grants_approved_total",
        Help: "Number of grants approved",
    })

    ActiveSessions = promauto.NewGauge(prometheus.GaugeOpts{
        Name: "active_sessions_current",
        Help: "Current number of active applicant sessions",
    })
)

// InstrumentHandler wraps an HTTP handler to record request metrics.
func InstrumentHandler(pattern string, next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        rw := &responseWriter{w, http.StatusOK}
        next.ServeHTTP(rw, r)
        duration := time.Since(start).Seconds()
        RequestDuration.WithLabelValues(
            r.Method, pattern, strconv.Itoa(rw.statusCode),
        ).Observe(duration)
    })
}

type responseWriter struct {
    http.ResponseWriter
    statusCode int
}

func (rw *responseWriter) WriteHeader(code int) {
    rw.statusCode = code
    rw.ResponseWriter.WriteHeader(code)
}
```

Register the metrics endpoint:

```go
import "github.com/prometheus/client_golang/prometheus/promhttp"

mux.Handle("/metrics", promhttp.Handler())
```

---

## Part 9: Release Git Workflow

### Semantic Versioning

Format: `MAJOR.MINOR.PATCH`

| Change | Version bump |
|---|---|
| New API endpoint | MINOR (v0.1.0 → v0.2.0) |
| Bug fix | PATCH (v0.2.0 → v0.2.1) |
| Breaking response format change | MAJOR (v0.x.x → v1.0.0) |

### Tagging a Release

```bash
# Finish all work on main or release branch
git checkout main
git pull

# Create annotated tag (preferred over lightweight tags)
git tag -a v0.1.0 -m "First Go API compatibility milestone

- All public endpoints implemented
- JWT auth working
- Business profile CRUD
- Grant submission and whitelist gate"

# Push the tag
git push origin v0.1.0
```

### Release Branch Workflow

```bash
# Cut a release branch from develop when feature-complete
git checkout develop
git checkout -b release/v1.0.0

# Only bug fixes allowed on release branch
git commit -m "Fix whitelist check on PUT /api/grant"

# Merge to main and tag
git checkout main
git merge release/v1.0.0
git tag -a v1.0.0 -m "First production release"

# Back-merge to develop
git checkout develop
git merge release/v1.0.0
git branch -d release/v1.0.0
```

### Hotfix Workflow

```bash
# Bug discovered in production at v1.0.0
git checkout -b hotfix/blocked-user-login v1.0.0
git commit -m "Fix blocked user returning 500 instead of 403"

git checkout main
git merge hotfix/blocked-user-login
git tag -a v1.0.1 -m "Fix blocked user login response"

git checkout develop
git merge hotfix/blocked-user-login
git branch -d hotfix/blocked-user-login
```

---

## Part 10: Rollback Strategy

### Code Rollback

Docker image tags make code rollback deterministic:

```bash
# Roll back to previous image
docker compose stop backend
docker tag peace-sme-backend:v0.1.0 peace-sme-backend:current
docker compose up -d backend

# Or use docker-compose.override.yml to pin an image
```

### Database Rollback

Schema changes are the hardest to roll back. The strategy:

1. **Forward-fix preferred**: rather than rolling back schema, add a new migration that restores safe state.
2. **Non-destructive migrations**: add columns with defaults (no data loss). Drop columns in a separate migration after code is stable.
3. **Down migrations**: keep `down.sql` files but treat them as emergency tools, not routine operations.

```bash
# Roll back one migration (emergency only)
migrate -path migrations -database "$DATABASE_URL" down 1
```

### Rollback Checklist

```
Before rollback:
  [ ] Identify the last known-good image tag or commit hash
  [ ] Note which migrations have run in production
  [ ] Snapshot the database (pg_dump)
  [ ] Notify the team

During rollback:
  [ ] docker compose stop backend worker
  [ ] Restore previous image or redeploy tagged release
  [ ] Run down migrations if the schema changed
  [ ] Flush Redis cache: redis-cli FLUSHDB
  [ ] docker compose up backend worker

After rollback:
  [ ] Smoke test critical paths
  [ ] Confirm /health returns "ok"
  [ ] Confirm login works
  [ ] Confirm admin dashboard loads
```

---

## Part 11: Mastery Roadmap

### Go Mastery Path

| Stage | Topics | Portal tasks |
|---|---|---|
| Beginner | packages, functions, structs, errors | `/health`, `/api/updates` |
| Intermediate | interfaces, goroutines, context, SQL | auth, business profile, reports |
| Advanced | profiling, race detector, generics | HFC scoring, concurrent reports |
| Mastery | stdlib internals, net/http source | custom middleware, HTTP/2 |

**Specific actions:**
- Read the `net/http` source in `$GOROOT/src/net/http/`.
- Use `go test -race ./...` on every PR.
- Profile a slow report query: `go test -cpuprofile cpu.out`, then `go tool pprof cpu.out`.
- Refactor only after tests protect behavior.
- Practice: implement one HFC rule as a pure function, test it, commit it, repeat.

### Vue 3 Mastery Path

| Stage | Topics | Portal tasks |
|---|---|---|
| Beginner | ref, reactive, v-model, v-if, v-for | login form, business form |
| Intermediate | computed, watch, composables, emit | language switcher, pagination |
| Advanced | provide/inject, Suspense, transitions | admin dashboard, chart |
| Mastery | custom directives, plugin authoring, SSR | performance optimization |

**Specific actions:**
- Build the bilingual label system as a composable `useLanguage()`.
- Test every route guard: write Cypress tests for protected routes.
- Keep API calls in one file (Axios instance); never scatter `fetch` calls across components.
- Treat `lang='urdu'` and RTL as first-class requirements, not an afterthought.

### Git Mastery Path

| Stage | Topics | Practice |
|---|---|---|
| Beginner | commit, branch, merge | one commit per logical unit |
| Intermediate | rebase, reset, bisect | rebase feature branch onto main |
| Advanced | reflog, cherry-pick, rerere | recover from bad merge |
| Mastery | custom hooks, worktrees | pre-commit lint, pre-push tests |

---

## Final Capstone Checklist

The Go + Vue rewrite is complete when:

```
API Compatibility
  [ ] All 70+ /api/* endpoints exist in Go
  [ ] Response shapes match the Flask original exactly
  [ ] JWT tokens issued by Go are validated by the Vue frontend
  [ ] Pagination shape is {data, total, page, per_page}

Auth & Security
  [ ] User login returns {token, user_id, language}
  [ ] Admin login returns {token, role, can_approve}
  [ ] Blocked user returns 403
  [ ] Geo-block returns 403 for non-PK IPs
  [ ] Access slot limit returns 429

Business Logic
  [ ] Registration closed (403) when GRANT_APPLICATION_OPEN=0
  [ ] Whitelist gate enforced when GRANT_REQUIRE_SELECTION=1
  [ ] Only in-scope districts accepted
  [ ] HFC scoring calculates correct risk bands
  [ ] Shadow mode: HFC score visible but does not block approval
  [ ] Only approving_authority role can approve grants

Infrastructure
  [ ] PostgreSQL schema matches 23-migration history
  [ ] Redis caching for updates, FAQs, filter options, stats
  [ ] S3 presigned URLs with 60-minute validity
  [ ] Email jobs enqueued to background worker
  [ ] /health endpoint returns postgres + redis status

Deployment
  [ ] docker compose up --build starts all 7 services
  [ ] Migrations run on startup
  [ ] Graceful shutdown on SIGTERM
  [ ] Vue frontend proxied through nginx

Testing
  [ ] HFC scoring rules have unit tests
  [ ] JWT middleware tested with httptest
  [ ] Whitelist gate tested
  [ ] Coverage above 70% for core packages

Release
  [ ] v0.1.0 tag exists
  [ ] CHANGELOG or commit log documents what changed
  [ ] Rollback plan documented
```

---

## Mastery Check

You understand this chapter when you can answer:

1. Why does a multi-stage Docker build produce a smaller image than a single-stage build? What is removed between stages?
2. What does `CGO_ENABLED=0` do and why is it necessary for a `scratch` base image?
3. The Go server receives `SIGTERM`. Walk through exactly what happens if you have implemented graceful shutdown correctly.
4. A critical bug is found in v1.0.0 production. Write the exact Git commands to create a hotfix branch, fix the bug, tag v1.0.1, and merge back to both `main` and `develop`.
5. What is the difference between `migrate up` and a `forward-fix migration`, and when should you prefer one over the other?
