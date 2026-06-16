# Software Requirements Specification (SRS)
## PEACE SME Grant Portal — Go Backend Rewrite

**Version:** 1.0  
**Date:** 2026-06-15  
**Source Document:** `description.md`  
**Prepared for:** Go rewrite engineering team

---

## Table of Contents

1. Introduction
2. System Overview
3. Technology Stack (Target)
4. Architecture Requirements
5. Database Requirements
6. Authentication & Security Requirements
7. Functional Requirements — User APIs
8. Functional Requirements — Admin APIs
9. Functional Requirements — Committee APIs
10. Functional Requirements — Public APIs
11. Background Job Requirements
12. External Integration Requirements
13. Caching Requirements
14. Non-Functional Requirements
15. Migration Requirements
16. API Contract Constraints
17. Frontend Compatibility Constraints

---

## 1. Introduction

### 1.1 Purpose

This document specifies the complete requirements for rewriting the **PEACE SME Grant Portal** backend from Python 3.12/Flask to **Go**. The frontend (Vue 3 SPA) will remain unchanged. The Go backend must serve identical JSON at identical paths so no frontend modification is needed.

### 1.2 Scope

The Go backend must implement:
- All 80+ REST API endpoints currently served by `app.py`
- JWT authentication for three actor types: User, Admin, Committee Member
- PostgreSQL 15 data access using the exact existing schema
- Redis caching and RQ-compatible background job queuing
- S3-compatible file storage (presigned URLs, object management)
- Brevo email API integration
- Geo-blocking and concurrent session rate limiting middleware

### 1.3 Out of Scope

- The Vue.js frontend (unchanged)
- The existing PostgreSQL schema (unchanged — Go backend connects to same DB)
- Docker Compose infrastructure (unchanged)
- The Go stub in `backend-go/` (to be replaced entirely)

---

## 2. System Overview

The portal serves three categories of users:

| Actor | Auth Method | Token Key | Session |
|---|---|---|---|
| SME Applicant | Email + password → JWT | `userToken` (localStorage) | 24 hours |
| Admin | Username + password → JWT | `adminToken` (localStorage) | 8 hours |
| Committee Member | Username + password → JWT | `committeeToken` (localStorage) | 8 hours |

**Application domain:** Pakistan-based SME grant management for SRSP (Sarhad Rural Support Programme), Khyber Pakhtunkhwa province.

**Current Python backend URL:** `http://localhost:5000` (internal Docker)  
**Go backend must bind to:** `0.0.0.0:5000` (same port, same Docker network)

---

## 3. Technology Stack (Target)

| Component | Requirement |
|---|---|
| Language | Go 1.21+ |
| HTTP framework | `net/http` stdlib or `chi` / `echo` (team choice) |
| PostgreSQL driver | `pgx/v5` with connection pooling |
| Redis client | `go-redis/v9` |
| JWT | `golang-jwt/jwt/v5` — HS256 only |
| Password hashing | `golang.org/x/crypto/bcrypt` |
| S3 | `aws-sdk-go-v2` with path-style addressing |
| Email | Brevo REST API via HTTP client |
| Background jobs | Redis-based queue (compatible with Python RQ queue format OR dedicated Go worker) |
| PDF generation | `go-pdf/fpdf` or `jung-kurt/gofpdf` |
| Config | Environment variables (same `.env` file as Python) |

---

## 4. Architecture Requirements

### 4.1 Request Pipeline

Every incoming request must pass through middleware in this exact order:

```
1. CORS headers
2. apply_geo_block()    — IP country check (skip for /admin/* paths)
3. apply_access_control() — Redis concurrent session limiter (skip for /admin/*)
4. authenticate_token()   — JWT verification (skip for unprotected endpoints)
5. Route handler
```

### 4.2 Unprotected Endpoints (No Auth Required)

The following paths must skip JWT verification:

```
POST /api/register
POST /api/login
GET  /api/pre-registration
POST /api/pre-registration
POST /api/admin/login
POST /api/committee/login
POST /api/forgot-password
POST /api/reset-password
GET  /api/system/access-status
GET  /api/updates
GET  /api/faqs
GET  /api/faqs/search
GET  /api/go-test
```

### 4.3 CORS

Allow all origins (`*`) on `/api/*` routes. Handle `OPTIONS` preflight on every endpoint — return 200 with empty body.

### 4.4 Project Structure

```
backend-go/
├── cmd/server/main.go          Entry point, server startup
├── internal/
│   ├── auth/                   JWT encode/decode, bcrypt helpers
│   ├── db/                     pgx pool, connection helpers
│   ├── cache/                  Redis client, get/set/delete helpers
│   ├── s3/                     S3 client, presigned URL generation
│   ├── mail/                   Brevo API client
│   ├── middleware/             Geo-block, rate-limit, auth token middleware
│   ├── user/                   user_service equivalents
│   ├── business/               business profile handlers
│   ├── grant/                  grant_service equivalents
│   ├── report/                 report_service equivalents (inc. HTML bulk export)
│   ├── admin/                  admin_service equivalents
│   ├── committee/              committee_service equivalents
│   ├── hfc/                    hfc_service + hfc_admin_service
│   ├── status/                 status_service equivalents
│   └── content/                updates, FAQs
├── migrations/                 SQL files (same as init_db.py)
└── Dockerfile
```

