# Chapter 4: Configuration, Environment, and Application Toggles

## Purpose

The Flask application is controlled heavily by environment variables. The Go rewrite must preserve that behavior. In this chapter, we will study error propagation, dynamic slices, and hash maps in Go. We will then expand our configuration parser to document, parse, and validate **every application toggle and secret** required by the system.

---

## Foundational Concepts Explained Simply

### 1. Errors as Values
In Go, there are no exceptions (`try/catch`). Errors are simple values returned from functions that must be explicitly checked.

:::expandable [Go Errors & Wrapping]
#### In-Depth Explanation
A function that can fail returns a value of type `error` (which is a built-in interface).
- **Sentinel Errors:** Package-level error constants like `sql.ErrNoRows` or custom errors declared with `errors.New()`.
- **Error Wrapping:** When returning an error, you can wrap it with context using `fmt.Errorf("failed: %w", err)`. This creates an error chain that preserves the original root error.
- **Checking Errors:** Use `errors.Is(err, target)` to check if a specific error exists in the chain, or `errors.As(err, &target)` to extract a custom error type.

#### Sandbox Program: Error Wrapping and Checks
This sandbox demonstrates how to wrap errors and inspect the error chain dynamically:

```go
package main

import (
	"errors"
	"fmt"
)

// Define sentinel error values
var ErrConfigNotFound = errors.New("configuration file not found")

func loadFile() error {
	// Simulate a low-level OS read error
	return ErrConfigNotFound
}

func parseConfig() error {
	err := loadFile()
	if err != nil {
		// Wrap the error with context using %w
		return fmt.Errorf("failed to parse environment: %w", err)
	}
	return nil
}

func main() {
	err := parseConfig()
	if err != nil {
		fmt.Println("Returned Error:", err)

		// Check if the ErrConfigNotFound is present in the error chain
		if errors.Is(err, ErrConfigNotFound) {
			fmt.Println("Action: Falling back to default system values.")
		}
	}
}
```
:::

### 2. Slices (Dynamic Lists)
A **Slice** is a dynamically-sized, flexible wrapper around a Go array.
- Slices grow automatically as you add items.
- You allocate them using `make()` or as slice literals: `[]int{1, 2, 3}`.

:::expandable [Slices, Capacity & Appending]
#### In-Depth Explanation
A slice contains three components:
1. **Pointer:** Points to the first element of the underlying array.
2. **Length (`len`):** The number of elements currently in the slice.
3. **Capacity (`cap`):** The maximum number of elements the slice can hold before the runtime must allocate a new, larger underlying array.

When you call `append(slice, value)`, if the length exceeds the capacity, Go automatically doubles the underlying array capacity, copies the elements, and returns the new slice pointer.

#### Sandbox Program: Slice Capacity Growth
This sandbox demonstrates how Go increases a slice's capacity as elements are added:

```go
package main

import "fmt"

func main() {
	// Initialize a slice of strings with length 0 and capacity 2
	names := make([]string, 0, 2)

	fmt.Printf("Initial - Len: %d, Cap: %d\n", len(names), cap(names))

	names = append(names, "Swat")
	names = append(names, "Shangla")
	fmt.Printf("After 2 Appends - Len: %d, Cap: %d\n", len(names), cap(names))

	// This third append exceeds the capacity of 2
	names = append(names, "Chitral")
	fmt.Printf("After 3 Appends (Grow) - Len: %d, Cap: %d\n", len(names), cap(names))
}
```
:::

### 3. Maps (Key-Value Lookups)
A **Map** is a built-in hash table mapping unique keys to values.
- Declare maps using `make(map[KeyType]ValueType)`.
- Writing to a `nil` (uninitialized) map triggers a runtime crash. Always allocate maps before inserting values.

:::expandable [Maps & Comma-OK Checks]
#### In-Depth Explanation
- **Comma-OK Idiom:** In Go, looking up a missing key returns the value's zero-value (e.g. `0` for int, `""` for string). To differentiate between a key that has a zero-value vs a key that is missing, use the double assignment syntax: `val, ok := myMap[key]`.
- **Deleting Keys:** Use the built-in `delete(myMap, key)` function.

#### Sandbox Program: Map Lookups and Deletions
This sandbox demonstrates lookups, checking for key existence, and deletion:

