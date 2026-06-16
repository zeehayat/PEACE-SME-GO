# Chapter 7: Applicant Registration, Login, and Business Profiles

## Purpose

This chapter implements the applicant foundation: closed registration behavior, login, profile lookup, and business profile create/update. In this chapter, we will study **Method Receivers**, learning the difference between attaching behaviors to structs by value vs by pointer. We will then implement struct validation receiver methods for our Request DTOs.

For a beginner Go developer, this is the first real vertical slice. You will move from HTTP JSON to service rules to SQL and back to Vue form state.

## Theory: Vertical Slices

A vertical slice is a small feature implemented through every layer:

```text
Vue form -> Axios request -> Go handler -> service -> repository -> PostgreSQL -> JSON response -> Vue state
```

Building one complete slice teaches more than building ten disconnected helpers. Login and business profile are ideal first slices because they touch authentication, validation, database queries, and frontend state without requiring the full grant workflow yet.

---

## Foundational Concepts Explained Simply

### Method Receivers (Value vs. Pointer Receivers)

:::expandable [Method Receivers: Value vs. Pointer]
#### In-Depth Explanation
Go does not support object-oriented classes, but it allows you to define behaviors (methods) on struct types. A method is declared like a regular function, but it includes an extra **Receiver** parameter located between the `func` keyword and the function name.
* **Value Receiver:** Declared as `func (s StructType) MethodName()`.
  * **Mechanism:** When the method is invoked, Go creates a shallow copy of the entire struct in memory.
  * **Mutability:** Any changes made to the struct's fields inside the method only affect the copy, leaving the original struct unmodified.
  * **When to Use:** Use value receivers for small, read-only structures where copying is cheap, or when you want to guarantee immutability.
* **Pointer Receiver:** Declared as `func (s *StructType) MethodName()`.
  * **Mechanism:** Go passes the memory address of the struct. No copying of fields occurs.
  * **Mutability:** Any changes made to the struct's fields inside the method directly alter the original instance.
  * **When to Use:** Use pointer receivers if the method needs to modify struct values, or if the struct contains many fields (making copying expensive).
  * *Consistency Rule:* If any method on a struct requires a pointer receiver, all other methods on that struct should also use pointer receivers for consistency.

#### Sandbox Program: Struct Mutation and Validation Checks
This program demonstrates how a value receiver fails to modify a struct's state while a pointer receiver successfully mutates it. It also shows a custom validation and normalization routine:

```go
package main

import (
	"fmt"
	"strings"
)

type BusinessProfile struct {
	Name     string
	District string
}

// Value Receiver: Attempts to capitalize the name but works on a copy
func (b BusinessProfile) NormaliseNameValue() {
	b.Name = strings.ToUpper(b.Name)
	fmt.Printf("[Inside Value Receiver] Normalised Name: %s\n", b.Name)
}

// Pointer Receiver: Successfully capitalises the name in place
func (b *BusinessProfile) NormaliseNamePointer() {
	b.Name = strings.ToUpper(b.Name)
	fmt.Printf("[Inside Pointer Receiver] Normalised Name: %s\n", b.Name)
}

func main() {
	// 1. Initialise struct
	profile := BusinessProfile{
		Name:     "Swat Honey Extractors",
		District: "Swat",
	}
	fmt.Println("Initial Profile Name:", profile.Name)

	// 2. Call Value Receiver
	profile.NormaliseNameValue()
	fmt.Println("Profile Name after Value Receiver call:", profile.Name) 
	// Output: Still "Swat Honey Extractors" because it worked on a copy!

	fmt.Println()

	// 3. Call Pointer Receiver
	profile.NormaliseNamePointer()
	fmt.Println("Profile Name after Pointer Receiver call:", profile.Name)
	// Output: "SWAT HONEY EXTRACTORS" because it modified the original!
}
```
:::

