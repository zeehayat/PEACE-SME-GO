# Chapter 1: Read the Existing System Like an Engineer

## Purpose

Before writing a single line of Go or Vue code, you must understand the system you are rebuilding. This chapter teaches a professional habit that separates senior engineers from beginners: do not start a rewrite by opening an editor and inventing code. Start by reading the system until you can describe what must remain true after the rewrite.

The PEACE SME Grant Portal is not just a set of pages. It is a workflow system:

1. Applicant registration and login.
2. Business profile entry and document upload.
3. Admin eligibility decisions.
4. Whitelisted grant application submission.
5. HFC fraud detection scoring.
6. Approval by an authorized approving authority.
7. Notifications, reports, CSV exports, FAQ management, and operational controls.

Every one of these steps has a precise behavior that the rewrite must preserve.

---

## Theory: What Is a Rewrite?

A rewrite is not "build a new app that looks similar." A rewrite is a controlled replacement of implementation while preserving all required behavior.

In this project:

- **Old implementation**: Flask (Python) backend + Vue 3 frontend.
- **New implementation**: Go backend + Vue 3 frontend.
- **Stable contract**: PostgreSQL schema, API paths, JSON shapes, JWT structure, auth behavior, business rules, and user workflows.

Think of the rewrite as replacing the engine of a running aircraft. The cockpit controls must continue to work. The frontend expects the same endpoints. The database stores the same business facts. Admins expect the same reports. Applicants expect the same workflow.

### The Two Levels of a System

Every system has two levels you must understand separately:

| Level | What it is | Examples |
|---|---|---|
| **Contract** | What other parts of the system depend on | API paths, JSON shapes, JWT claims, business rules |
| **Implementation** | How you satisfy the contract | Flask vs Go, sync vs async, SQL query structure |

The contract is fixed until you also migrate the frontend. The implementation is yours to design.

---

## How Senior Engineers Read Codebases

When a senior engineer encounters an unfamiliar codebase, they do not read every file top to bottom. They use a structured approach:

### Step 1: Read the Entry Point

Find where the application starts. In the Flask app, that is `app.py`. Every route is registered there. In the Go rewrite, it will be `cmd/server/main.go`.

```bash
# Find the entry point
ls backend/
cat backend/app.py | head -100
```

The entry point tells you:
- What libraries are used
- Which modules handle which routes
- What middleware runs before handlers
- What happens at startup

### Step 2: Read the Route Table

Every web application has a route table — a list mapping HTTP verbs and paths to handler functions. In Flask, routes look like:

```python
# From app.py
@app.route('/api/login', methods=['POST'])
def login():
    return user_service.login_user_logic()

@app.route('/api/business', methods=['GET', 'POST', 'PUT'])
@token_required
def business():
    return user_service.handle_business_profile_logic()
```

Your job: extract this table and map it to Go handlers you will write.

### Step 3: Trace One Request End to End

Pick one important workflow and follow it through every layer. For the PEACE SME portal, trace the grant submission:

```
Vue SmeGrantApplication.vue
  → axios.post('/api/grant', payload)
    → Flask POST /api/grant
      → token_required middleware (auth check)
        → grant_service.apply_for_grant_logic()
          → check grant_access_whitelist (if GRANT_REQUIRE_SELECTION=1)
          → INSERT INTO grants (...)
          → enqueue_hfc_recalculate(user_id) → Redis → RQ worker
            → run_hfc_recalculate_job()
              → calculate_hfc_for_user()
              → UPDATE grants SET hfc_score=...
```

This trace tells you:
- Which tables are touched
- Which environment toggles affect behavior
- What side effects occur (Redis queue, HFC scoring)
- What the response must look like

### Step 4: Read the Data Model

After understanding routes and flows, read the database schema. In the PEACE SME system, the schema lives in `backend/init_db.py`. Every `CREATE TABLE` statement tells you exactly what data the system manages.

```bash
grep -n "CREATE TABLE" backend/init_db.py
```

Expected output:
```
CREATE TABLE users (...)
CREATE TABLE businesses (...)
CREATE TABLE grants (...)
CREATE TABLE business_documents (...)
CREATE TABLE grant_media (...)
CREATE TABLE grant_approval_logs (...)
CREATE TABLE grant_access_whitelist (...)
CREATE TABLE applicant_status (...)
CREATE TABLE hfc_evaluations (...)
CREATE TABLE hfc_review_actions (...)
CREATE TABLE hfc_rule_config (...)
CREATE TABLE initial_registrations (...)
CREATE TABLE updates (...)
CREATE TABLE faqs (...)
CREATE TABLE schema_migrations (...)
```

