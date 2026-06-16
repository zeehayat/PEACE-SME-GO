# Chapter 11: Admin, Reports, CSV, and Database Browser

## Purpose

Admin features teach pagination, filtering, sorting, authorization, CSV streaming, and defensive SQL.

## Theoretical Background

### SQL Injection Prevention
SQL Injection occurs when untrusted user input is concatenated directly into SQL query strings, allowing attackers to manipulate queries.
- **Parametric Queries:** Always use parameters (`$1`, `$2` in PostgreSQL) rather than concatenation. The driver sends values to the database engine separately from the SQL command structure, neutralizing threats.
- **Dynamic Sort Columns:** You cannot use query parameters for SQL keywords or schema object names (like columns or tables in `ORDER BY`). To sort dynamically, use a strict **allow-list** mapping user-provided sorting keys to absolute SQL columns.

### Pagination Strategies
1. **Offset-Based Pagination (`LIMIT X OFFSET Y`):** Simple to implement and allows direct page jumping.
   - **Performance issue:** As `OFFSET` grows, the database must scan and discard all records leading up to the offset, degrading performance on millions of rows.
2. **Cursor-Based (Keyset) Pagination (`WHERE id > last_seen_id LIMIT X`):** Highly performant and works on a constant execution plan.
   - **Trade-off:** Does not allow jumping directly to page 50 without loading pages 1-49 first.

### Memory-Efficient CSV Streaming
When exporting millions of database rows to a CSV file:
- **Do not** fetch all records into an in-memory array first, as this causes RAM exhaustion.
- Instead, query the database, retrieve a row iterator, and stream rows line-by-line directly to the HTTP response writer. Using `encoding/csv` flushed periodically ensures constant memory usage.