---

## 5. Database Requirements

### 5.1 Connection

- Use `pgx/v5` connection pool
- Min connections: `DB_POOL_MIN_CONN` (env, default 2)
- Max connections: `DB_POOL_MAX_CONN` (env, default 40)
- Host: `POSTGRES_HOST`, Port: `POSTGRES_PORT`, DB: `POSTGRES_DB`
- User: `POSTGRES_USER`, Password: `POSTGRES_PASSWORD`

### 5.2 Schema

The Go backend connects to the **existing PostgreSQL 15 database**. The schema must not be modified by the Go backend. All 27 migrations have already been applied by `init_db.py`. The Go backend is read/write only — no schema migrations.

### 5.3 Tables (all existing)

| Table | Primary Key | Notes |
|---|---|---|
| `users` | `user_id` SERIAL | `email_address` UNIQUE, `cnic` indexed |
| `businesses` | `business_id` SERIAL | `user_id` UNIQUE FK |
| `grants` | `grant_id` SERIAL | `user_id` UNIQUE FK |
| `business_documents` | `document_id` SERIAL | FK: user_id, business_id |
| `grant_media` | `media_id` SERIAL | FK: user_id, business_id, grant_id |
| `grant_approval_logs` | `approval_log_id` SERIAL | FK: grant_id, user_id |
| `grant_access_whitelist` | `access_id` SERIAL | `user_id` UNIQUE FK |
| `applicant_status` | `status_id` SERIAL | `user_id` UNIQUE FK, CHECK constraint |
| `hfc_evaluations` | `evaluation_id` SERIAL | FK: user_id, grant_id |
| `hfc_review_actions` | `action_id` SERIAL | FK: user_id, grant_id |
| `hfc_rule_config` | `rule_code` VARCHAR PK | |
| `initial_registrations` | `cnic` VARCHAR PK | |
| `updates` | `update_id` SERIAL | |
| `faqs` | `faq_id` SERIAL | |
| `schema_migrations` | `version` INTEGER PK | |
| `admin_users` | `admin_id` SERIAL | Migration 24 |
| `committee_members` | `member_id` SERIAL | Migration 25; `signature_url` added in M27 |
| `committee_reviews` | `review_id` SERIAL | Migration 26; UNIQUE(user_id, member_id) |

### 5.4 JSONB Field Handling

Many columns store JSON arrays or objects as `TEXT` or `JSONB`. The Go backend must:
- Deserialise JSONB columns to `[]interface{}` or typed structs when reading
- Re-serialise to JSON string when writing
- Preserve `null` vs `[]` distinction (empty arrays must be stored as `'[]'::jsonb`, not NULL)

Key JSONB columns:
```
grants.expression_of_interest   TEXT (JSON array)
grants.business_type            JSONB (array)
grants.tax_registration_status  JSONB (array)
grants.financed_items           JSONB (array of objects)
grants.employment_grid          JSONB (object)
grants.srsp_relatives           JSONB (array of objects)
businesses.business_registration_authority  JSONB (array)
committee_reviews.supporting_documents      JSONB (array of objects)
applicant_status.supporting_documents       JSONB (array)
```

---

## 6. Authentication & Security Requirements

### 6.1 JWT Specification

**Algorithm:** HS256 only  
**Secret:** `JWT_SECRET_KEY` environment variable (default: `"Supersecret"`)  
**Tokens issued by Go must be verifiable by the Vue frontend using the same secret.**

#### User JWT Payload
```json
{ "user_id": 42, "exp": 1234567890 }
```
- Expiry: 24 hours from issue
- Stored by frontend as `localStorage.userToken`

#### Admin JWT Payload
```json
{
  "admin_username": "admin1",
  "role": "admin",
  "is_admin": true,
  "is_approver": false,
  "exp": 1234567890
}
```
- Expiry: 8 hours from issue
- Stored as `localStorage.adminToken`

#### Committee Member JWT Payload
```json
{
  "member_id": 3,
  "username": "sara_committee",
  "full_name": "Sara Bibi",
  "role": "committee",
  "exp": 1234567890
}
```
- Expiry: 8 hours from issue
- Stored as `localStorage.committeeToken`

### 6.2 Token Verification Middleware

On every protected request:
1. Read `Authorization: Bearer <token>` header
2. If missing, check `?token=<token>` query param (for CSV download endpoints)
3. Decode JWT with HS256
4. Determine actor type from payload:
    - `role == "committee"` → set `ctx.MemberID`, `ctx.IsCommittee = true`
    - `is_admin == true` → set `ctx.IsAdmin`, `ctx.AdminUsername`, `ctx.IsApprover`
    - else → set `ctx.UserID` (must be non-zero, else 401)