### Step 5: Read the Environment Variables

Environment variables are the configuration layer. They control behavior without changing code. Reading `.env` or the environment variable reference tells you:

- What external services exist (S3, Redis, Brevo email, PostgreSQL)
- What feature toggles are in play
- What secrets must be provided at runtime

```bash
cat .env
```

Key toggles in the PEACE SME system:

| Variable | Current value | Effect |
|---|---|---|
| `GRANT_APPLICATION_OPEN` | `0` | Registration is closed — returns 403 |
| `GRANT_REQUIRE_SELECTION` | `1` | Only whitelisted users can submit grants |
| `HFC_SHADOW_MODE` | `1` | HFC scores calculated but don't block approval |
| `GEO_BLOCK_ENABLED` | `1` | Non-PK IPs are blocked |
| `ACCESS_CONTROL_ENABLED` | `1` | Max 300 concurrent sessions enforced |

---

## Git Log as a Reading Tool

`git log` is not just for history — it is a reading tool that tells you the sequence in which the system was built.

```bash
# Read the project's own construction log
git log --oneline --reverse

# What changed in a specific commit?
git show abc1234

# Who wrote which part of a file, and when?
git blame backend/services/grant_service.py

# When was a specific function added?
git log -S "def apply_for_grant_logic" --oneline

# What files changed between two points?
git diff v1.0..v1.1 --name-only
```

Reading git history answers:
- In what order was the system built?
- Which features were added late and might be less tested?
- Which parts of the code change frequently (risk areas)?
- What bugs were fixed, revealing edge cases?

### Practical: Read the PEACE SME Git History

```bash
cd E:\Programming\Go\PEACE-SME-GO

git log --oneline
# d18dc0c Initial steps
# 8e65358 Claude.md main.go
# 3fdc369 Add System reading notes
# 1fc0a6d Add First Go Entry Point
# 636027b First Commit

git show 8e65358
# Shows what was added in the Claude.md and main.go commit
```

---

## API Reverse-Engineering

When reading a Flask codebase to rewrite it in Go, you are reverse-engineering the API contract. Here is a systematic method:

### Extract All Endpoints

```bash
# Find all route decorators in the Flask app
grep -n "@app.route" backend/app.py
```

For each endpoint, capture:
1. Method (GET, POST, PUT, DELETE)
2. Path
3. Auth requirement (which decorator protects it?)
4. Request body shape
5. Response shape
6. Business rules applied

### Map Flask Decorators to Go Middleware

The Flask app uses decorators as middleware:

```python
# Flask patterns
@token_required          # → Go: auth middleware, reads JWT, sets user_id in context
@admin_required          # → Go: admin middleware, checks is_admin claim
@approver_required       # → Go: approver middleware, checks is_approver claim
```

In Go, these become middleware functions applied to route groups:

```go
// Go equivalent
router.Group(func(r chi.Router) {
    r.Use(middleware.AuthRequired)
    r.Post("/grant", grantHandler.Apply)
})

router.Group(func(r chi.Router) {
    r.Use(middleware.AdminRequired)
    r.Get("/admin/applicants", adminHandler.ListApplicants)
})
```

### Read the Service Layer

Flask routes delegate immediately to service functions. Read each service function to understand the business logic:

```python
# grant_service.py
def apply_for_grant_logic():
    user_id = get_jwt_identity()
    
    # Business rule: whitelist gate
    if os.environ.get('GRANT_REQUIRE_SELECTION') == '1':
        whitelist = query("SELECT is_selected FROM grant_access_whitelist WHERE user_id=%s", user_id)
        if not whitelist or not whitelist['is_selected']:
            return jsonify({"error": "Not selected"}), 403
    
    # Insert or update grant
    ...
```

This tells you exactly what your Go `GrantService.Apply()` method must do.

---

## Mapping Data Flows

A data flow diagram helps you understand how information moves through the system. Build one for the PEACE SME portal:

```
[Applicant Browser]
    |
    | HTTPS POST /api/grant (JWT in header, grant form in body)
    |
[Go HTTP Server: internal/grant/handler.go]
    |
    | Parse & validate request body
    | Extract user_id from JWT context
    |
[GrantService: internal/grant/service.go]
    |
    | Check whitelist (if GRANT_REQUIRE_SELECTION=1)
    |     └── [DB: grant_access_whitelist]
    |
    | INSERT grant row
    |     └── [DB: grants table]
    |
    | Enqueue HFC job
    |     └── [Redis: hfc queue]
    |             |
    |             └── [HFC Worker goroutine]
    |                     |
    |                     └── [DB: hfc_evaluations, UPDATE grants.hfc_score]
    |
[HTTP Response: {message, grant_id}]
    |
[Applicant Browser receives confirmation]
```

Build this diagram for every major workflow before writing code.

---

## Building a Mental Model

A mental model is a simplified internal representation of how the system works. For the PEACE SME portal, your mental model should include:

### The Three User Types

```
1. APPLICANT (SME owner)
   - Registers (when open)
   - Creates business profile
   - Uploads documents
   - Submits grant application (when whitelisted)
   - Waits for approval

2. ADMIN (SRSP staff)
   - Reviews applicant profiles
   - Sets eligibility status
   - Whitelists applicants for grant submission
   - Reviews submitted grants
   - Manages reports and exports
   - Cannot approve grants (unless has approving_authority role)

3. APPROVING AUTHORITY (senior SRSP staff)
   - Has all admin capabilities
   - Can approve or reject grant applications
   - Sets approved_amount and approval_reason
```

### The Lifecycle of a Grant

```
[Registration Closed] → applicant waits

[Registration Open] → applicant registers → fills business profile → uploads documents
                                                                           ↓
[Admin reviews] → marks Eligible/Ineligible/Decision Pending
                                                                           ↓
[Admin whitelists applicant] → applicant.grant_access_whitelist.is_selected = true
                                                                           ↓
[Applicant submits grant] → grants.status = 'Pending'
                         → HFC job enqueued → score calculated
                                                                           ↓
[Approving authority reviews] → sees HFC score (shadow mode: non-blocking)
                              → sets grants.status = 'Approved' or 'Rejected'
                              → email sent to applicant
```

### The Feature Toggle System

```
GRANT_APPLICATION_OPEN = 0  →  Registration endpoints return 403
GRANT_APPLICATION_OPEN = 1  →  Registration endpoints accept new users

GRANT_REQUIRE_SELECTION = 0  →  Any registered user can submit a grant
GRANT_REQUIRE_SELECTION = 1  →  Only whitelisted users can submit

HFC_SHADOW_MODE = 0  →  HFC score blocks approval if HIGH/CRITICAL
HFC_SHADOW_MODE = 1  →  HFC score visible but cannot block approval

GEO_BLOCK_ENABLED = 0  →  All IPs accepted
GEO_BLOCK_ENABLED = 1  →  Only ALLOWED_COUNTRY_CODES IPs accepted (currently PK)
```

---

## Complete Endpoint Map

Build this table before writing a single Go handler. Every row is a unit of work:

### Public Endpoints (no auth)

| Method | Path | Vue View | Go Package | Tables | Rules |
|---|---|---|---|---|---|
| POST | `/api/pre-registration` | `RegistrationForm.vue` | `internal/user` | `initial_registrations` | CNIC must exist in list |
| POST | `/api/register` | `RegistrationForm.vue` | `internal/user` | `users` | GRANT_APPLICATION_OPEN=1 required |
| POST | `/api/login` | `UserLogin.vue` | `internal/user`, `internal/auth` | `users` | status != 'blocked' |
| POST | `/api/forgot-password` | `ForgotPassword.vue` | `internal/user` | — | Returns 403 DISABLED |
| POST | `/api/reset-password` | `ResetPassword.vue` | `internal/user` | — | Returns 403 DISABLED |
| POST | `/api/admin/login` | `AdminLogin.vue` | `internal/auth` | — | bcrypt check against ADMIN_USERS_JSON |
| GET | `/api/updates` | `MainLandingPage.vue` | `internal/content` | `updates` | Redis cached 3600s |
| GET | `/api/faqs` | `FAQBot.vue` | `internal/content` | `faqs` | Redis cached 300s |
| GET | `/api/faqs/search` | `FAQBot.vue` | `internal/content` | `faqs` | Fuzzy search |
| GET | `/api/system/access-status` | `WaitingRoom.vue` | `internal/security` | — | Redis session slots |