### External Resources
- [Use The Index, Luke! - Keyset Pagination Guide](https://use-the-index-luke.com/sql/partial-results/fetch-next-page)
- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
- [Go encoding/csv package documentation](https://pkg.go.dev/encoding/csv)

---

## Admin Areas

Implement:
- Applicants list.
- Applicant detail dossier.
- Applicant reports.
- Submitted grants report.
- Approved grants report.
- Missing documents report.
- Fully verified report.
- Eligibility criteria report.
- Dashboard stats and frequency charts.
- Updates and FAQ management.
- User blocking and password reset stubs.
- Database browser.

---

## Pagination Shape

Preserve:

```json
{
  "data": [],
  "total": 0,
  "page": 1,
  "per_page": 20
}
```

The frontend depends on this shape.

---

## Filtering

Reports filter by:
- document status
- language
- gender
- search
- district
- sector
- status
- date range
- HFC status
- amount range

Build filters with parameterized SQL. Never concatenate user input directly into SQL values.

For `sort_by`, use an allow-list:

```go
var allowedSorts = map[string]string{
    "created_at": "u.created_at",
    "district": "b.business_location_district",
}
```

---

## CSV Exports

CSV export endpoints use a short-lived query token:
- `/api/admin/reports/full-applicant-profiles/csv?token=<query_token>`
- `/api/admin/reports/business-profiles/csv?token=<query_token>`

Do not expose CSV exports with no auth. Query-token auth exists because browsers have trouble attaching bearer headers to direct file downloads.

---

## Database Browser

Endpoints:
- `GET /api/admin/db-browser/tables`
- `GET /api/admin/db-browser/data/<table_name>`

Security rule:
- Table names must come from `information_schema.tables`.
- Do not let arbitrary path input become raw SQL.

Use an allow-list built from the database table list.

---

## Content Management

Updates and FAQs are simple CRUD, but they teach cache invalidation:
- Public `/api/updates` and `/api/faqs` can be cached.
- Admin writes must invalidate those cache keys.
- FAQ search can be uncached or cached by query if needed.

---

## Practical Examples

### Example 1: Defensive Dynamic SQL Builder for Paginated Reports
This example constructs a parameterized query with dynamic filters and validates sorting parameters defensively against SQL injection:

```go
// File: internal/report/repository.go
package report

import (
	"context"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

type ReportFilter struct {
	District string
	Status   string
	Page     int
	PerPage  int
	SortBy   string
}

// Allow-list for Order By clauses
var allowedSortColumns = map[string]string{
	"id":         "g.grant_id",
	"amount":     "g.grant_required",
	"created_at": "g.application_date",
}

func (r *Repository) GetGrantsReport(ctx context.Context, f ReportFilter) ([]GrantSummary, int64, error) {
	var conditions []string
	var args []interface{}
	argCounter := 1

	// Add dynamic status filter safely
	if f.Status != "" {
		conditions = append(conditions, fmt.Sprintf("g.status = $%d", argCounter))
		args = append(args, f.Status)
		argCounter++
	}

	// Add dynamic district filter safely
	if f.District != "" {
		conditions = append(conditions, fmt.Sprintf("g.domicile_district = $%d", argCounter))
		args = append(args, f.District)
		argCounter++
	}

	// Build WHERE clause
	whereClause := ""
	if len(conditions) > 0 {
		whereClause = "WHERE " + strings.Join(conditions, " AND ")
	}

	// Validate sorting inputs defensively
	sortCol, ok := allowedSortColumns[f.SortBy]
	if !ok {
		sortCol = "g.application_date" // fallback default
	}

	// Run total count query
	countQuery := fmt.Sprintf("SELECT COUNT(*) FROM grants g %s", whereClause)
	var total int64
	err := r.db.QueryRow(ctx, countQuery, args...).Scan(&total)
	if err != nil {
		return nil, 0, fmt.Errorf("failed to count records: %w", err)
	}

	// Build main query with Pagination limiters
	limit := f.PerPage
	offset := (f.Page - 1) * f.PerPage

	mainQuery := fmt.Sprintf(`
		SELECT g.grant_id, g.user_id, g.status, g.grant_required 
		FROM grants g 
		%s 
		ORDER BY %s DESC 
		LIMIT $%d OFFSET $%d`, whereClause, sortCol, argCounter, argCounter+1)

	args = append(args, limit, offset)

	// Execute mainQuery and scan rows...
	return summaries, total, nil
}
```

### Example 2: Streaming CSV Direct to Client
This example streams database records as CSV directly into an HTTP response using constant memory overhead:

```go
// File: internal/report/handler.go
package report

import (
	"encoding/csv"
	"log"
	"net/http"
	"strconv"
)

type Handler struct {
	db *pgxpool.Pool
}

func (h *Handler) StreamCSVExport(w http.ResponseWriter, r *http.Request) {
	// Set correct response headers for direct download
	w.Header().Set("Content-Type", "text/csv")
	w.Header().Set("Content-Disposition", "attachment;filename=grants_export.csv")

	// Instantiate standard Go CSV writer writing directly to the ResponseWriter
	writer := csv.NewWriter(w)
	defer writer.Flush()

	// Write CSV headers
	if err := writer.Write([]string{"Grant ID", "User ID", "Amount Requested"}); err != nil {
		log.Printf("Failed to write CSV header: %v", err)
		return
	}

	// Open connection and iterate rows row-by-row
	rows, err := h.db.Query(r.Context(), "SELECT grant_id, user_id, grant_required FROM grants")
	if err != nil {
		http.Error(w, "database read failure", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	for rows.Next() {
		var grantID, userID int64
		var amount float64
		if err := rows.Scan(&grantID, &userID, &amount); err != nil {
			log.Printf("Failed to scan row: %v", err)
			return
		}

		record := []string{
			strconv.FormatInt(grantID, 10),
			strconv.FormatInt(userID, 10),
			strconv.FormatFloat(amount, 'f', 2, 64),
		}

		if err := writer.Write(record); err != nil {
			log.Printf("Failed to write CSV row: %v", err)
			return
		}
		
		// Flush buffer to client periodically
		writer.Flush()
	}
}
```

---

## Complete Implementations

### Implementation 1: Redis Cache Layer

Before building the dashboard stats endpoint, you need a reusable cache abstraction. The `Cache` struct wraps the Redis client, handles JSON serialization automatically, and can be disabled entirely in environments that have no Redis (like a minimal local dev setup).

```go
// File: internal/cache/redis.go
package cache

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

// Cache wraps a Redis client with JSON helpers and a circuit-breaker style
// enabled flag so callers never need to nil-check the cache themselves.
type Cache struct {
	client  *redis.Client
	prefix  string
	enabled bool
}

// New creates a Cache. If enabled is false every operation becomes a no-op
// and the caller falls through to the database every time.
func New(client *redis.Client, prefix string, enabled bool) *Cache {
	return &Cache{
		client:  client,
		prefix:  prefix,
		enabled: enabled,
	}
}

func (c *Cache) key(k string) string {
	return fmt.Sprintf("%s:%s", c.prefix, k)
}

// GetJSON attempts to retrieve a cached value and JSON-unmarshal it into dst.
// Returns (true, nil) on a hit, (false, nil) on a miss, and (false, err) on a
// Redis or unmarshal error.
func (c *Cache) GetJSON(ctx context.Context, key string, dst interface{}) (bool, error) {
	if !c.enabled {
		return false, nil
	}

	val, err := c.client.Get(ctx, c.key(key)).Result()
	if errors.Is(err, redis.Nil) {
		// Cache miss — not an error, just not present.
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("cache get %q: %w", key, err)
	}

	if err := json.Unmarshal([]byte(val), dst); err != nil {
		// Treat a corrupt cache entry as a miss so the handler regenerates it.
		return false, nil
	}
	return true, nil
}

// SetJSON serializes val to JSON and stores it in Redis with the given TTL.
func (c *Cache) SetJSON(ctx context.Context, key string, val interface{}, ttl time.Duration) error {
	if !c.enabled {
		return nil
	}

	b, err := json.Marshal(val)
	if err != nil {
		return fmt.Errorf("cache marshal %q: %w", key, err)
	}

	if err := c.client.Set(ctx, c.key(key), b, ttl).Err(); err != nil {
		return fmt.Errorf("cache set %q: %w", key, err)
	}
	return nil
}

// Delete removes a key from the cache. Used for cache invalidation after writes.
func (c *Cache) Delete(ctx context.Context, key string) error {
	if !c.enabled {
		return nil
	}
	if err := c.client.Del(ctx, c.key(key)).Err(); err != nil {
		return fmt.Errorf("cache delete %q: %w", key, err)
	}
	return nil
}

// DeleteMany removes multiple keys in one round-trip using DEL with varargs.
func (c *Cache) DeleteMany(ctx context.Context, keys ...string) error {
	if !c.enabled || len(keys) == 0 {
		return nil
	}
	full := make([]string, len(keys))
	for i, k := range keys {
		full[i] = c.key(k)
	}
	if err := c.client.Del(ctx, full...).Err(); err != nil {
		return fmt.Errorf("cache delete many: %w", err)
	}
	return nil
}
```

**Why a wrapper instead of using `redis.Client` directly?**

Three reasons. First, every caller would have to repeat the `json.Marshal` / `redis.Nil` check boilerplate. Second, if you later swap Redis for Memcached you change one file, not every handler. Third, the `enabled` flag lets you write tests without spinning up Redis.

---

### Implementation 2: Admin Dashboard Stats

The dashboard stats endpoint is called every time an admin opens the portal homepage. It aggregates data across four tables. Without caching, those four queries run on every page load. The cache key `admin:dashboard_stats_v2` stores the result for 60 seconds, meaning at worst the numbers are one minute stale — an acceptable trade-off for a grant portal.

```go
// File: internal/admin/handler.go
package admin

import (
	"net/http"
	"time"

	"github.com/peace-sme/portal/internal/cache"
	"github.com/peace-sme/portal/internal/httpx"
)

// DashboardStats is the shape the Vue dashboard component expects.
// Every field must be present in the JSON even when zero, so use concrete
// types rather than pointers.
type DashboardStats struct {
	TotalUsers      int64            `json:"total_users"`
	TotalBusinesses int64            `json:"total_businesses"`
	GrantsByStatus  map[string]int64 `json:"grants_by_status"`
	HFCPendingCount int64            `json:"hfc_pending_count"`
	GeneratedAt     time.Time        `json:"generated_at"`
}

const dashboardStatsCacheKey = "admin:dashboard_stats_v2"
const dashboardStatsTTL = 60 * time.Second

// AdminService holds the database repository and cache so it can be injected
// via the app's dependency graph.
type AdminService struct {
	repo  *Repository
	cache *cache.Cache
}

func NewAdminService(repo *Repository, c *cache.Cache) *AdminService {
	return &AdminService{repo: repo, cache: c}
}

// Handler is the HTTP handler layer — it delegates to AdminService for logic.
type Handler struct {
	svc *AdminService
}

func NewHandler(svc *AdminService) *Handler {
	return &Handler{svc: svc}
}

// GetDashboardStats handles GET /api/admin/dashboard/stats
func (h *Handler) GetDashboardStats(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	// Step 1: Check Redis cache.
	var stats DashboardStats
	hit, err := h.svc.cache.GetJSON(ctx, dashboardStatsCacheKey, &stats)
	if err != nil {
		// A cache error should not break the endpoint — log and fall through.
		// In production, emit a metric here so you can alert on Redis failures.
		_ = err // replace with logger.Warn in production
	}
	if hit {
		httpx.WriteJSON(w, http.StatusOK, stats)
		return
	}

	// Step 2: Cache miss — query PostgreSQL.
	stats, err = h.svc.repo.FetchDashboardStats(ctx)
	if err != nil {
		httpx.WriteError(w, http.StatusInternalServerError, "failed to fetch dashboard stats")
		return
	}
	stats.GeneratedAt = time.Now().UTC()

	// Step 3: Populate cache for next request. Fire-and-forget is acceptable
	// here because a failure only means the next request also hits the DB.
	_ = h.svc.cache.SetJSON(ctx, dashboardStatsCacheKey, stats, dashboardStatsTTL)

	httpx.WriteJSON(w, http.StatusOK, stats)
}
```

Now the repository method that does the actual database work:

```go
// File: internal/admin/repository.go
package admin

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct {
	db *pgxpool.Pool
}

func NewRepository(db *pgxpool.Pool) *Repository {
	return &Repository{db: db}
}

// FetchDashboardStats runs four queries in sequence and assembles the result.
// For a heavily loaded system you could run these concurrently with goroutines,
// but sequential is simpler and four queries is fast enough for a 60s cache.
func (r *Repository) FetchDashboardStats(ctx context.Context) (DashboardStats, error) {
	var stats DashboardStats
	stats.GrantsByStatus = make(map[string]int64)

	// Query 1: total registered users.
	if err := r.db.QueryRow(ctx,
		`SELECT COUNT(*) FROM users`,
	).Scan(&stats.TotalUsers); err != nil {
		return stats, fmt.Errorf("count users: %w", err)
	}

	// Query 2: total businesses with a profile on record.
	if err := r.db.QueryRow(ctx,
		`SELECT COUNT(*) FROM businesses`,
	).Scan(&stats.TotalBusinesses); err != nil {
		return stats, fmt.Errorf("count businesses: %w", err)
	}

	// Query 3: grant counts broken down by status.
	// The JOIN ensures we only count grants that have a linked user and business,
	// filtering out any orphaned test rows.
	rows, err := r.db.Query(ctx, `
		SELECT g.status, COUNT(*) AS cnt
		FROM grants g
		INNER JOIN users      u ON u.user_id = g.user_id
		INNER JOIN businesses b ON b.user_id = g.user_id
		GROUP BY g.status
	`)
	if err != nil {
		return stats, fmt.Errorf("grants by status: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var status string
		var cnt int64
		if err := rows.Scan(&status, &cnt); err != nil {
			return stats, fmt.Errorf("scan grants by status: %w", err)
		}
		stats.GrantsByStatus[status] = cnt
	}
	if err := rows.Err(); err != nil {
		return stats, fmt.Errorf("iterate grants by status: %w", err)
	}

	// Query 4: HFC queue depth — grants where HFC has not yet been resolved.
	// hfc_status values that mean "pending review": 'Pending', 'InReview'.
	if err := r.db.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM grants
		WHERE hfc_status IN ('Pending', 'InReview')
	`).Scan(&stats.HFCPendingCount); err != nil {
		return stats, fmt.Errorf("hfc pending count: %w", err)
	}

	return stats, nil
}
```

**Why `v2` in the cache key?**

Cache key versioning is a simple, zero-downtime invalidation strategy. If you change the shape of `DashboardStats` (add a new field, rename one), old cached JSON will silently deserialize with the wrong shape. Bumping the suffix (`v2`, `v3`) forces all instances to miss on the next request and regenerate fresh data. You never have to flush Redis manually during a deployment.

---

### Implementation 3: Complete Paginated Applicant Report

The applicant report is the most filter-heavy endpoint in the portal. The Vue table sends up to nine different filter parameters simultaneously. Building the WHERE clause one condition at a time using an `argCounter` pattern keeps the code safe and readable.

First, define the data shapes:

```go
// File: internal/admin/applicant_report.go
package admin

