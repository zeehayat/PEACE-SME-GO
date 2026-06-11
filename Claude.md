# PEACE SME Grant Portal — Complete Technical Description

> Purpose: This document describes every part of the PEACE SME Grant Portal so that a rewrite agent can reproduce the full system in **Go (backend) + Vue.js 3 (frontend)** with identical behaviour and the same PostgreSQL schema.

---

## 1. Overview

The **PEACE SME Grant Portal** is a web application built for SRSP (Sarhad Rural Support Programme) to manage small-business grant applications in Pakistan's Khyber Pakhtunkhwa province. It is bilingual (English / Urdu with RTL support).

### What it does end-to-end

1. A small-business owner registers an account (pre-registration list controlled).
2. The owner fills in a business profile and uploads required documents to S3-compatible cloud storage.
3. An admin reviews the profile and marks the applicant **Eligible / Ineligible / Decision Pending**.
4. Selected applicants are whitelisted to submit a grant application form.
5. On submission the system runs a fraud-detection (HFC) scoring job asynchronously.
6. An admin with the `approving_authority` role reviews the HFC score and approves or rejects the grant.
7. On approval, notification emails are sent to the applicant and an internal address.
8. Admins have a rich reporting suite, CSV exports, a database browser, FAQ management, and announcement management.

### Current operational state

