# Chapter 6: Authentication, JWT, bcrypt, and Middleware

## Purpose

Authentication is where backend compatibility matters immediately. The Vue frontend stores tokens and sends them as opaque bearer strings. The Go backend must issue and verify compatible JWTs. In this chapter, we will learn how Go handles functions as first-class citizens, how to use closures to configure handlers, and how `context.Context` propagates metadata. We will then build an authentication middleware chain.

Application parallel: this chapter builds the security boundary for both applicants and admins. The applicant uses `UserLogin.vue` and receives `userToken`. The admin uses `AdminLogin.vue` and receives `adminToken`. The same Go server must understand both tokens, but permissions are different.

---

## Foundational Concepts Explained Simply

### 1. First-Class Functions & Closures
In Go, functions are **first-class citizens**, meaning they behave like any other value:
- You can assign a function to a variable.
- You can pass a function as an argument to another function.
- You can return a function from a function.

A **Closure** is an anonymous function that references variables from outside its immediate body. The function "closes over" those variables, carrying them along wherever it is passed.

Here is an example demonstrating a closure that returns a custom greeting handler:

```go
package main

import "fmt"

// GreetingGenerator returns a function that takes a name string
func GreetingGenerator(prefix string) func(string) string {
    // This anonymous function is a closure because it references 'prefix'
    return func(name string) string {
        return fmt.Sprintf("%s, %s!", prefix, name)
    }
}

func main() {
    sayHello := GreetingGenerator("Hello")
    sayUrdu := GreetingGenerator("اسلام علیکم")

    fmt.Println(sayHello("Aftab")) // Prints "Hello, Aftab!"
    fmt.Println(sayUrdu("Aftab"))  // Prints "اسلام علیکم, Aftab!"
}
```

### 2. Context (`context.Context`)
When an HTTP request enters a Go server, it creates a request-specific lifecycle.
- Go uses `context.Context` to propagate deadlines, cancellation signals, and request-scoped values down the call stack (e.g., from middleware to handlers to repositories).
- **Injecting values:** Use `context.WithValue(parentContext, key, value)`. Contexts are immutable; this returns a *new* child context containing the key-value pair.
- **Reading values:** Use `ctx.Value(key)` to fetch the value.
  > [!TIP]
  > Always declare a custom, unexported type for context keys to prevent other packages from accidentally overwriting your values.

```go
type contextKey string
const UserKey contextKey = "user_id"

// Injecting
ctx := context.WithValue(r.Context(), UserKey, 42)

// Extracting
userID := ctx.Value(UserKey).(int) // Type assertion
```