5. Inject into request context

### 6.3 Admin Password Verification

Admin passwords are stored as bcrypt hashes in either:
1. `ADMIN_USERS_JSON` environment variable (array of `{username, password_hash, role, can_approve_grants}`)
2. `admin_users` DB table (Migration 24)

Check DB table first; fall back to env var if DB table is empty.

### 6.4 Geo-Blocking

- Read header `CF-IPCountry` or `X-Country-Code`
- If `GEO_BLOCK_ENABLED=1` and country code not in `ALLOWED_COUNTRY_CODES` → return 403
- Skip for paths starting with `/api/admin/`
- `ALLOWED_COUNTRY_CODES` is comma-separated (e.g. `"PK"`)

### 6.5 Concurrent Session Rate Limiting

- Only when `ACCESS_CONTROL_ENABLED=1`
- On each request: SETEX `peace_sme:session:<session_id>` with TTL = `ACCESS_SLOT_TTL_SEC` (default 90s)
- Count active keys matching prefix `peace_sme:session:*`
- If count ≥ `MAX_ACTIVE_APPLICANTS` (default 300) → return 429 JSON `{"message": "...", "in_queue": true}`
- Session ID derived from IP + User-Agent fingerprint
- Skip for `/api/admin/*` paths

---

## 7. Functional Requirements — User APIs

All require `Authorization: Bearer <userToken>` unless marked public.

### 7.1 Pre-Registration Check

```
GET/POST /api/pre-registration
```
- **Currently CLOSED** — always return 403 `{"message": "Registration is currently closed."}`
- Behaviour is toggled by `GRANT_APPLICATION_OPEN` env var (0 = closed)

### 7.2 User Registration

```
POST /api/register
Body: {email_address, password, first_name, last_name, cnic, language, gender, mobile_no, whatsapp_number, terms_accepted}
```
- **Currently CLOSED** — return 403
- When open: INSERT into `users`, bcrypt hash password, enqueue welcome email, return 201

### 7.3 User Login

```
POST /api/login
Body: {email_address, password}
Response: {token: JWT, user_id, language}
```
- Look up user by `email_address`
- bcrypt verify password
- Check `users.status != 'blocked'` — if blocked return 403
- Return 24h JWT on success

### 7.4 User Profile

```
GET /api/user/profile
Response: {user_id, email_address, first_name, last_name, cnic, language, gender, mobile_no, ...}
```
- Return full `users` row for authenticated `user_id`
- Join with business name if exists

### 7.5 Business Profile

```
GET  /api/business      → return business row for user_id or empty object
POST /api/business      → INSERT new business profile
PUT  /api/business      → UPDATE existing business profile
```

**Validation:**
- `business_location_district` must be one of: `Swat`, `Shangla`, `Upper Dir`, `Upper Chitral`, `Lower Chitral`
- Reject with 400 if district not in allowed list

**One business per user** — `businesses.user_id` is UNIQUE. POST fails with 409 if already exists.

### 7.6 Document Upload

```
POST /api/upload-document/<business_id>
Content-Type: multipart/form-data
Fields: file, document_type
```
- Upload file to S3 at path `documents/<business_id>/<timestamp>_<filename>`
- INSERT or UPDATE `business_documents` row
- Return `{message, file_path}`

### 7.7 Business Media Presigned URL

```
POST /api/business/media/generate-upload-url
Body: {file_name, mime_type, media_category}
Response: {upload_url, object_key}
```
- Generate S3 presigned PUT URL valid 3600s
- Object key: `business-media/<user_id>/<timestamp>_<file_name>`

### 7.8 Business Media Save Reference

```
POST /api/business/media/save-reference
Body: {object_key, file_name, mime_type, document_type}
```
- INSERT into `business_documents`

### 7.9 Grant Application

```
GET  /api/grant   → return grant row for user + access_state
POST /api/grant   → submit new grant application
PUT  /api/grant   → (currently unused but registered)
```

**GET response** must include `access_state` computed from `grant_access_whitelist`:
```json
{
  "exists": true,
  "grant_id": 42,
  "status": "Pending",
  "can_apply": false,
  "reason_message": "...",
  "has_srsp_relative": false,
  "srsp_relatives": []
}
```

**POST validation:**
1. If `GRANT_REQUIRE_SELECTION=1`: check `grant_access_whitelist.is_selected = TRUE` for this user — else 403
2. `expression_of_interest` must be non-empty array OR `working_capital = true` — else 400
3. `grant_required` must be present — else 400
4. `application_date` must be present — else 400
5. Check for existing grant → 409 if already exists

**POST payload (all fields required):**
```
expression_of_interest, other_purpose_text, working_capital, domicile_district,
business_type, business_type_other, tax_registration_status, ntn_registration_no,
tax_filer_status, financed_items, contribution_type, financial_amount,
financial_amount_words, inkind_details, inkind_value, inkind_value_words,
contribution_utilization, grant_support_growth, expected_production_increase,
employment_grid, grant_required, grant_amount_words, has_srsp_relative,
srsp_relatives, declaration_accepted, declaration_name, application_date,
how_did_you_hear
```

