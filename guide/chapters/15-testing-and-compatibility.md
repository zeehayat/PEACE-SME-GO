# Chapter 15: Testing, Debugging, and API Compatibility

## Purpose

Testing proves that the Go and Vue rewrite matches the Flask behavior. Compatibility is the product.

## Theoretical Background

### The Testing Pyramid
A balanced software testing strategy is represented as a pyramid:
1. **Unit Tests (Base):** Focus on isolated functions (e.g., config loaders, score calculators). They are fast, reliable, and run entirely in memory.
2. **Integration Tests (Middle):** Validate that multiple components (e.g., service layers interacting with a real PostgreSQL connection pool or S3 mock) work together correctly.
3. **End-to-End (E2E) Tests (Top):** Spin up the entire system (Vue frontend + Go backend + DB + Redis) and simulate real user flows via browser automated drivers (like Cypress or Playwright).

```text
       /\
      /  \     <-- E2E Tests (Slow, High Fidelity)
     /----\
    /      \   <-- Integration Tests (Medium Speed)
   /--------\
  /          \ <-- Unit Tests (Fast, In-Memory)
 /------------\
```

### Table-Driven Testing in Go
Go's idiomatic pattern for unit testing is **Table-Driven Testing**:
- You define a slice of anonymous structs representing input parameters, expected outputs, and test description names.
- You iterate over this "table" of test cases, running each case as an isolated subtest using `t.Run()`.
- This keeps test files clean, makes it easy to add new test vectors, and avoids repetitive copy-paste testing code.

### Keyset Regression & API Compatibility
When migrating a backend:
- The HTTP path, request verbs, response JSON keys, and HTTP status codes must match the original implementation exactly.
- Test suites must verify contract details: e.g., verifying that a missing field returns exactly `422 Unprocessable Entity` containing the specific error keys expected by Axios interceptors.

### Git Bisect for Debugging Regressions
When a regression bug is introduced in a codebase and it is unclear which commit caused it:
- **Git Bisect** executes a binary search through your commit history.
- You mark a known "good" commit (where the bug did not exist) and a known "bad" commit (where the bug exists).
- Git checks out intermediate commits, prompting you (or an automated test script) to classify each commit as `good` or `bad`, rapidly locating the root cause commit.

### External Resources
- [Go Wiki: Table-Driven Tests](https://github.com/golang/go/wiki/TableDrivenTests)
- [Git Documentation: git-bisect](https://git-scm.com/docs/git-bisect)
- [Cypress End-to-End Testing Guide](https://docs.cypress.io/guides/overview/why-cypress)

---

## Go Test Layers

Use:
- Unit tests for config, validation, JWT, HFC scoring.
- Repository tests for SQL queries.
- Handler tests for HTTP status and JSON shape.
- Integration tests for full workflows.

---

## Handler Tests

Use `httptest`:

```go
req := httptest.NewRequest(http.MethodGet, "/api/updates", nil)
rr := httptest.NewRecorder()
handler.ServeHTTP(rr, req)
```

Assert:
- status code
- content type
- JSON fields
- error shape

---

## Compatibility Tests

For each endpoint, test:
- method
- path
- auth requirement
- request payload
- response shape
- important business rules

Examples:
- Registration closed returns 403.
- Blocked user cannot login.
- Grant submission requires whitelist when enabled.
- Non-approver cannot approve grant.
- HFC shadow mode does not block approval.

---

## Vue Testing

Use component tests for:
- route guard behavior
- login form submission
- language switching
- grant form conditional sections
- admin table filters

Use end-to-end tests for:
- login to dashboard
- create/update business profile
- admin login and report loading
- grant application submission path

---

## Debugging Tools

Backend:

```bash
go test ./...
go test ./internal/grant -run TestGrantAccess -v
go test -race ./...
```

Frontend:

```bash
npm run test
npm run build
```

Git:

```bash
git diff
git blame path/to/file
git bisect start
```

---

## Practical Examples

### Example 1: Table-Driven Unit Test in Go
This complete testing code demonstrates table-driven unit testing using Go subtests for a business registration validation helper:

```go
// File: internal/business/dto_test.go
package business

import (
	"testing"
)

func TestCreateBusinessRequest_Validate(t *testing.T) {
	// Table of test cases
	tests := []struct {
		name        string
		request     CreateBusinessRequest
		expectError bool
		errorMsg    string
	}{
		{
			name: "Valid request",
			request: CreateBusinessRequest{
				Name:            "Khyber Tech Solutions",
				Address:         "Main Bazaar, Swat",
				District:        "Swat",
				MaleEmployees:   5,
				FemaleEmployees: 2,
			},
			expectError: false,
		},
		{
			name: "Empty business name",
			request: CreateBusinessRequest{
				Name:            "",
				Address:         "Main Bazaar, Swat",
				District:        "Swat",
				MaleEmployees:   1,
				FemaleEmployees: 0,
			},
			expectError: true,
			errorMsg:    "business name is required",
		},
		{
			name: "Invalid district out of scope",
			request: CreateBusinessRequest{
				Name:            "Khyber Tech Solutions",
				Address:         "Main Bazaar, Swat",
				District:        "Peshawar", // not in allowed list
				MaleEmployees:   1,
				FemaleEmployees: 0,
			},
			expectError: true,
			errorMsg:    "business location district is out of allowed scope",
		},
		{
			name: "Negative employee counts",
			request: CreateBusinessRequest{
				Name:            "Khyber Tech Solutions",
				Address:         "Main Bazaar, Swat",
				District:        "Swat",
				MaleEmployees:   -1,
				FemaleEmployees: 0,
			},
			expectError: true,
			errorMsg:    "employee counts cannot be negative",
		},
	}

	// Iterate over the table
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.request.Validate()
			
			if tt.expectError {
				if err == nil {
					t.Errorf("expected error containing %q, got nil", tt.errorMsg)
				} else if err.Error() != tt.errorMsg {
					t.Errorf("expected error message %q, got %q", tt.errorMsg, err.Error())
				}
			} else {
				if err != nil {
					t.Errorf("unexpected error: %v", err)
				}
			}
		})
	}
}
```

### Example 2: Automatic Git Bisect Session
To find a commit that broke a test automatically:

```bash
# Start bisect session
git bisect start

# Mark current HEAD as bad
git bisect bad

# Mark a known good tag or commit hash (e.g., release-v1.0.0)
git bisect good release-v1.0.0

# Run git bisect automatically using a test script
git bisect run go test ./internal/business -run TestCreateBusinessRequest_Validate
```
Git will iterate through the history, run the test, and output the first bad commit.

---

## Mastery Check

You understand this chapter when you can:
- Write table-driven Go tests.
- Test authenticated HTTP handlers.
- Detect API contract regressions.
- Reproduce a bug with a failing test before fixing it.
- Use Git history to find when behavior changed.