import "time"

// ApplicantFilter holds every filter the Vue report table can send.
// All fields are optional — zero values mean "no filter applied".
type ApplicantFilter struct {
	// Document status: "Pending", "Verified", "Rejected"
	DocStatus string `json:"doc_status"`
	// Preferred language: "en", "ur"
	Language string `json:"language"`
	// Gender: "Male", "Female", "Other"
	Gender string `json:"gender"`
	// Free-text search across name, email, CNIC
	Search string `json:"search"`
	// Business district from the allowed district list
	District string `json:"district"`
	// Business sector: "Agriculture", "Manufacturing", etc.
	Sector string `json:"sector"`
	// Grant application status
	Status string `json:"status"`
	// HFC risk level: "LOW", "MEDIUM", "HIGH", "CRITICAL"
	HFCStatus string `json:"hfc_status"`
	// Sort column — validated against allowedApplicantSorts
	SortBy string `json:"sort_by"`
	// Sort direction — validated to "ASC" or "DESC" only
	SortDir string `json:"sort_dir"`
	// Pagination
	Page    int `json:"page"`
	PerPage int `json:"per_page"`
}

// ApplicantRow is the shape returned for each row in the applicant report table.
// It is a denormalized read model — data from users, businesses, and grants
// joined into a single flat struct the Vue component can render directly.
type ApplicantRow struct {
	UserID          int64      `json:"user_id"`
	FullName        string     `json:"full_name"`
	CNIC            string     `json:"cnic"`
	EmailAddress    string     `json:"email_address"`
	MobileNo        string     `json:"mobile_no"`
	Gender          string     `json:"gender"`
	Language        string     `json:"language"`
	District        string     `json:"district"`
	BusinessName    string     `json:"business_name"`
	Sector          string     `json:"sector"`
	GrantStatus     string     `json:"grant_status"`
	GrantRequired   float64    `json:"grant_required"`
	DocStatus       string     `json:"doc_status"`
	HFCStatus       string     `json:"hfc_status"`
	HFCScore        *int       `json:"hfc_score"`
	ApplicationDate *time.Time `json:"application_date"`
	CreatedAt       time.Time  `json:"created_at"`
}
```

Now the repository method. Read through the comments — they explain the pattern step by step:

```go
// File: internal/admin/applicant_report_repository.go
package admin