```go
package main

import "fmt"

func main() {
	// Declare and allocate map
	districts := make(map[string]bool)
	districts["Swat"] = true
	districts["Shangla"] = true

	// Check if Swat exists
	if val, ok := districts["Swat"]; ok {
		fmt.Printf("Swat exists! Value: %t\n", val)
	}

	// Check if Peshawar exists
	if _, ok := districts["Peshawar"]; !ok {
		fmt.Println("Peshawar is not a supported KP district.")
	}

	// Delete a key
	delete(districts, "Swat")
	_, ok := districts["Swat"]
	fmt.Printf("Does Swat exist after delete? %t\n", ok)
}
```
:::

---

## Detailed Environment Variables Reference

Below is a comprehensive guide to every environment variable used to control the portal's operational behavior, including validation rules, security notes, and fallback details:

### 1. HTTP Server & Security Controls
* **`PORT`**
  * **Data Type:** Integer
  * **Default / Fallback:** `8080`
  * **Validation Rule:** Must be a valid port number between `1` and `65535`.
  * **Operational Impact / Fallback:** The local TCP port the HTTP server binds to. If parsing fails, the configuration loader will return a non-nil parsing error and crash the application immediately at startup, preventing a silent boot failure on an invalid port.
* **`JWT_SECRET_KEY`**
  * **Data Type:** String
  * **Default / Fallback:** *Required (No Default)*
  * **Validation Rule:** Must not be empty. In production, this should be a high-entropy cryptographically secure string (at least 32 characters long).
  * **Operational Impact / Fallback:** Used as the HMAC symmetric key to sign and verify JSON Web Tokens (JWT) for both applicants and admins. If omitted or empty, the application will crash during startup with an error: `"required environment variable JWT_SECRET_KEY is empty"`.
* **`ADMIN_USERS_JSON`**
  * **Data Type:** String (JSON Array)
  * **Default / Fallback:** `[]` (Empty Array)
  * **Validation Rule:** Must be valid JSON array conforming to the schema: `[{"username":"admin", "password_hash":"...", "role":"admin", "can_approve_grants":true}]`.
  * **Operational Impact / Fallback:** Bootstraps admin login profiles. Password hashes must be pre-hashed using the `bcrypt` algorithm. If the JSON is malformed, the startup sequence will abort with a deserialization error.

### 2. Database & Cache Connectivity
* **`POSTGRES_HOST`** / **`POSTGRES_PORT`** / **`POSTGRES_USER`** / **`POSTGRES_PASSWORD`** / **`POSTGRES_DB`**
  * **Data Type:** Strings / Integers
  * **Defaults:** `localhost` / `5432` / `sme_user` / `sme_password` / `sme_app`
  * **Validation Rule:** Must be valid connectivity details.
  * **Operational Impact / Fallback:** These fields are parsed and concatenated into a standard Postgres connection string (`postgres://...`). The Go loader will append `sslmode=disable` to allow local developer environments to connect without SSL certificates, but production overrides should use proper connection URLs.
* **`REDIS_URL`**
  * **Data Type:** String (Redis connection URI)
  * **Default / Fallback:** `redis://localhost:6379/0`
  * **Validation Rule:** Must be a valid URI format.
  * **Operational Impact / Fallback:** Connects to the Redis cluster used for queuing background jobs (emails, risk rule audits) and storing active session keys.

### 3. Object Storage (S3-Compatible)
* **`S3_ENDPOINT_URL`**
  * **Data Type:** String (URL)
  * **Default / Fallback:** *Required*
  * **Validation Rule:** Must be a valid URL with scheme (e.g. `https://s3.contabostorage.com`).
  * **Operational Impact / Fallback:** Configures the client SDK endpoint to contact S3.
* **`S3_ACCESS_KEY`** / **`S3_SECRET_KEY`**
  * **Data Type:** Strings
  * **Default / Fallback:** *Required*
  * **Validation Rule:** Non-empty credentials.
  * **Operational Impact / Fallback:** S3 credentials. Omission results in S3 client generation errors.
* **`S3_BUCKET_NAME`**
  * **Data Type:** String
  * **Default / Fallback:** `peace-economic`
  * **Validation Rule:** Must conform to DNS bucket naming conventions.
  * **Operational Impact / Fallback:** Folder target bucket.
* **`S3_PUBLIC_BASE_URL`**
  * **Data Type:** String (URL)
  * **Default / Fallback:** *Required*
  * **Validation Rule:** Must be a valid public URL.
  * **Operational Impact / Fallback:** Used by the backend to construct permanent public HTTP paths for saved business documents and media files.

