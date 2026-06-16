# Chapter 0: Go Toolchain Setup and Your First Program

## Purpose

Before writing a single line of the PEACE SME portal, you need a working Go environment and a clear mental model of what Go is. This chapter takes you from nothing to a running HTTP server. It also gives you a concrete weekend learning plan so you know exactly what to build each day.

---

## What Go Is (and Why It Fits This Project)

Go is a compiled, statically typed, garbage-collected language created at Google in 2009. For a backend developer coming from Python or JavaScript, the biggest differences are:

| Python/JavaScript | Go |
|---|---|
| Dynamic types — any variable can hold any value | Static types — every variable has a declared type checked at compile time |
| Exceptions (`try/catch`) | Errors as return values — you must check them explicitly |
| Runs in an interpreter | Compiles to a native binary — no runtime needed on the server |
| Slow startup | Instant startup — the binary is self-contained |
| GIL or event loop for concurrency | True OS threads + lightweight goroutines |
| Flexible package layout | `cmd/` and `internal/` conventions enforced by the toolchain |

For the PEACE SME portal, Go gives us:
- A single binary that runs inside a Docker container with no Python installed.
- Fast startup so Docker Compose restarts are almost instant.
- Goroutines for handling hundreds of concurrent HTTP requests.
- Static type checks that catch shape mismatches between the database model and the JSON response before the code ever runs.

---

## Installing Go

### Step 1: Download