import (
	"context"
	"fmt"
	"strings"
)

// allowedApplicantSorts maps the safe keys the frontend may send to the actual
// SQL column expressions. Any key not in this map is silently replaced with
// the default. This is the ONLY protection needed against ORDER BY injection.
var allowedApplicantSorts = map[string]string{
	"created_at":       "u.created_at",
	"full_name":        "u.full_name",
	"district":         "b.business_location_district",
	"grant_required":   "g.grant_required",
	"hfc_score":        "g.hfc_score",
	"application_date": "g.application_date",
}

// ApplicantReport returns a page of applicant rows and the total matching count.
func (r *Repository) ApplicantReport(ctx context.Context, f ApplicantFilter) ([]ApplicantRow, int64, error) {
	// Sanitize pagination inputs so a caller can never request negative pages.
	if f.Page < 1 {
		f.Page = 1
	}
	if f.PerPage < 1 || f.PerPage > 200 {
		f.PerPage = 20
	}

	// --- Build WHERE clause ---
	// We accumulate SQL fragments and positional args in parallel slices so
	// each fragment can reference $n which is incremented as we go.
	var conditions []string
	var args []interface{}
	n := 1 // next positional parameter number

	if f.DocStatus != "" {
		conditions = append(conditions, fmt.Sprintf("u.doc_status = $%d", n))
		args = append(args, f.DocStatus)
		n++
	}
	if f.Language != "" {
		conditions = append(conditions, fmt.Sprintf("u.language = $%d", n))
		args = append(args, f.Language)
		n++
	}
	if f.Gender != "" {
		conditions = append(conditions, fmt.Sprintf("u.gender = $%d", n))
		args = append(args, f.Gender)
		n++
	}
	if f.District != "" {
		conditions = append(conditions, fmt.Sprintf("b.business_location_district = $%d", n))
		args = append(args, f.District)
		n++
	}
	if f.Sector != "" {
		conditions = append(conditions, fmt.Sprintf("b.business_sector = $%d", n))
		args = append(args, f.Sector)
		n++
	}
	if f.Status != "" {
		conditions = append(conditions, fmt.Sprintf("g.status = $%d", n))
		args = append(args, f.Status)
		n++
	}
	if f.HFCStatus != "" {
		conditions = append(conditions, fmt.Sprintf("g.hfc_status = $%d", n))
		args = append(args, f.HFCStatus)
		n++
	}
	// Search: free-text across name, email, and CNIC.
	// ILIKE is case-insensitive LIKE in PostgreSQL.
	// The % wildcards are added here in Go, not in the SQL literal.
	if f.Search != "" {
		searchPattern := "%" + f.Search + "%"
		conditions = append(conditions, fmt.Sprintf(
			"(u.full_name ILIKE $%d OR u.email_address ILIKE $%d OR u.cnic ILIKE $%d)",
			n, n, n,
		))
		args = append(args, searchPattern)
		n++
	}

	whereClause := ""
	if len(conditions) > 0 {
		whereClause = "WHERE " + strings.Join(conditions, " AND ")
	}

	// --- Validate ORDER BY ---
	sortCol, ok := allowedApplicantSorts[f.SortBy]
	if !ok {
		sortCol = "u.created_at"
	}
	sortDir := "DESC"
	if strings.ToUpper(f.SortDir) == "ASC" {
		sortDir = "ASC"
	}

	// --- COUNT query runs first ---
	// Re-use the same args slice (without LIMIT/OFFSET) for an efficient count.
	countSQL := fmt.Sprintf(`
		SELECT COUNT(*)
		FROM users u
		INNER JOIN businesses b ON b.user_id = u.user_id
		LEFT  JOIN grants     g ON g.user_id = u.user_id
		%s
	`, whereClause)

	var total int64
	if err := r.db.QueryRow(ctx, countSQL, args...).Scan(&total); err != nil {
		return nil, 0, fmt.Errorf("applicant report count: %w", err)
	}

	// Short-circuit: if there are no results we can skip the data query.
	if total == 0 {
		return []ApplicantRow{}, 0, nil
	}

	// --- Data query ---
	// LIMIT and OFFSET are appended as the last two positional parameters
	// so they do not collide with filter args above.
	offset := (f.Page - 1) * f.PerPage
	args = append(args, f.PerPage, offset)

	dataSQL := fmt.Sprintf(`
		SELECT
			u.user_id,
			u.full_name,
			u.cnic,
			u.email_address,
			u.mobile_no,
			u.gender,
			u.language,
			b.business_location_district,
			b.business_name,
			b.business_sector,
			COALESCE(g.status,          '')   AS grant_status,
			COALESCE(g.grant_required,   0)   AS grant_required,
			COALESCE(u.doc_status,      '')   AS doc_status,
			COALESCE(g.hfc_status,      '')   AS hfc_status,
			g.hfc_score,
			g.application_date,
			u.created_at
		FROM users u
		INNER JOIN businesses b ON b.user_id = u.user_id
		LEFT  JOIN grants     g ON g.user_id = u.user_id
		%s
		ORDER BY %s %s
		LIMIT $%d OFFSET $%d
	`, whereClause, sortCol, sortDir, n, n+1)

	rows, err := r.db.Query(ctx, dataSQL, args...)
	if err != nil {
		return nil, 0, fmt.Errorf("applicant report query: %w", err)
	}
	defer rows.Close()

	var results []ApplicantRow
	for rows.Next() {
		var row ApplicantRow
		if err := rows.Scan(
			&row.UserID,
			&row.FullName,
			&row.CNIC,
			&row.EmailAddress,
			&row.MobileNo,
			&row.Gender,
			&row.Language,
			&row.District,
			&row.BusinessName,
			&row.Sector,
			&row.GrantStatus,
			&row.GrantRequired,
			&row.DocStatus,
			&row.HFCStatus,
			&row.HFCScore,
			&row.ApplicationDate,
			&row.CreatedAt,
		); err != nil {
			return nil, 0, fmt.Errorf("scan applicant row: %w", err)
		}
		results = append(results, row)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, fmt.Errorf("iterate applicant rows: %w", err)
	}

	return results, total, nil
}
```

The handler is thin — it parses query parameters, calls the repository, and returns the standard paginated envelope:

```go
// File: internal/admin/applicant_report_handler.go
package admin