### 4. Third-Party Integrations
* **`EMAIL_API_KEY`**
  * **Data Type:** String
  * **Default / Fallback:** *Required*
  * **Validation Rule:** Must not be empty.
  * **Operational Impact / Fallback:** Brevo API key used to deliver transactional emails to applicants when they pre-register or when a grant status changes.

### 5. Application Feature Flags & Toggles
* **`GRANT_APPLICATION_OPEN`**
  * **Data Type:** String/Boolean (`0` or `1`)
  * **Default / Fallback:** `0` (Closed)
  * **Validation:** Checked using `getEnv(...) == "1"`.
  * **Operational Impact:** If set to `0`, registration routes immediately return `403 Forbidden`. If `1`, registrations are enabled.
* **`GRANT_REQUIRE_SELECTION`**
  * **Data Type:** String/Boolean (`0` or `1`)
  * **Default / Fallback:** `1` (Required)
  * **Operational Impact:** If `1`, only whitelisted user records can proceed past initial drafts.
* **`HFC_SHADOW_MODE`**
  * **Data Type:** String/Boolean (`0` or `1`)
  * **Default / Fallback:** `1` (Shadow Mode Active)
  * **Operational Impact:** If `1`, background fraud scoring rules are executed and logged but do not block human approval workflows. If `0`, rules are active blocks.
* **`ACCESS_CONTROL_ENABLED`**
  * **Data Type:** String/Boolean (`0` or `1`)
  * **Default / Fallback:** `1` (Active)
  * **Operational Impact:** Enables concurrent session limits using Redis counters.
* **`MAX_ACTIVE_APPLICANTS`**
  * **Data Type:** Integer
  * **Default / Fallback:** `300`
  * **Operational Impact:** The maximum number of concurrent applicant sessions.
* **`GEO_BLOCK_ENABLED`**
  * **Data Type:** String/Boolean (`0` or `1`)
  * **Default / Fallback:** `1` (Active)
  * **Operational Impact:** Inspects country code headers to block traffic.
* **`ALLOWED_COUNTRY_CODES`**
  * **Data Type:** String (Comma-separated values)
  * **Default / Fallback:** `PK`
  * **Operational Impact:** Traffic outside this list is blocked. Case-insensitive and trimmed during loading.

---

## Phased Configuration Implementation

To master parsing, we will now define our configuration loader.

