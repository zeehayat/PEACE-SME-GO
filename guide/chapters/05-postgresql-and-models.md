# Chapter 5: PostgreSQL, Migrations, and Data Modeling

## Purpose

The database is the most important compatibility layer. The Go backend must use the same PostgreSQL schema as the Flask application. In this chapter, we will study relational modeling, database connection pools, migrations, nullable values, JSONB, and transactions. We will also learn about Go's **Generics** system and implement the generic data wrappers used across the portal API layer.

---

## Foundational Concepts Explained Simply

### 1. Relational Databases & Connection Pools

:::expandable [Relational Databases & Connection Pools]
#### In-Depth Explanation
In relational databases (like PostgreSQL), structured facts are stored in tables representing entity definitions. 
* **Primary Key (PK):** A column that uniquely identifies each row (e.g. `users.id`).
* **Foreign Key (FK):** A column that references the PK of another table, creating an association.
  * **One-to-One (1:1):** One user record maps to exactly one business profile (e.g., `businesses.user_id` has a unique constraint).
  * **One-to-Many (1:N):** One business profile maps to multiple uploaded documents (e.g., `business_documents.business_id` references `businesses.id`).
* **Connection Pooling:** Instead of spending ~10-50 milliseconds establishing a new TCP connection and database handshake for every single incoming HTTP request, a connection pool (like Go's `pgxpool`) boots a preset amount of active connections (e.g., MinConns=5, MaxConns=50) at startup. When a query is run, the driver leases an available connection from the pool, runs the query, and instantly returns the connection to the pool.

#### Sandbox Program: Mock Connection Pool & Relational Registry
This sandbox simulates a thread-safe in-memory database registry and a connection pool using Go channels. It lets you simulate leasing connections, fetching related entities (1:N mapping), and handles concurrent leases:

```go
package main

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// Mock DB structures representing relational models
type User struct {
	ID    int64
	Email string
}

type Business struct {
	ID     int64
	UserID int64 // FK referencing User.ID
	Name   string
}

// Connection represents a leased database handle
type Connection struct {
	ID int
}

func (c *Connection) QueryRow(query string) string {
	return fmt.Sprintf("[Conn %d] Result for query: %s", c.ID, query)
}

// Pool maintains a channel of open connections
type Pool struct {
	conns chan *Connection
}

func NewPool(size int) *Pool {
	p := &Pool{
		conns: make(chan *Connection, size),
	}
	for i := 1; i <= size; i++ {
		p.conns <- &Connection{ID: i}
	}
	return p
}

// Acquire leases a connection or blocks until one is free or context cancels
func (p *Pool) Acquire(ctx context.Context) (*Connection, error) {
	select {
	case conn := <-p.conns:
		return conn, nil
	case <-ctx.Done():
		return nil, errors.New("context deadline exceeded waiting for connection")
	}
}

// Release returns a leased connection to the pool
func (p *Pool) Release(conn *Connection) {
	p.conns <- conn
}

func main() {
	// 1. Initialize Mock Data representing 1:1 Relational Association
	user := User{ID: 42, Email: "contact@peace.gov"}
	biz := Business{ID: 101, UserID: user.ID, Name: "Swat Organic Farms"}

	fmt.Printf("Relational Map: User %s (ID %d) owns Business %s (ID %d, FK UserID %d)\n\n",
		user.Email, user.ID, biz.Name, biz.ID, biz.UserID)

	// 2. Initialize connection pool of size 2
	pool := NewPool(2)

	// Lease 1
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	conn1, err := pool.Acquire(ctx)
	if err != nil {
		fmt.Println("Acquire 1 failed:", err)
		return
	}
	fmt.Println("Acquired:", conn1.QueryRow("SELECT * FROM businesses WHERE user_id = 42"))

	// Lease 2
	conn2, err := pool.Acquire(ctx)
	if err != nil {
		fmt.Println("Acquire 2 failed:", err)
		return
	}
	fmt.Println("Acquired:", conn2.QueryRow("SELECT * FROM users WHERE id = 42"))

	// Try Lease 3 (Should fail as pool size is 2 and both are leased)
	_, err = pool.Acquire(ctx)
	if err != nil {
		fmt.Println("Acquire 3 expectedly failed:", err)
	}

	// Release one connection and try again
	pool.Release(conn1)
	fmt.Println("Released Conn 1.")

	conn3, err := pool.Acquire(ctx)
	if err == nil {
		fmt.Println("Successfully acquired connection after release:", conn3.QueryRow("SELECT 1"))
		pool.Release(conn3)
	}
	
	pool.Release(conn2)
}
```
:::

### 2. PostgreSQL Nullable Columns

:::expandable [Handling SQL NULL in Go]
#### In-Depth Explanation
In SQL databases, any column without a `NOT NULL` constraint can store a value or `NULL` (meaning the absence of a value). In contrast, primitive Go types (like `string`, `int64`, `float64`) are value types and can never hold `nil`.
* **The Problem:** If you attempt to scan a SQL `NULL` value directly into a Go primitive `string` variable using standard database drivers, the driver will trigger a runtime error because `nil` cannot be assigned to a string.
* **The Solution:** Go provides special types inside the standard `database/sql` package (e.g. `sql.NullString`, `sql.NullInt64`, `sql.NullBool`). These are structs containing:
  1. `String` / `Int64` / `Bool`: The underlying value of that type.
  2. `Valid`: A boolean flag that is `true` if the database value was not null, and `false` if it was null.
* **JSON Considerations:** By default, serializing a `sql.NullString` to JSON returns an object like `{"String": "value", "Valid": true}`. To return a clean null (`null` or `"value"`) in HTTP responses, we must implement custom JSON marshaling for these null types.

#### Sandbox Program: Serializing & Scanning Null Values
This program demonstrates how `sql.NullString` holds SQL null states, and how we write a wrapper type to marshal clean JSON payloads for our Vue frontend:

```go
package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
)

// CleanNullString wraps sql.NullString to provide clean JSON serialization
type CleanNullString struct {
	sql.NullString
}

// MarshalJSON override converts the struct into clean JSON
func (c CleanNullString) MarshalJSON() ([]byte, error) {
	if !c.Valid {
		return json.Marshal(nil)
	}
	return json.Marshal(c.String)
}

// UnmarshalJSON override lets us decode nulls back into our struct
func (c *CleanNullString) UnmarshalJSON(data []byte) error {
	if string(data) == "null" {
		c.Valid = false
		c.String = ""
		return nil
	}
	var s string
	if err := json.Unmarshal(data, &s); err != nil {
		return err
	}
	c.String = s
	c.Valid = true
	return nil
}

type GrantApplication struct {
	ID             int64           `json:"id"`
	ApprovedAmount float64         `json:"approved_amount"`
	ApprovalReason CleanNullString `json:"approval_reason"` // Nullable in DB
}

func main() {
	// 1. Simulating an application that has NOT yet been approved (Reason is NULL)
	app1 := GrantApplication{
		ID:             1,
		ApprovedAmount: 0.0,
		ApprovalReason: CleanNullString{sql.NullString{String: "", Valid: false}},
	}

	// 2. Simulating an approved application (Reason is populated)
	app2 := GrantApplication{
		ID:             2,
		ApprovedAmount: 150000.0,
		ApprovalReason: CleanNullString{sql.NullString{String: "Approved by HFC board", Valid: true}},
	}

	// Marshal both to JSON
	json1, _ := json.Marshal(app1)
	json2, _ := json.Marshal(app2)

	fmt.Println("JSON output for App 1 (NULL reason):", string(json1))
	fmt.Println("JSON output for App 2 (Valid reason):", string(json2))

	// Decode back
	var decodedApp GrantApplication
	_ = json.Unmarshal(json1, &decodedApp)
	fmt.Printf("Decoded App 1 -> Valid: %t, Value: %q\n", 
		decodedApp.ApprovalReason.Valid, decodedApp.ApprovalReason.String)
}
```
:::

### 3. Generics in Go (Type Parameters)

:::expandable [Go Generics & Type Parameters]
#### In-Depth Explanation
Before Go 1.18, writing reusable data structures (like lists, maps, or unified API envelopes) required using the empty interface `interface{}` (which is now alias-named `any`).
* **The Problem with Interface-based Reusability:** Operating on `interface{}` values requires manual runtime type assertions (e.g. `val.(concreteType)`). If you perform an incorrect type assertion, the program crashes at runtime. This bypasses compile-time type safety.
* **The Generics Solution:** Generics allow you to parameterize structs, functions, or methods with type parameters (declared in square brackets like `[T any]`). 
  * `T` is a placeholder that is substituted with a concrete type when the struct is initialized or the function is called.
  * **Type Constraints:** You can limit what types can fill the placeholder. The constraint `any` allows any type. The constraint `comparable` restricts to types that support comparison operators (`==` and `!=`).

#### Sandbox Program: Type-Safe Generic Cache Registry
This sandbox demonstrates how to create a generic Cache container that stores any data type `T` type-safely, preventing runtime errors by enforcing strict types at compile time:

```go
package main

import (
	"fmt"
)

// CacheEntry is a generic container holding type T
type CacheEntry[T any] struct {
	Key   string
	Value T
}

// KeyValuePair registry using generics
type CacheRegistry[T any] struct {
	store map[string]CacheEntry[T]
}

func NewCacheRegistry[T any]() *CacheRegistry[T] {
	return &CacheRegistry[T]{
		store: make(map[string]CacheEntry[T]),
	}
}

func (cr *CacheRegistry[T]) Set(key string, val T) {
	cr.store[key] = CacheEntry[T]{Key: key, Value: val}
}

func (cr *CacheRegistry[T]) Get(key string) (T, bool) {
	entry, exists := cr.store[key]
	if !exists {
		var zero T // Returns the zero value of type T
		return zero, false
	}
	return entry.Value, true
}

func main() {
	// 1. Create a cache registry specifically for integer IDs
	intCache := NewCacheRegistry[int]()
	intCache.Set("active_session_count", 245)
	
	val, _ := intCache.Get("active_session_count")
	fmt.Printf("Int Cache - Value: %d (Type: %T)\n", val, val)

	// 2. Create a cache registry specifically for string user roles
	stringCache := NewCacheRegistry[string]()
	stringCache.Set("user_42_role", "admin")
	
	role, _ := stringCache.Get("user_42_role")
	fmt.Printf("String Cache - Value: %s (Type: %T)\n", role, role)

	// Note: Trying to do stringCache.Set("id", 123) would fail at compile time!
}
```
:::

### External Resources
- [Go Dev: Tutorial on Generics](https://go.dev/doc/tutorial/generics)
- [pgx Connection Pool Documentation](https://pkg.go.dev/github.com/jackc/pgx/v5/pgxpool)
- [System Design Primer: Database Connection Pools](https://github.com/donnemartin/system-design-primer#database)

---

## Phased Generics Implementation Guide

To practice generics, we will now define **all generic wrapper structures** used by the PEACE SME Grant Portal's HTTP layers.

Create a file named [internal/httpx/json.go](file:///var/www/peace-sme-go/internal/httpx/json.go) to declare these structures.

### 1. Generic API Response Wrapper
Every API response returned to the Vue frontend should share a consistent envelope layout containing success status, metadata messages, and payload data:

```go
package httpx

import (
	"encoding/json"
	"net/http"
)

// APIResponse wraps any payload type T in a standard HTTP envelope.
type APIResponse[T any] struct {
	Success bool   `json:"success"`
	Message string `json:"message,omitempty"`
	Data    T      `json:"data,omitempty"`
}

// WriteJSON writes a type-safe generic response.
func WriteJSON[T any](w http.ResponseWriter, status int, data T) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)

	envelope := APIResponse[T]{
		Success: status < 400,
		Data:    data,
	}

	_ = json.NewEncoder(w).Encode(envelope)
}
```

### 2. Generic Paginated Response Container
For administrative tables and audit report views, pages must return paginated list data along with paging counts:

```go
// PaginatedData holds list items and pagination metadata.
type PaginatedData[T any] struct {
	Items   []T   `json:"data"`
	Total   int64 `json:"total"`
	Page    int   `json:"page"`
	PerPage int   `json:"per_page"`
}

// WritePaginatedJSON renders paginated lists type-safely.
func WritePaginatedJSON[T any](w http.ResponseWriter, status int, items []T, total int64, page int, perPage int) {
	payload := PaginatedData[T]{
		Items:   items,
		Total:   total,
		Page:    page,
		PerPage: perPage,
	}
	WriteJSON(w, status, payload)
}
```

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

---

## Practical Examples

### Example: Executing a PostgreSQL Database Transaction in Go
This repository transaction updates a grant status and creates an approval log atomically:

```go
// File: internal/grant/repository.go
package grant

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct {
	db *pgxpool.Pool
}

func (r *Repository) ApproveGrant(ctx context.Context, userID int64, approver string, amount float64, reason string) error {
	tx, err := r.db.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	// Defer a rollback; if tx commits successfully first, rollback is a safe no-op.
	defer tx.Rollback(ctx)

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

	logQuery := `
		INSERT INTO grant_approval_logs (user_id, approved_by, approved_amount, reason, created_at) 
		VALUES ($1, $2, $3, $4, $5)`
	
	_, err = tx.Exec(ctx, logQuery, userID, approver, amount, reason, time.Now())
	if err != nil {
		return fmt.Errorf("failed to write audit log: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	return nil
}
```

---

## Mastery Check

You understand this chapter when you can:
- Explain what type parameters `[T any]` solve in Go.
- Declare and initialize a generic structure type-safely.
- Explain why a connection pool handles concurrent HTTP request volume better than raw single connections.
- Write a database transaction block checking row-affected results and utilizing deferred rollbacks.