After INSERT: enqueue HFC recalculation job.

### 7.10 Grant Disclaimer Update

```
PUT /api/grant/disclaimer
Body: {has_srsp_relative, srsp_relatives}
```
- UPDATE only `has_srsp_relative` and `srsp_relatives` on existing grant
- Returns 404 if no grant exists for user

### 7.11 Grant Status

```
GET /api/grant-status
Response: {hasApplied, status, approved_amount, approval_reason, ...access_state}
```

### 7.12 Grant Media

```
POST /api/grant/generate-upload-url
Body: {file_name, mime_type}
Response: {upload_url, object_key}

POST /api/grant/save-media-reference
Body: {object_key, file_name, mime_type, media_type}
```
- Object key prefix: `grant-media/<user_id>/`
- INSERT into `grant_media`

### 7.13 Password Reset (Disabled)

```
POST /api/forgot-password  → 403 {"message": "Feature temporarily disabled."}
POST /api/reset-password   → 403 {"message": "Feature temporarily disabled."}
```

---

## 8. Functional Requirements — Admin APIs

All require `Authorization: Bearer <adminToken>` with `is_admin: true`.

### 8.1 Admin Login

```
POST /api/admin/login
Body: {username, password}
Response: {token: JWT, role, can_approve}
```
- Check `admin_users` DB table first, then `ADMIN_USERS_JSON` env var
- bcrypt verify
- Return 8h JWT with `{admin_username, role, is_admin: true, is_approver: bool}`

### 8.2 Applicant Reports

```
GET /api/admin/applicants
→ All users with business name, no pagination

GET /api/admin/applicants/registered?limit=N
→ Most recent N users (default 50, max 200)

GET /api/admin/applicants/report?page&per_page&doc_status&language&gender&search&district&sector&status&sort_by&sort_dir
→ Paginated: {data: [...], total, page, per_page}

GET /api/admin/applicants/<user_id>
→ Full user + business + documents + grants + media

GET /api/admin/applicants/<user_id>/pdf
→ PDF binary (Content-Type: application/pdf)
```

**Pagination shape** (all paginated endpoints):
```json
{"data": [...], "total": 150, "page": 1, "per_page": 20}
```

### 8.3 Grant Reports

```
GET /api/admin/grants/submitted
→ All submitted grants with user + business info

GET /api/admin/grants/submitted/bulk-pdf?status&district&search
→ HTML document (Content-Type: text/html; charset=utf-8)
   Complete printable report with Urdu font support

GET /api/admin/reports/applied-detailed?page&per_page&district&sector&status&date_from&date_to&hfc_status&amount_min&amount_max&sort_by&sort_dir
→ Paginated grant applications

GET /api/admin/reports/filter-options
→ {districts: [], sectors: [], statuses: []} — Redis cached 120s

GET /api/admin/reports/approved-grants
→ List of approved grants

GET /api/admin/reports/full-applicant-profiles
→ All profiles

GET /api/admin/reports/full-applicant-profiles/csv?token=<query_token>
→ CSV download

GET /api/admin/reports/business-profiles/csv?token=<query_token>
→ CSV download

GET /api/admin/reports/fully-verified
→ Applicants with all required documents

GET /api/admin/reports/missing-documents
→ Applicants missing docs

GET /api/admin/reports/eligibility-criteria
→ Breakdown by criteria
```

### 8.4 Dashboard

```
GET /api/admin/dashboard/stats
→ Summary stats: total users, businesses, grants, approved, HFC pending
→ Redis cached 60s, cache key: "admin:dashboard_stats_v2"

GET /api/admin/dashboard/frequency?interval=daily|weekly|hourly
→ Registration/application counts over time

GET /api/admin/dashboard/grant-stats
→ Full grant analytics: by_district, grant_amounts, by_purpose, by_contribution_type,
  by_business_type, by_tax_status, employment_summary, overall
→ Redis cached 60s, cache key: "admin:grant_stats_v2"
```

### 8.5 Grant Approval

Requires additionally `is_approver: true` in JWT:

```
GET  /api/admin/grants/<user_id>/approval-check
→ {hfc_score, risk_level, latest_evaluation, checklist, can_approve}

POST /api/admin/grants/<user_id>/approve
Body: {approved_amount, approval_reason, missing_fields, confirmation_text}
→ UPDATE grants.status='Approved', INSERT grant_approval_logs, enqueue emails
```

### 8.6 Grant Access Whitelist

```
POST /api/admin/grants/access
Body: {user_id, is_selected, selection_note}
→ UPSERT grant_access_whitelist

GET /api/admin/grants/access/<user_id>
→ {is_selected, selection_note, selected_by, selected_at}
```

### 8.7 HFC (Fraud Detection)

