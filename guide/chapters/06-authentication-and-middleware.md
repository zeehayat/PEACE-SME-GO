# Chapter 6: Authentication, JWT, bcrypt, and Middleware

## Purpose

Authentication is where backend compatibility matters immediately. The Vue frontend stores tokens and sends them as opaque bearer strings. The Go backend must issue and verify compatible JWTs. In this chapter, we will learn how Go handles functions as first-class citizens, how to use closures to configure handlers, and how `context.Context` propagates metadata. We will then build an authentication middleware chain.

Application parallel: this chapter builds the security boundary for both applicants and admins. The applicant uses `UserLogin.vue` and receives `userToken`. The admin uses `AdminLogin.vue` and receives `adminToken`. The same Go server must understand both tokens, but permissions are different.

---

## Foundational Concepts Explained Simply

### 1. First-Class Functions & Closures

:::expandable [First-Class Functions & Closures]
#### In-Depth Explanation
In Go, functions are **first-class citizens**, meaning they are treated like any other value type:
* They can be assigned to variables.
* They can be passed as arguments to other functions.
* They can be returned as output values from other functions.
* **Closures:** A closure is an anonymous function that references (captures) variables from outside its immediate scope. The function "closes over" these variables, keeping them alive and carrying them around as long as the closure exists.
* **Middleware Signature:** In Go, HTTP middleware uses closures to wrap handlers: `func(http.Handler) http.Handler`. The outer function accepts a dependency (like a configuration or database helper) and returns a closure that wraps the subsequent handler in the pipeline.

#### Sandbox Program: Middleware Logger Closure
This sandbox demonstrates how to use closures to build an HTTP middleware decorator that injects logging capabilities around a standard handler function:

```go
package main

import (
	"fmt"
	"time"
)

// MockResponseWriter simulates http.ResponseWriter
type MockResponseWriter struct {
	Status int
}

func (m *MockResponseWriter) WriteHeader(status int) {
	m.Status = status
}

// HandlerFunc type matching net/http
type HandlerFunc func(w *MockResponseWriter, path string)

// LoggerMiddleware wraps a handler func inside a closure, injecting log context
func LoggerMiddleware(environment string, next HandlerFunc) HandlerFunc {
	return func(w *MockResponseWriter, path string) {
		start := time.Now()
		fmt.Printf("[%s] Incoming Request: %s\n", environment, path)
		
		// Execute the wrapped handler
		next(w, path)
		
		fmt.Printf("[%s] Completed Request in %s. Status: %d\n", 
			environment, time.Since(start), w.Status)
	}
}

func main() {
	// A simple mock HTTP handler
	welcomeHandler := func(w *MockResponseWriter, path string) {
		time.Sleep(10 * time.Millisecond) // Simulate work
		w.WriteHeader(200)
		fmt.Println(" -> Executed Welcome Handler: Hello from PEACE SME!")
	}

	// Wrap the handler with our closure-based middleware
	devPipeline := LoggerMiddleware("DEVELOPMENT", welcomeHandler)

	w := &MockResponseWriter{}
	devPipeline(w, "/api/dashboard")
}
```
:::

### 2. Context (`context.Context`)

:::expandable [Go Context & Request-Scoped Values]
#### In-Depth Explanation
When a web request is processed by a Go server, the request traverses a pipeline of middleware and handlers.
* **Request Lifecycle:** Go's `context.Context` propagates deadlines, cancellation signals, and request-scoped values down the call stack.
* **Injecting Values:** Use `context.WithValue(parent, key, value)`. Because contexts are immutable, this returns a *new* child context carrying the key-value pair.
* **Type-Safe Key Rule:** Always declare a custom, unexported type for context keys (e.g. `type contextKey struct{}`) rather than using raw strings. This prevents other packages from accidentally overwriting your context values.
* **Extraction:** Use `ctx.Value(key)` and convert the returned `interface{}` to the concrete target type using a type assertion `v.(Type)`.

