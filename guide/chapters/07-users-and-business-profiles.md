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
Go does not have classes, but you can define **Methods** on struct types. A method is simply a function with a special **Receiver** parameter listed between the `func` keyword and the method name.
- **Value Receiver:** Declared as `func (s StructType) Method()`. 
  - Go creates a complete **copy** of the struct when running the method.
  - Modifying struct fields inside the method *does not* affect the original caller's struct.
  - Use value receivers for small, read-only structures where copying is cheap.
- **Pointer Receiver:** Declared as `func (s *StructType) Method()`.
  - Go passes the **memory address** of the struct instead of copying it.
  - Modifying fields inside the method *directly alters* the original caller's struct.
  - Use pointer receivers if the method needs to edit the struct, or if the struct is large and copying it would consume unnecessary resources.

Here is an example showing the difference:

```go
package main

import "fmt"

type Circle struct {
    Radius float64
}

// Value Receiver (read-only calculation, works on copy)
func (c Circle) Area() float64 {
    return 3.14159 * c.Radius * c.Radius
}

// Pointer Receiver (modifies original, does not copy)
func (c *Circle) DoubleRadius() {
    c.Radius = c.Radius * 2
}

func main() {
    circle := Circle{Radius: 5}
    
    fmt.Println("Area:", circle.Area()) // Prints 78.53975
    
    circle.DoubleRadius()
    fmt.Println("New Radius:", circle.Radius) // Prints 10 (radius was modified)
}
```

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

## Mastery Check

You understand this chapter when you can:
- Explain what receiver parameters are in Go.
- Contrast value receivers and pointer receivers.
- Implement validation routines on request structures using pointer receivers.
