# Chapter 3: Go Project Structure and HTTP Server

## Purpose

Replace the stub server with a production-shaped Go application. In this chapter, we will learn the basics of Go's dependency management, package visibility, custom data types, pointers, handlers, and application assembly. We will apply these concepts by building the shell that will eventually host every PEACE SME API endpoint.

This chapter should answer a beginner question: "Where does code go in a Go web app?"

---

## Foundational Concepts Explained Simply

### 1. Go Modules (`go mod`)
In Go, a **Module** is a collection of Go packages stored in a file tree with a `go.mod` file at its root. The `go.mod` file defines the module's import path (its name) and lists the third-party dependency packages required to build the project.
- **Initialization:** Running `go mod init peace-sme-go` creates the `go.mod` file.
- **Adding Dependencies:** When you import a third-party library (like a router or database driver) and run `go get github.com/jackc/pgx/v5`, Go downloads the package and adds it as a dependency in `go.mod`.
- **`go.sum` File:** Go automatically generates a `go.sum` file. This file contains the cryptographic hashes of the dependencies, ensuring that future builds download the exact same code and have not been tampered with.

Application parallel: the portal backend will need dependencies for PostgreSQL, Redis, JWTs, bcrypt, and S3. Go records those dependencies in `go.mod`, which makes the backend reproducible for you, CI, and deployment.

### 2. Packages and Project Organization
Every Go file must start with a package declaration (e.g., `package main` or `package config`).
- **Visibility (Exporting):** Go uses a simple rule for access control:
  - If a struct, function, variable, or field name starts with a **Capital Letter** (e.g., `UserID`, `FindUser()`), it is **exported** (public) and can be accessed by other packages.
  - If it starts with a **lowercase letter** (e.g., `userID`, `findUser()`), it is **unexported** (private) and can only be accessed within the same package.
- **Structure Convention:**
  - **`cmd/`:** Holds entry points (main packages) that compile into executables.
  - **`internal/`:** Packages containing business logic. Go enforces a compiler rule: packages inside `internal/` cannot be imported by external projects outside this module, protecting your internal implementation details.

Application parallel: `internal/grant` should be importable by your server, but not by some unrelated external project. The portal's business rules are internal product logic, not a public Go library.

### 2.1 A Beginner-Friendly Package Rule

Start with packages named after responsibilities, not technical layers only:

```text
internal/user       applicant login and profile behavior
internal/business   business profile behavior
internal/grant      grant application and approval behavior
internal/report     admin report queries
internal/hfc        fraud scoring behavior
```

Inside each package, you can still separate handlers, services, repositories, and models:

```text
internal/grant/
  handler.go
  service.go
  repository.go
  model.go
  validation.go
```

This layout helps you read one feature vertically.

### 3. Structs (Custom Data Types)
A **Struct** is a typed collection of fields. It is used to group related data together to form custom data structures (like a User profile or a Business record).

```go
// Defining a Struct
type Book struct {
    Title  string // Exported field
    Pages  int    // Exported field
    author string // Unexported (private) field
}
```

#### Struct Tags
Fields in a struct can have **tags** (strings metadata) attached to them. Tags are commonly used by encoders to map struct fields to other formats like JSON or SQL database columns:
```go
type User struct {
    Email string `json:"email_address"` // When serialized to JSON, this key becomes "email_address"
}
```

### 4. Pointers (Memory Management)
When you pass a variable to a function in Go, Go always creates a **copy** of that variable's value. 
- If you pass a large struct, copying it consumes memory.
- If you modify the struct inside the function, you are modifying the *copy*, not the original struct.

**Pointers** solve this. A pointer stores the **memory address** of a variable rather than its value.
- <b>Address-of Operator (&):</b> Placing an ampersand before a variable gets its pointer (memory address).
- <b>Dereferencing Operator (*):</b> Placing an asterisk before a pointer variable accesses the underlying value stored at that memory address.
- <b>Type Declaration (asterisk-Type):</b> the notation `*User` means "a pointer to a User struct".

```go
package main

import "fmt"

type Counter struct {
    Val int
}

// Pass by value (copies the struct)
func incrementValue(c Counter) {
    c.Val++ // Modifies only the copy
}

// Pass by pointer (receives the memory address)
func incrementPointer(c *Counter) {
    c.Val++ // Modifies the original struct
}

func main() {
    c := Counter{Val: 10}
    
    incrementValue(c)
    fmt.Println(c.Val) // Prints 10 (original was unchanged)
    
    incrementPointer(&c) // Pass the memory address
    fmt.Println(c.Val) // Prints 11 (original was modified directly)
}
```