```
GET  /api/admin/hfc/dashboard/stats
→ {pending, review, cleared, failed, total}

GET  /api/admin/hfc/queue?page&per_page&risk&hfc_status&district&search
→ Paginated flagged applications

GET  /api/admin/hfc/applicant/<user_id>
→ {evaluations, review_actions, checklist}

POST /api/admin/hfc/applicant/<user_id>/action
Body: {action_type: "mark_clear"|"mark_failed"|"override", comment}
→ INSERT hfc_review_actions, UPDATE grants.hfc_status

POST /api/admin/hfc/applicant/<user_id>/recalculate
→ Trigger HFC recalculation job, return new score
```

### 8.8 User Management

```
GET  /api/admin/users
→ All users with status

POST /api/admin/users/<user_id>/status
Body: {status: "blocked"|"unblocked"}
→ UPDATE users.status

POST /api/admin/users/<user_id>/reset-password
→ Send password reset email (currently disabled, return message)
```

### 8.9 Applicant Status

```
GET    /api/admin/applicant-status/eligible-users
→ Users with completed business profiles

GET    /api/admin/applicant-status
→ All status records

POST   /api/admin/applicant-status
Body: {user_id, status, decision_justification, supporting_documents}
status must be: "Eligible" | "Ineligible" | "Decision Pending"
→ UPSERT applicant_status

DELETE /api/admin/applicant-status/<user_id>
→ DELETE applicant_status row

POST   /api/admin/applicant-status/generate-upload-url
Body: {file_name, mime_type}
→ Presigned S3 URL, prefix: "status-docs/"
```

### 8.10 Content Management

```
GET    /api/updates               → public — active announcements (Redis cached 3600s)
GET    /api/admin/updates         → all updates
POST   /api/admin/updates         Body: {title, body, tag}
PUT    /api/admin/updates/<id>    Body: {title, body, tag}
DELETE /api/admin/updates/<id>

GET    /api/faqs                  → public — active FAQs (Redis cached 300s)
GET    /api/faqs/search?q=        → fuzzy search FAQs
GET    /api/admin/faqs            → all FAQs
POST   /api/admin/faqs            Body: {question, answer, keywords, category}
PUT    /api/admin/faqs/<id>       Body: {question, answer, keywords, category, is_active}
DELETE /api/admin/faqs/<id>
```

**FAQ search** must perform fuzzy matching on `question`, `keywords`, and `answer` fields. Return results sorted by match score.

### 8.11 Maintenance

```
POST /api/admin/maintenance/cleanup-duplicates
→ Delete duplicate business_documents rows by (business_id, document_type), keep latest

GET /api/admin/db-browser/tables
→ All table names in public schema

GET /api/admin/db-browser/data/<table_name>?page&per_page
→ Paginated SELECT from named table
```

### 8.12 Committee Administration

```
GET  /api/admin/committee/members
→ All committee members with review_count

POST /api/admin/committee/members
Body: {username, password, full_name, email, designation}
→ INSERT committee_members (bcrypt hash password)

PUT  /api/admin/committee/members/<member_id>
Body: {full_name, email, designation, is_active}

POST /api/admin/committee/members/<member_id>/reset-password
Body: {new_password}
→ UPDATE hashed_password (no old password required)

GET  /api/admin/committee/reviews?page&per_page&decision&district
→ Decision matrix: per applicant × per member

GET  /api/admin/committee/reviews/<user_id>
→ All members' decisions for one applicant

GET  /api/admin/committee/decision-sheet/<user_id>
→ HTML document: applicant summary + all committee decisions + signature images
   Content-Disposition: attachment; filename=decision_sheet_<user_id>.pdf
```

---

## 9. Functional Requirements — Committee APIs

All require `Authorization: Bearer <committeeToken>` with `role: "committee"`.

### 9.1 Committee Login

```
POST /api/committee/login
Body: {username, password}
Response: {token: JWT, member_id, full_name, username}
```
- Look up in `committee_members` by username
- bcrypt verify password
- Check `is_active = true` — else 403
- Return 8h JWT

### 9.2 Committee Profile

```
GET /api/committee/profile
→ {member_id, username, full_name, email, designation, signature_url}
```

### 9.3 Committee Applicant List

```
GET /api/committee/applicants?page&per_page&decision&district&search
→ {data: [...], total, page, per_page}
```

Each row includes:
- User: `user_id`, `first_name`, `last_name`, `cnic`, `gender`
- Business: `name_of_business`, `business_location_district`, `business_sector`
- Grant: `grant_id`, `grant_required`, `application_date`, `grant_status`
- This member's review: `decision` (default "Pending"), `review_id`, `reviewed_at`

Filter by `decision` = `COALESCE(cr.decision, 'Pending')`.

### 9.4 Committee Applicant Detail

```
GET /api/committee/applicants/<user_id>
→ {user, business, grant, documents, review}
```

Committee members can READ all applicant data but cannot write to users/grants/businesses.

### 9.5 Committee Reviews