import (
	"net/http"
	"strconv"

	"github.com/peace-sme/portal/internal/httpx"
)

func (h *Handler) GetApplicantReport(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()

	page, _ := strconv.Atoi(q.Get("page"))
	perPage, _ := strconv.Atoi(q.Get("per_page"))

	f := ApplicantFilter{
		DocStatus: q.Get("doc_status"),
		Language:  q.Get("language"),
		Gender:    q.Get("gender"),
		Search:    q.Get("search"),
		District:  q.Get("district"),
		Sector:    q.Get("sector"),
		Status:    q.Get("status"),
		HFCStatus: q.Get("hfc_status"),
		SortBy:    q.Get("sort_by"),
		SortDir:   q.Get("sort_dir"),
		Page:      page,
		PerPage:   perPage,
	}

	rows, total, err := h.svc.repo.ApplicantReport(r.Context(), f)
	if err != nil {
		httpx.WriteError(w, http.StatusInternalServerError, "report query failed")
		return
	}

	httpx.WriteJSON(w, http.StatusOK, map[string]interface{}{
		"data":     rows,
		"total":    total,
		"page":     f.Page,
		"per_page": f.PerPage,
	})
}
```

**Why `LEFT JOIN` for grants but `INNER JOIN` for businesses?**

An applicant exists in the `users` table as soon as they register. They only appear in `businesses` after completing the business profile step, and only in `grants` after submitting a grant application. The `INNER JOIN businesses` means the report only shows users who have reached at least the business profile step — the minimum to be a real applicant. The `LEFT JOIN grants` means a user with a business profile but no submitted grant still appears in the report, with `NULL` grant fields coalesced to empty defaults.

---

### Implementation 4: Cache Invalidation on Content Writes

Every time an admin creates, updates, or deletes an Update or FAQ, the public cache for those endpoints must be cleared. This is the most common source of "why is my change not showing up?" bugs.

Here is the full FAQ CRUD service showing the invalidation pattern:

```go
// File: internal/admin/faq_service.go
package admin