Application parallel: when you create an HTTP handler, it often needs access to a service. You usually store a pointer:

```go
type Handler struct {
    service *Service
}
```

Each request uses the same handler instance and the same service dependencies. You do not copy the service for every request.

### 5. HTTP Handlers

In Go's standard library, a handler is any value that can serve an HTTP request:

```go
type Handler interface {
    ServeHTTP(ResponseWriter, *Request)
}
```

Most beginner code starts with:

```go
func healthHandler(w http.ResponseWriter, r *http.Request) {
    w.Write([]byte("ok"))
}
```

For the portal, move toward method handlers:

```go
func (h *Handler) Login(w http.ResponseWriter, r *http.Request) {
    // decode JSON, call service, write response
}
```

Application parallel: every API endpoint in `Claude.md` eventually becomes one handler method.

### External Resources
- [Go Dev: Tutorial on Go Modules](https://go.dev/doc/tutorial/database-access)
- [A Tour of Go: Structs](https://go.dev/tour/moretypes/2)
- [A Tour of Go: Pointers](https://go.dev/tour/moretypes/1)

---

## Project Implementation: Build the Server Skeleton First

The first backend milestone should be small:

```text
cmd/server/main.go
internal/app/app.go
internal/config/config.go
internal/httpx/json.go
internal/health/handler.go
```

### `main.go` Should Stay Boring

`main.go` should not contain grant rules, SQL strings, JWT parsing, or S3 logic. It should compose the program:

```go
func main() {
    cfg, err := config.Load()
    if err != nil {
        log.Fatal(err)
    }

    app, err := app.New(cfg)
    if err != nil {
        log.Fatal(err)
    }

    if err := app.Run(context.Background()); err != nil {
        log.Fatal(err)
    }
}
```

Application parallel: when you later add `/api/grant`, `main.go` should barely change. You add a grant package and register its routes inside the app assembly.

### JSON Helpers

Most PEACE SME endpoints return JSON. Add one helper early:

```go
func WriteJSON(w http.ResponseWriter, status int, value any) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    _ = json.NewEncoder(w).Encode(value)
}
```

And one error helper:

```go
func WriteError(w http.ResponseWriter, status int, code string, message string) {
    WriteJSON(w, status, map[string]string{
        "error": code,
        "message": message,
    })
}
```

Application parallel: login, business profile, grant submission, and admin reports should all use the same response-writing helpers.

## Project Implementation: Defining the Application Models (Structs)

Now we will create the core models for the PEACE SME Grant Portal. We will write them in a centralized location first, so you can practice struct layouts, field types, nullable values, and JSON tags.

Create a file named [internal/db/models.go](file:///var/www/peace-sme-go/internal/db/models.go) to declare all structs.

### 1. Database Nullable Types
In PostgreSQL, fields can be `NULL`. Standard Go primitive types like `string` or `int` cannot hold `nil`.
- To scan nullable database columns safely, Go provides database wrappers under the standard `database/sql` package: `sql.NullString`, `sql.NullInt64`, `sql.NullBool`, `sql.NullTime`.
- When using these, access the value via `.String` or `.Int64` after checking if `.Valid` is true.

### 2. Complete Models File Boilerplate

```go
// File: internal/db/models.go
package db

import (
	"database/sql"
	"encoding/json"
	"time"
)

// User represents a registered applicant or admin user.
type User struct {
	UserID            int64          `json:"user_id"`
	EmailAddress      string         `json:"email_address"`
	HashedPassword    string         `json:"-"` // "-" prevents password hash from rendering in JSON
	FirstName         sql.NullString `json:"first_name"`
	LastName          sql.NullString `json:"last_name"`
	MiddleName        sql.NullString `json:"middle_name"`
	CNIC              sql.NullString `json:"cnic"`
	Language          sql.NullString `json:"language"`
	Gender            sql.NullString `json:"gender"`
	MobileNo          sql.NullString `json:"mobile_no"`
	WhatsappNumber    sql.NullString `json:"whatsapp_number"`
	TermsAccepted     bool           `json:"terms_accepted"`
	Status            string         `json:"status"` // 'blocked' | 'unblocked'
	LastLoginIP       sql.NullString `json:"last_login_ip"`
	DeviceFingerprint sql.NullString `json:"device_fingerprint"`
	CreatedAt         time.Time      `json:"created_at"`
}

// Business represents the applicant's business profile.
type Business struct {
	BusinessID                   int64           `json:"business_id"`
	UserID                       int64           `json:"user_id"`
	NameOfBusiness               sql.NullString  `json:"name_of_business"`
	BusinessRegistrationNumber   sql.NullString  `json:"business_registration_number"`
	BusinessRegistrationDate     sql.NullTime    `json:"business_registration_date"`
	BusinessRegistrationAuthority json.RawMessage `json:"business_registration_authority"` // JSONB Array
	OtherAuthorityText           sql.NullString  `json:"other_authority_text"`
	BusinessFullAddress          sql.NullString  `json:"business_full_address"`
	SocialMediaPage              sql.NullString  `json:"social_media_page"`
	SocialMediaPage2             sql.NullString  `json:"social_media_page_2"`
	SocialMediaPage3             sql.NullString  `json:"social_media_page_3"`
	SocialMediaPage4             sql.NullString  `json:"social_media_page_4"`
	MaleEmployees                sql.NullInt64   `json:"male_employees"`
	FemaleEmployees              sql.NullInt64   `json:"female_employees"`
	BusinessLocationDistrict     sql.NullString  `json:"business_location_district"`
	BusinessSector               sql.NullString  `json:"business_sector"`
	HowDidYouHear                sql.NullString  `json:"how_did_you_hear"`
	HasSRSPRelation              bool            `json:"has_srsp_relation"`
	SRSPRelativesData            json.RawMessage `json:"srsp_relatives_data"` // JSONB Array
	CreatedAt                    time.Time       `json:"created_at"`
}

// BusinessDocument represents uploaded files (e.g., CNIC scans, bank statements).
type BusinessDocument struct {
	DocumentID   int64     `json:"document_id"`
	BusinessID   int64     `json:"business_id"`
	DocumentType string    `json:"document_type"`
	FileName     string    `json:"file_name"`
	FilePath     string    `json:"file_path"` // Public S3 URL
	MIMEType     string    `json:"mime_type"`
	CreatedAt    time.Time `json:"created_at"`
}

// FinancedItem represents an item requested within a grant application.
type FinancedItem struct {
	Item          string  `json:"item"`
	Quantity      int     `json:"quantity"`
	EstimatedCost float64 `json:"estimated_cost"`
}

// SRSPRelative represents a relative working at SRSP.
type SRSPRelative struct {
	Name     string `json:"name"`
	Position string `json:"position"`
	Office   string `json:"office"`
}

// Grant represents the full grant application form.
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
	HFCStatus                  string          `json:"hfc_status"` // 'HFC_Pending', 'Clear', etc.
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
	FinancedItems              json.RawMessage `json:"financed_items"` // Scans nested FinancedItem slice
	ExpectedProductionIncrease sql.NullString  `json:"expected_production_increase"`
	EmploymentGrid             json.RawMessage `json:"employment_grid"`
	DeclarationAccepted        bool            `json:"declaration_accepted"`
	DeclarationName            sql.NullString  `json:"declaration_name"`
	HasSRSPRelative            bool            `json:"has_srsp_relative"`
	SRSPRelatives              json.RawMessage `json:"srsp_relatives"` // Scans nested SRSPRelative slice
}

// HFCEvaluation holds audit records of run fraud scoring rules.
type HFCEvaluation struct {
	EvaluationID int64     `json:"evaluation_id"`
	UserID       int64     `json:"user_id"`
	Score        int       `json:"score"`
	RiskLevel    string    `json:"risk_level"`
	RuleDetails  string    `json:"rule_details"` // JSON string breakdown
	EvaluatedAt  time.Time `json:"evaluated_at"`
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

## Practical Examples

### Example: Creating a Bootstrappable Main Package
We compile our server bootstrapping code inside `/cmd/server/main.go`. In the example below, we initialize a server struct passing it by pointer:

```go
// File: cmd/server/main.go
package main

import (
	"log"
	"net/http"
	"time"
)

type Server struct {
	Addr string
}

// NewServer allocates a server struct and returns a pointer to it.
func NewServer(addr string) *Server {
	return &Server{Addr: addr}
}

func (s *Server) Start() error {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/health", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"status":"healthy"}`))
	})

	srv := &http.Server{
		Addr:         s.Addr,
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
	}

	log.Printf("Bootstrapping server on %s", s.Addr)
	return srv.ListenAndServe()
}

func main() {
	// Allocate server using pointer construct
	srv := NewServer(":8080")
	if err := srv.Start(); err != nil {
		log.Fatalf("Server startup failed: %v", err)
	}
}
```

---

## Mastery Check

You understand this chapter when you can:
- Explain why we compile executables in `cmd/` and put logic in `internal/`.
- Initialize a Go module and fetch libraries.
- Define a custom struct with JSON tags.
- Explain the difference between passing a struct by value and passing it by pointer.
- Use `sql.NullString` to parse nullable database fields.