```
GET  /api/committee/reviews/<user_id>
→ {review: {...} | null}

POST /api/committee/reviews/<user_id>
Body: {decision, justification}
decision: "Selected" | "Not Selected" | "Pending"
→ UPSERT committee_reviews; require justification when decision != "Pending"
```

### 9.6 Committee Document Upload

```
POST /api/committee/reviews/<user_id>/upload-url
Body: {file_name, mime_type}
→ {upload_url, object_key}  (prefix: "committee-docs/<member_id>/<user_id>/")

POST /api/committee/reviews/<user_id>/save-document
Body: {object_key, file_name, mime_type}
→ Append to committee_reviews.supporting_documents JSONB array
  UPSERT committee_reviews row if not exists
```

### 9.7 Committee Signature

```
POST /api/committee/signature/upload-url
Body: {file_name, mime_type}
→ {upload_url, object_key}  (prefix: "committee-signatures/<member_id>/")

POST /api/committee/signature/save
Body: {object_key}
→ UPDATE committee_members.signature_url
```

### 9.8 Committee Change Password

```
POST /api/committee/change-password
Body: {old_password, new_password}
→ Verify old, bcrypt hash new, UPDATE committee_members.hashed_password
→ new_password must be >= 8 characters
```

---

## 10. Functional Requirements — Public APIs

No authentication required.

```
GET /api/system/access-status
→ {session_id, server_time, in_queue: bool}

GET /api/go-test
→ Proxy to internal Go service at http://go_processor:8080/go-test (optional)
```

---

## 11. Background Job Requirements

### 11.1 HFC Fraud Detection Job

**Trigger:** On every grant POST (and manual recalculate)

**Debounce:** Redis key `peace_sme:hfc_debounce:<user_id>` with 60s TTL. Skip enqueue if key exists.

**Job logic (deterministic v1 scoring):**

| Rule | Points |
|---|---|
| Duplicate CNIC in users table | 50 |
| Duplicate email | 20 |
| Duplicate mobile | 20 |
| Missing business profile | 30 |
| Missing required documents | 25 |
| Missing grant media | 10 |
| Business district not in allowed list | 40 |
| Grant amount > threshold | 15 |
| Application submitted very fast (< X min) | 10 |
| Missing expression of interest | 15 |

**Risk bands:**
- 0–29: LOW
- 30–59: MEDIUM
- 60–79: HIGH
- 80+: CRITICAL

**Output:**
- UPSERT `hfc_evaluations` row
- UPDATE `grants.hfc_score`, `grants.hfc_status`, `grants.hfc_risk_level`, `grants.hfc_last_evaluated_at`

**`HFC_SHADOW_MODE=1`**: Calculate and store scores, but scores do NOT gate grant approval.

**Queue name:** `hfc` (Redis list key `rq:queue:hfc`)

### 11.2 Email Jobs

**Queue name:** `emails` (Redis list key `rq:queue:emails`)

| Function | Trigger | Recipient |
|---|---|---|
| `send_welcome_email` | User registration | Applicant email |
| `send_grant_approved_email` | Grant approval | Applicant email |
| `send_grant_approval_notification_email` | Grant approval | `APPROVAL_NOTIFICATION_EMAIL` env var |
| `send_reset_email` | Password reset request (disabled) | Applicant email |

**Important:** If the Go backend enqueues jobs in RQ-compatible format, the existing Python worker continues to process them. Alternatively implement a Go worker that reads from the same Redis queues.

### 11.3 Job Queue Format

If maintaining Python RQ compatibility, enqueue jobs as:
```json
{
  "func": "services.mail_service.send_welcome_email",
  "args": ["user_id"],
  "kwargs": {},
  "timeout": 180
}
```
Stored in Redis list `rq:queue:emails` (RPUSH).

---

## 12. External Integration Requirements

### 12.1 S3-Compatible Storage (Contabo)

```
S3_ENDPOINT_URL     = https://eu2.contabostorage.com
S3_ACCESS_KEY       = <key>
S3_SECRET_KEY       = <secret>
S3_BUCKET_NAME      = peace-economic
S3_PUBLIC_BASE_URL  = https://eu2.contabostorage.com/...
S3_UPLOAD_ACL       = public-read
```

**Requirements:**
- Force path-style addressing: `endpoint/bucket/key` (not virtual-hosted)
- Presigned PUT URLs valid 3600 seconds
- Public URLs constructed as: `S3_PUBLIC_BASE_URL + object_key`
- Support: upload, delete, presigned URL generation

**Object key prefixes by type:**
```
documents/            Business documents
business-media/       Business media
grant-media/          Grant audio/video
status-docs/          Applicant status supporting docs
committee-docs/       Committee review documents
committee-signatures/ Committee member signatures
```

### 12.2 Brevo Email API

```
POST https://api.brevo.com/v3/smtp/email
Headers: api-key: <EMAIL_API_KEY>
Body:
{
  "sender": {"email": "<SENDER_EMAIL>", "name": "<SENDER_NAME>"},
  "to": [{"email": "<recipient>"}],
  "subject": "...",
  "htmlContent": "..."
}
```

