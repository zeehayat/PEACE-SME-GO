# Chapter 3: Go Project Structure and HTTP Server

## Purpose

Replace the stub server with a production-shaped Go application. In this chapter, we will learn Go's dependency management, package visibility, custom data types, and pointers. We will apply these concepts by defining **every single core struct** used throughout the database, configuration, and API layers of the PEACE SME Grant Portal.

---

## Foundational Concepts Explained Simply

### 1. Go Modules (`go mod`)
In Go, a **Module** is a collection of Go packages versioned together. The `go.mod` file at the root of your project defines the module name and tracks dependencies:
- `go mod init <name>` initializes a module.
- `go get <package-path>` downloads a third-party dependency.
- `go.sum` stores cryptographic hashes of dependencies to ensure builds are reproducible and secure.

:::expandable [Go Modules & Dependency Tracking]
#### In-Depth Explanation
Before the introduction of Modules, Go developers were forced to place all source code inside a single global workspace directory named `$GOPATH`. This made project isolation and version pinning extremely difficult.
Go Modules solved this by introducing local dependency manifests:
- **`go.mod`:** Declares the module's path identity (e.g. `module peace-sme-go`), the required Go language specification version, and a list of dependent packages with pinned semantic versions.
- **`go.sum`:** Records the checksums of all direct and indirect dependencies. If a hacker alters the dependency package on a mirror server, Go's checksum validation will fail-fast, preventing code injection.

#### Sandbox Program: Module Manifest Simulation
Here is a simulation demonstrating how Go models depend on modules:

```go
package main

import (
	"fmt"
	"strings"
)

// Dependency models a required library recorded in go.mod
type Dependency struct {
	Path    string
	Version string
}

func main() {
	// Simulate the content of a go.mod file
	moduleName := "peace-sme-go"
	deps := []Dependency{
		{Path: "github.com/jackc/pgx/v5", Version: "v5.5.0"},
		{Path: "github.com/redis/go-redis/v9", Version: "v9.3.0"},
	}

	fmt.Printf("Module Name: %s\n", moduleName)
	fmt.Println("--- Direct Dependencies ---")
	for _, dep := range deps {
		fmt.Printf("Import: %-30s | Version: %s\n", dep.Path, dep.Version)
	}
}
```
:::

### 2. Packages and Visibility
Go groups files in the same directory into a **Package**. Go uses a simple rule for code visibility:
- **Exported (Public):** If a variable, function, struct, or field name begins with a **Capital Letter** (e.g., `UserID`, `ApproveGrant`), it is public and can be accessed by other packages importing it.
- **Unexported (Private):** If it begins with a **lowercase letter** (e.g., `dbStatus`, `findUser`), it is private and accessible only within its own package.

:::expandable [Package Layout, Imports & Visibility]
#### In-Depth Explanation
Go enforces a clean directory-to-package mapping:
1. Every file in a directory must belong to the **same package** (with testing files as a slight exception).
2. Package names should be lowercase, singular nouns (e.g. `auth`, not `authenticator` or `AuthServices`).
3. To consume functions from another package, you use the `import` statement followed by the module path and package name:

```go
import "peace-sme-go/internal/config"
```

#### Sandbox Program: Visibility and Namespace Rules
This sandbox demonstrates public vs private accessibility boundary checks:

```go
package main

import "fmt"

type DBConfig struct {
	Host     string // Public (Capitalized)
	Port     int    // Public (Capitalized)
	password string // Private (lowercase, inaccessible outside package)
}

func NewDBConfig(host string, port int, pwd string) DBConfig {
	return DBConfig{
		Host:     host,
		Port:     port,
		password: pwd, // Accessible here because we are inside the same package
	}
}

func main() {
	cfg := NewDBConfig("localhost", 5432, "supersecret")
	
	fmt.Printf("Connecting to %s on port %d...\n", cfg.Host, cfg.Port)
	// fmt.Println(cfg.password) // UNCOMMENTING THIS LINE WILL CAUSE A COMPILE ERROR
}
```
:::

### 3. Structs (Custom Data Types)
A **Struct** is a schema of typed fields, used to group related data.
```go
type Book struct {
    Title  string // Exported
    Pages  int    // Exported
    author string // Unexported
}
```