Go to [go.dev/dl](https://go.dev/dl) and download the installer for your system. Always choose the latest stable release (1.21 or later — the portal requires 1.21+ for `log/slog`).

### Step 2: Install

**Linux (tar.gz):**
```bash
# Remove any previous Go installation
sudo rm -rf /usr/local/go

# Extract to /usr/local
sudo tar -C /usr/local -xzf go1.21.x.linux-amd64.tar.gz

# Add to PATH in ~/.bashrc or ~/.zshrc
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
source ~/.bashrc
```

**macOS (pkg installer):** Run the `.pkg` file. It sets the PATH automatically.

**Windows:** Run the `.msi` installer. It sets the PATH automatically.

### Step 3: Verify

```bash
go version
# Output: go version go1.21.x linux/amd64
```

If you see a version number, Go is installed.

---

## GOPATH and GOROOT — Explained Once

New Go developers are often confused by two environment variables:

**`GOROOT`** — where Go is installed (e.g. `/usr/local/go`). You never touch this. The toolchain manages it.

**`GOPATH`** — your Go workspace. Defaults to `~/go`. It contains:
- `~/go/bin/` — installed binaries from `go install` (e.g. `gopls`, `goimports`)
- `~/go/pkg/` — compiled package caches
- `~/go/src/` — historically where code lived before modules (you can ignore this)

Since Go 1.11 introduced Modules, you no longer need to put your code inside `GOPATH/src`. You can put projects anywhere. The `go.mod` file in the project root defines the module.

**Short version:** Leave `GOROOT` alone. Add `~/go/bin` to your `PATH` so installed tools work.

```bash
echo 'export PATH=$PATH:$(go env GOPATH)/bin' >> ~/.bashrc
source ~/.bashrc
```

---

## Go Toolchain Commands Reference

These are the commands you will use constantly while building the portal.

### `go run`
Compile and run in one step. No binary is saved.
```bash
go run cmd/server/main.go
go run .   # run the package in the current directory
```
Use this during development when you want instant feedback.

### `go build`
Compile to a binary.
```bash
go build -o server ./cmd/server    # Output: ./server
```
The binary is self-contained. Copy it to any Linux machine and it runs.

For production Docker builds, add flags to strip debug symbols and reduce binary size:
```bash
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-w -s" -o server ./cmd/server
```

### `go test`
Run tests. The most important command in this book.
```bash
go test ./...                              # run all tests in all packages
go test ./internal/user/...               # run tests in one package
go test ./internal/user -run TestLogin -v # run one test verbosely
go test -race ./...                        # run with data race detector
go test -cover ./...                       # show coverage percentages
```

### `go mod`
Manage the `go.mod` and `go.sum` files.
```bash
go mod init peace-sme-go    # create a new module
go mod tidy                  # remove unused dependencies, add missing ones
go mod download              # download all dependencies without building
go mod verify                # check that cached modules match go.sum checksums
```

### `go get`
Add or update a dependency.
```bash
go get github.com/jackc/pgx/v5@v5.5.0
go get github.com/golang-jwt/jwt/v5
go get golang.org/x/crypto
```

After adding, run `go mod tidy` to clean up.

### `go fmt`
Format code to Go's standard style. No configuration, no debates.
```bash
go fmt ./...
```
Many editors run this on save automatically. The portal's CI will reject unformatted code.

### `go vet`
Static analysis for common bugs.
```bash
go vet ./...
```
Catches issues like: passing wrong types to `fmt.Printf`, unreachable code, suspicious string conversions.

### `go doc`
Look up documentation without leaving the terminal.
```bash
go doc encoding/json Marshal
go doc github.com/jackc/pgx/v5/pgxpool
```

---

## Your First Go Program

Create a directory and initialize a module:
```bash
mkdir hello-go && cd hello-go
go mod init hello-go
```

Create `main.go`:
```go
package main

import "fmt"

func main() {
    fmt.Println("Hello from the PEACE SME portal!")
}
```

Run it:
```bash
go run main.go
# Output: Hello from the PEACE SME portal!
```

Now evolve it into a minimal HTTP server — closer to what the portal actually is:

```go
package main

import (
    "encoding/json"
    "fmt"
    "log"
    "net/http"
)

func main() {
    mux := http.NewServeMux()

    // Register a health-check route
    mux.HandleFunc("/ping", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
    })

    // Register a second route
    mux.HandleFunc("/api/updates", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        updates := []map[string]string{
            {"title": "Portal is live", "body": "Registration opens Monday."},
        }
        json.NewEncoder(w).Encode(updates)
    })

    addr := ":8080"
    fmt.Printf("Server listening on %s\n", addr)
    log.Fatal(http.ListenAndServe(addr, mux))
}
```

Run it and test in another terminal:
```bash
go run main.go &
curl http://localhost:8080/ping
# {"status":"ok"}
curl http://localhost:8080/api/updates
# [{"body":"Registration opens Monday.","title":"Portal is live"}]
```

This is the shape of every endpoint you will build in the portal. More structure, more packages, more middleware — but the core is always: register a path, write a function, return JSON.

---

## VS Code Setup

1. Install [Visual Studio Code](https://code.visualstudio.com/).
2. Install the **Go** extension by the Go Team at Google (`golang.go`).
3. Open the command palette (`Ctrl+Shift+P`) and run: `Go: Install/Update Tools`. Select all tools and install them. This installs `gopls` (language server), `dlv` (debugger), `goimports`, and others.
4. Add to your VS Code `settings.json`:
```json
{
    "editor.formatOnSave": true,
    "[go]": {
        "editor.defaultFormatter": "golang.go"
    },
    "go.lintTool": "golangci-lint",
    "go.testFlags": ["-v", "-race"]
}
```

With this setup, saving a file automatically formats it, and errors from `gopls` appear inline as you type — like a type checker running in real time.

---

## Understanding `go.mod`

When you run `go mod init peace-sme-go`, Go creates:

```
module peace-sme-go

go 1.21

require (
    github.com/golang-jwt/jwt/v5 v5.2.0
    github.com/jackc/pgx/v5 v5.5.0
    github.com/redis/go-redis/v9 v9.3.1
    golang.org/x/crypto v0.17.0
)
```

- **`module peace-sme-go`** — the module path. When you write `import "peace-sme-go/internal/config"`, Go finds the package at `./internal/config/` relative to this root.
- **`go 1.21`** — the minimum Go version required.
- **`require`** — pinned dependencies. Each line is `package@version`. The specific version is committed in source control so every developer and every CI run gets the exact same code.

`go.sum` is a lockfile. It records cryptographic hashes of every dependency. If a package on a public mirror is tampered with after you recorded it, `go mod verify` will detect the mismatch and refuse to build.

---

## Project Layout for This Book

The portal follows Go's `cmd/` + `internal/` convention:

```
peace-sme-go/
├── cmd/
│   └── server/
│       └── main.go          ← entry point: load config, build app, listen
├── internal/
│   ├── app/
│   │   └── app.go           ← wire all packages together
│   ├── config/
│   │   └── config.go        ← parse environment variables
│   ├── db/
│   │   └── models.go        ← PostgreSQL entity structs
│   ├── httpx/
│   │   └── json.go          ← WriteJSON, WriteError helpers
│   ├── health/
│   │   └── handler.go       ← GET /health
│   ├── auth/
│   │   └── jwt.go           ← JWT signing and verification
│   ├── middleware/
│   │   ├── auth.go          ← bearer token verification
│   │   ├── geoblock.go      ← CF-IPCountry header check
│   │   └── ratelimit.go     ← Redis session slot limiter
│   ├── user/
│   │   ├── handler.go       ← HTTP handlers
│   │   ├── service.go       ← business logic
│   │   └── repository.go    ← SQL queries
│   ├── business/            ← same structure as user/
│   ├── grant/               ← same structure
│   ├── admin/               ← same structure
│   ├── hfc/                 ← fraud detection scorer
│   ├── cache/
│   │   └── redis.go         ← Redis JSON cache wrapper
│   └── storage/
│       └── s3.go            ← S3 presigned URLs
├── go.mod
└── go.sum
```

**Why `internal/`?** Packages inside `internal/` can only be imported by code inside the parent tree. If you publish `peace-sme-go` as a module, outside code cannot import `peace-sme-go/internal/user`. This enforces that these packages are implementation details, not a public API.

**Why `cmd/`?** A Go project can have multiple executables. `cmd/server/` is the HTTP server. You might later add `cmd/worker/` for the background job processor. Each directory under `cmd/` becomes a separate binary.

---

## Common Beginner Mistakes

### 1. Forgetting to check errors

```go
// WRONG — user might be nil if sql.ErrNoRows
user, _ := repo.FindByEmail(ctx, email)
fmt.Println(user.FirstName) // panic: nil pointer dereference

// CORRECT
user, err := repo.FindByEmail(ctx, email)
if err != nil {
    return fmt.Errorf("finding user: %w", err)
}
if user == nil {
    return ErrUserNotFound
}
```

The `_` tells Go you intentionally discard the error. Never do this for database operations, file I/O, or network calls.

### 2. Writing to a nil map

```go
// WRONG — var m map[string]bool creates a nil map
var countryCodes map[string]bool
countryCodes["PK"] = true  // panic: assignment to entry in nil map

// CORRECT
countryCodes := make(map[string]bool)
countryCodes["PK"] = true
```

### 3. Shadowing variables with `:=`

```go
err := doFirst()
if err != nil {
    // handle
}
// This creates a NEW err variable scoped to the if block, not the outer err:
if result, err := doSecond(); err != nil {
    // This err is the one from doSecond
}
// The outer err is still the one from doFirst
```

Use `=` inside a block when you want to reuse the outer variable.

### 4. Slices share underlying arrays

```go
a := []int{1, 2, 3}
b := a[1:3]   // b shares memory with a
b[0] = 99
fmt.Println(a) // [1 99 3] — a was modified!

// To get an independent copy:
b := make([]int, 2)
copy(b, a[1:3])
```

### 5. String indexing gives bytes, not characters

```go
s := "hello"
fmt.Println(s[0])        // 104 (byte value of 'h')
fmt.Println(string(s[0])) // "h"

// For Unicode (Urdu text):
for _, r := range s {
    fmt.Printf("%c\n", r) // r is a rune (int32), not a byte
}
```

---

## Go Formatting: No Style Debates

`gofmt` (and `goimports`) produce a single canonical format for all Go code. There are no `.editorconfig` files, no Prettier configs, no team arguments about tabs vs spaces. Go tabs are 1 tab wide. Braces go on the same line. The formatter handles everything else.

This matters at scale: when you read any Go code in the standard library, in `pgx`, in `chi`, or in your own project, it all looks the same.

---

## Weekend Learning Plan

The portal is a large system. Build it in deliberate layers, not all at once. Here is a concrete schedule:

### Saturday Morning — 3 hours
**Goal: Go program that reads config and serves one route**

- Read Chapters 0–3: toolchain, system overview, project structure
- Initialize `go.mod`
- Create `internal/config/config.go` (parse all env vars)
- Create `internal/httpx/json.go` (WriteJSON, WriteError helpers)
- Create `cmd/server/main.go` (load config, start server)
- Serve `GET /health` returning `{"status":"ok"}`
- Commit: `git commit -m "Add config loader and health endpoint"`

### Saturday Afternoon — 3 hours
**Goal: Database connected, auth middleware working**

- Read Chapters 4–6: configuration, database models, auth/middleware
- Create `internal/db/models.go` (User, Business, Grant structs)
- Connect pgx pool at startup
- Implement JWT service: `GenerateUserToken`, `VerifyUserToken`
- Implement auth middleware
- Serve `POST /api/login` returning a real JWT
- Commit per layer: models, JWT, middleware, login handler

### Saturday Evening — 2 hours
**Goal: Applicant vertical slice works end-to-end**

- Read Chapter 7: registration, login, business profile
- Implement `GET /api/user/profile`
- Implement `GET/POST/PUT /api/business`
- Test with `curl` — a login followed by a profile fetch

### Sunday Morning — 3 hours
**Goal: Uploads and Redis working**

- Read Chapters 8–10: grants, storage, Redis/jobs
- Implement `POST /api/grant` with JSONB fields
- Connect S3 client, implement presigned URL generation
- Connect Redis client, implement cache wrapper
- Implement access slot middleware (Redis session counter)
- Commit: one commit per infrastructure concern

### Sunday Afternoon — 3 hours
**Goal: Admin reports and HFC scoring working**

- Read Chapters 11–12: admin reports, HFC approval
- Implement paginated applicant report
- Implement dashboard stats with Redis cache
- Implement HFC scorer (all 10 rules)
- Implement grant approval with transaction + audit log
- Commit: one commit per report, then HFC, then approval

### Sunday Evening — 2 hours
**Goal: Vue frontend calls Go backend successfully**

- Read Chapters 13–14: Vue integration
- Configure Axios base URL to point to Go server
- Test login from Vue form to Go JWT and back
- Verify admin dashboard loads from Go endpoint
- Commit: `git commit -m "Vue connects to Go backend - login and dashboard verified"`

### Stretch Goals (after the weekend)
- Chapter 15: Testing — write table-driven tests for critical endpoints
- Chapter 16: Deployment — Dockerfile for the Go binary
- Chapter 17: Fill any Go concept gaps from the primer

---

## Go Playground

For quick experiments when you do not want to set up a file: [go.dev/play](https://go.dev/play)

Paste any Go program and run it in your browser. The playground has the standard library but no third-party packages, so it is best for learning language features — structs, goroutines, interfaces — not for testing database or Redis code.

---

## Mastery Check

You understand this chapter when you can:

- Install Go and verify the installation.
- Explain what `GOPATH` is and why you add `~/go/bin` to your `PATH`.
- Run `go run`, `go build`, `go test`, `go fmt`, `go mod tidy` and know what each does.
- Write a Go program that starts an HTTP server and responds with JSON.
- Explain the `cmd/` and `internal/` directory conventions.
- Name three common Go beginner mistakes and explain how to avoid them.
- Describe the weekend plan: what you will build each session.
