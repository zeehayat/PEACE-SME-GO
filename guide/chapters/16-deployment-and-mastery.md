# Chapter 16: Deployment, Release Git, and Mastery Roadmap

## Purpose

The final stage is operating the rewritten application: build artifacts, containers, migrations, environment configuration, release tags, and rollback strategy.

## Theoretical Background

### Multi-Stage Container Builds
Docker images are built layer-by-layer. Every instruction in a `Dockerfile` (e.g., `RUN`, `COPY`) adds a new layer to the image.
- **Cache Optimization:** By copying dependency files (like `go.mod` and `go.sum`) first and running `go mod download`, Docker caches the dependencies. Source code changes will not trigger re-downloading dependencies, speeding up builds.
- **Multi-Stage Builds:** Allow you to separate compile environments from deployment runtimes. You compile the Go app inside a heavy, tool-rich image (`golang:1.22`), then copy only the compiled binary into a minimal execution runtime image (like `alpine` or `scratch`).
- This reduces the final production image size from ~1GB down to ~30MB, eliminating build tools and reducing the security attack surface.

```text
[ Stage 1: Build Env ] ---> Compiles Go code ---> (Server Binary)
                                                        | (Copy Binary)
                                                        v
[ Stage 2: Runtime Env ] <----------------------- [ Alpine / Scratch Image ] (Minimal Size)
```

### Semantic Versioning (SemVer)
Releases are versioned using a standard three-part format: `MAJOR.MINOR.PATCH` (e.g., `v1.4.2`):
- **MAJOR:** Increment when you make incompatible API changes.
- **MINOR:** Increment when you add functionality in a backwards-compatible manner.
- **PATCH:** Increment when you make backwards-compatible bug fixes.

### Git Flow Branching Model
A structured branching workflow facilitates organized software development and releases:
- **`main`:** Stores production-ready code. Every commit here matches a tagged release.
- **`develop`:** Integration branch for features.
- **`feature/` branches:** Short-lived branches created from `develop` to work on single features, merged back via pull requests.
- **`release/` branches:** Created from `develop` when preparing for a release. Only bug fixes are allowed here before merging into `main` and `develop`.
- **`hotfix/` branches:** Branches cut directly from `main` to address critical production issues, merged back to `main` and `develop`.

### External Resources
- [Semantic Versioning 2.0.0 Specification](https://semver.org/)
- [Docker Documentation: Best Practices for Writing Dockerfiles](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [Atlassian Git Tutorials: Git Flow Workflows](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow)

---

## Deployment Units

The system has:
- PostgreSQL 15.
- Redis 7.
- Go backend.
- Go worker or compatible worker process.
- Vue frontend served by nginx.
- Adminer or pgAdmin for database inspection.

---

## Release Git

Use tags:

```bash
git tag -a v0.1.0 -m "First Go API compatibility milestone"
git push origin v0.1.0
```

Use release branches when stabilizing:

```bash
git checkout -b release/v1.0.0
```

Use hotfix branches from the release tag:

```bash
git checkout -b hotfix/login-blocked-users v1.0.0
```

---

## Rollback Strategy

A rollback plan includes:
- Previous container image tag.
- Database migration rollback or forward-fix plan.
- Preserved environment variables.
- Redis cache invalidation.
- Smoke tests after rollback.

Never deploy schema changes casually. Database compatibility is harder to roll back than code.

---

## Practical Examples

### Example 1: Multi-Stage Production Dockerfile for Go Backend
This Dockerfile compiles a statically-linked Go binary in a build stage and runs it inside a minimal Alpine container containing no compilers or build tools:

```dockerfile
# STEP 1: Build phase
FROM golang:1.22-alpine AS builder

# Install certificates and git
RUN apk update && apk add --no-cache git ca-certificates

WORKDIR /app

# Copy dependency manifests first to leverage Docker caching
COPY go.mod go.sum ./
RUN go mod download

# Copy application source files
COPY . .

# Compile binary statically, disabling CGO and targetting OS/Arch
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-w -s" -o server ./cmd/server

# STEP 2: Minimal Runtime phase
FROM alpine:3.19

# Import certificates to enable secure outbound HTTPS calls
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /app/server /usr/local/bin/server

# Create a non-root group and user for security isolation
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/server"]
```

### Example 2: Dockerfile and Nginx setup for Vue Frontend
This multi-stage Dockerfile builds the static Vue asset bundle and serves it using Nginx, including custom routing fallbacks for single page applications:

```dockerfile
# STEP 1: Node Build phase
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# STEP 2: Nginx Web Server phase
FROM nginx:1.25-alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# Replace default configuration with one optimized for SPA routers
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

Example supporting config file (`nginx.conf`) to ensure client-side routing fallback:
```nginx
server {
    listen 80;
    server_name localhost;

    location / {
        root /usr/share/nginx/html;
        index index.html index.htm;
        # Direct all URI requests to index.html for client-side routing
        try_files $uri $uri/ /index.html;
    }

    # Proxy API calls to Go backend server
    location /api {
        proxy_pass http://sme_backend_app:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Mastery Roadmap

To master Go:
- Read standard library HTTP code.
- Practice contexts, interfaces, errors, and tests.
- Profile slow report queries.
- Use `go test -race`.
- Refactor only after tests protect behavior.

To master Vue:
- Build small components with clear props and emits.
- Keep API calls centralized.
- Manage form state explicitly.
- Test route guards and complex conditional forms.
- Treat accessibility and bilingual layout as core requirements.

To master Git:
- Commit in small units.
- Read diffs before every commit.
- Use branches intentionally.
- Practice conflict resolution.
- Tag releases.
- Learn bisect for regression hunting.

---

## Final Capstone

The capstone is complete when:
- All documented `/api` endpoints exist in Go.
- Existing Vue screens work against the Go backend.
- New Vue screens reproduce the applicant and admin workflows.
- PostgreSQL schema matches the original.
- Redis caching and access control work.
- HFC scoring and approval logs work.
- S3 uploads work.
- Email jobs are queued.
- Tests cover critical workflows.
- A release tag marks the milestone.