### Applicant Endpoints (JWT required)

| Method | Path | Vue View | Go Package | Tables | Rules |
|---|---|---|---|---|---|
| GET | `/api/user/profile` | `AppDashboard.vue` | `internal/user` | `users`, `businesses` | user_id from JWT |
| GET | `/api/business` | `SmeBusinessProfile.vue` | `internal/business` | `businesses` | user_id from JWT |
| POST | `/api/business` | `SmeBusinessProfile.vue` | `internal/business` | `businesses` | one per user |
| PUT | `/api/business` | `SmeBusinessProfile.vue` | `internal/business` | `businesses` | district validation |
| POST | `/api/upload-document/:business_id` | `AppDashboard.vue` | `internal/storage` | `business_documents` | multipart, S3 upload |
| POST | `/api/business/media/generate-upload-url` | `AppDashboard.vue` | `internal/storage` | — | presigned PUT URL |
| POST | `/api/business/media/save-reference` | `AppDashboard.vue` | `internal/storage` | `business_documents` | save S3 key |
| GET | `/api/grant` | `SmeGrantApplication.vue` | `internal/grant` | `grants`, `grant_access_whitelist` | includes access_state |
| POST | `/api/grant` | `SmeGrantApplication.vue` | `internal/grant` | `grants` | whitelist gate |
| PUT | `/api/grant` | `SmeGrantApplication.vue` | `internal/grant` | `grants` | re-enqueue HFC |
| GET | `/api/grant-status` | `AppDashboard.vue` | `internal/grant` | `grants` | status, approved_amount |
| POST | `/api/grant/generate-upload-url` | `RecordingCapture.vue` | `internal/storage` | — | presigned PUT URL |
| POST | `/api/grant/save-media-reference` | `RecordingCapture.vue` | `internal/storage` | `grant_media` | audio or video |

### Admin Endpoints (admin JWT required)