### External Resources
- [A Tour of Go: Methods](https://go.dev/tour/methods/1)
- [Go Dev: FAQ on Receiver Types](https://go.dev/doc/faq#methods_on_values_or_pointers)

---

## Endpoints

Public:

| Method | Path |
|---|---|
| POST | `/api/pre-registration` |
| POST | `/api/register` |
| POST | `/api/login` |
| POST | `/api/forgot-password` |
| POST | `/api/reset-password` |

User:

| Method | Path |
|---|---|
| GET | `/api/user/profile` |
| GET | `/api/business` |
| POST | `/api/business` |
| PUT | `/api/business` |

---

## Registration Toggle

The current operational state has registration closed. Preserve:
- `/api/pre-registration` returns 403 when `GRANT_APPLICATION_OPEN=0`.
- `/api/register` returns 403 when `GRANT_APPLICATION_OPEN=0`.
- Password reset endpoints return 403 because the feature is disabled.

This is a good lesson: compatibility sometimes means reproducing disabled behavior.

Application parallel: the frontend has registration screens, but production config currently closes registration. The Go backend must enforce this even if a user manually calls the API.

Go concept: configuration-driven branching.

```go
if !cfg.GrantApplicationOpen {
    return ErrRegistrationClosed
}
```

Vue concept: show the closed-registration UI when the API returns 403 or when a public status endpoint says registration is closed.

---

## Business Profile Rules

The app allows one business per user:

```sql
businesses.user_id INTEGER UNIQUE NOT NULL
```

Allowed districts:
- Swat
- Shangla
- Upper Dir
- Upper Chitral
- Lower Chitral

Reject any other district in create/update logic.

Go concept: validate before write.

```go
func ValidateDistrict(district string) error {
    if !AllowedDistricts[district] {
        return fmt.Errorf("district %q is not allowed", district)
    }
    return nil
}
```

Database concept: the unique constraint protects data even if two requests arrive at the same time. Application validation improves the error message, but the database is the final guard.

---

## Request Validation

Validate at the boundary:
- Required fields.
- Email shape.
- CNIC as string.
- Boolean fields.
- JSON arrays such as `business_registration_authority`.
- District allow-list.

Do not trust the frontend. Vue validation improves UX; Go validation protects the system.

---

## Practical Examples

### Example 1: Defining a Request DTO with Pointer Receiver Validation
This example declares a data structure for business profiles and implements a validation method using a pointer receiver to optimize performance:

```go
// File: internal/business/dto.go
package business

import (
	"errors"
	"strings"
)

var allowedDistricts = map[string]bool{
	"swat":          true,
	"shangla":       true,
	"upper dir":     true,
	"upper chitral": true,
	"lower chitral": true,
}

type CreateBusinessRequest struct {
	Name            string `json:"name_of_business"`
	Address         string `json:"business_full_address"`
	District        string `json:"business_location_district"`
	MaleEmployees   int    `json:"male_employees"`
	FemaleEmployees int    `json:"female_employees"`
}

// Validate uses a pointer receiver to check the request fields without copying memory.
func (req *CreateBusinessRequest) Validate() error {
	if strings.TrimSpace(req.Name) == "" {
		return errors.New("business name is required")
	}
	if strings.TrimSpace(req.Address) == "" {
		return errors.New("business full address is required")
	}
	
	// Check against allowed KP districts
	districtClean := strings.ToLower(strings.TrimSpace(req.District))
	if !allowedDistricts[districtClean] {
		return errors.New("business location district is out of allowed scope")
	}

	if req.MaleEmployees < 0 || req.FemaleEmployees < 0 {
		return errors.New("employee counts cannot be negative")
	}

	return nil
}
```

### Example 2: Handler Executing DTO Validation
This controller handler decodes the request body and executes the validation method:

```go
// File: internal/business/handler.go
package business

import (
	"encoding/json"
	"net/http"
	"peace-sme-go/internal/httpx"
)

type Handler struct{}

func (h *Handler) Create(w http.ResponseWriter, r *http.Request) {
	var req CreateBusinessRequest
	
	// Decode JSON directly into the struct
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpx.WriteError(w, http.StatusBadRequest, "invalid_json", "Failed to parse request JSON")
		return
	}

	// Execute pointer-receiver validation
	if err := req.Validate(); err != nil {
		httpx.WriteError(w, http.StatusUnprocessableEntity, "validation_failed", err.Error())
		return
	}

	// Logic to pass req to Service...
}
```

---

## Service Design

Use a service between handlers and repositories:

```go
type Service struct {
    users      UserRepository
    businesses BusinessRepository
    auth       TokenService
}
```

Handlers decode HTTP. Services enforce rules. Repositories run SQL.

### Beginner Walkthrough: `POST /api/business`

1. Vue gathers form fields in `reactive` state.
2. Axios sends JSON with `Authorization: Bearer <userToken>`.
3. Auth middleware verifies JWT and stores `user_id` in context.
4. Handler decodes JSON into `BusinessRequest`.
5. Service validates district and ownership.
6. Repository inserts row into `businesses`.
7. Handler returns `{message,business_id}`.
8. Vue shows success and redirects to dashboard.

Write this flow in notes before coding. It prevents mixing responsibilities.

---

## Vue Link

These endpoints power:
- `RegistrationForm.vue`
- `UserLogin.vue`
- `AppDashboard.vue`
- `SmeBusinessProfile.vue`
- route guards using `userToken`

Keep response shapes stable so the Vue application does not need workaround code.

---

## Complete Login Implementation

This vertical slice shows every layer from HTTP to database to response.

### Sentinel Errors (`internal/user/errors.go`)

```go
package user

import "errors"

var (
    ErrInvalidCredentials = errors.New("invalid credentials")
    ErrUserBlocked        = errors.New("user account is blocked")
    ErrUserNotFound       = errors.New("user not found")
    ErrRegistrationClosed = errors.New("registration is currently closed")
    ErrBusinessExists     = errors.New("business profile already exists for this user")
    ErrInvalidDistrict    = errors.New("business location district is not in the allowed list")
)
```

Define these before implementing logic so the service and handler can reference them.

### Repository (`internal/user/repository.go`)

```go
package user

import (
    "context"
    "database/sql"
    "fmt"

    "github.com/jackc/pgx/v5"
    "github.com/jackc/pgx/v5/pgxpool"
    "peace-sme-go/internal/db"
)

type Repository struct {
    pool *pgxpool.Pool
}

func NewRepository(pool *pgxpool.Pool) *Repository {
    return &Repository{pool: pool}
}

// FindByEmail looks up a user by email. Returns (nil, nil) when not found.
func (r *Repository) FindByEmail(ctx context.Context, email string) (*db.User, error) {
    query := `
        SELECT user_id, email_address, hashed_password, first_name, last_name,
               cnic, language, gender, mobile_no, whatsapp_no, status, created_at
        FROM users
        WHERE email_address = $1`

    row := r.pool.QueryRow(ctx, query, email)

    var u db.User
    err := row.Scan(
        &u.UserID, &u.EmailAddress, &u.HashedPassword,
        &u.FirstName, &u.LastName, &u.CNIC, &u.Language,
        &u.Gender, &u.MobileNo, &u.WhatsappNo, &u.Status, &u.CreatedAt,
    )
    if err != nil {
        if err == pgx.ErrNoRows {
            return nil, nil // not found — caller checks for nil
        }
        return nil, fmt.Errorf("FindByEmail: %w", err)
    }
    return &u, nil
}

// FindByID looks up a user by primary key.
func (r *Repository) FindByID(ctx context.Context, userID int64) (*db.User, error) {
    query := `
        SELECT user_id, email_address, first_name, last_name,
               cnic, language, gender, mobile_no, whatsapp_no, status, created_at
        FROM users
        WHERE user_id = $1`

    row := r.pool.QueryRow(ctx, query, userID)

    var u db.User
    err := row.Scan(
        &u.UserID, &u.EmailAddress,
        &u.FirstName, &u.LastName, &u.CNIC, &u.Language,
        &u.Gender, &u.MobileNo, &u.WhatsappNo, &u.Status, &u.CreatedAt,
    )
    if err != nil {
        if err == pgx.ErrNoRows {
            return nil, nil
        }
        return nil, fmt.Errorf("FindByID: %w", err)
    }
    return &u, nil
}
```

Key pattern: `pgx.ErrNoRows` means the record does not exist. Return `(nil, nil)` — no record and no error. The service layer then checks for nil explicitly.

### Service (`internal/user/service.go`)

```go
package user

import (
    "context"
    "fmt"

    "golang.org/x/crypto/bcrypt"
    "peace-sme-go/internal/auth"
    "peace-sme-go/internal/db"
)

type Service struct {
    repo   *Repository
    tokens *auth.TokenService
}

func NewService(repo *Repository, tokens *auth.TokenService) *Service {
    return &Service{repo: repo, tokens: tokens}
}

type LoginRequest struct {
    EmailAddress string `json:"email_address"`
    Password     string `json:"password"`
}

type LoginResponse struct {
    Token    string `json:"token"`
    UserID   int64  `json:"user_id"`
    Language string `json:"language"`
}

func (s *Service) Login(ctx context.Context, req LoginRequest) (*LoginResponse, error) {
    // 1. Look up by email — wrong email returns same error as wrong password
    //    (never reveal which was wrong — prevents user enumeration)
    user, err := s.repo.FindByEmail(ctx, req.EmailAddress)
    if err != nil {
        return nil, fmt.Errorf("Login: %w", err)
    }
    if user == nil {
        return nil, ErrInvalidCredentials
    }

    // 2. Verify password against stored bcrypt hash
    err = bcrypt.CompareHashAndPassword([]byte(user.HashedPassword), []byte(req.Password))
    if err != nil {
        // bcrypt.ErrMismatchedHashAndPassword means wrong password
        return nil, ErrInvalidCredentials
    }

    // 3. Check account status — blocked users cannot proceed
    if user.Status == "blocked" {
        return nil, ErrUserBlocked
    }

    // 4. Issue a 24-hour JWT
    token, err := s.tokens.GenerateUserToken(user.UserID)
    if err != nil {
        return nil, fmt.Errorf("Login token generation: %w", err)
    }

    language := "en"
    if user.Language.Valid {
        language = user.Language.String
    }

    return &LoginResponse{
        Token:    token,
        UserID:   user.UserID,
        Language: language,
    }, nil
}

type ProfileResponse struct {
    UserID       int64  `json:"user_id"`
    EmailAddress string `json:"email_address"`
    FirstName    string `json:"first_name"`
    LastName     string `json:"last_name"`
    CNIC         string `json:"cnic"`
    Language     string `json:"language"`
    Gender       string `json:"gender"`
    MobileNo     string `json:"mobile_no"`
    Status       string `json:"status"`
}

func nullStr(ns db.User, field string) string {
    // helper used inline when building ProfileResponse
    return ""
}

func (s *Service) GetProfile(ctx context.Context, userID int64) (*ProfileResponse, error) {
    user, err := s.repo.FindByID(ctx, userID)
    if err != nil {
        return nil, fmt.Errorf("GetProfile: %w", err)
    }
    if user == nil {
        return nil, ErrUserNotFound
    }
    return &ProfileResponse{
        UserID:       user.UserID,
        EmailAddress: user.EmailAddress,
        FirstName:    user.FirstName.String,
        LastName:     user.LastName.String,
        CNIC:         user.CNIC.String,
        Language:     user.Language.String,
        Gender:       user.Gender.String,
        MobileNo:     user.MobileNo.String,
        Status:       user.Status,
    }, nil
}
```

### Handler (`internal/user/handler.go`)

```go
package user

import (
    "encoding/json"
    "errors"
    "net/http"

    "peace-sme-go/internal/httpx"
    "peace-sme-go/internal/middleware"
)

type Handler struct {
    svc *Service
}

func NewHandler(svc *Service) *Handler {
    return &Handler{svc: svc}
}

func (h *Handler) Login(w http.ResponseWriter, r *http.Request) {
    var req LoginRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        httpx.WriteError(w, http.StatusBadRequest, "Invalid request body")
        return
    }

    resp, err := h.svc.Login(r.Context(), req)
    if err != nil {
        switch {
        case errors.Is(err, ErrInvalidCredentials):
            httpx.WriteError(w, http.StatusUnauthorized, "Invalid email or password.")
        case errors.Is(err, ErrUserBlocked):
            httpx.WriteError(w, http.StatusForbidden, "Your account has been blocked. Contact support.")
        default:
            httpx.WriteError(w, http.StatusInternalServerError, "An unexpected error occurred.")
        }
        return
    }

    httpx.WriteJSON(w, http.StatusOK, resp)
}

func (h *Handler) Profile(w http.ResponseWriter, r *http.Request) {
    identity, ok := middleware.IdentityFromContext(r.Context())
    if !ok {
        httpx.WriteError(w, http.StatusUnauthorized, "Not authenticated.")
        return
    }

    profile, err := h.svc.GetProfile(r.Context(), identity.UserID)
    if err != nil {
        if errors.Is(err, ErrUserNotFound) {
            httpx.WriteError(w, http.StatusNotFound, "User not found.")
            return
        }
        httpx.WriteError(w, http.StatusInternalServerError, "Failed to load profile.")
        return
    }

    httpx.WriteJSON(w, http.StatusOK, profile)
}
```

The handler knows nothing about SQL. It decodes HTTP, calls the service, maps errors to status codes, and returns JSON. Each layer has one job.

---

## Complete Business Profile Implementation

### Repository (`internal/business/repository.go`)

```go
package business

import (
    "context"
    "fmt"

    "github.com/jackc/pgx/v5"
    "github.com/jackc/pgx/v5/pgxpool"
    "peace-sme-go/internal/db"
)

type Repository struct {
    pool *pgxpool.Pool
}

func NewRepository(pool *pgxpool.Pool) *Repository {
    return &Repository{pool: pool}
}

func (r *Repository) FindByUserID(ctx context.Context, userID int64) (*db.Business, error) {
    query := `
        SELECT business_id, user_id, name_of_business, business_registration_number,
               business_full_address, business_location_district, business_sector,
               male_employees, female_employees, created_at
        FROM businesses
        WHERE user_id = $1`

    row := r.pool.QueryRow(ctx, query, userID)
    var b db.Business
    err := row.Scan(
        &b.BusinessID, &b.UserID, &b.NameOfBusiness, &b.BusinessRegistrationNumber,
        &b.BusinessFullAddress, &b.BusinessLocationDistrict, &b.BusinessSector,
        &b.MaleEmployees, &b.FemaleEmployees, &b.CreatedAt,
    )
    if err != nil {
        if err == pgx.ErrNoRows {
            return nil, nil
        }
        return nil, fmt.Errorf("FindByUserID business: %w", err)
    }
    return &b, nil
}

type CreateParams struct {
    UserID                   int64
    NameOfBusiness           string
    BusinessRegistrationNum  string
    BusinessFullAddress      string
    BusinessLocationDistrict string
    BusinessSector           string
    MaleEmployees            int
    FemaleEmployees          int
}

// Create inserts a new business row and returns the new business_id.
func (r *Repository) Create(ctx context.Context, p CreateParams) (int64, error) {
    query := `
        INSERT INTO businesses
            (user_id, name_of_business, business_registration_number,
             business_full_address, business_location_district, business_sector,
             male_employees, female_employees, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
        RETURNING business_id`

    var id int64
    err := r.pool.QueryRow(ctx, query,
        p.UserID, p.NameOfBusiness, p.BusinessRegistrationNum,
        p.BusinessFullAddress, p.BusinessLocationDistrict, p.BusinessSector,
        p.MaleEmployees, p.FemaleEmployees,
    ).Scan(&id)
    if err != nil {
        return 0, fmt.Errorf("Create business: %w", err)
    }
    return id, nil
}

// Update modifies an existing business row.
func (r *Repository) Update(ctx context.Context, userID int64, p CreateParams) error {
    query := `
        UPDATE businesses
        SET name_of_business = $1,
            business_registration_number = $2,
            business_full_address = $3,
            business_location_district = $4,
            business_sector = $5,
            male_employees = $6,
            female_employees = $7
        WHERE user_id = $8`

    _, err := r.pool.Exec(ctx, query,
        p.NameOfBusiness, p.BusinessRegistrationNum,
        p.BusinessFullAddress, p.BusinessLocationDistrict, p.BusinessSector,
        p.MaleEmployees, p.FemaleEmployees, userID,
    )
    if err != nil {
        return fmt.Errorf("Update business: %w", err)
    }
    return nil
}
```

### Service (`internal/business/service.go`)

```go
package business

import (
    "context"
    "fmt"
    "strings"
)

var allowedDistricts = map[string]bool{
    "swat":          true,
    "shangla":       true,
    "upper dir":     true,
    "upper chitral": true,
    "lower chitral": true,
}

type Service struct {
    repo *Repository
}

func NewService(repo *Repository) *Service {
    return &Service{repo: repo}
}

type BusinessRequest struct {
    NameOfBusiness           string `json:"name_of_business"`
    BusinessRegistrationNum  string `json:"business_registration_number"`
    BusinessFullAddress      string `json:"business_full_address"`
    BusinessLocationDistrict string `json:"business_location_district"`
    BusinessSector           string `json:"business_sector"`
    MaleEmployees            int    `json:"male_employees"`
    FemaleEmployees          int    `json:"female_employees"`
}

func (s *Service) Get(ctx context.Context, userID int64) (interface{}, error) {
    b, err := s.repo.FindByUserID(ctx, userID)
    if err != nil {
        return nil, err
    }
    if b == nil {
        return map[string]interface{}{}, nil // frontend expects empty object when none exists
    }
    return b, nil
}

func (s *Service) Create(ctx context.Context, userID int64, req BusinessRequest) (int64, error) {
    if err := validateDistrict(req.BusinessLocationDistrict); err != nil {
        return 0, err
    }

    // Enforce one-business-per-user at the service layer
    // (the DB UNIQUE constraint is the final safety net)
    existing, err := s.repo.FindByUserID(ctx, userID)
    if err != nil {
        return 0, err
    }
    if existing != nil {
        return 0, ErrBusinessExists
    }

    id, err := s.repo.Create(ctx, CreateParams{
        UserID:                   userID,
        NameOfBusiness:           req.NameOfBusiness,
        BusinessRegistrationNum:  req.BusinessRegistrationNum,
        BusinessFullAddress:      req.BusinessFullAddress,
        BusinessLocationDistrict: req.BusinessLocationDistrict,
        BusinessSector:           req.BusinessSector,
        MaleEmployees:            req.MaleEmployees,
        FemaleEmployees:          req.FemaleEmployees,
    })
    return id, err
}

func (s *Service) Update(ctx context.Context, userID int64, req BusinessRequest) error {
    if err := validateDistrict(req.BusinessLocationDistrict); err != nil {
        return err
    }
    return s.repo.Update(ctx, userID, CreateParams{
        UserID:                   userID,
        NameOfBusiness:           req.NameOfBusiness,
        BusinessRegistrationNum:  req.BusinessRegistrationNum,
        BusinessFullAddress:      req.BusinessFullAddress,
        BusinessLocationDistrict: req.BusinessLocationDistrict,
        BusinessSector:           req.BusinessSector,
        MaleEmployees:            req.MaleEmployees,
        FemaleEmployees:          req.FemaleEmployees,
    })
}

func validateDistrict(d string) error {
    if !allowedDistricts[strings.ToLower(strings.TrimSpace(d))] {
        return fmt.Errorf("%w: %q", ErrInvalidDistrict, d)
    }
    return nil
}
```

### Handler (GET / POST / PUT on `/api/business`)

```go
package business

import (
    "encoding/json"
    "errors"
    "net/http"

    "peace-sme-go/internal/httpx"
    "peace-sme-go/internal/middleware"
)

type Handler struct {
    svc *Service
}

func NewHandler(svc *Service) *Handler {
    return &Handler{svc: svc}
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
    switch r.Method {
    case http.MethodGet:
        h.Get(w, r)
    case http.MethodPost:
        h.Create(w, r)
    case http.MethodPut:
        h.Update(w, r)
    case http.MethodOptions:
        w.WriteHeader(http.StatusOK)
    default:
        http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
    }
}

func (h *Handler) Get(w http.ResponseWriter, r *http.Request) {
    identity, _ := middleware.IdentityFromContext(r.Context())
    result, err := h.svc.Get(r.Context(), identity.UserID)
    if err != nil {
        httpx.WriteError(w, http.StatusInternalServerError, "Failed to load business profile.")
        return
    }
    httpx.WriteJSON(w, http.StatusOK, result)
}

func (h *Handler) Create(w http.ResponseWriter, r *http.Request) {
    identity, _ := middleware.IdentityFromContext(r.Context())

    var req BusinessRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        httpx.WriteError(w, http.StatusBadRequest, "Invalid request body.")
        return
    }

    id, err := h.svc.Create(r.Context(), identity.UserID, req)
    if err != nil {
        switch {
        case errors.Is(err, ErrBusinessExists):
            httpx.WriteError(w, http.StatusConflict, "A business profile already exists for your account.")
        case errors.Is(err, ErrInvalidDistrict):
            httpx.WriteError(w, http.StatusBadRequest, err.Error())
        default:
            httpx.WriteError(w, http.StatusInternalServerError, "Failed to create business profile.")
        }
        return
    }

    httpx.WriteJSON(w, http.StatusCreated, map[string]interface{}{
        "message":     "Business profile created.",
        "business_id": id,
    })
}

func (h *Handler) Update(w http.ResponseWriter, r *http.Request) {
    identity, _ := middleware.IdentityFromContext(r.Context())

    var req BusinessRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        httpx.WriteError(w, http.StatusBadRequest, "Invalid request body.")
        return
    }

    if err := h.svc.Update(r.Context(), identity.UserID, req); err != nil {
        if errors.Is(err, ErrInvalidDistrict) {
            httpx.WriteError(w, http.StatusBadRequest, err.Error())
            return
        }
        httpx.WriteError(w, http.StatusInternalServerError, "Failed to update business profile.")
        return
    }

    httpx.WriteJSON(w, http.StatusOK, map[string]string{
        "message": "Business profile updated.",
    })
}
```

---

## Mastery Check

You understand this chapter when you can:
- Explain what receiver parameters are in Go.
- Contrast value receivers and pointer receivers.
- Implement validation routines on request structures using pointer receivers.
- Write a complete three-layer implementation: repository (SQL), service (rules), handler (HTTP).
- Explain why `pgx.ErrNoRows` should return `(nil, nil)` and how the service layer handles that.
- Explain why `ErrInvalidCredentials` is returned for both "email not found" and "wrong password."