### External Resources
- [Go Tour: Function Closures](https://go.dev/tour/moretypes/25)
- [Go Blog: Context Package Explained](https://go.dev/blog/context)
- [Go Web Examples: Middleware](https://gowebexamples.com/middleware/)

---

## User JWT

Payload:

```json
{ "user_id": 42, "exp": 1234567890 }
```

Rules:
- HS256.
- Secret from `JWT_SECRET_KEY`.
- Expiry: 24 hours.

Beginner explanation: a JWT is a signed string. The server does not need to store it in a sessions table. The browser sends it back, and the server verifies the signature. If someone edits the `user_id` inside the token, verification fails.

---

## Admin JWT

Payload:

```json
{
  "admin_username": "admin1",
  "role": "admin",
  "is_admin": true,
  "is_approver": false,
  "exp": 1234567890
}
```

Rules:
- HS256.
- Secret from `JWT_SECRET_KEY`.
- Expiry: 8 hours.
- `is_approver` comes from `can_approve_grants`.

Application parallel: loading an admin report requires admin identity. Approving a grant requires approver identity. That is why `is_admin` and `is_approver` are separate claims.

---

## bcrypt

Use `golang.org/x/crypto/bcrypt`:

```go
err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
```

Never log plaintext passwords. Never return whether the email or password was wrong separately for normal user login.

Beginner explanation: bcrypt is intentionally slow. You never decrypt a bcrypt hash. You compare a password attempt against the stored hash. This protects users if hashes are ever exposed.

---

## Middleware Pipeline

The original request pipeline is:

```text
apply_geo_block()
apply_access_control()
authenticate_token()
```

In Go, build composable middleware:

```go
handler := Recover(
    Logger(
        GeoBlock(
            AccessControl(
                Auth(router),
            ),
        ),
    ),
)
```

Admin routes skip geo-block. Public routes skip auth. Applicant-only and admin-only routes require different token claims.

## Application Parallel: Route Categories

| Route category | Example | Middleware needed | Identity needed |
|---|---|---|---|
| Public | `GET /api/updates` | logging, recovery | none |
| Public auth | `POST /api/login` | logging, recovery, applicant access controls if enabled | none |
| Applicant | `GET /api/business` | user auth | `user_id` |
| Admin | `GET /api/admin/applicants/report` | admin auth | `admin_username`, `role` |
| Approver | `POST /api/admin/grants/<user_id>/approve` | admin auth plus approver check | `is_approver=true` |

The beginner mistake is to make one global middleware decision for every route. This portal has public pages, applicant pages, admin pages, and approver-only actions.

---

## Context Values

After auth, attach identity to request context:

```go
type Identity struct {
    UserID        int64
    AdminUsername string
    Role          string
    IsAdmin       bool
    IsApprover    bool
}
```

Handlers can read identity from context without reparsing JWTs.

Use a helper instead of type assertions everywhere:

```go
func IdentityFromContext(ctx context.Context) (Identity, bool) {
    identity, ok := ctx.Value(identityKey{}).(Identity)
    return identity, ok
}
```

Application parallel: `BusinessHandler.Get` reads `user_id` from context and returns only that user's business. It should never accept `user_id` from the applicant request body for applicant-owned data.

---

## Practical Examples

### Example 1: JWT Verification Token Service
This helper generates and parses claims using `github.com/golang-jwt/jwt/v5`:

```go
// File: internal/security/jwt.go
package security

import (
	"errors"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

type UserClaims struct {
	UserID int64 `json:"user_id"`
	jwt.RegisteredClaims
}

type JWTService struct {
	secretKey []byte
}

func NewJWTService(secret string) *JWTService {
	return &JWTService{secretKey: []byte(secret)}
}

// GenerateUserToken generates a 24-hour token for applicants.
func (s *JWTService) GenerateUserToken(userID int64) (string, error) {
	claims := UserClaims{
		UserID: userID,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(24 * time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(s.secretKey)
}

// VerifyUserToken decodes and validates a user token.
func (s *JWTService) VerifyUserToken(tokenStr string) (int64, error) {
	token, err := jwt.ParseWithClaims(tokenStr, &UserClaims{}, func(t *jwt.Token) (interface{}, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
		}
		return s.secretKey, nil
	})

	if err != nil {
		return 0, err
	}

	claims, ok := token.Claims.(*UserClaims)
	if !ok || !token.Valid {
		return 0, errors.New("invalid token claims")
	}

	return claims.UserID, nil
}
```

### Example 2: Closure-based Middleware injecting Context Identity
This middleware uses a closure pattern to receive dependencies (`JWTService`) and returns an `http.Handler` wrapper that injects validated identities into `r.Context()`:

```go
// File: internal/security/middleware.go
package security

import (
	"context"
	"net/http"
	"strings"
)

type contextKey string

const UserIdentityKey contextKey = "userIdentity"

type Identity struct {
	UserID int64
}

// AuthMiddleware is a closure wrapping handlers with authorization checks.
func AuthMiddleware(jwtSvc *JWTService) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			authHeader := r.Header.Get("Authorization")
			if authHeader == "" {
				http.Error(w, `{"error":"missing authorization header"}`, http.StatusUnauthorized)
				return
			}

			// Expecting "Bearer <token>"
			parts := strings.Split(authHeader, " ")
			if len(parts) != 2 || strings.ToLower(parts[0]) != "bearer" {
				http.Error(w, `{"error":"invalid authorization format"}`, http.StatusUnauthorized)
				return
			}

			userID, err := jwtSvc.VerifyUserToken(parts[1])
			if err != nil {
				http.Error(w, `{"error":"invalid or expired token"}`, http.StatusUnauthorized)
				return
			}

			// Injected Identity into Request Context
			ctx := context.WithValue(r.Context(), UserIdentityKey, &Identity{UserID: userID})
			
			// Call next handler in decorator chain
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// GetIdentity extracts the Identity object from the context.
func GetIdentity(ctx context.Context) (*Identity, bool) {
	id, ok := ctx.Value(UserIdentityKey).(*Identity)
	return id, ok
}
```

---

## Security Rules

Preserve:
- Blocked users cannot login.
- Applicant status does not block login.
- Admin approval endpoint requires approver identity.
- CSV export query tokens are short-lived and separate from normal bearer auth.
- Geo-block checks `CF-IPCountry` first, then `X-Country-Code`.

---

## Mastery Check

You understand this chapter when you can:
- Explain how functions behave as values in Go.
- Write a simple closure that captures outside variables.
- Write a custom middleware function with the `func(http.Handler) http.Handler` signature.
- Propagate values securely through request scopes using `context.WithValue()`.