:::expandable [Structs & JSON Tags]
#### In-Depth Explanation
Structs are Go's primary mechanism for representation of domain objects, schemas, request bodies, and database mappings.
- **Instantiation:** Structs can be allocated on the stack directly or as zero-valued objects: `u := User{}`.
- **Struct Tags:** Are string literals attached to fields. Go's runtime library uses reflection (`reflect` package) to read these tags. For example, during JSON decoding, the `encoding/json` package matches keys in a JSON request (like `email_address`) to the struct field tagged with `json:"email_address"`.

#### Sandbox Program: Serializing Structs to JSON with Tags
This sandbox demonstrates how tags convert struct fields into customized JSON payload keys:

```go
package main

import (
	"encoding/json"
	"fmt"
)

type Applicant struct {
	ID        int64  `json:"applicant_id"`
	FullName  string `json:"full_name"`
	PlainPass string `json:"-"` // Prevents field from serialization
}

func main() {
	app := Applicant{
		ID:        1024,
		FullName:  "Aftab Khan",
		PlainPass: "mypassword123",
	}

	// Marshal struct to JSON bytes
	bytes, err := json.MarshalIndent(app, "", "  ")
	if err != nil {
		fmt.Println("Error:", err)
		return
	}

	fmt.Println("Serialized JSON Payload:")
	fmt.Println(string(bytes)) // Note that PlainPass is completely omitted
}
```
:::

### 4. Pointers (Memory Management)
In Go, passing a variable to a function copies its value. If the struct is large, copying it wastes memory. If you modify it inside the function, the caller's copy is unaffected.
- **Pointers** store the **memory address** of a variable instead of its value.
- <b>Address-of Operator (&):</b> Prefixing a variable with `&` returns its memory address (e.g., `&user`).
- <b>Dereferencing Operator (asterisk):</b> Prefixing a pointer with the asterisk character (`*`) reads the value at that address.
- <b>Type Declaration (asterisk-Type):</b> Prefixing a type name with the asterisk character (such as `*User`) declares a pointer type that references the original struct.

:::expandable [Pointers & Memory Referencing]
#### In-Depth Explanation
Understanding Go's memory allocation model is crucial:
1. **Stack vs Heap:** Stack allocation is extremely fast and handled automatically. When a variable's address is shared outside the current function execution frame (escape analysis), the compiler automatically allocates it to the **Heap**.
2. **Nil Pointers:** Declaring a pointer without assigning it leaves it empty: `var u *User` (which is `nil`). Trying to read or write fields on a `nil` pointer triggers a runtime crash (**panic: runtime error: invalid memory address or nil pointer dereference**). Always verify pointer variables are not `nil` before usage.

#### Sandbox Program: Pointers and Memory Address Referencing
This sandbox shows how pointers manipulate values at identical memory addresses:

```go
package main

import "fmt"

type Profile struct {
	District string
}

// Modifies the original profile directly via pointer dereference
func changeDistrict(p *Profile, newDist string) {
	if p == nil {
		return // Avoid nil pointer panic
	}
	p.District = newDist
}

func main() {
	p := Profile{District: "Peshawar"}
	fmt.Println("Original District:", p.District)

	// Pass the memory address using & operator
	changeDistrict(&p, "Swat")
	fmt.Println("Modified District:", p.District)
	
	// Inspect the raw memory address
	fmt.Printf("Memory address of struct: %p\n", &p)
}
```
:::

---

## Phased Struct Implementation Guide

To master structs, we will now define **every core data structure** required by the PEACE SME Grant Portal.