import (
	"context"
	"fmt"
	"time"

	"github.com/peace-sme/portal/internal/cache"
)

// These are the keys the public-facing /api/faqs endpoint caches under.
// They must match exactly what the public handler uses when it calls SetJSON.
const (
	publicFAQListCacheKey = "public:faqs:list"
	// Search keys include the query param so they are not invalidated explicitly.
	// Short TTLs (30s) handle staleness for search results instead.
)

type FAQ struct {
	FAQID     int64     `json:"faq_id"`
	Question  string    `json:"question"`
	Keywords  string    `json:"keywords"`
	Answer    string    `json:"answer"`
	IsActive  bool      `json:"is_active"`
	SortOrder int       `json:"sort_order"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type FAQService struct {
	repo  *FAQRepository
	cache *cache.Cache
}

func NewFAQService(repo *FAQRepository, c *cache.Cache) *FAQService {
	return &FAQService{repo: repo, cache: c}
}

// CreateFAQ inserts a new FAQ and clears the public list cache.
func (s *FAQService) CreateFAQ(ctx context.Context, faq FAQ) (FAQ, error) {
	created, err := s.repo.InsertFAQ(ctx, faq)
	if err != nil {
		return FAQ{}, fmt.Errorf("insert faq: %w", err)
	}

	// Invalidate public list. Search results depend on the list so they are
	// also stale — we cannot predict every search query key, so we rely on
	// short TTLs for search caches (30s) rather than explicit invalidation.
	if err := s.cache.Delete(ctx, publicFAQListCacheKey); err != nil {
		// Cache invalidation failure is non-fatal. The old data will expire
		// on its TTL. Log and continue.
		_ = err
	}

	return created, nil
}

// UpdateFAQ updates an existing FAQ and clears the public list cache.
func (s *FAQService) UpdateFAQ(ctx context.Context, faqID int64, faq FAQ) (FAQ, error) {
	updated, err := s.repo.UpdateFAQ(ctx, faqID, faq)
	if err != nil {
		return FAQ{}, fmt.Errorf("update faq: %w", err)
	}

	_ = s.cache.Delete(ctx, publicFAQListCacheKey)
	return updated, nil
}

// DeleteFAQ removes a FAQ and clears the public list cache.
func (s *FAQService) DeleteFAQ(ctx context.Context, faqID int64) error {
	if err := s.repo.DeleteFAQ(ctx, faqID); err != nil {
		return fmt.Errorf("delete faq: %w", err)
	}

	_ = s.cache.Delete(ctx, publicFAQListCacheKey)
	return nil
}
```

The same pattern applies to the Updates CRUD — replace `FAQ` with `Update` and the cache key with `public:updates:list`. This is deliberately repetitive rather than clever: it is immediately obvious what each method does and what it invalidates.

---

### Implementation 5: Complete FAQ Search

The SRS requires fuzzy search across the question, keywords, and answer fields. PostgreSQL's `ILIKE` operator gives case-insensitive substring matching without requiring full-text search configuration. Relevance sorting is done by ordering on a `CASE` expression that assigns priority 1 to question matches, 2 to keyword matches, and 3 to answer matches.

```go
// File: internal/faq/repository.go
package faq

import (
	"context"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

type FAQ struct {
	FAQID     int64  `json:"faq_id"`
	Question  string `json:"question"`
	Keywords  string `json:"keywords"`
	Answer    string `json:"answer"`
	SortOrder int    `json:"sort_order"`
}

type Repository struct {
	db *pgxpool.Pool
}

func NewRepository(db *pgxpool.Pool) *Repository {
	return &Repository{db: db}
}

// SearchFAQs performs a case-insensitive substring search across question,
// keywords, and answer, and returns results ordered by relevance then sort_order.
func (r *Repository) SearchFAQs(ctx context.Context, query string) ([]FAQ, error) {
	if strings.TrimSpace(query) == "" {
		return r.ListActive(ctx)
	}

	// Wrap the search term in % wildcards once here in Go.
	// The same parameter is reused three times in the SQL ($1).
	pattern := "%" + query + "%"

	// The CASE expression in ORDER BY produces a relevance score:
	//   1 = match in question (highest priority — user is searching for this)
	//   2 = match in keywords (good — intentionally tagged)
	//   3 = match in answer  (lowest — large text, noisier match)
	// Rows not matching any of the three fall through to priority 4
	// (which cannot happen given the WHERE clause, but makes the CASE exhaustive).
	sql := `
		SELECT
			faq_id,
			question,
			keywords,
			answer,
			sort_order
		FROM faqs
		WHERE
			is_active = true
			AND (
				question ILIKE $1
				OR keywords ILIKE $1
				OR answer   ILIKE $1
			)
		ORDER BY
			CASE
				WHEN question  ILIKE $1 THEN 1
				WHEN keywords  ILIKE $1 THEN 2
				WHEN answer    ILIKE $1 THEN 3
				ELSE 4
			END ASC,
			sort_order ASC
	`

	rows, err := r.db.Query(ctx, sql, pattern)
	if err != nil {
		return nil, fmt.Errorf("faq search query: %w", err)
	}
	defer rows.Close()

	var results []FAQ
	for rows.Next() {
		var f FAQ
		if err := rows.Scan(&f.FAQID, &f.Question, &f.Keywords, &f.Answer, &f.SortOrder); err != nil {
			return nil, fmt.Errorf("scan faq row: %w", err)
		}
		results = append(results, f)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate faq rows: %w", err)
	}

	return results, nil
}

// ListActive returns all active FAQs in sort_order, used when no search query
// is present.
func (r *Repository) ListActive(ctx context.Context) ([]FAQ, error) {
	rows, err := r.db.Query(ctx,
		`SELECT faq_id, question, keywords, answer, sort_order
		 FROM faqs
		 WHERE is_active = true
		 ORDER BY sort_order ASC`,
	)
	if err != nil {
		return nil, fmt.Errorf("list active faqs: %w", err)
	}
	defer rows.Close()

	var results []FAQ
	for rows.Next() {
		var f FAQ
		if err := rows.Scan(&f.FAQID, &f.Question, &f.Keywords, &f.Answer, &f.SortOrder); err != nil {
			return nil, fmt.Errorf("scan faq row: %w", err)
		}
		results = append(results, f)
	}
	return results, rows.Err()
}
```

The public handler reads the `?q=` query parameter and serves cached results for the empty-query (list) case:

```go
// File: internal/faq/handler.go
package faq

import (
	"net/http"
	"time"

	"github.com/peace-sme/portal/internal/cache"
	"github.com/peace-sme/portal/internal/httpx"
)

type Handler struct {
	repo  *Repository
	cache *cache.Cache
}

func NewHandler(repo *Repository, c *cache.Cache) *Handler {
	return &Handler{repo: repo, cache: c}
}

// GetFAQs handles GET /api/faqs?q=<optional search term>
func (h *Handler) GetFAQs(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	query := r.URL.Query().Get("q")

	// For empty queries, try the cache first.
	if query == "" {
		var cached []FAQ
		if hit, _ := h.cache.GetJSON(ctx, "public:faqs:list", &cached); hit {
			httpx.WriteJSON(w, http.StatusOK, cached)
			return
		}
	}

	faqs, err := h.repo.SearchFAQs(ctx, query)
	if err != nil {
		httpx.WriteError(w, http.StatusInternalServerError, "failed to fetch FAQs")
		return
	}

	// Cache the full list (empty query) for 5 minutes.
	if query == "" {
		_ = h.cache.SetJSON(ctx, "public:faqs:list", faqs, 5*time.Minute)
	}

	httpx.WriteJSON(w, http.StatusOK, faqs)
}
```

**Why not cache per-query?**

Caching search results per query (`"public:faqs:search:"+query`) creates unbounded cache entries — every unique search string becomes a key. For an FAQ list that is at most a few hundred rows, querying the database on every search is fast enough. Per-query caching only pays off when the search is expensive (full-text index, large tables, or computed scores).

---

### Implementation 6: Database Browser with SQL Injection Protection

The database browser lets admins inspect table contents. The `<table_name>` comes from the URL path, which means a crafty user could send `; DROP TABLE users; --` as the table name if you concatenate it directly into SQL. The protection is two-step: fetch the real table list from `information_schema`, then check the user's input against that list before using it.

```go
// File: internal/admin/db_browser.go
package admin

import (
	"fmt"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"
	"github.com/peace-sme/portal/internal/httpx"
)

// GetDBTables returns the list of tables visible in the current schema.
// This same list is used by GetDBTableData for validation.
func (h *Handler) GetDBTables(w http.ResponseWriter, r *http.Request) {
	tables, err := h.svc.repo.ListTables(r.Context())
	if err != nil {
		httpx.WriteError(w, http.StatusInternalServerError, "failed to list tables")
		return
	}
	httpx.WriteJSON(w, http.StatusOK, map[string]interface{}{"tables": tables})
}

// GetDBTableData handles GET /api/admin/db-browser/data/<table_name>
func (h *Handler) GetDBTableData(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	rawName := chi.URLParam(r, "table_name")

	// Step 1: Fetch the real table list from information_schema.
	// This is a live query — not a hardcoded list — so it stays accurate as
	// migrations add or remove tables.
	allowedTables, err := h.svc.repo.ListTables(ctx)
	if err != nil {
		httpx.WriteError(w, http.StatusInternalServerError, "failed to load table list")
		return
	}

	// Step 2: Build a set for O(1) lookup.
	tableSet := make(map[string]bool, len(allowedTables))
	for _, t := range allowedTables {
		tableSet[t] = true
	}

	// Step 3: Validate the user's input against the set.
	if !tableSet[rawName] {
		httpx.WriteError(w, http.StatusNotFound, fmt.Sprintf("table %q not found", rawName))
		return
	}

	// Step 4: Use the validated name from the allowlist in the query.
	// rawName was found in allowedTables which came from information_schema,
	// so it is a real table identifier. We cannot use a query parameter for a
	// table name in SQL syntax, but interpolation is safe here because we have
	// just proven the name originates from the database catalogue itself.
	page, _ := strconv.Atoi(r.URL.Query().Get("page"))
	if page < 1 {
		page = 1
	}
	perPage := 50
	offset := (page - 1) * perPage

	// #nosec G201 — rawName is validated against information_schema above.
	query := fmt.Sprintf(
		"SELECT * FROM %s LIMIT $1 OFFSET $2",
		rawName,
	)

	rows, err := h.svc.repo.db.Query(ctx, query, perPage, offset)
	if err != nil {
		httpx.WriteError(w, http.StatusInternalServerError, "query failed")
		return
	}
	defer rows.Close()

	// pgx provides field descriptions so we can build dynamic column names
	// without knowing the schema at compile time.
	fields := rows.FieldDescriptions()
	colNames := make([]string, len(fields))
	for i, f := range fields {
		colNames[i] = string(f.Name)
	}

	var result []map[string]interface{}
	for rows.Next() {
		vals, err := rows.Values()
		if err != nil {
			httpx.WriteError(w, http.StatusInternalServerError, "scan failed")
			return
		}
		row := make(map[string]interface{}, len(colNames))
		for i, col := range colNames {
			row[col] = vals[i]
		}
		result = append(result, row)
	}

	httpx.WriteJSON(w, http.StatusOK, map[string]interface{}{
		"table":   rawName,
		"columns": colNames,
		"data":    result,
		"page":    page,
	})
}
```

The repository method that queries `information_schema`:

```go
// File: internal/admin/db_browser_repository.go
package admin

import (
	"context"
	"fmt"
)

// ListTables returns all user-visible table names in the 'public' schema.
// We scope to table_schema = 'public' to exclude PostgreSQL system tables
// and any future additional schemas.
func (r *Repository) ListTables(ctx context.Context) ([]string, error) {
	rows, err := r.db.Query(ctx, `
		SELECT table_name
		FROM information_schema.tables
		WHERE table_schema = 'public'
		  AND table_type   = 'BASE TABLE'
		ORDER BY table_name ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("list tables: %w", err)
	}
	defer rows.Close()

	var tables []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, fmt.Errorf("scan table name: %w", err)
		}
		tables = append(tables, name)
	}
	return tables, rows.Err()
}
```

**The `#nosec G201` comment** suppresses the `gosec` static analysis warning about string formatting in SQL. The comment justification is mandatory and explains to any future reader why this specific interpolation is safe. Never add `#nosec` without the explanation.

---

## Mastery Check

You understand this chapter when you can:
- Build paginated SQL with total count, including the short-circuit on `total == 0`.
- Add up to nine filters to a query without SQL injection, using the `argCounter` pattern.
- Stream a CSV response using `encoding/csv` and constant memory.
- Explain why `LEFT JOIN grants` is used instead of `INNER JOIN` in the applicant report.
- Implement a `Cache` struct with `GetJSON`, `SetJSON`, `Delete`, and explain why the `enabled` flag exists.
- Describe what cache key versioning (`_v2`) solves and when to bump the version.
- Build a database browser that validates table names against `information_schema` before interpolation.
- Explain why per-query FAQ search caching creates an unbounded cache and when it is worth doing anyway.
- Protect admin-only routes via middleware and explain why the DB browser is an admin-only endpoint even though it looks read-only.
- Write a FAQ CRUD service that invalidates the correct public cache key on every mutating operation.