#### Sandbox Program: Type-Safe Request Context Propagation
This sandbox simulates request context propagation. It injects a user identity structure, passes the context down, and safely retrieves it using unexported keys:

```go
package main

import (
	"context"
	"fmt"
)

// 1. Declare unexported custom types for context keys to prevent collisions
type contextKey struct{}

var userKey = contextKey{}

type UserIdentity struct {
	UserID int64
	Role   string
}

// InjectUser returns a new context containing the identity
func InjectUser(ctx context.Context, id int64, role string) context.Context {
	identity := UserIdentity{UserID: id, Role: role}
	return context.WithValue(ctx, userKey, identity)
}

// ExtractUser retrieves the identity from context type-safely
func ExtractUser(ctx context.Context) (UserIdentity, bool) {
	val, ok := ctx.Value(userKey).(UserIdentity)
	return val, ok
}

func main() {
	// Start with a root background context
	rootCtx := context.Background()

	// Inject identity (simulating authentication middleware)
	reqCtx := InjectUser(rootCtx, 42, "applicant")

	// Call repository (simulating database query layer)
	fetchData(reqCtx)
}

func fetchData(ctx context.Context) {
	// Retrieve values from context
	identity, ok := ExtractUser(ctx)
	if !ok {
		fmt.Println("Error: No identity found in request context!")
		return
	}

	fmt.Printf("Database Query: Executing search scoped to User ID: %d (Role: %s)\n",
		identity.UserID, identity.Role)
}
```
:::

### 3. JSON Web Tokens (JWT)

:::expandable [JSON Web Tokens (JWT) Signing & Verification]
#### In-Depth Explanation
A JSON Web Token (JWT) is a compact, URL-safe container used to transmit information as a JSON object.
* **Structure:** Consists of three parts separated by dots (`.`): Header (signing algorithm), Payload (the claim details like `user_id` and expiry `exp`), and Signature.
* **HMAC Signing (HS256):** The signature is created by hashing the base64-encoded Header and Payload together with a secret key using HMAC-SHA256.
* **Stateless Auth:** The server does not store active tokens in a database. When a request arrives, the server recalculates the signature using its secret key. If the calculated signature matches the token's signature and the expiry `exp` time is in the future, the token is verified.

#### Sandbox Program: Mock HMAC Token Signature Verification
This program implements base64-encoded signing and signature verification using Go's built-in `crypto/hmac` package. It demonstrates how tampering with the token payload invalidates the signature:

```go
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"strings"
)

// Sign generates a mock JWT structure: header.payload.signature
func Sign(payload string, secret []byte) string {
	header := "HS256"
	h64 := base64.RawURLEncoding.EncodeToString([]byte(header))
	p64 := base64.RawURLEncoding.EncodeToString([]byte(payload))
	
	unsignedToken := h64 + "." + p64
	
	// Create HMAC signature
	h := hmac.New(sha256.New, secret)
	h.Write([]byte(unsignedToken))
	sig := base64.RawURLEncoding.EncodeToString(h.Sum(nil))
	
	return unsignedToken + "." + sig
}

// Verify validates that the signature matches and has not been altered
func Verify(token string, secret []byte) (string, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return "", fmt.Errorf("invalid token format")
	}

	unsignedToken := parts[0] + "." + parts[1]
	providedSig := parts[2]

	// Recalculate HMAC signature
	h := hmac.New(sha256.New, secret)
	h.Write([]byte(unsignedToken))
	expectedSig := base64.RawURLEncoding.EncodeToString(h.Sum(nil))

	// Compare signatures in constant time to prevent timing attacks
	if !hmac.Equal([]byte(providedSig), []byte(expectedSig)) {
		return "", fmt.Errorf("signature verification failed (tampered token)")
	}

	// Decode payload
	payloadBytes, _ := base64.RawURLEncoding.DecodeString(parts[1])
	return string(payloadBytes), nil
}

func main() {
	secret := []byte("secret-portal-key-12345")
	payload := `{"user_id":42,"role":"applicant"}`

	// 1. Generate token
	token := Sign(payload, secret)
	fmt.Println("Generated Token:", token)

	// 2. Verify valid token
	decoded, err := Verify(token, secret)
	if err == nil {
		fmt.Println("Verification Success! Payload:", decoded)
	}

	// 3. Simulate tampering (change user_id from 42 to 1)
	tamperedParts := strings.Split(token, ".")
	tamperedPayload := base64.RawURLEncoding.EncodeToString([]byte(`{"user_id":1,"role":"applicant"}`))
	tamperedToken := tamperedParts[0] + "." + tamperedPayload + "." + tamperedParts[2]
	fmt.Println("\nTampered Token:", tamperedToken)

	_, err = Verify(tamperedToken, secret)
	if err != nil {
		fmt.Println("Verification Failed as expected:", err)
	}
}
```
:::

