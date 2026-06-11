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

## Mastery Check

You understand this chapter when you can:
- Build paginated SQL with total count.
- Add filters without SQL injection.
- Stream a CSV response.
- Protect admin-only routes.
- Invalidate cache after content writes.
- Build a database browser without allowing arbitrary SQL execution.
