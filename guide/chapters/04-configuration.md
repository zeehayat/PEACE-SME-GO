# Chapter 4: Configuration, Environment, and Application Toggles

## Purpose

The Flask application is controlled heavily by environment variables. The Go rewrite must preserve that behavior. In this chapter, we will learn how Go handles errors as normal values, how to use dynamic lists (slices), and key-value tables (maps). We will then implement a robust configuration parser that processes application toggles and administrator user lists.

---

## Foundational Concepts Explained Simply

### 1. Errors as Values
In Go, there are no `try/catch` exception blocks. Instead, errors are treated as normal values that implement the standard `error` interface (which requires a single `Error() string` method).
- **Handling Errors:** If a function can fail, it returns an error as its last return parameter. The caller must explicitly check if the error is not `nil`:

```go
file, err := os.Open("config.json")
if err != nil {
    // Handle the error (fail fast, log it, or return it)
    return err
}
```

- **Error Wrapping:** When returning an error from a function, it is best practice to add context to it using the `%w` verb in `fmt.Errorf`. This preserves the original error for downstream investigation:

```go
if err != nil {
    return fmt.Errorf("failed to open config: %w", err)
}
```

### 2. Slices (Dynamic Arrays)
Unlike standard arrays in Go which have a fixed size defined at compile-time, a **Slice** is a dynamically-sized view into an underlying array.
- **Declaration & Appending:** Use the `append` function to dynamically add elements to a slice:

```go
var list []string // Declares a nil slice
list = append(list, "admin1")
list = append(list, "admin2")
fmt.Println(list) // Prints ["admin1", "admin2"]
```

- **Make:** You can pre-allocate a slice with a specified capacity using `make([]Type, length, capacity)` to optimize memory allocations.

### 3. Maps (Key-Value Tables)
A **Map** is an unordered collection of key-value pairs (a hash map).
- **Initialization:** Maps must be initialized using `make` before you can write to them, otherwise it will cause a panic:

```go
// Creating a map mapping country codes (strings) to existence checks (booleans)
countryMap := make(map[string]bool)
countryMap["PK"] = true
countryMap["AE"] = true
```

- **The Comma-OK Idiom:** To check if a key exists in a map without raising an error:

```go
exists, ok := countryMap["PK"]
if ok {
    fmt.Println("PK is allowed:", exists)
} else {
    fmt.Println("PK is not in the map")
}
```

### External Resources
- [Go Blog: Go Video on Error Handling](https://go.dev/blog/error-handling-and-go)
- [A Tour of Go: Slices](https://go.dev/tour/moretypes/7)
- [A Tour of Go: Maps](https://go.dev/tour/moretypes/19)

---

## Required Configuration Areas

Model these as typed Go fields:

| Area | Variables |
|---|---|
| Auth | `JWT_SECRET_KEY`, `ADMIN_USERS_JSON`, `ADMIN_USERS_PLAIN_JSON` |
| Database | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, pool sizes |
| Redis | Redis URL or host/port |
| S3 | endpoint, access key, secret key, bucket, public base URL, ACL |
| Email | Brevo key, sender email, sender name, approval notification email |
| Toggles | `GRANT_APPLICATION_OPEN`, `GRANT_REQUIRE_SELECTION`, `HFC_SHADOW_MODE`, `HFC_ASYNC_ENABLED` |
| Access | `ACCESS_CONTROL_ENABLED`, `MAX_ACTIVE_APPLICANTS`, `ACCESS_SLOT_TTL_SEC`, `GEO_BLOCK_ENABLED`, `ALLOWED_COUNTRY_CODES` |
| Cache | `CACHE_ENABLED`, `CACHE_PREFIX`, TTL values |

---

## Typed Config

Do not pass raw environment strings throughout the app. Convert once:

```go
type Config struct {
    HTTPAddr              string
    JWTSecret             string
    GrantApplicationOpen  bool
    GrantRequireSelection bool
    HFCShadowMode         bool
    CachePrefix           string
    AllowedCountryCodes   map[string]bool // Map lookup for allowed countries
}
```

Typed config prevents repeated string comparisons such as `os.Getenv("X") == "1"` across the codebase.

---

## Admin Users

`ADMIN_USERS_JSON` contains:

```json
[
  {
    "username": "admin1",
    "password_hash": "$2b$12$...",
    "role": "admin",
    "can_approve_grants": false
  }
]
```

In Go, unmarshal it into:

```go
type AdminUser struct {
    Username         string `json:"username"`
    PasswordHash     string `json:"password_hash"`
    Role             string `json:"role"`
    CanApproveGrants bool   `json:"can_approve_grants"`
}
```

---

## Practical Examples

### Example: Writing a Fail-Fast Configuration Loader
This complete configuration loader parses basic string flags, converts strings to integers/booleans, maps country codes into a lookup Map, and unmarshals the admin JSON array into a Slice:

```go
// File: internal/config/config.go
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
	Port                 int
	JWTSecret            string
	GrantApplicationOpen bool
	AllowedCountryCodes  map[string]bool // Fast lookup map
	AdminUsers           []AdminUser     // Slice of admin users
}

// Load compiles config values, returning wrapping errors on parsing failures.
func Load() (*Config, error) {
	cfg := &Config{
		AllowedCountryCodes: make(map[string]bool),
	}

	// 1. Parsing Port integer
	portStr := getEnv("PORT", "8080")
	port, err := strconv.Atoi(portStr)
	if err != nil {
		return nil, fmt.Errorf("parsing PORT %q failed: %w", portStr, err)
	}
	cfg.Port = port

	// 2. Validate required secret
	cfg.JWTSecret = os.Getenv("JWT_SECRET_KEY")
	if cfg.JWTSecret == "" {
		return nil, fmt.Errorf("required environment key JWT_SECRET_KEY is empty")
	}

	// 3. Parsing application toggle bool
	cfg.GrantApplicationOpen = getEnv("GRANT_APPLICATION_OPEN", "0") == "1"

	// 4. Split allowed country codes string into a fast lookup map
	allowedStr := getEnv("ALLOWED_COUNTRY_CODES", "PK")
	countries := strings.Split(allowedStr, ",") // Returns a slice
	for _, country := range countries {
		cleanCode := strings.TrimSpace(strings.ToUpper(country))
		if cleanCode != "" {
			cfg.AllowedCountryCodes[cleanCode] = true
		}
	}

	// 5. Unmarshal admin users array
	adminJSON := os.Getenv("ADMIN_USERS_JSON")
	if adminJSON != "" {
		var admins []AdminUser // Allocates slice
		if err := json.Unmarshal([]byte(adminJSON), &admins); err != nil {
			return nil, fmt.Errorf("decoding admin user JSON array failed: %w", err)
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

## Toggle Behavior to Preserve

- If `GRANT_APPLICATION_OPEN=0`, pre-registration and registration return 403.
- If `GRANT_REQUIRE_SELECTION=1`, grant submission requires whitelist selection.
- If `HFC_SHADOW_MODE=1`, HFC scores are visible but do not block approval.
- If `GEO_BLOCK_ENABLED=1`, non-allowed country codes are rejected.
- If `ACCESS_CONTROL_ENABLED=1`, applicant traffic is limited by Redis session slots.

---

## Mastery Check

You understand this chapter when you can:
- Explain why Go handles errors as return values instead of using exceptions.
- Explain the memory differences between static arrays and slices.
- Populate and look up key presence in a map.
- Fail application startup immediately if critical configuration variables are malformed or missing.