Create a file named [internal/db/models.go](file:///var/www/peace-sme-go/internal/db/models.go) to declare all structs.

### 1. Database Nullable Types
PostgreSQL columns can contain `NULL` values. Standard Go types (like `string` or `int64`) cannot hold `nil`.
- We use the standard library `database/sql` types: `sql.NullString`, `sql.NullInt64`, `sql.NullFloat64`, `sql.NullBool`, and `sql.NullTime`.
- To access values, inspect `.Valid` first, then access the typed field (e.g., `name.String`).

### 2. Database Entity Structs

```go
package db

import (
	"database/sql"
	"encoding/json"
	"time"
)

// User models the 'users' table, storing applicant and admin authentication credentials.
type User struct {
	UserID            int64          `json:"user_id"`
	EmailAddress      string         `json:"email_address"`
	HashedPassword    string         `json:"-"` // Prevents password hashes from encoding in JSON
	FirstName         sql.NullString `json:"first_name"`
	LastName          sql.NullString `json:"last_name"`
	MiddleName        sql.NullString `json:"middle_name"`
	CNIC              sql.NullString `json:"cnic"`
	Language          sql.NullString `json:"language"`
	Gender            sql.NullString `json:"gender"`
	MobileNo          sql.NullString `json:"mobile_no"`
	WhatsappNo        sql.NullString `json:"whatsapp_no"`
	TermsAccepted     bool           `json:"terms_accepted"`
	Status            string         `json:"status"` // 'blocked' | 'unblocked'
	LastLoginIP       sql.NullString `json:"last_login_ip"`
	DeviceFingerPrint sql.NullString `json:"device_fingerprint"`
	CreatedAt         time.Time      `json:"created_at"`
}

// Business models the 'businesses' table, storing profile details.
type Business struct {
	BusinessID                    int64           `json:"business_id"`
	UserID                        int64           `json:"user_id"`
	NameOfBusiness                sql.NullString  `json:"name_of_business"`
	BusinessRegistrationNumber    sql.NullString  `json:"business_registration_number"`
	BusinessRegistrationDate      sql.NullTime    `json:"business_registration_date"`
	BusinessRegistrationAuthority json.RawMessage `json:"business_registration_authority"` // JSONB Array
	OtherAuthorityText            sql.NullString  `json:"other_authority_text"`
	BusinessFullAddress           sql.NullString  `json:"business_full_address"`
	SocialMediaPage               sql.NullString  `json:"social_media_page"`
	SocialMediaPage2              sql.NullString  `json:"social_media_page_2"`
	SocialMediaPage3              sql.NullString  `json:"social_media_page_3"`
	SocialMediaPage4              sql.NullString  `json:"social_media_page_4"`
	MaleEmployees                 sql.NullInt64   `json:"male_employees"`
	FemaleEmployees               sql.NullInt64   `json:"female_employees"`
	BusinessLocationDistrict      sql.NullString  `json:"business_location_district"`
	BusinessSector                sql.NullString  `json:"business_sector"`
	HowDidYouHear                 sql.NullString  `json:"how_did_you_hear"`
	HasSRSPRelation               bool            `json:"has_srsp_relation"`
	SRSPRelativesData             json.RawMessage `json:"srsp_relatives_data"` // JSONB Array
	CreatedAt                     time.Time       `json:"created_at"`
}

// BusinessDocument models uploaded files linked to businesses.
type BusinessDocument struct {
	DocumentID   int64     `json:"document_id"`
	BusinessID   int64     `json:"business_id"`
	DocumentType string    `json:"document_type"`
	FileName     string    `json:"file_name"`
	FilePath     string    `json:"file_path"`
	MIMEType     string    `json:"mime_type"`
	CreatedAt    time.Time `json:"created_at"`
}

// FinancedItem is a nested structure stored as JSONB in the 'grants' table.
type FinancedItem struct {
	Item          string  `json:"item"`
	Quantity      int     `json:"quantity"`
	EstimatedCost float64 `json:"estimated_cost"`
}

// SRSPRelative is a nested structure stored as JSONB in the 'grants' table.
type SRSPRelative struct {
	Name     string `json:"name"`
	Position string `json:"position"`
	Office   string `json:"office"`
}

// Grant models the complete grant application workflow.
type Grant struct {
	GrantID                    int64           `json:"grant_id"`
	UserID                     int64           `json:"user_id"`
	ExpressionOfInterest       sql.NullString  `json:"expression_of_interest"` // JSON string array
	GrantRequired              sql.NullFloat64 `json:"grant_required"`
	ApplicationDate            sql.NullTime    `json:"application_date"`
	Status                     string          `json:"status"` // 'Pending', 'Approved', etc.
	ContributionType           sql.NullString  `json:"contribution_type"`
	FinancialAmount            sql.NullFloat64 `json:"financial_amount"`
	FinancialAmountWords       sql.NullString  `json:"financial_amount_words"`
	InKindDetails              sql.NullString  `json:"inkind_details"`
	InKindValue                sql.NullFloat64 `json:"inkind_value"`
	ContributionUtilization    sql.NullString  `json:"contribution_utilization"`
	GrantSupportGrowth         sql.NullString  `json:"grant_support_growth"`
	JobCreationDetails         sql.NullString  `json:"job_creation_details"`
	GrantAmountWords           sql.NullString  `json:"grant_amount_words"`
	OtherPurposeText           sql.NullString  `json:"other_purpose_text"`
	HowDidYouHear              sql.NullString  `json:"how_did_you_hear"`
	ApprovedAmount             sql.NullFloat64 `json:"approved_amount"`
	ApprovalReason             sql.NullString  `json:"approval_reason"`
	ApprovedAt                 sql.NullTime    `json:"approved_at"`
	ApprovedBy                 sql.NullString  `json:"approved_by"`
	HFCStatus                  string          `json:"hfc_status"`
	HFCScore                   int             `json:"hfc_score"`
	HFCRiskLevel               string          `json:"hfc_risk_level"`
	HFCLastEvaluatedAt         sql.NullTime    `json:"hfc_last_evaluated_at"`
	HFCModelVersion            sql.NullString  `json:"hfc_model_version"`
	DomicileDistrict           sql.NullString  `json:"domicile_district"`
	BusinessType               json.RawMessage `json:"business_type"`
	BusinessTypeOther          sql.NullString  `json:"business_type_other"`
	TaxRegistrationStatus      json.RawMessage `json:"tax_registration_status"`
	NTNRegistrationNo          sql.NullString  `json:"ntn_registration_no"`
	TaxFilerStatus             sql.NullString  `json:"tax_filer_status"`
	WorkingCapital             bool            `json:"working_capital"`
	FinancedItems              json.RawMessage `json:"financed_items"`
	ExpectedProductionIncrease sql.NullString  `json:"expected_production_increase"`
	EmploymentGrid             json.RawMessage `json:"employment_grid"`
	DeclarationAccepted        bool            `json:"declaration_accepted"`
	DeclarationName            sql.NullString  `json:"declaration_name"`
	HasSRSPRelative            bool            `json:"has_srsp_relative"`
	SRSPRelatives              json.RawMessage `json:"srsp_relatives"`
}

// GrantMedia models files associated with a grant.
type GrantMedia struct {
	MediaID   int64     `json:"media_id"`
	GrantID   int64     `json:"grant_id"`
	MediaType string    `json:"media_type"`
	FileName  string    `json:"file_name"`
	FilePath  string    `json:"file_path"`
	CreatedAt time.Time `json:"created_at"`
}

// GrantApprovalLog audits administrative approval decisions.
type GrantApprovalLog struct {
	LogID          int64     `json:"log_id"`
	UserID         int64     `json:"user_id"`
	ApprovedBy     string    `json:"approved_by"`
	ApprovedAmount float64   `json:"approved_amount"`
	Reason         string    `json:"reason"`
	CreatedAt      time.Time `json:"created_at"`
}

// HFCEvaluation audits fraud scoring rule evaluations.
type HFCEvaluation struct {
	EvaluationID int64     `json:"evaluation_id"`
	UserID       int64     `json:"user_id"`
	Score        int       `json:"score"`
	RiskLevel    string    `json:"risk_level"`
	RuleDetails  string    `json:"rule_details"` // JSON string breakdown
	EvaluatedAt  time.Time `json:"evaluated_at"`
}

// HFCReviewAction models HFC clear/failed status changes by admin.
type HFCReviewAction struct {
	ActionID    int64     `json:"action_id"`
	UserID      int64     `json:"user_id"`
	ActionType  string    `json:"action_type"`
	Comment     string    `json:"comment"`
	PerformedBy string    `json:"performed_by"`
	CreatedAt   time.Time `json:"created_at"`
}

// HFCRuleConfig stores weights for the deterministic scoring engine.
type HFCRuleConfig struct {
	RuleKey     string    `json:"rule_key"`
	Weight      int       `json:"weight"`
	Description string    `json:"description"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// Update represents public system announcements.
type Update struct {
	UpdateID  int64     `json:"update_id"`
	Title     string    `json:"title"`
	Content   string    `json:"content"`
	IsUrgent  bool      `json:"is_urgent"`
	CreatedAt time.Time `json:"created_at"`
}

// FAQ represents database elements for the FAQ bot.
type FAQ struct {
	FAQID     int64     `json:"faq_id"`
	Question  string    `json:"question"`
	Answer    string    `json:"answer"`
	Keywords  string    `json:"keywords"`
	Language  string    `json:"language"`
	CreatedAt time.Time `json:"created_at"`
}
```

### 3. Application Configuration Structs

```go
package config

// Config models application environment variables.
type Config struct {
	Port                  int
	DatabaseURL           string
	RedisURL              string
	JWTSecret             string
	GrantApplicationOpen  bool
	GrantRequireSelection bool
	HFCShadowMode         bool
	CachePrefix           string
	AllowedCountryCodes   map[string]bool
	AdminUsers            []AdminUser
}

// AdminUser matches the schema of ADMIN_USERS_JSON configuration values.
type AdminUser struct {
	Username         string `json:"username"`
	PasswordHash     string `json:"password_hash"`
	Role             string `json:"role"`
	CanApproveGrants bool   `json:"can_approve_grants"`
}
```

### 4. Authentication Structs

```go
package security

import "github.com/golang-jwt/jwt/v5"

// UserClaims models custom payload claims for JWT authentication.
type UserClaims struct {
	UserID int64 `json:"user_id"`
	jwt.RegisteredClaims
}

// AdminClaims models claims for administrative access.
type AdminClaims struct {
	Username   string `json:"admin_username"`
	Role       string `json:"role"`
	IsAdmin    bool   `json:"is_admin"`
	IsApprover bool   `json:"is_approver"`
	jwt.RegisteredClaims
}

// Identity matches the context object set by auth middlewares.
type Identity struct {
	UserID        int64
	AdminUsername string
	Role          string
	IsAdmin       bool
	IsApprover    bool
}
```

### 5. DTO (Data Transfer Object) Structs

```go
package dto

// LoginRequest models incoming user credential JSON bodies.
type LoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

// RegisterRequest models applicant signup registration requests.
type RegisterRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	CNIC     string `json:"cnic"`
	Name     string `json:"name"`
	Gender   string `json:"gender"`
}

