# Chapter 5: PostgreSQL, Migrations, and Data Modeling

## Purpose

The database is the most important compatibility layer. The Go backend must use the same PostgreSQL schema as the Flask application. In this chapter, we will study relational modeling, Go database access, connection pools, migrations, nullable values, JSONB, and transactions.

Generics are useful in Go, but they are not the main database lesson. The main lesson is this: your Go code must treat the database as a contract, not as an afterthought.

---

## Foundational Concepts Explained Simply

### 1. Relational Modeling

A relational database stores facts in tables and connects those facts with keys.

Application parallel:

- `users` stores applicant identity.
- `businesses` stores one business per applicant.
- `grants` stores one grant application per applicant.
- `business_documents` stores many uploaded documents per business.
- `grant_approval_logs` stores many approval actions per grant.

The relationships matter:

```text
users 1 -> 1 businesses
users 1 -> 1 grants
businesses 1 -> many business_documents
grants 1 -> many grant_approval_logs
```

This is why blindly embedding everything in one JSON document would be a poor fit for this application. Admin reports need filtering, joining, counting, and exporting.

### 2. Generics in Go (Type Parameters)
Before Go 1.18, if you wanted to write a helper struct or function that could work with *any* data type, you had to use the empty interface (`interface{}` or `any`). This removed compile-time type safety, requiring you to cast values back and forth.
- **Generics** introduce **Type Parameters**, allowing you to write code that placeholder-types specify at creation time.
- **Syntax:** Place the type parameter constraint (like `[T any]` or `[T comparable]`) after the struct or function name.

Here is a simple example of a generic `Box` container:

```go
package main

import "fmt"

// Box is a generic struct containing any type T
type Box[T any] struct {
    Content T
}

func main() {
    // A box holding an integer
    intBox := Box[int]{Content: 123}
    
    // A box holding a string
	stringBox := Box[string]{Content: "PEACE Grant"}
	
	fmt.Println(intBox.Content)    // Prints 123 (typed as int)
	fmt.Println(stringBox.Content) // Prints "PEACE Grant" (typed as string)
}
```

Application parallel: a generic paginated response can hold applicants, grants, HFC queue rows, or updates while preserving the same envelope shape.

### 3. Database Connection Pooling
Every SQL query requires network communication with the database engine. Establishing a raw TCP database connection is incredibly slow because it performs handshakes, SSL handshakes, and process allocations.
- **The Pool Solution:** Instead of opening a new connection for every request, a **Connection Pool** maintains a pool of persistently open, active connections.
- When Go wants to run a query, it leases a connection from the pool, executes the SQL, and releases it back to the pool.
- Go's `github.com/jackc/pgx/v5/pgxpool` manages this process concurrently and safely.

Application parallel: admin reports may be requested by multiple staff at once. Without a pool, the backend would waste time repeatedly opening connections. With a pool, requests borrow existing connections safely.

### 4. Nullable Values

PostgreSQL columns can be `NULL`. Go's plain `string`, `int`, and `float64` cannot represent SQL null.

Use nullable types:

```go
type User struct {
    FirstName sql.NullString
    CreatedAt time.Time
}
```

When sending JSON to Vue, you may convert database rows into response DTOs so null handling is cleaner:

```go
type UserProfileResponse struct {
    FirstName *string `json:"first_name"`
}
```

Application parallel: optional fields such as `middle_name`, `business_registration_number`, `approved_amount`, and `approval_reason` may be empty until later in the workflow.

### 5. JSONB

JSONB is PostgreSQL's binary JSON type. It is useful for flexible nested data while still keeping the main workflow relational.

Application parallel:

- `business_registration_authority` is an array.
- `financed_items` is an array of item rows.
- `employment_grid` is an object.
- `srsp_relatives` is an array of relative rows.
- `rules_triggered` is an array of HFC rules.

Beginner rule: if Go needs to validate or inspect the JSON, create typed structs. If Go only stores and returns it, `json.RawMessage` can be acceptable.