| Method | Path | Go Package | Tables | Notes |
|---|---|---|---|---|
| GET | `/api/admin/applicants` | `internal/report` | `users`, `businesses` | all users |
| GET | `/api/admin/applicants/registered` | `internal/report` | `users` | recent N |
| GET | `/api/admin/applicants/report` | `internal/report` | `users`, `businesses`, `business_documents` | paginated, filterable |
| GET | `/api/admin/applicants/:user_id` | `internal/report` | all tables | full detail |
| GET | `/api/admin/applicants/:user_id/pdf` | `internal/report` | all tables | PDF binary |
| GET | `/api/admin/reports/applied-detailed` | `internal/report` | `grants`, `users`, `businesses` | paginated |
| GET | `/api/admin/reports/filter-options` | `internal/report` | multiple | Redis cached |
| GET | `/api/admin/reports/approved-grants` | `internal/report` | `grants`, `grant_approval_logs` | — |
| GET | `/api/admin/reports/full-applicant-profiles` | `internal/report` | all | no filters |
| GET | `/api/admin/reports/full-applicant-profiles/csv` | `internal/report` | all | query token auth |
| GET | `/api/admin/reports/business-profiles/csv` | `internal/report` | `businesses` | query token auth |
| GET | `/api/admin/reports/fully-verified` | `internal/report` | `business_documents` | all 5 doc types |
| GET | `/api/admin/reports/missing-documents` | `internal/report` | `business_documents` | missing any doc |
| GET | `/api/admin/reports/eligibility-criteria` | `internal/report` | `applicant_status` | grouped counts |
| GET | `/api/admin/grants/submitted` | `internal/report` | `grants`, `users` | paginated |
| GET | `/api/admin/grants/:user_id/approval-check` | `internal/grant` | `grants`, `hfc_evaluations` | approver only |
| POST | `/api/admin/grants/:user_id/approve` | `internal/grant` | `grants`, `grant_approval_logs` | approver only |
| POST | `/api/admin/grants/access` | `internal/grant` | `grant_access_whitelist` | whitelist upsert |
| GET | `/api/admin/grants/access/:user_id` | `internal/grant` | `grant_access_whitelist` | get whitelist row |
| GET | `/api/admin/hfc/dashboard/stats` | `internal/hfc` | `grants` | HFC counts |
| GET | `/api/admin/hfc/queue` | `internal/hfc` | `grants`, `hfc_evaluations` | paginated |
| GET | `/api/admin/hfc/applicant/:user_id` | `internal/hfc` | `hfc_evaluations`, `hfc_review_actions` | detail |
| POST | `/api/admin/hfc/applicant/:user_id/action` | `internal/hfc` | `hfc_review_actions`, `grants` | mark_clear etc |
| POST | `/api/admin/hfc/applicant/:user_id/recalculate` | `internal/hfc` | `hfc_evaluations` | trigger rescore |
| GET | `/api/admin/users` | `internal/admin` | `users` | all users |
| POST | `/api/admin/users/:user_id/status` | `internal/admin` | `users` | block/unblock |
| GET | `/api/admin/applicant-status/eligible-users` | `internal/status` | `users`, `businesses` | has business profile |
| GET | `/api/admin/applicant-status` | `internal/status` | `applicant_status` | all rows |
| POST | `/api/admin/applicant-status` | `internal/status` | `applicant_status` | upsert |
| DELETE | `/api/admin/applicant-status/:user_id` | `internal/status` | `applicant_status` | delete row |
| GET | `/api/admin/updates` | `internal/content` | `updates` | all |
| POST | `/api/admin/updates` | `internal/content` | `updates` | create |
| PUT | `/api/admin/updates/:update_id` | `internal/content` | `updates` | update |
| DELETE | `/api/admin/updates/:update_id` | `internal/content` | `updates` | delete |
| GET | `/api/admin/faqs` | `internal/content` | `faqs` | all |
| POST | `/api/admin/faqs` | `internal/content` | `faqs` | create |
| PUT | `/api/admin/faqs/:faq_id` | `internal/content` | `faqs` | update |
| DELETE | `/api/admin/faqs/:faq_id` | `internal/content` | `faqs` | delete |
| POST | `/api/admin/maintenance/cleanup-duplicates` | `internal/admin` | `business_documents` | dedup |
| GET | `/api/admin/db-browser/tables` | `internal/admin` | `information_schema` | table names |
| GET | `/api/admin/db-browser/data/:table_name` | `internal/admin` | any | paginated rows |

---

## Reading Flask Code and Mapping to Go

This section shows concrete examples of reading Flask code and understanding what equivalent Go code must do.

### Example 1: Login Handler

**Flask (what you read):**

```python
# backend/services/user_service.py
def login_user_logic():
    data = request.get_json()
    email = data.get('email_address')
    password = data.get('password')
    
    user = query_one("SELECT * FROM users WHERE email_address=%s", email)
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401
    
    if user['status'] == 'blocked':
        return jsonify({"error": "Account blocked"}), 403
    
    if not bcrypt.check_password_hash(user['hashed_password'], password):
        return jsonify({"error": "Invalid credentials"}), 401
    
    token = jwt.encode(
        {"user_id": user['user_id'], "exp": datetime.utcnow() + timedelta(hours=24)},
        JWT_SECRET_KEY,
        algorithm="HS256"
    )
    
    return jsonify({"token": token, "user_id": user['user_id'], "language": user['language']}), 200
```

**What you learn from reading this:**
- Request body fields: `email_address`, `password`
- DB lookup: by `email_address`
- Auth check: bcrypt comparison
- Status check: `blocked` means 403 (distinct error from wrong password)
- JWT payload: `user_id`, `exp` (24h)
- Response shape: `{token, user_id, language}`

**Go equivalent you will write:**

```go
// internal/user/handler.go
type LoginRequest struct {
    EmailAddress string `json:"email_address"`
    Password     string `json:"password"`
}

type LoginResponse struct {
    Token    string `json:"token"`
    UserID   int64  `json:"user_id"`
    Language string `json:"language"`
}

func (h *Handler) Login(w http.ResponseWriter, r *http.Request) {
    var req LoginRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        http.Error(w, `{"error":"invalid request"}`, http.StatusBadRequest)
        return
    }

    resp, err := h.svc.Login(r.Context(), req.EmailAddress, req.Password)
    if err != nil {
        switch {
        case errors.Is(err, ErrInvalidCredentials):
            http.Error(w, `{"error":"Invalid credentials"}`, http.StatusUnauthorized)
        case errors.Is(err, ErrUserBlocked):
            http.Error(w, `{"error":"Account blocked"}`, http.StatusForbidden)
        default:
            http.Error(w, `{"error":"internal server error"}`, http.StatusInternalServerError)
        }
        return
    }

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(resp)
}
```