- `SENDER_EMAIL` = `info@srsp.cloud`
- `SENDER_NAME` = `PEACE SME GRANT`
- `APPROVAL_NOTIFICATION_EMAIL` = notification recipient for grant approvals

### 12.3 Redis

```
REDIS_URL = redis://redis:6379/0 (Docker internal)
```

Used for:
1. Session slot tracking (`peace_sme:session:*`)
2. Cache (`peace_sme:*`)
3. Job queues (`rq:queue:emails`, `rq:queue:hfc`)
4. HFC debounce keys

---

## 13. Caching Requirements

All cache keys use prefix `peace_sme` (from `CACHE_PREFIX` env var).

| Cache Key | TTL | Invalidate On |
|---|---|---|
| `admin:dashboard_stats_v2` | 60s | Any grant/user change |
| `admin:grant_stats_v2` | 60s | Any grant change |
| `admin:filter_options` | 120s | — |
| `public:updates` | 60s | Update CRUD |
| `public:faqs` | 300s | FAQ CRUD |

**Cache format:** JSON serialised to Redis string.

When `CACHE_ENABLED=0` env var: bypass all cache reads/writes.

---

## 14. Non-Functional Requirements

### 14.1 Performance

- All API responses < 500ms under normal load
- Paginated endpoints must use SQL `LIMIT/OFFSET` — no in-memory pagination
- Database queries must use existing indexes (do not scan indexed columns without index use)
- Bulk HTML report generation may take up to 30s for large datasets — no timeout

### 14.2 Concurrency

- Go HTTP server: use `net/http` default goroutine-per-connection model
- Database pool: min 2, max 40 connections (env configurable)
- Redis connection pool: min 5 connections

### 14.3 Security

- All passwords bcrypt with cost factor 12 minimum
- JWT secret min 16 characters (enforced at startup)
- SQL queries must use parameterised queries only — never string concatenation
- File upload type validation at MIME type level
- Admin query tokens for CSV export: short-lived (15 min), signed with same JWT secret

### 14.4 Error Responses

All error responses must match existing shape exactly:
```json
{"message": "Human readable error description."}
```
With appropriate HTTP status codes:
- 400: validation errors
- 401: missing/expired/invalid token
- 403: blocked user, closed feature, insufficient role
- 404: resource not found
- 409: already exists (duplicate grant, duplicate username)
- 429: concurrent session limit exceeded
- 500: internal server error

### 14.5 Logging

- Log all requests with method, path, status code, duration
- Log all database errors
- Log all external API failures (S3, Brevo)
- Do not log passwords, tokens, or personally identifiable data

### 14.6 Startup

On startup the Go server must:
1. Verify database connectivity
2. Verify Redis connectivity
3. Log successful startup with port number
4. NOT run database migrations (handled by `init_db.py` in Python container at startup)

---

## 15. Migration Requirements

### 15.1 Data

No data migration required. The Go backend connects to the **live existing database**. All data is preserved.

### 15.2 Cutover

The cutover is a Docker Compose swap:
1. Stop `sme_backend_app` (Python)
2. Start Go container on same port 5000
3. The `sme_worker` (Python RQ worker) continues running
4. Frontend is unchanged

### 15.3 Backwards Compatibility

- All existing JWT tokens issued by the Python backend must remain valid — same secret, same algorithm
- All existing Redis cache entries may be ignored (Go will repopulate)
- All S3 URLs remain valid (same bucket, same object structure)

---

## 16. API Contract Constraints

The following must be reproduced **exactly** — any deviation breaks the Vue frontend:

### 16.1 Response Shape

All list endpoints return:
```json
{"data": [...], "total": 150, "page": 1, "per_page": 20}
```

Grant GET response must include all of these fields:
```json
{
  "exists": bool,
  "can_apply": bool,
  "reason_message": string,
  "grant_id": int | null,
  "status": string | null,
  "application_date": string | null,
  "grant_amount_words": string | null,
  "has_srsp_relative": bool,
  "srsp_relatives": array
}
```

### 16.2 HTTP Methods

Exactly match the Python `app.py` method registrations. Endpoints registered with multiple methods must handle all:
- `GET /api/business` AND `POST /api/business` AND `PUT /api/business` — all on same path
- `GET /api/admin/applicant-status` AND `POST /api/admin/applicant-status`

### 16.3 Paths

All paths exactly as defined. Note:
- `/api/admin/applicants/report` (note: not `/admin/applicants/updated` — that path is a dead link in the old navbar)
- `/api/admin/grants/submitted/bulk-pdf` must come BEFORE `/api/admin/grants/submitted` in router registration (more specific path first)
- `/api/admin/applicant-status/eligible-users` must come BEFORE `/api/admin/applicant-status/<user_id>` (avoid routing conflict)

### 16.4 Date Formats