// BusinessProfileRequest represents payloads to create/update business profiles.
type BusinessProfileRequest struct {
	NameOfBusiness               string   `json:"name_of_business"`
	BusinessRegistrationNumber    string   `json:"business_registration_number"`
	BusinessRegistrationAuthority []string `json:"business_registration_authority"`
	BusinessFullAddress           string   `json:"business_full_address"`
	BusinessLocationDistrict      string   `json:"business_location_district"`
	BusinessSector                string   `json:"business_sector"`
}

// GrantApplicationRequest models submitted grant details.
type GrantApplicationRequest struct {
	GrantRequired    float64 `json:"grant_required"`
	ContributionType string  `json:"contribution_type"`
	FinancialAmount  float64 `json:"financial_amount"`
	InKindDetails    string  `json:"inkind_details"`
}
```

---

## Target Shape

```text
cmd/server/main.go
internal/app/app.go
internal/config/config.go
internal/httpx/json.go
internal/health/handler.go
internal/db/models.go
```

`main.go` should do very little:
1. Load config.
2. Build the app.
3. Start the HTTP server.
4. Shut down cleanly on signals.

---

## Handler Style

Prefer explicit handlers:

```go
func (h *Handler) Health(w http.ResponseWriter, r *http.Request) {
    httpx.WriteJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}
```

This style keeps framework magic low while learning Go.

---

## Mastery Check

You understand this chapter when you can:
- Explain what Go Modules are and how `go.mod` is used.
- Explain Go package visibility rules.
- Define a custom struct with JSON tags and explain why tag values are critical.
- Use pointers to share memory resources cleanly.
- Choose between Go value and pointer receiver models.