### Example 2: Reading a Business Rule

**Flask (the whitelist gate):**

```python
# backend/services/grant_service.py
def apply_for_grant_logic():
    user_id = get_jwt_identity()
    
    if os.environ.get('GRANT_REQUIRE_SELECTION') == '1':
        row = query_one(
            "SELECT is_selected FROM grant_access_whitelist WHERE user_id = %s",
            user_id
        )
        if not row or not row['is_selected']:
            return jsonify({
                "error": "You have not been selected to apply for a grant.",
                "access_state": "not_selected"
            }), 403
```

**What you learn:**
- The toggle is checked at runtime from environment (not config loaded once)
- The error response must include `access_state: "not_selected"` — the frontend reads this field
- 403 is the correct status code for this business rule violation

**Go equivalent:**

```go
// internal/grant/service.go
func (s *Service) Apply(ctx context.Context, userID int64, req ApplyRequest) error {
    if s.cfg.GrantRequireSelection {
        row, err := s.repo.GetWhitelistEntry(ctx, userID)
        if err != nil || !row.IsSelected {
            return ErrNotWhitelisted // maps to 403 + access_state in handler
        }
    }
    // ... proceed with INSERT
}
```

### Example 3: Reading Middleware

**Flask middleware pattern:**

```python
# backend/services/security.py
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        try:
            data = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
            g.user_id = data['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated
```

**Go equivalent middleware:**

```go
// internal/security/middleware.go
func AuthRequired(cfg *config.Config) func(http.Handler) http.Handler {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            authHeader := r.Header.Get("Authorization")
            if !strings.HasPrefix(authHeader, "Bearer ") {
                http.Error(w, `{"error":"missing token"}`, http.StatusUnauthorized)
                return
            }
            tokenStr := strings.TrimPrefix(authHeader, "Bearer ")

            claims, err := auth.ParseUserToken(tokenStr, cfg.JWTSecret)
            if err != nil {
                if errors.Is(err, auth.ErrExpiredToken) {
                    http.Error(w, `{"error":"Token expired"}`, http.StatusUnauthorized)
                    return
                }
                http.Error(w, `{"error":"Invalid token"}`, http.StatusUnauthorized)
                return
            }

            ctx := context.WithValue(r.Context(), ContextKeyUserID, claims.UserID)
            next.ServeHTTP(w, r.WithContext(ctx))
        })
    }
}
```

---

## Dependency Tracing

Dependency tracing means following the imports to understand what a module needs in order to work.

### Tracing the Grant Service

```python
# grant_service.py imports
import os              # → environment variables (toggles)
from flask import request, jsonify, g  # → HTTP framework
from services.database import query_one, execute  # → PostgreSQL access
from services.cache_service import cache_get_json, cache_set_json  # → Redis
from services.hfc_service import enqueue_hfc_recalculate  # → background job queue
```

This tells you: to implement `GrantService` in Go, you need:
- Config (for toggles)
- DB pool (for queries)
- Cache client (for Redis caching)
- HFC enqueuer (for background jobs)

In Go, you express these dependencies as interface parameters:

```go
type GrantService struct {
    cfg    *config.Config
    repo   GrantRepository
    cache  cache.Client
    hfc    HFCEnqueuer
}

func NewGrantService(
    cfg *config.Config,
    repo GrantRepository,
    cache cache.Client,
    hfc HFCEnqueuer,
) *GrantService {
    return &GrantService{cfg: cfg, repo: repo, cache: cache, hfc: hfc}
}
```

---

## The API Contract Document

Your most important pre-coding artifact is the API contract document. Before writing any handler, document the exact contract you are implementing.

Here is the template for one endpoint:

```markdown
## POST /api/grant

**Auth**: Bearer userToken (user JWT)
**Content-Type**: application/json

### Request Body
```json
{
  "expression_of_interest": ["Manufacturing", "Other"],
  "other_purpose_text": "Textile processing",
  "grant_required": 500000,
  "grant_amount_words": "Five Hundred Thousand",
  "application_date": "2026-01-15",
  "working_capital": false,
  "financed_items": [
    {"item": "Loom Machine", "quantity": 2, "estimated_cost": 150000}
  ],
  "contribution_type": "Cash/Financial",
  "financial_amount": 50000,
  "financial_amount_words": "Fifty Thousand",
  "inkind_details": "",
  "inkind_value": null,
  "contribution_utilization": "Purchase raw materials",
  "grant_support_growth": "Will increase production by 40%",
  "job_creation_details": "Will hire 5 female weavers",
  "how_did_you_hear": "Social Media",
  "domicile_district": "Swat",
  "business_type": ["Manufacturing"],
  "business_type_other": "",
  "tax_registration_status": ["Registered (NTN/STRN)"],
  "ntn_registration_no": "1234567",
  "tax_filer_status": "Active",
  "expected_production_increase": "40%",
  "employment_grid": {
    "before_male": 2, "before_female": 1,
    "after_male": 4, "after_female": 3
  },
  "declaration_accepted": true,
  "declaration_name": "Muhammad Ali Khan",
  "has_srsp_relative": false,
  "srsp_relatives": []
}
```

### Success Response (201)
```json
{"message": "Grant application submitted successfully", "grant_id": 42}
```

### Error Responses
- 403: User not whitelisted (`{"error":"...", "access_state":"not_selected"}`)
- 409: Grant already submitted (`{"error":"Grant already exists"}`)
- 422: Validation failure (`{"error":"...", "field":"grant_required"}`)
- 500: Server error
```

---

## Reading the Frontend to Understand Contracts

The Vue frontend is the authoritative consumer of your API. Reading it tells you exactly what the contract must look like.

### Reading apiConfig.js

```javascript
// frontend/src/apiConfig.js
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000';
export default API_BASE_URL;
```

This tells you: the Go backend must listen at port 5000 (or whatever the env var says) to be compatible without changing the frontend.

### Reading a Vue Component's API Call

```javascript
// From SmeGrantApplication.vue
const submitGrant = async () => {
    try {
        const token = localStorage.getItem('userToken');
        const response = await axios.post(
            `${API_BASE_URL}/api/grant`,
            formData.value,
            { headers: { Authorization: `Bearer ${token}` } }
        );
        // Uses response.data.grant_id
        router.push('/dashboard');
    } catch (error) {
        if (error.response?.status === 403) {
            // Checks error.response.data.access_state
            if (error.response.data.access_state === 'not_selected') {
                showNotSelectedMessage.value = true;
            }
        }
    }
};
```

This tells you:
- The `Authorization` header format: `Bearer <token>`
- The localStorage key: `userToken`
- The success path uses `response.data.grant_id`
- The 403 error response must contain `access_state` field

### Reading the Router Guards

```javascript
// frontend/src/router/index.js
router.beforeEach((to, from, next) => {
    if (to.meta.requiresAuth) {
        const token = localStorage.getItem('userToken');
        if (!token) {
            next('/login');
            return;
        }
    }
    if (to.meta.requiresAdmin) {
        const token = localStorage.getItem('adminToken');
        if (!token) {
            next('/admin/login');
            return;
        }
    }
    next();
});
```

This tells you: the JWT token is stored opaquely in localStorage — the frontend does not inspect its claims. It only checks for presence. So your Go tokens just need to be valid JWTs with the right signing key and expiry.

---

## The Complete System Map

Here is the full system map you build from reading:

| User action | Vue view | API endpoint | Go package | Tables touched | Business rule |
|---|---|---|---|---|---|
| Visit homepage | `MainLandingPage.vue` | GET `/api/updates` | `internal/content` | `updates` | Redis cached |
| Check language | `LanguageSelection.vue` | — | — | — | localStorage only |
| Accept T&C | `TermsAndConditions.vue` | — | — | — | localStorage only |
| Register | `RegistrationForm.vue` | POST `/api/register` | `internal/user` | `users` | GRANT_APPLICATION_OPEN=1 |
| Login | `UserLogin.vue` | POST `/api/login` | `internal/user`, `internal/auth` | `users` | status != blocked |
| View dashboard | `AppDashboard.vue` | GET `/api/user/profile` | `internal/user` | `users`, `businesses` | user JWT |
| Create business profile | `SmeBusinessProfile.vue` | POST `/api/business` | `internal/business` | `businesses` | district validation |
| Upload CNIC | `AppDashboard.vue` | POST `/api/upload-document/:id` | `internal/storage` | `business_documents` | multipart to S3 |
| Submit grant | `SmeGrantApplication.vue` | POST `/api/grant` | `internal/grant` | `grants` | whitelist gate |
| Admin login | `AdminLogin.vue` | POST `/api/admin/login` | `internal/auth` | — | ADMIN_USERS_JSON |
| Admin set eligible | `AdminApplicantStatus.vue` | POST `/api/admin/applicant-status` | `internal/status` | `applicant_status` | — |
| Admin whitelist | `AdminUserAccess.vue` | POST `/api/admin/grants/access` | `internal/grant` | `grant_access_whitelist` | — |
| Admin approve grant | `AdminGrantDetail.vue` | POST `/api/admin/grants/:id/approve` | `internal/grant` | `grants`, `grant_approval_logs` | approver role |

---

## Beginner Go Lens: What This System Teaches You

The PEACE SME portal teaches Go in layers through concrete problems:

| Layer | Problem to solve | Go concept learned |
|---|---|---|
| Config | Parse environment toggles | `os.Getenv`, `strconv`, `encoding/json` |
| DB | Store and retrieve users and grants | `pgx`, SQL, structs, error handling |
| Auth | JWT signing and verification | `golang-jwt/jwt`, bcrypt, middleware |
| HTTP | Handle 70+ routes | `net/http`, chi router, JSON encode/decode |
| Validation | Validate the 9-section grant form | custom error types, struct validation |
| Storage | Upload files to S3-compatible storage | AWS SDK v2, presigned URLs |
| Cache | Cache dashboard stats and filter options | go-redis v9, JSON serialization |
| Workers | Run HFC scoring and email sending asynchronously | goroutines, channels, context |
| Testing | Verify handlers return correct JSON | `httptest`, mock interfaces, table-driven tests |

Do not try to master all these concepts before building. Learn each feature when the application gives you a reason to use it.

---

## Exercise: Build Your Contract Notes File

Create this file now, before writing any Go code:

```bash
mkdir -p guide
# Create your contract notes
```

The file `guide/app-contract-notes.md` should contain:

```markdown
# PEACE SME Portal — API Contract Notes

## Auth Contracts
- User JWT: HS256, payload: {user_id, exp}, expiry: 24h
- Admin JWT: HS256, payload: {admin_username, role, is_admin, is_approver, exp}, expiry: 8h
- Header format: Authorization: Bearer <token>
- localStorage keys: userToken (user), adminToken (admin)

## Response Shape Contracts
- Pagination: {data: [...], total: int, page: int, per_page: int}
- Login: {token: string, user_id: int, language: string}
- Grant submit: {message: string, grant_id: int}
- Error: {error: string} with optional extra fields (access_state, field)

## Business Rule Contracts
- GRANT_APPLICATION_OPEN=0 → POST /register returns 403
- GRANT_REQUIRE_SELECTION=1 → POST /grant returns 403 if not whitelisted
- HFC_SHADOW_MODE=1 → HFC score stored but approval not blocked
- Allowed districts: Swat, Shangla, Upper Dir, Upper Chitral, Lower Chitral
- status='blocked' → login returns 403 (different from invalid credentials 401)

## Endpoints to Implement (checkboxes)
- [ ] POST /api/login
- [ ] GET /api/business
- [ ] POST /api/grant
... (add all 70+ endpoints)
```

---

## Git Practice: System Reading Branch

```bash
git status
git checkout -b chapter-01-system-reading
git add guide/
git commit -m "Add system contract notes from reading exercise"
```

Use `git diff --staged` before committing to review what you are about to record.

---

## Mastery Check

You understand this chapter when you can explain:

1. Why the Go rewrite must preserve the exact Flask API contract, including error response shapes and HTTP status codes.
2. What the `GRANT_REQUIRE_SELECTION` toggle controls and how it affects the POST /api/grant handler.
3. Which Flask modules map to which Go packages, and what each package is responsible for.
4. How to trace a single user action (e.g., grant submission) through Vue → API → service → database → background job → response.
5. What the difference is between a "contract" and an "implementation", and why beginners confuse them during rewrites.
