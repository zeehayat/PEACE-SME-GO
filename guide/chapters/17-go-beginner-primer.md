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

## Capstone Exercise

Build a tiny vertical slice:

1. Define `LoginRequest` and `LoginResponse`.
2. Implement `UserRepository.FindByEmail`.
3. Implement `UserService.Login`.
4. Implement `POST /api/login`.
5. Add a Vue login form that stores `userToken`.
6. Commit each layer separately.

When this works, you have practiced structs, methods, pointers, interfaces, errors, context, JSON, SQL, Vue state, and Git.