All dates returned as strings: `"2026-01-15"` (ISO 8601 date) or `"2026-01-15T10:30:00"` (ISO 8601 datetime). Match exactly what PostgreSQL returns via `RealDictCursor`.

### 16.5 Null vs Absent Fields

Return `null` for missing optional fields — do not omit the key from the JSON response. The Vue frontend accesses many fields with optional chaining (`?.`) and expects the key to exist even when null.

---

## 17. Frontend Compatibility Constraints

The Vue frontend stores and sends the following — Go must match exactly:

### 17.1 localStorage Keys

| Key | Written by | Read by |
|---|---|---|
| `userToken` | `UserLogin.vue` | Every user API call |
| `adminToken` | `AdminLogin.vue` | Every admin API call |
| `committeeToken` | `CommitteeLogin.vue` | Every committee API call |
| `committeeMemberId` | `CommitteeLogin.vue` | UI display |
| `committeeFullName` | `CommitteeLogin.vue` | UI display |
| `language` | `LanguageSelection.vue` | Bilingual switching |

### 17.2 axios Base URL

Configured in `frontend/src/apiConfig.js`:
```javascript
const API_URL = 'http://localhost:5000/api'
```
On production this may be overridden. Go server must serve at the same base.

### 17.3 Authorization Header Format

```
Authorization: Bearer <token>
```
Exact format. No other format accepted by the frontend.

### 17.4 Bulk HTML Report

The `/api/admin/grants/submitted/bulk-pdf` endpoint returns `text/html; charset=utf-8`. The frontend opens it in a new window via:
```javascript
win.document.write(html)
```
The HTML must be a complete self-contained document (no external dependencies except Google Fonts CDN) with:
- `@page { size: A4; margin: 12mm 14mm; }`
- `page-break-before: always` on each application div
- Google Fonts: `Noto Nastaliq Urdu` for Urdu name rendering
- A fixed print button at the top calling `window.print()`

### 17.5 Decision Sheet HTML

The `/api/admin/committee/decision-sheet/<user_id>` endpoint returns an HTML document served with:
```
Content-Disposition: attachment; filename=decision_sheet_<user_id>.pdf
Content-Type: text/html; charset=utf-8
```
The HTML includes embedded signature images fetched from S3 URLs stored in `committee_members.signature_url`.

---

## Appendix A — Environment Variables Reference

```env
# JWT
JWT_SECRET_KEY=Supersecret

# Admin users (fallback when admin_users table is empty)
ADMIN_USERS_JSON=[{"username":"...","password_hash":"$2b$...","role":"admin","can_approve_grants":false}]

# Email
SENDER_EMAIL=info@srsp.cloud
EMAIL_API_KEY=xkeysib-...
SENDER_NAME=PEACE SME GRANT
APPROVAL_NOTIFICATION_EMAIL=aftab@srsp.org.pk

# S3
S3_ENDPOINT_URL=https://eu2.contabostorage.com
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_BUCKET_NAME=peace-economic
S3_PUBLIC_BASE_URL=https://eu2.contabostorage.com/peace-economic/
S3_UPLOAD_ACL=public-read

# Database
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=sme_app
POSTGRES_USER=sme_user
POSTGRES_PASSWORD=sme_password
DB_POOL_MIN_CONN=2
DB_POOL_MAX_CONN=40

# Feature toggles
GRANT_APPLICATION_OPEN=0
GRANT_REQUIRE_SELECTION=1
FRONTEND_URL=https://peace-grant.srsp.cloud

# HFC
HFC_SHADOW_MODE=1
HFC_ASYNC_ENABLED=1
HFC_ENQUEUE_DEBOUNCE_SEC=60

# Access control
ACCESS_CONTROL_ENABLED=1
MAX_ACTIVE_APPLICANTS=300
ACCESS_SLOT_TTL_SEC=90
GEO_BLOCK_ENABLED=1
ALLOWED_COUNTRY_CODES=PK

# Cache
CACHE_ENABLED=1
CACHE_PREFIX=peace_sme
CACHE_TTL_UPDATES=60
CACHE_TTL_FAQS=300
CACHE_TTL_FILTERS=120
```

---

## Appendix B — Allowed Business Districts

```go
var AllowedDistricts = []string{
    "Swat",
    "Shangla",
    "Upper Dir",
    "Upper Chitral",
    "Lower Chitral",
}
```

District matching must be **case-insensitive**.

---

## Appendix C — HFC Status Values

```go
const (
    HFCPending  = "HFC_Pending"
    HFCReview   = "HFC_Review"
    HFCCleared  = "HFC_Cleared"
    HFCFailed   = "HFC_Failed"
)
```

---

## Appendix D — Applicant Status Values

```go
const (
    StatusEligible        = "Eligible"
    StatusIneligible      = "Ineligible"
    StatusDecisionPending = "Decision Pending"
)
```

PostgreSQL `CHECK` constraint enforces these values. Go must validate before INSERT/UPDATE.

---

*End of SRS*