Create a file named [internal/config/config.go](file:///var/www/peace-sme-go/internal/config/config.go) to declare these structures and parser functions.

```go
package config

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
)

type AdminUser struct {
	Username         string `json:"username"`
	PasswordHash     string `json:"password_hash"`
	Role             string `json:"role"`
	CanApproveGrants bool   `json:"can_approve_grants"`
}

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

// Load compiles and validates configuration values from the environment.
// It executes the following step-by-step loading procedure:
// 1. Os Environment Lookup: Scans environment variables on the system.
// 2. Type Conversion: Safe conversion of strings to integers (Port) and booleans.
// 3. String Interp: Concatenates PostgreSQL components into a connection URL.
// 4. Presence Validation: Verifies critical keys like JWT_SECRET_KEY exist.
// 5. Normalization: Splits allowed countries by comma and capitalizes them.
// 6. JSON Deserialization: Unmarshals ADMIN_USERS_JSON into slices.
func Load() (*Config, error) {
	cfg := &Config{
		AllowedCountryCodes: make(map[string]bool),
	}

	// 1. Parsing integer Port
	portStr := getEnv("PORT", "8080")
	port, err := strconv.Atoi(portStr)
	if err != nil {
		return nil, fmt.Errorf("parsing PORT %q failed: %w", portStr, err)
	}
	cfg.Port = port

	// 2. Database credentials compilation
	dbHost := getEnv("POSTGRES_HOST", "localhost")
	dbPort := getEnv("POSTGRES_PORT", "5432")
	dbUser := getEnv("POSTGRES_USER", "sme_user")
	dbPass := getEnv("POSTGRES_PASSWORD", "sme_password")
	dbName := getEnv("POSTGRES_DB", "sme_app")
	cfg.DatabaseURL = fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=disable",
		dbUser, dbPass, dbHost, dbPort, dbName)

	// 3. Redis URL
	cfg.RedisURL = getEnv("REDIS_URL", "redis://localhost:6379/0")

	// 4. Validate required variables
	cfg.JWTSecret = os.Getenv("JWT_SECRET_KEY")
	if cfg.JWTSecret == "" {
		return nil, fmt.Errorf("required environment variable JWT_SECRET_KEY is empty")
	}

	// 5. Parsing boolean toggles
	cfg.GrantApplicationOpen = getEnv("GRANT_APPLICATION_OPEN", "0") == "1"
	cfg.GrantRequireSelection = getEnv("GRANT_REQUIRE_SELECTION", "1") == "1"
	cfg.HFCShadowMode = getEnv("HFC_SHADOW_MODE", "1") == "1"

	// 6. Split allowed country codes into a lookup map
	allowedStr := getEnv("ALLOWED_COUNTRY_CODES", "PK")
	for _, code := range strings.Split(allowedStr, ",") {
		clean := strings.TrimSpace(strings.ToUpper(code))
		if clean != "" {
			cfg.AllowedCountryCodes[clean] = true
		}
	}

	// 7. Unmarshal admin users array
	adminJSON := os.Getenv("ADMIN_USERS_JSON")
	if adminJSON != "" {
		var admins []AdminUser
		if err := json.Unmarshal([]byte(adminJSON), &admins); err != nil {
			return nil, fmt.Errorf("decoding ADMIN_USERS_JSON failed: %w", err)
		}
		cfg.AdminUsers = admins
	}

	return cfg, nil
}

func getEnv(key, defaultVal string) string {
	val := os.Getenv(key)
	if val == "" {
		return defaultVal
	}
	return val
}
```

---

## Practical Examples

:::expandable [Runnable Configuration Sandbox]
#### In-Depth Explanation
This sandbox program simulates our configuration loader. It sets up a mock environment, parses integers, converts booleans, maps country codes, and validates admin JSON configs in an isolated, runnable environment.

#### Sandbox Program: Mock Environment Configuration Loader
```go
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
)

type SandboxAdmin struct {
	Username string `json:"username"`
	Role     string `json:"role"`
}

type SandboxConfig struct {
	Port                int
	Open                bool
	AllowedCountries    map[string]bool
	Admins              []SandboxAdmin
}

func main() {
	// Set mock environment variables
	os.Setenv("MOCK_PORT", "9000")
	os.Setenv("MOCK_OPEN", "1")
	os.Setenv("MOCK_COUNTRIES", "PK,AE")
	os.Setenv("MOCK_ADMINS", `[{"username":"aftab", "role":"approver"}]`)

	cfg := &SandboxConfig{
		AllowedCountries: make(map[string]bool),
	}

	// 1. Parse Port
	portStr := os.Getenv("MOCK_PORT")
	port, err := strconv.Atoi(portStr)
	if err != nil {
		fmt.Println("Error parsing port:", err)
		return
	}
	cfg.Port = port

	// 2. Parse Toggle
	cfg.Open = os.Getenv("MOCK_OPEN") == "1"

	// 3. Parse Allowed Countries Map
	countriesStr := os.Getenv("MOCK_COUNTRIES")
	for _, code := range strings.Split(countriesStr, ",") {
		cfg.AllowedCountries[strings.TrimSpace(code)] = true
	}

	// 4. Parse Admins Slice
	adminsStr := os.Getenv("MOCK_ADMINS")
	var admins []SandboxAdmin
	if err := json.Unmarshal([]byte(adminsStr), &admins); err != nil {
		fmt.Println("Error parsing admins:", err)
		return
	}
	cfg.Admins = admins

	// Output parsed values
	fmt.Println("--- Parsed Sandbox Config ---")
	fmt.Printf("Server Port: %d\n", cfg.Port)
	fmt.Printf("Registration Open: %t\n", cfg.Open)
	fmt.Printf("Whitelisted Countries: %v\n", cfg.AllowedCountries)
	fmt.Printf("Loaded Admins: %+v\n", cfg.Admins)
}
```
:::

---

## Mastery Check

You understand this chapter when you can:
- List every environmental variable that controls the portal's security state.
- Explain the role of the `GRANT_APPLICATION_OPEN` toggle.
- Parse environment variables into integers, booleans, and nested JSON structs.
- Use maps for whitelisted country lookups.
- Propagate parsing errors safely using formatting context.