### 4. bcrypt Password Hashing

:::expandable [Bcrypt Hashing & Password Safety]
#### In-Depth Explanation
* **Why Plain Hashing (SHA256) is Weak:** Simple cryptographic hash functions (like SHA256) are designed to be fast. An attacker who steals a database of SHA256 hashes can run billions of password guesses per second (using GPU-accelerated rainbow tables) to crack them.
* **The Bcrypt Solution:** Bcrypt is a key-derivation function that incorporates:
  1. **A Salt:** A random value generated automatically for each password. This ensures two users with the same password will have completely different hashes.
  2. **Work Factor (Cost):** An exponent (e.g. 10 to 14) that controls how many iteration rounds the algorithm executes. This makes the hashing process intentionally slow (e.g. taking 100-300 milliseconds per hash). This slowness completely defeats brute-force attempts while remaining unnoticeable to individual logging-in users.
* **Verification:** Since bcrypt hashes are salted, you can never "decrypt" the hash. Instead, you pass the candidate password and the stored hash into a comparison library. The library extracts the salt from the hash, hashes the candidate password with that salt, and compares the results.

#### Sandbox Program: Bcrypt Simulation & Password Checks
This program simulates how bcrypt uses salts to create unique hashes for identical inputs and verify password attempts securely:

```go
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"math/rand"
)

// SimulatedBcryptHash creates a mock salted hash simulating bcrypt behaviour
func SimulatedBcryptHash(password string, cost int) (string, string) {
	// Generate a mock random salt
	saltBytes := make([]byte, 8)
	rand.Read(saltBytes)
	salt := hex.EncodeToString(saltBytes)

	// Hash password + salt multiple times (cost)
	hash := password + salt
	for i := 0; i < cost*1000; i++ {
		h := sha256.Sum256([]byte(hash))
		hash = hex.EncodeToString(h[:])
	}
	return hash, salt
}

// SimulatedBcryptVerify verifies if the candidate matches
func SimulatedBcryptVerify(password, storedHash, salt string, cost int) bool {
	hash := password + salt
	for i := 0; i < cost*1000; i++ {
		h := sha256.Sum256([]byte(hash))
		hash = hex.EncodeToString(h[:])
	}
	return hash == storedHash
}

func main() {
	password := "SecurePass123"
	cost := 5 // Simulates work factor iterations

	// 1. Hash password twice (demonstrates different salts yield different hashes)
	hash1, salt1 := SimulatedBcryptHash(password, cost)
	hash2, salt2 := SimulatedBcryptHash(password, cost)

	fmt.Println("Password:", password)
	fmt.Printf("Hash 1: %s (Salt: %s)\n", hash1[:32], salt1)
	fmt.Printf("Hash 2: %s (Salt: %s)\n\n", hash2[:32], salt2)

	// 2. Verify correct attempt
	ok := SimulatedBcryptVerify("SecurePass123", hash1, salt1, cost)
	fmt.Println("Verify with correct password:", ok)

	// 3. Verify incorrect attempt
	bad := SimulatedBcryptVerify("WrongPass", hash1, salt1, cost)
	fmt.Println("Verify with wrong password:", bad)
}
```
:::

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