### External Resources
- [Go Dev: Tutorial on Generics](https://go.dev/doc/tutorial/generics)
- [pgx Connection Pool Documentation](https://pkg.go.dev/github.com/jackc/pgx/v5/pgxpool)
- [System Design Primer: Database Connection Pools](https://github.com/donnemartin/system-design-primer#database)

---

## Tables to Preserve

The core tables are:
- `users`
- `businesses`
- `business_documents`
- `grants`
- `grant_media`
- `grant_approval_logs`
- `grant_access_whitelist`
- `applicant_status`
- `hfc_evaluations`
- `hfc_review_actions`
- `hfc_rule_config`
- `initial_registrations`
- `updates`
- `faqs`
- `schema_migrations`

All foreign keys use `ON DELETE CASCADE`. Preserve that behavior.

## Application Parallel: Business Feature to Table

| Portal feature | Tables touched | Go concept practiced |
|---|---|---|
| Login | `users` | row scanning, bcrypt hash retrieval |
| Business profile | `businesses` | one-to-one relation, nullable fields |
| Document upload | `business_documents` | one-to-many relation |
| Grant application | `grants` | JSONB, unique constraint |
| Grant approval | `grants`, `grant_approval_logs` | transaction |
| HFC scoring | `grants`, `hfc_evaluations` | insert plus update |
| Reports | many joined tables | filters, pagination, indexes |

---

## Migration Strategy

Create SQL migration files matching the original `init_db.py` history:

```text
migrations/
  001_initial_users_businesses_documents.sql
  002_create_grants.sql
  ...
  023_add_grant_srsp_relatives.sql
```

Use `schema_migrations` to record applied versions.

---

## Practical Examples

### Example 1: Implementing a Generic API Response Wrapper
We can use Go's generics to build a single, type-safe HTTP response envelope structure. This ensures that whether we return a list of `User` models or a single `Business` profile, the JSON response layout remains identical:

```go
// File: internal/httpx/json.go
package httpx

import (
	"encoding/json"
	"net/http"
)

// APIResponse wraps any data type T in a standard envelope structure.
type APIResponse[T any] struct {
	Success bool   `json:"success"`
	Message string `json:"message,omitempty"`
	Data    T      `json:"data,omitempty"`
}

// WriteJSON sends a generic payload with a HTTP status code.
func WriteJSON[T any](w http.ResponseWriter, status int, data T) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	
	envelope := APIResponse[T]{
		Success: status < 400,
		Data:    data,
	}

	json.NewEncoder(w).Encode(envelope)
}
```

### Example 2: Database Transaction Execution
This example demonstrates how to execute multiple writes within a single transactional block to update a grant's status and insert an approval audit log, rolling back automatically if any query fails:

```go
// File: internal/grant/repository.go
package grant

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct {
	db *pgxpool.Pool
}

func NewRepository(db *pgxpool.Pool) *Repository {
	return &Repository{db: db}
}

// ApproveGrant performs a transaction: updates grant status, inserts approval audit log.
func (r *Repository) ApproveGrant(ctx context.Context, userID int64, approver string, amount float64, reason string) error {
	// 1. Begin transaction
	tx, err := r.db.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	// Defer a rollback. If tx commits successfully before function ends, rollback is a safe no-op.
	defer tx.Rollback(ctx)

	// 2. Update grant record
	updateQuery := `
		UPDATE grants 
		SET status = 'Approved', approved_amount = $1, approval_reason = $2, approved_at = $3, approved_by = $4 
		WHERE user_id = $5`
	
	result, err := tx.Exec(ctx, updateQuery, amount, reason, time.Now(), approver, userID)
	if err != nil {
		return fmt.Errorf("failed to update grant: %w", err)
	}
	if result.RowsAffected() == 0 {
		return fmt.Errorf("grant record not found for user %d", userID)
	}

	// 3. Write approval audit log
	logQuery := `
		INSERT INTO grant_approval_logs (user_id, approved_by, approved_amount, reason, created_at) 
		VALUES ($1, $2, $3, $4, $5)`
	
	_, err = tx.Exec(ctx, logQuery, userID, approver, amount, reason, time.Now())
	if err != nil {
		return fmt.Errorf("failed to write audit log: %w", err)
	}

	// 4. Commit transaction
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	return nil
}
```

---

## Repository Pattern

Keep SQL in repository packages. Handlers should not build SQL strings directly.

### Why Repositories Help Beginners

Repositories keep the code readable:

```text
handler:    HTTP details
service:    business rules
repository: SQL details
```

When login fails, you know where to look:

- bad JSON body: handler
- blocked user rule: service
- wrong SQL query: repository

Project task:

```go
type UserRepository interface {
    FindByEmail(ctx context.Context, email string) (*User, error)
    FindByID(ctx context.Context, userID int64) (*User, error)
}
```

Then `UserService` depends on this interface or concrete repository depending on test needs.

---

## Mastery Check

You understand this chapter when you can:
- Explain what type parameters `[T any]` do in structures.
- Create a generic container struct.
- Explain why we use connection pools rather than spawning raw TCP queries for every request.
- Execute a multi-query transaction and explain the purpose of `defer tx.Rollback()`.