| Feature | Status |
|---|---|
| New registrations | **CLOSED** (`GRANT_APPLICATION_OPEN=0`) |
| Grant applications | **CLOSED** (toggle `GRANT_APPLICATION_OPEN=1`) |
| Whitelist-gated grant access | **ON** (`GRANT_REQUIRE_SELECTION=1`) |
| HFC in shadow mode (scores don't block approval) | **ON** (`HFC_SHADOW_MODE=1`) |
| Password reset | **DISABLED** (stubs return 403) |

---

## 2. Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Vue 3.2 (Composition API), Vue Router 4, Axios, Tailwind CSS 3, Chart.js 4 |
| Backend | Python 3.12, Flask 3, gunicorn (8 workers × 4 threads) |
| Database | PostgreSQL 15 |
| Cache / Queue | Redis 7 |
| Background jobs | RQ (Redis Queue) — `emails` and `hfc` queues |
| File storage | S3-compatible (Contabo eu2); boto3 |
| Email | Brevo REST API |
| Auth | JWT HS256; bcrypt password hashing |
| Containerisation | Docker Compose (7 services) |

---

## 3. Project Directory Layout

```
peace-sme-form/
├── frontend/                   Vue 3 SPA
│   ├── src/
│   │   ├── main.js
│   │   ├── App.vue
│   │   ├── apiConfig.js        Single source of API base URL
│   │   ├── router/index.js     All routes + route guards
│   │   ├── views/              Page-level components (see §6)
│   │   └── components/         Shared components (see §7)
│   ├── Dockerfile.frontend     Builds with npm, serves via nginx
│   └── package.json
├── backend/                    Flask application
│   ├── app.py                  Entry point, all route registrations
│   ├── init_db.py              Schema + 23 migrations
│   ├── services/               Domain service modules (see §9)
│   │   ├── auth_service.py
│   │   ├── user_service.py
│   │   ├── grant_service.py
│   │   ├── report_service.py
│   │   ├── admin_service.py
│   │   ├── hfc_service.py
│   │   ├── hfc_admin_service.py
│   │   ├── status_service.py
│   │   ├── mail_service.py
│   │   ├── s3_service.py
│   │   ├── database.py
│   │   ├── cache_service.py
│   │   ├── security.py
│   │   ├── logger_service.py
│   │   └── utils.py
│   └── Dockerfile.backend
├── backend-go/                 Placeholder Go service (stub only)
├── docker-compose.yml
├── .env                        All secrets and runtime config
├── remote_backup.py            SSH-based backup/restore/migrate tool
└── load-tests/
```

---

## 4. Docker Compose Services

```
┌─────────────────────────────────────────┐
│              sme_network                │
│                                         │
│  postgres:15  ←──── backend (Flask)     │
│  (sme_postgres_db)  (sme_backend_app)   │
│  port 5433:5432     port 5000:5000      │
│                                         │
│  redis:7      ←──── worker (RQ)         │
│  (sme_redis)        (sme_backend_worker)│
│                                         │
│  nginx        ←──── frontend (Vue)      │
│  (sme_frontend)     port 3001:80        │
│                                         │
│  go_processor       port 8081:8080      │
│  adminer            port 8082:8080      │
│  pgadmin            port 5051:80        │
└─────────────────────────────────────────┘
```

- **Backend container startup**: `python init_db.py && gunicorn app:app --bind 0.0.0.0:5000 --workers 8 --threads 4 --timeout 120`
- **Worker startup**: `rq worker --url redis://redis:6379/0 emails hfc`
- **Backend code is baked into the image** (not volume-mounted), so code changes require `docker compose up --build`.
- Only the uploaded files volume (`/var/www/sme-uploads`) persists outside Docker.

---

## 5. Environment Variables

```env
# Auth
JWT_SECRET_KEY=Supersecret
ADMIN_USERS_JSON=[{...}]          # Array of {username, password_hash, role, can_approve_grants}
ADMIN_USERS_PLAIN_JSON=[{...}]    # Optional plain-password format

# Email (Brevo)
SENDER_EMAIL=info@srsp.cloud
EMAIL_API_KEY=xkeysib-...
SENDER_NAME=PEACE SME GRANT
APPROVAL_NOTIFICATION_EMAIL=aftab@srsp.org.pk

# S3 (Contabo)
S3_ENDPOINT_URL=https://eu2.contabostorage.com
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_BUCKET_NAME=peace-economic
S3_PUBLIC_BASE_URL=https://eu2.contabostorage.com/...
S3_UPLOAD_ACL=public-read

# Database
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=sme_app
POSTGRES_USER=sme_user
POSTGRES_PASSWORD=sme_password
DB_POOL_MIN_CONN=2
DB_POOL_MAX_CONN=40

# Application toggles
GRANT_APPLICATION_OPEN=0          # 0 = registrations closed
GRANT_REQUIRE_SELECTION=1         # 1 = only whitelisted users can apply
FRONTEND_URL=https://peace-grant.srsp.cloud

# HFC (Fraud Detection)
HFC_SHADOW_MODE=1                 # 1 = scores visible but don't block approval
HFC_ASYNC_ENABLED=1
HFC_ENQUEUE_DEBOUNCE_SEC=60

# Access / Geo control
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

## 6. Frontend — All Views

### Authentication / Onboarding

| File | Route | Purpose |
|---|---|---|
| `MainLandingPage.vue` | `/` | Public homepage with project info, announcements, and links |
| `LanguageSelection.vue` | `/initial-data-entry` | Choose language (EN/UR) before pre-registration |
| `TermsAndConditions.vue` | `/terms-and-conditions` | Terms page (must accept before registering) |
| `RegistrationForm.vue` | `/register` | User sign-up form (CNIC, email, password, name, gender) |
| `UserLogin.vue` | `/login` | User login form |
| `ForgotPassword.vue` | `/forgot-password` | "Feature Temporarily Disabled" stub |
| `ResetPassword.vue` | `/reset-password` | "Feature Temporarily Disabled" stub |
| `WaitingRoom.vue` | `/waiting-room` | Shown when concurrent session limit is reached |
| `GeoBlocked.vue` | `/access-restricted` | Shown to non-PK IP addresses |
| `UserRegisterNot.vue` | — | Shown when pre-registration is closed |
| `TermsAndConditionsNot.vue` | — | T&C when registration closed variant |

### Applicant (SME user) Flow

| File | Route | Purpose |
|---|---|---|
| `AppDashboard.vue` | `/dashboard` | User's home: profile status, grant status, announcements, media upload |
| `SmeBusinessProfile.vue` | `/business-profile` | Multi-section business profile form (create or edit) |
| `SmeGrantApplication.vue` | `/grant-application` | Full grant application form (bilingual, multi-section) |
| `SmeGrantReview.vue` | `/grant-review` | Read-only review of submitted grant before final submit |

#### SmeGrantApplication.vue — sections in order

1. **Applicant Identification** — domicile district dropdown
2. **Business Details** — business type (checkboxes, Other expands textbox), tax registration status (checkboxes), NTN number, tax filer status (radio)
3. **Purpose of Grant** — expression of interest (checkboxes, Other expands textarea), working capital toggle
4. **Items to be Financed** — repeating rows: item name, quantity, estimated cost
5. **Contribution** — contribution type radio (Cash / In-Kind / Both), conditional cash amount + words / in-kind details + value, utilisation textarea
6. **Business Growth** — how grant supports growth (textarea), job creation details (textarea)
7. **Disclaimer** — conflict of interest declaration text box, SRSP relative radio (Yes/No), dynamic relatives table (name, position, office) with add/remove
8. **Declaration** — declaration accepted checkbox, full name of declarant
9. **How did you hear** — dropdown

All labels are served from a translation object (`t`) that switches between `en` and `ur` objects based on `isUrdu` (computed from `localStorage.getItem('language')`). RTL layout is toggled via `:class="{ 'text-right font-urdu': isUrdu }"`.

### Admin Flow

| File | Route | Roles | Purpose |
|---|---|---|---|
| `AdminLogin.vue` | `/admin/login` | Public | Admin sign-in |
| `AdminDashboard.vue` | `/admin/dashboard` | Admin | Stats cards, charts, recent registrations |
| `AdminGrantsSubmitted.vue` | `/admin/grants/submitted` | Admin | Table of all submitted grants with filters |
| `AdminGrantDetail.vue` | `/admin/grants/submitted/:id` | Admin | Full grant detail; approve button (approvers only) |
| `AdminApplicantStatus.vue` | `/admin/applicant-status` | Admin | Set Eligible/Ineligible/Decision Pending per user |
| `AdminUserAccess.vue` | `/admin/user-access` | Admin | Whitelist users to unlock grant application |
| `AdminApplicantsReport.vue` | `/admin/applicants/report` | Admin | Filtered/paginated applicant table with CSV export |
| `AdminAppliedDetails.vue` | `/admin/reports/applied-detailed` | Admin | Filtered grant applications report |
| `AdminApprovedGrants.vue` | `/admin/reports/approved-grants` | Admin | Approved grants table |
| `AdminEligibilityCriteriaReport.vue` | `/admin/reports/eligibility-criteria` | Admin | Eligibility analysis by criteria |
| `AdminMissingDocs.vue` | `/admin/reports/missing-docs` | Admin | Applicants with incomplete documents |
| `AdminFullReport.vue` | `/admin/reports/full-report` | Admin | Full export of all data |
| `AdminHfcDashboard.vue` | `/admin/hfc/dashboard` | Admin | HFC fraud detection summary stats |
| `AdminHfcQueue.vue` | `/admin/hfc/queue` | Admin | Queue of flagged applications for review |
| `AdminHfcModelTuning.vue` | `/admin/hfc/tuning` | Admin | HFC rule weights config |
| `AdminUpdates.vue` | `/admin/updates` | Admin | Create / edit / delete announcements |
| `AdminDbBrowser.vue` | `/admin/db-browser` | Admin | Browse any DB table via API |

---

## 7. Frontend — Shared Components

| File | Purpose |
|---|---|
| `Navbar.vue` | Top nav for SME users (logo, menu, language toggle, logout) |
| `AdminNavbar.vue` | Top nav for admins (role badge, menu) |
| `Footer.vue` | Site footer |
| `BackgroundMosaicSlider.vue` | Animated mosaic background used on auth pages |
| `FAQBot.vue` | FAQ search drawer with fuzzy matching and Urdu support |
| `HelpDrawer.vue` | Slide-in help panel |
| `InformationDrawer.vue` | Slide-in info panel |
| `ProjectBanner.vue` | Banner with project logos |
| `RecordingCapture.vue` | Audio/video recording for grant media |
| `VideoModal.vue` | Lightbox for video playback |
| `WhatsappButton.vue` | Floating WhatsApp contact button |

---

## 8. Frontend — Auth & Token Handling

### Token Storage

| Key | Value | Set by | Used by |
|---|---|---|---|
| `userToken` | JWT string | `UserLogin.vue` after `/api/login` | Every Axios request as `Authorization: Bearer <token>` |
| `adminToken` | JWT string | `AdminLogin.vue` after `/api/admin/login` | Every admin Axios request |
| `language` | `'english'` or `'urdu'` | `LanguageSelection.vue` | `isUrdu` computed in every view |

### User JWT Payload

```json
{ "user_id": 42, "exp": 1234567890 }
```

- Expiry: 24 hours
- Algorithm: HS256

### Admin JWT Payload

```json
{
  "admin_username": "admin1",
  "role": "admin",
  "is_admin": true,
  "is_approver": false,
  "exp": 1234567890
}
```

- Expiry: 8 hours
- Algorithm: HS256

### Route Guards (`router/index.js`)

```
beforeEach:
  if route.meta.requiresAuth  → check localStorage.userToken  → else /login
  if route.meta.requiresAdmin → check localStorage.adminToken → else /admin/login
```

---

## 9. Backend — Service Modules

### auth_service.py

- `admin_login_logic(data)` — bcrypt-verify admin password against `ADMIN_USERS_JSON` env var; return 8h JWT.
- `decode_admin_query_token(token)` — verify a short-lived query token used for CSV exports.

### user_service.py

- `pre_register_logic()` — check if CNIC is in `initial_registrations`; currently always returns 403 CLOSED.
- `register_user_logic()` — create user row; currently always returns 403 CLOSED.
- `login_user_logic()` — look up user by email, bcrypt verify, check `users.status != 'blocked'`; return 24h JWT.
- `get_user_profile_logic(user_id)` — return user row joined with business name.
- `handle_business_profile_logic()` — GET returns business row for user; POST creates; PUT updates. Districts allowed: Swat, Shangla, Upper Dir, Upper Chitral, Lower Chitral.
- `upload_document_logic()` — multipart file → S3 upload; insert/update `business_documents` row.
- `generate_business_media_upload_url_logic()` — return a presigned S3 PUT URL valid 60 min.
- `save_business_media_reference_logic()` — insert `business_documents` row with pre-uploaded S3 key.
- `forgot_password_logic()` — returns 403 (disabled).
- `reset_password_logic()` — returns 403 (disabled).

### grant_service.py

- `apply_for_grant_logic()`:
    - **GET**: return grant row for user (all columns); also compute `access_state` from whitelist if `GRANT_REQUIRE_SELECTION=1`.
    - **POST**: validate user is whitelisted (if required), insert grant row, enqueue HFC job.
    - **PUT**: update existing draft grant, re-enqueue HFC.
- `get_grant_status_logic()` — return status, approved_amount, approval_reason for user's grant.
- `generate_upload_url_logic()` — presigned S3 URL for grant media.
- `save_media_reference_logic()` — insert `grant_media` row.
- `admin_grant_approval_check_logic(user_id)` — return HFC score, risk, latest evaluation, checklist.
- `admin_approve_grant_logic(user_id)` — set `grants.status='Approved'`, record `grant_approval_logs`, enqueue approval emails.
- `admin_set_grant_access_logic()` — upsert `grant_access_whitelist` row.
- `admin_grant_access_get_logic(user_id)` — return whitelist row.

### report_service.py

All report endpoints support pagination (`page`, `per_page`) and sorting (`sort_by`, `sort_dir`).

- `get_applicants_report_logic()` — paginated users with filters: `doc_status`, `language`, `gender`, `search` (name/CNIC/email), `district`, `sector`, `status`.
- `get_admin_applicants_logic()` — all users (no pagination).
- `get_registered_applicants_logic()` — most recent N users.
- `get_admin_applicant_detail_logic(user_id)` — full user + business + documents + grants + media in one response.
- `get_admin_applicant_pdf_logic(user_id)` — generate PDF dossier (HTML → PDF).
- `get_applied_detailed_logic()` — grant applications with advanced filters: district, sector, status, date range, HFC status, amount range.
- `get_report_filter_options_logic()` — distinct values for all filter dropdowns (Redis cached 120s).
- `get_approved_grants_logic()` — approved grants list with approver and amount.
- `get_full_applicant_profiles_logic()` — all profiles (no filters).
- `get_full_applicant_profiles_csv_logic()` — CSV export (requires admin query token in URL).
- `get_business_profile_report_csv_logic()` — business CSV export.
- `get_fully_verified_report_logic()` — applicants who have uploaded all required document types.
- `get_missing_documents_report_logic()` — applicants missing one or more document types.
- `get_eligibility_criteria_report_logic()` — breakdown of applicants by each eligibility criterion.
- `get_dashboard_stats_logic()` — admin dashboard: total users, businesses, grants, approved, HFC pending (Redis cached 60s).
- `get_dashboard_frequency_logic()` — registration/application count over time, grouped by day/week/month.
- `get_grants_submitted_logic()` — all submitted grant rows with user + business info.

### admin_service.py

- `list_admin_users_logic()` — all users with status.
- `admin_set_user_status_logic(user_id)` — set `users.status = 'blocked'` or `'unblocked'`.
- `admin_reset_user_password_logic(user_id)` — force password reset (currently sends reset link).
- `cleanup_duplicate_documents_logic()` — delete duplicate `business_documents` rows by `(business_id, document_type)`, keep latest.
- `admin_db_browser_tables_logic()` — `SELECT table_name FROM information_schema.tables WHERE table_schema='public'`.
- `admin_db_browser_data_logic(table_name)` — paginated SELECT from any table.
- `get_updates_logic()` — return active announcements (Redis cached 3600s).
- CRUD for `updates` and `faqs` tables.
- `search_faqs_logic(q)` — fuzzy string matching on question + keywords + answer; Urdu → transliterated English hints supported.

### hfc_service.py — Fraud Detection (HFC)

**Score rules (deterministic v1):**

| Rule | Points |
|---|---|
| Duplicate CNIC | 50 |
| Duplicate email | 20 |
| Duplicate mobile | 20 |
| Missing business profile | 30 |
| Missing required documents | 25 |
| Missing grant media | 10 |
| Business district out of scope | 40 |
| Grant amount > threshold | 15 |
| Application submitted very fast (< X min) | 10 |
| Missing expression of interest | 15 |

**Risk bands:**

| Score | Level |
|---|---|
| 0–29 | LOW |
| 30–59 | MEDIUM |
| 60–79 | HIGH |
| 80+ | CRITICAL |

**ML scoring**: Optional additional ML score via `ml_model` module (combined with rule score). If ML unavailable, `ml_unavailable=true` is stored.

**Job flow:**
1. Grant submission → `enqueue_hfc_recalculate(user_id)` → Redis debounce 60s → RQ `hfc` queue.
2. Worker runs `run_hfc_recalculate_job()` → `calculate_hfc_for_user()` → upsert `hfc_evaluations`, update `grants.hfc_score/status/risk_level`.

**`HFC_SHADOW_MODE=1`**: HFC score is calculated and stored but cannot block grant approval.

### hfc_admin_service.py

- `admin_hfc_dashboard_stats_logic()` — counts by HFC status.
- `admin_hfc_queue_logic()` — paginated queue; filters: risk level, HFC status, district, search.
- `admin_hfc_applicant_detail_logic(user_id)` — latest evaluation + all review actions + checklist.
- `admin_hfc_action_logic(user_id, action_type)` — actions: `mark_clear`, `mark_failed`, `override`; writes `hfc_review_actions`, updates `grants.hfc_status`.

### status_service.py

- `get_eligible_applicants_logic()` — users who have completed a business profile.
- `list_applicant_status_logic()` — all `applicant_status` rows with user info.
- `upsert_applicant_status_logic()` — INSERT or UPDATE status (Eligible / Ineligible / Decision Pending) with optional `decision_justification` and `supporting_documents` (JSONB array of S3 URLs).
- `delete_applicant_status_logic(user_id)` — DELETE row.
- `generate_status_upload_url_logic()` — presigned S3 URL for supporting document upload.

### security.py — Middleware

**Request pipeline (every request):**

```
apply_geo_block()        → check CF-IPCountry or X-Country-Code header; 403 if not in ALLOWED_COUNTRY_CODES
apply_access_control()   → Redis SETEX session slot; 429 if > MAX_ACTIVE_APPLICANTS
authenticate_token()     → parse Authorization: Bearer header; decode JWT; attach user_id or is_admin to request context
```

Admin routes skip geo-block. Unprotected routes skip auth.

**Admin user config** (from env `ADMIN_USERS_JSON`):
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

### mail_service.py

Uses **Brevo REST API** (`POST https://api.brevo.com/v3/smtp/email`).

| Function | Trigger | Recipients |
|---|---|---|
| `send_welcome_email()` | User registration | Applicant |
| `send_grant_approved_email()` | Grant approval | Applicant |
| `send_grant_approval_notification_email()` | Grant approval | `APPROVAL_NOTIFICATION_EMAIL` |
| `send_reset_email()` | Password reset request | Applicant |

All emails are **async** via RQ `emails` queue.

### s3_service.py

- Supports Contabo, Backblaze, Cloudflare R2, AWS S3 via path-style addressing.
- `get_s3_client()` — boto3 client from env.
- `build_public_object_url(key)` — construct public URL from `S3_PUBLIC_BASE_URL + key`.
- `get_object_key_from_url(url)` — extract key from full URL.
- `delete_s3_object(url)` — delete from S3.

### database.py

- `ThreadedConnectionPool` with min=2, max=40 connections.
- All queries use `DictCursor` / `RealDictCursor` for dict-like row access.
- `table_exists(conn, name)` / `column_exists(conn, table, col)` — used by `init_db.py` for safe migrations.

### cache_service.py

- Thin Redis wrapper with JSON serialisation.
- `cache_get_json(key)` / `cache_set_json(key, value, ttl)`.
- `cache_delete_prefix(prefix)` — invalidate all keys matching a prefix.
- Default key prefix: `peace_sme`.

---

## 10. Database Schema

### Table: users

```sql
CREATE TABLE users (
  user_id           SERIAL PRIMARY KEY,
  email_address     VARCHAR(255) UNIQUE NOT NULL,
  hashed_password   TEXT NOT NULL,
  first_name        VARCHAR(100),
  last_name         VARCHAR(100),
  middle_name       VARCHAR(100),
  cnic              VARCHAR(25),
  language          VARCHAR(10),
  gender            VARCHAR(10),
  mobile_no         VARCHAR(20),
  whatsapp_number   VARCHAR(20),
  terms_accepted    BOOLEAN DEFAULT FALSE,
  status            VARCHAR(20) DEFAULT 'unblocked',  -- 'blocked' | 'unblocked'
  last_login_ip     VARCHAR(64),
  device_fingerprint VARCHAR(255),
  created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ON users (cnic);
CREATE INDEX ON users (created_at DESC);
```

### Table: businesses

```sql
CREATE TABLE businesses (
  business_id                    SERIAL PRIMARY KEY,
  user_id                        INTEGER UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  name_of_business               TEXT,
  business_registration_number   TEXT,
  business_registration_date     DATE,
  business_registration_authority JSONB DEFAULT '[]',  -- array of authority names
  other_authority_text           TEXT,
  business_full_address          TEXT,
  social_media_page              TEXT,
  social_media_page_2            TEXT,
  social_media_page_3            TEXT,
  social_media_page_4            TEXT,
  male_employees                 INTEGER,
  female_employees               INTEGER,
  business_location_district     TEXT,  -- must be in allowed districts list
  business_sector                TEXT,
  how_did_you_hear               TEXT,
  has_srsp_relation              BOOLEAN DEFAULT FALSE,
  srsp_relatives_data            JSONB DEFAULT '[]',
  created_at                     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ON businesses (business_location_district);
CREATE INDEX ON businesses (business_sector);
```

**Allowed districts**: Swat, Shangla, Upper Dir, Upper Chitral, Lower Chitral.

### Table: grants

```sql
CREATE TABLE grants (
  grant_id                  SERIAL PRIMARY KEY,
  user_id                   INTEGER UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  expression_of_interest    TEXT,               -- JSON array of selected purposes
  grant_required            REAL,
  application_date          DATE,
  status                    VARCHAR(50) DEFAULT 'Pending',

  -- Contribution
  contribution_type         VARCHAR(100),       -- 'Cash/Financial' | 'In-kind (materials, equipment, services)' | 'Both'
  financial_amount          REAL,
  financial_amount_words    TEXT,
  inkind_details            TEXT,
  inkind_value              REAL,
  contribution_utilization  TEXT,

  -- Grant narrative
  grant_support_growth      TEXT,
  job_creation_details      TEXT,
  grant_amount_words        TEXT,
  other_purpose_text        TEXT,
  how_did_you_hear          VARCHAR(255),

  -- Approval
  approved_amount           REAL,
  approval_reason           TEXT,
  approved_at               TIMESTAMP,
  approved_by               VARCHAR(100),

  -- HFC (Fraud Detection)
  hfc_status                VARCHAR(30) DEFAULT 'HFC_Pending',
  hfc_score                 INTEGER DEFAULT 0,
  hfc_risk_level            VARCHAR(20) DEFAULT 'LOW',
  hfc_last_evaluated_at     TIMESTAMP,
  hfc_model_version         VARCHAR(50),

  -- Additional application fields (migration 21)
  domicile_district         TEXT,
  business_type             JSONB DEFAULT '[]',   -- array of selected types
  business_type_other       TEXT,
  tax_registration_status   JSONB DEFAULT '[]',   -- array
  ntn_registration_no       TEXT,
  tax_filer_status          VARCHAR(20),
  working_capital           BOOLEAN DEFAULT FALSE,
  financed_items            JSONB DEFAULT '[]',   -- [{item, quantity, estimated_cost}]
  expected_production_increase TEXT,
  employment_grid           JSONB DEFAULT '{}',   -- {before_male, before_female, after_male, after_female}
  declaration_accepted      BOOLEAN DEFAULT FALSE,
  declaration_name          TEXT,

  -- Disclaimer (migration 23)
  has_srsp_relative         BOOLEAN DEFAULT FALSE,
  srsp_relatives            JSONB DEFAULT '[]'    -- [{name, position, office}]
);
-- Indexes
CREATE INDEX ON grants (status);
CREATE INDEX ON grants (application_date DESC);
CREATE INDEX ON grants (user_id, status);
CREATE INDEX ON grants (hfc_status);
CREATE INDEX ON grants (hfc_risk_level);
CREATE INDEX ON grants (approved_at DESC);
CREATE INDEX ON grants (approved_by);
CREATE INDEX ON grants (hfc_status, hfc_score);
```

### Table: business_documents

```sql
CREATE TABLE business_documents (
  document_id    SERIAL PRIMARY KEY,
  user_id        INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  business_id    INTEGER NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
  document_type  VARCHAR(100),
  file_name      TEXT,
  file_path      TEXT,    -- S3 public URL
  mime_type      VARCHAR(100),
  uploaded_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ON business_documents (business_id);
CREATE INDEX ON business_documents (business_id, document_type);
```

**Required document types** (for "fully verified" check):
- CNIC (front)
- CNIC (back)
- Business registration certificate
- Tax certificate / NTN
- Bank statement

### Table: grant_media

```sql
CREATE TABLE grant_media (
  media_id    SERIAL PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  business_id INTEGER NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
  grant_id    INTEGER NOT NULL REFERENCES grants(grant_id) ON DELETE CASCADE,
  media_type  VARCHAR(10),    -- 'video' | 'audio'
  file_name   TEXT,
  file_path   TEXT UNIQUE,    -- S3 public URL
  uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ON grant_media (user_id);
CREATE INDEX ON grant_media (business_id);
```

### Table: grant_approval_logs

```sql
CREATE TABLE grant_approval_logs (
  approval_log_id    SERIAL PRIMARY KEY,
  grant_id           INTEGER NOT NULL REFERENCES grants(grant_id) ON DELETE CASCADE,
  user_id            INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  approving_authority VARCHAR(100),
  action             VARCHAR(30),
  approved_amount    REAL,
  approval_reason    TEXT,
  missing_fields     JSONB DEFAULT '[]',
  confirmation_text  TEXT,
  created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: grant_access_whitelist

```sql
CREATE TABLE grant_access_whitelist (
  access_id      SERIAL PRIMARY KEY,
  user_id        INTEGER UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  is_selected    BOOLEAN DEFAULT FALSE,
  selection_note TEXT,
  selected_by    VARCHAR(100),
  selected_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ON grant_access_whitelist (is_selected, updated_at DESC);
```

### Table: applicant_status

```sql
CREATE TABLE applicant_status (
  status_id              SERIAL PRIMARY KEY,
  user_id                INTEGER UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  status                 VARCHAR(50) NOT NULL CHECK (status IN ('Eligible', 'Ineligible', 'Decision Pending')),
  decision_justification TEXT,
  supporting_documents   JSONB DEFAULT '[]',   -- array of S3 URLs
  created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ON applicant_status (status);

-- Auto-update trigger
CREATE OR REPLACE FUNCTION update_applicant_status_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_applicant_status_updated_at
BEFORE UPDATE ON applicant_status
FOR EACH ROW EXECUTE FUNCTION update_applicant_status_updated_at();
```

### Table: hfc_evaluations

```sql
CREATE TABLE hfc_evaluations (
  evaluation_id   SERIAL PRIMARY KEY,
  user_id         INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  grant_id        INTEGER NOT NULL REFERENCES grants(grant_id) ON DELETE CASCADE,
  rule_score      INTEGER DEFAULT 0,
  ml_score        INTEGER DEFAULT 0,
  final_score     INTEGER DEFAULT 0,
  risk_level      VARCHAR(20),
  rules_triggered JSONB DEFAULT '[]',
  feature_vector  JSONB DEFAULT '{}',
  model_version   VARCHAR(50),
  checklist       JSONB DEFAULT '{}',
  evaluator_type  VARCHAR(20) DEFAULT 'system',  -- 'system' | 'manual'
  ml_unavailable  BOOLEAN DEFAULT FALSE,
  evaluated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ON hfc_evaluations (grant_id, evaluated_at DESC);
CREATE INDEX ON hfc_evaluations (user_id, evaluated_at DESC);
```

### Table: hfc_review_actions

```sql
CREATE TABLE hfc_review_actions (
  action_id      SERIAL PRIMARY KEY,
  user_id        INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  grant_id       INTEGER NOT NULL REFERENCES grants(grant_id) ON DELETE CASCADE,
  actor_username VARCHAR(100),
  action_type    VARCHAR(30),   -- 'mark_clear' | 'mark_failed' | 'override'
  comment        TEXT,
  before_state   JSONB DEFAULT '{}',
  after_state    JSONB DEFAULT '{}',
  created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ON hfc_review_actions (grant_id, created_at DESC);
CREATE INDEX ON hfc_review_actions (actor_username, created_at DESC);
```

### Table: hfc_rule_config

```sql
CREATE TABLE hfc_rule_config (
  rule_code   VARCHAR(100) PRIMARY KEY,
  enabled     BOOLEAN DEFAULT TRUE,
  weight      INTEGER DEFAULT 10,
  threshold   JSONB DEFAULT '{}',
  description TEXT,
  updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: initial_registrations

```sql
CREATE TABLE initial_registrations (
  cnic       VARCHAR(25) PRIMARY KEY,
  full_name  VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: updates (Announcements)

```sql
CREATE TABLE updates (
  update_id  SERIAL PRIMARY KEY,
  title      VARCHAR(255),
  body       TEXT,
  tag        VARCHAR(50),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Table: faqs

```sql
CREATE TABLE faqs (
  faq_id     SERIAL PRIMARY KEY,
  question   TEXT,
  answer     TEXT,
  keywords   TEXT,
  category   VARCHAR(50) DEFAULT 'General',  -- 'General' | 'Registration' | 'Grants' | 'Account'
  is_active  BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: schema_migrations

```sql
CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY
);
```

### Entity Relationship Summary

```
users (user_id)
├── businesses            (1:1, user_id UNIQUE)
│   └── business_documents (1:many, business_id)
├── grants                (1:1, user_id UNIQUE)
│   ├── grant_media        (1:many, grant_id)
│   ├── grant_approval_logs (1:many, grant_id)
│   ├── hfc_evaluations    (1:many, grant_id)
│   └── hfc_review_actions (1:many, grant_id)
├── grant_access_whitelist (1:1, user_id UNIQUE)
└── applicant_status       (1:1, user_id UNIQUE)
```

All FKs use `ON DELETE CASCADE`.

---

## 11. Complete API Reference

All endpoints are prefixed `/api`. Frontend base URL configured in `apiConfig.js`.

### Public endpoints (no auth required)

| Method | Path | Body / Params | Response |
|---|---|---|---|
| POST | `/pre-registration` | `{cnic}` | `{eligible: bool}` or 403 CLOSED |
| POST | `/register` | `{email_address, password, first_name, last_name, cnic, language, gender, mobile_no, whatsapp_number, terms_accepted}` | `{message}` or 403 CLOSED |
| POST | `/login` | `{email_address, password}` | `{token: JWT, user_id, language}` |
| POST | `/forgot-password` | `{email_address}` | 403 DISABLED |
| POST | `/reset-password` | `{token, new_password}` | 403 DISABLED |
| POST | `/admin/login` | `{username, password}` | `{token: JWT, role, can_approve}` |
| GET | `/updates` | — | `[{update_id, title, body, tag, created_at}]` |
| GET | `/faqs` | — | `[{faq_id, question, answer, keywords, category}]` |
| GET | `/faqs/search` | `?q=<query>` | `[{faq_id, question, answer, score}]` |
| GET | `/system/access-status` | — | `{session_id, server_time, in_queue: bool}` |

### User endpoints (requires `Authorization: Bearer <userToken>`)

| Method | Path | Body / Params | Response |
|---|---|---|---|
| GET | `/user/profile` | — | `{user_id, email_address, first_name, last_name, cnic, language, gender, mobile_no, ...}` |
| GET | `/business` | — | Business profile row or `{}` |
| POST | `/business` | Business profile fields (see schema) | `{message, business_id}` |
| PUT | `/business` | Business profile fields | `{message}` |
| POST | `/upload-document/<business_id>` | multipart/form-data: `file`, `document_type` | `{message, file_path}` |
| POST | `/business/media/generate-upload-url` | `{file_name, mime_type, media_category}` | `{upload_url, object_key}` |
| POST | `/business/media/save-reference` | `{object_key, file_name, mime_type, document_type}` | `{message, document_id}` |
| GET | `/grant` | — | Grant row + `access_state` field |
| POST | `/grant` | Full grant form payload (see schema) | `{message, grant_id}` |
| PUT | `/grant` | Grant form fields | `{message}` |
| GET | `/grant-status` | — | `{status, approved_amount, approval_reason}` |
| POST | `/grant/generate-upload-url` | `{file_name, mime_type}` | `{upload_url, object_key}` |
| POST | `/grant/save-media-reference` | `{object_key, file_name, mime_type, media_type}` | `{message, media_id}` |

**Grant POST payload** (all fields):
```json
{
  "expression_of_interest": ["Purpose A", "Purpose B"],
  "other_purpose_text": "...",
  "grant_required": 500000,
  "grant_amount_words": "Five Hundred Thousand",
  "application_date": "2026-01-15",
  "working_capital": false,
  "financed_items": [{"item": "Machine", "quantity": 1, "estimated_cost": 300000}],
  "contribution_type": "Cash/Financial",
  "financial_amount": 50000,
  "financial_amount_words": "Fifty Thousand",
  "inkind_details": "",
  "inkind_value": null,
  "contribution_utilization": "...",
  "grant_support_growth": "...",
  "job_creation_details": "...",
  "how_did_you_hear": "Social Media",
  "domicile_district": "Swat",
  "business_type": ["Manufacturing", "Other"],
  "business_type_other": "Textile",
  "tax_registration_status": ["Registered (NTN/STRN)"],
  "ntn_registration_no": "1234567",
  "tax_filer_status": "Active",
  "expected_production_increase": "20%",
  "employment_grid": {"before_male": 2, "before_female": 1, "after_male": 4, "after_female": 2},
  "declaration_accepted": true,
  "declaration_name": "Muhammad Ali",
  "has_srsp_relative": true,
  "srsp_relatives": [{"name": "Ahmed Khan", "position": "Officer", "office": "Swat"}]
}
```

### Admin endpoints (requires `Authorization: Bearer <adminToken>`)

#### Applicants / Reports

| Method | Path | Params | Response |
|---|---|---|---|
| GET | `/admin/applicants` | — | `[users + business name]` |
| GET | `/admin/applicants/registered` | `?limit=10` | `[latest users]` |
| GET | `/admin/applicants/report` | `?page, per_page, doc_status, language, gender, search, district, sector, status, sort_by, sort_dir` | `{data: [...], total, page, per_page}` |
| GET | `/admin/applicants/<user_id>` | — | Full user + business + docs + grants + media |
| GET | `/admin/applicants/<user_id>/pdf` | — | PDF binary |
| GET | `/admin/reports/applied-detailed` | `?page, per_page, district, sector, status, date_from, date_to, hfc_status, amount_min, amount_max, sort_by, sort_dir` | `{data, total, page, per_page}` |
| GET | `/admin/reports/filter-options` | — | `{districts: [], sectors: [], statuses: []}` |
| GET | `/admin/reports/approved-grants` | — | `[{grant_id, user, business, approved_amount, approved_by, approved_at}]` |
| GET | `/admin/reports/full-applicant-profiles` | — | All profiles |
| GET | `/admin/reports/full-applicant-profiles/csv` | `?token=<query_token>` | CSV download |
| GET | `/admin/reports/business-profiles/csv` | `?token=<query_token>` | CSV download |
| GET | `/admin/reports/fully-verified` | — | Applicants with all required docs |
| GET | `/admin/reports/missing-documents` | — | Applicants missing docs |
| GET | `/admin/reports/eligibility-criteria` | — | `{criteria: [{name, eligible, ineligible}]}` |
| GET | `/admin/grants/submitted` | `?page, per_page, sort_by, sort_dir, search, status` | `{data, total}` |

#### Grant Approval (requires `is_approver` flag)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/admin/grants/<user_id>/approval-check` | — | `{hfc_score, risk_level, latest_evaluation, checklist, can_approve}` |
| POST | `/admin/grants/<user_id>/approve` | `{approved_amount, approval_reason, missing_fields, confirmation_text}` | `{message}` |
| POST | `/admin/grants/access` | `{user_id, is_selected, selection_note}` | `{message}` |
| GET | `/admin/grants/access/<user_id>` | — | `{is_selected, selection_note, selected_by, selected_at}` |

#### HFC (Fraud Detection)

| Method | Path | Params / Body | Response |
|---|---|---|---|
| GET | `/admin/hfc/dashboard/stats` | — | `{pending, review, cleared, failed, total}` |
| GET | `/admin/hfc/queue` | `?page, per_page, risk, hfc_status, district, search` | `{data, total}` |
| GET | `/admin/hfc/applicant/<user_id>` | — | `{evaluations, review_actions, checklist}` |
| POST | `/admin/hfc/applicant/<user_id>/action` | `{action_type, comment}` | `{message}` |
| POST | `/admin/hfc/applicant/<user_id>/recalculate` | — | `{message, new_score}` |

#### User Management

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/admin/users` | — | `[{user_id, email, first_name, last_name, cnic, status, created_at}]` |
| POST | `/admin/users/<user_id>/status` | `{status: 'blocked'|'unblocked'}` | `{message}` |
| POST | `/admin/users/<user_id>/reset-password` | — | `{message}` |

#### Applicant Status

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/admin/applicant-status/eligible-users` | — | `[users with business profiles]` |
| GET | `/admin/applicant-status` | — | `[{status_id, user_id, status, decision_justification, updated_at}]` |
| POST | `/admin/applicant-status` | `{user_id, status, decision_justification, supporting_documents}` | `{message}` |
| DELETE | `/admin/applicant-status/<user_id>` | — | `{message}` |
| POST | `/admin/applicant-status/generate-upload-url` | `{file_name, mime_type}` | `{upload_url, object_key}` |

#### Content Management

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/admin/updates` | — | `[updates]` |
| POST | `/admin/updates` | `{title, body, tag}` | `{message, update_id}` |
| PUT | `/admin/updates/<update_id>` | `{title, body, tag}` | `{message}` |
| DELETE | `/admin/updates/<update_id>` | — | `{message}` |
| GET | `/admin/faqs` | — | `[faqs]` |
| POST | `/admin/faqs` | `{question, answer, keywords, category}` | `{message, faq_id}` |
| PUT | `/admin/faqs/<faq_id>` | `{question, answer, keywords, category, is_active}` | `{message}` |
| DELETE | `/admin/faqs/<faq_id>` | — | `{message}` |

#### Maintenance / DB Browser

| Method | Path | Params | Response |
|---|---|---|---|
| POST | `/admin/maintenance/cleanup-duplicates` | — | `{message, removed_count}` |
| GET | `/admin/db-browser/tables` | — | `[table_names]` |
| GET | `/admin/db-browser/data/<table_name>` | `?page, per_page` | `{columns, data, total}` |

---

## 12. Key Business Rules

1. **Registration closed**: `pre_register_logic` and `register_user_logic` both return 403. Any Go rewrite must reproduce this toggle via `GRANT_APPLICATION_OPEN`.

2. **Grant access control**: If `GRANT_REQUIRE_SELECTION=1`, a user must have `grant_access_whitelist.is_selected = TRUE` before they can POST to `/api/grant`. The GET response includes `access_state` field indicating whitelist status.

3. **One business per user**: `businesses.user_id` is UNIQUE. A user creates a profile once and edits it with PUT.

4. **One grant per user**: `grants.user_id` is UNIQUE. Grant is submitted once and can be updated in draft state.

5. **Allowed districts**: Only businesses in Swat, Shangla, Upper Dir, Upper Chitral, Lower Chitral are accepted. The district check is enforced in `user_service.py`.

6. **HFC does not block approval in shadow mode**: When `HFC_SHADOW_MODE=1`, admins see HFC scores but can approve regardless.

7. **Admin roles**: Two roles exist — `admin` (full access) and `approving_authority` (can approve grants). `can_approve_grants` flag controls the approve endpoint.

8. **Login gating**: `users.status = 'blocked'` returns a specific error on login. The `applicant_status` table (Eligible/Ineligible) is **not** checked at login — it is a separate tracking record.

9. **Language neutrality**: Form radio button values are stored as English strings regardless of the UI language. Urdu translation only affects display labels.

10. **CNIC format**: Stored as-is (string, up to 25 chars). The 13-digit Pakistani CNIC is expected.

---

## 13. Bilingual (Urdu) Support

- Language stored in `localStorage` as `'english'` or `'urdu'`.
- Each view has a `translations` object with `en` and `ur` keys.
- `isUrdu = computed(() => localStorage.getItem('language') === 'urdu')`.
- All text rendered via `t.sectionName.label` where `t = isUrdu ? translations.ur : translations.en`.
- RTL layout: `:class="{ 'text-right font-urdu': isUrdu }"` on text elements; `:class="{ 'flex-row-reverse': isUrdu }"` on flex rows.
- A custom `font-urdu` CSS class applies a Urdu web font (Noto Nastaliq Urdu or similar).
- FAQ search backend has a transliteration hint layer for Urdu queries.

---

## 14. Pending / Disabled Features

| Feature | State | Notes |
|---|---|---|
| Password reset | Disabled (returns 403) | Infrastructure exists (`send_reset_email`, token table design), but `password_reset_tokens` table not created and logic not implemented |
| New registrations | Closed | Toggle `GRANT_APPLICATION_OPEN=1` to open |
| ML-based HFC scoring | Optional | `ml_model` module; falls back gracefully if unavailable |
| Cloudinary | Config only | `CLOUDINARY_CLOUD_NAME` set but not used in code |
| Go processor | Stub | `backend-go/` exists with a Dockerfile but contains no working logic |
| Mobile app | Partial | Capacitor 7 configured in frontend but not built/deployed |

---

## 15. Migration History (init_db.py)

| Version | Changes |
|---|---|
| 1 | Create `users`, `businesses`, `documents` tables |
| 2 | Create `grants` table |
| 3 | Add expression_of_interest, grant_required, application_date to grants |
| 4 | Add document storage fields |
| 5 | Add initial schema indexes |
| 6 | Create `grant_media` table |
| 7 | Add `how_did_you_hear` to users |
| 8 | Create `initial_registrations` table |
| 9 | Add `middle_name`, `gender`, `mobile_no`, `whatsapp_number`, `terms_accepted` to users |
| 10 | Rename `documents` to `business_documents` |
| 11 | Add mime_type to business_documents |
| 12 | Create `updates` table |
| 13 | Create `faqs` table |
| 14 | Add performance indexes (grants, businesses) |
| 15 | Add indexes on users.cnic, users.created_at |
| 16 | Create `grant_approval_logs`; add approval fields to grants |
| 17 | Create `hfc_evaluations`, `hfc_review_actions`, `hfc_rule_config`; add HFC fields to grants |
| 18 | Create `grant_access_whitelist` |
| 19 | Create `applicant_status` with auto-trigger |
| 20 | Add `status` column to users |
| 21 | Add domicile, business_type, tax, employment, SRSP fields to grants |
| 22 | (reserved / skipped) |
| 23 | Add `has_srsp_relative`, `srsp_relatives` to grants |

---

## 16. Go Rewrite — Implementation Notes

### What to replicate exactly

- **All 70+ API endpoints** with identical paths, methods, request shapes, and response shapes.
- **JWT algorithm**: HS256. Same `JWT_SECRET_KEY`. Tokens issued by Go must be verifiable by the Vue frontend which only stores and sends them as opaque strings.
- **bcrypt**: Use `golang.org/x/crypto/bcrypt` for password verification. Admin passwords are already hashed and stored in env var.
- **JSONB fields**: Deserialise to Go slices/maps; re-serialise as JSON when writing back. Preserve null-vs-empty-array distinction where needed.
- **Pagination shape**: `{data: [...], total: int, page: int, per_page: int}` — frontend depends on this exact shape.
- **Redis key prefix**: `peace_sme` — keep consistent so existing cached data is not served stale.
- **RQ job format**: If rewriting the worker too, replicate the same debouncing logic and same queue names (`emails`, `hfc`).
- **S3 presigned URLs**: Use AWS SDK v2 for Go with path-style forcing. URL validity: 60 minutes.
- **Geo-block header**: Read `CF-IPCountry` or `X-Country-Code` from request headers.
- **Concurrent session control**: Redis SETEX with 90s TTL; max 300 keys matching prefix pattern `peace_sme:session:*`.

### Suggested Go project structure

```
backend-go/
├── cmd/server/main.go
├── internal/
│   ├── auth/           JWT + bcrypt
│   ├── db/             pgx pool + helpers
│   ├── cache/          Redis client
│   ├── s3/             S3 client
│   ├── mail/           Brevo client
│   ├── security/       Middleware (geo, rate, auth)
│   ├── user/           user_service equivalents
│   ├── business/
│   ├── grant/
│   ├── report/
│   ├── admin/
│   ├── hfc/
│   ├── status/
│   └── content/        updates, faqs
├── migrations/         SQL files matching init_db.py
└── Dockerfile
```

### Vue.js 3 frontend

The frontend **does not need to change** unless the API contract changes. If the Go backend serves identical JSON at the same paths, the existing Vue 3 frontend works without modification. The only file to update is `frontend/src/apiConfig.js` if the base URL changes.

If rebuilding the frontend in Vue 3:
- Use the same Composition API pattern (`setup`, `ref`, `reactive`, `computed`, `watch`, `onMounted`).
- Copy the `translations` objects as-is for bilingual support.
- Recreate the same `router/index.js` route guard logic.
- Keep `userToken` / `adminToken` key names in localStorage.
- Tailwind CSS 3 for styling.

---

*End of document.*
