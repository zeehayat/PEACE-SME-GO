# Chapter 18: Project Parallel Workbook

## Purpose

This chapter turns the book into a build plan. Each row pairs a concept with a concrete PEACE SME implementation task. Use it when you ask, "What should I build to understand this topic?"

## Parallel Task Table

| Learning topic | Theory to study | Backend task | Vue task | Git task |
|---|---|---|---|---|
| HTTP routing | request methods, paths, status codes | implement `/health` and `/api/updates` | show updates on landing page | commit route and handler separately |
| JSON encoding | struct tags, request decoding | implement `ReadJSON` and `WriteJSON` | consume JSON with Axios | inspect diff for response names |
| Config | env vars, defaults, validation | parse `GRANT_APPLICATION_OPEN` | show registration closed page | add config tests before commit |
| Auth | JWT, bcrypt, bearer headers | implement `/api/login` | store `userToken` | branch `feature/user-login` |
| Admin auth | roles and permissions | implement `/api/admin/login` | store `adminToken` | commit admin claims tests |
| Middleware | chain of handlers | auth, geo-block, access slot middleware | redirect unauthenticated routes | diff middleware order |
| Database | schema, indexes, joins | migrate `users`, `businesses` | dashboard fetches profile | tag first DB milestone |
| Transactions | atomic multi-step writes | approve grant and log action | approval button | commit failing test then fix |
| JSONB | typed nested data | save `financed_items` | dynamic item rows | review JSON names |
| Validation | business rule enforcement | allowed districts, contribution rules | inline form errors | commit validation table tests |
| Uploads | presigned URLs, object keys | generate upload URL | document upload component | branch `feature/uploads` |
| Redis | TTL, cache, debounce | cache FAQs and updates | FAQ drawer consumes API | commit cache invalidation |
| Reports | pagination, filters, sorting | applicant report endpoint | admin table filters | compare query params diff |
| CSV | streaming, query tokens | full applicant export | export button | add token expiry test |
| HFC | deterministic scoring | calculate score and risk | HFC queue display | commit rule tests one by one |
| Workers | durable background jobs | enqueue HFC and email jobs | show pending state | tag async milestone |
| Bilingual UI | translation dictionaries, RTL | return language from login | language switcher | commit English/Urdu together |
| Deployment | containers, migrations | Dockerfile and migration runner | static frontend build | tag release candidate |

## Milestone 1: Skeleton That Teaches Go Basics

Goal: make the Go program feel understandable.

Build:

- `cmd/server/main.go`
- `internal/config`
- `internal/httpx`
- `internal/health`
- `internal/app`

Theory:

- packages
- exported vs unexported names
- functions
- structs
- pointers
- errors

Portal feature:

- `/health` proves the server runs.
- `/api/updates` proves a public JSON route works.

Vue parallel:

- create a landing page section that calls `/api/updates`.

Git:

```bash
git checkout -b milestone-01-server-skeleton
git commit -m "Add Go server skeleton"
git commit -m "Add public updates endpoint"
```

Done when:

- `go test ./...` passes.
- `/health` returns JSON.
- `/api/updates` returns an empty list or seeded rows.

## Milestone 2: Login Vertical Slice

Goal: understand web auth end to end.

Build:

- `users` table migration.
- `UserRepository.FindByEmail`.
- bcrypt password verification.
- JWT token generation.
- `POST /api/login`.
- Vue login page.
- route guard for `/dashboard`.

Theory:

- SQL query result scanning.
- nullable values.
- service errors.
- JWT claims.
- localStorage.
- Axios headers.

Portal feature:

- applicant logs in with email and password.
- blocked user receives a specific failure.
- successful login returns `{token, user_id, language}`.

Git:

```bash
git checkout -b feature/user-login
git commit -m "Add user login repository"
git commit -m "Add JWT user token service"
git commit -m "Implement user login endpoint"
git commit -m "Add Vue user login flow"
```

Done when:

- invalid password fails.
- blocked user fails.
- valid login stores `userToken`.
- authenticated route sends `Authorization: Bearer`.

## Milestone 3: Business Profile

Goal: learn create/update workflows and validation.

Build:

- `businesses` migration.
- `BusinessRequest` struct.
- allowed district validation.
- `GET /api/business`.
- `POST /api/business`.
- `PUT /api/business`.
- Vue business profile form.

Theory:

- one-to-one table relation.
- unique constraints.
- validation before database writes.
- form state with `reactive`.

Portal feature:

- each applicant has one business profile.
- district must be in scope.
- profile can be edited.

Git:

```bash
git checkout -b feature/business-profile
git commit -m "Add business profile schema"
git commit -m "Implement business profile service"
git commit -m "Add Vue business profile form"
```

Done when:

- creating twice does not create duplicate rows.
- invalid district is rejected.
- form loads existing profile.

## Milestone 4: Grant Form and Whitelist Gate

Goal: master larger payloads and workflow rules.

Build:

- `grants` migration.
- `grant_access_whitelist` migration.
- grant request validation.
- `GET /api/grant`.
- `POST /api/grant`.
- `PUT /api/grant`.
- `GET /api/grant-status`.
- Vue multi-section grant form.

Theory:

- JSONB fields.
- slices of structs.
- conditional validation.
- workflow gates.
- HTTP 403 vs 409 vs 422.

Portal feature:

- user can apply only when whitelisted if `GRANT_REQUIRE_SELECTION=1`.
- one user has one grant.
- financed items repeat dynamically.
- SRSP relatives are conditional rows.

Git:

```bash
git checkout -b feature/grant-application
git commit -m "Add grant schema and models"
git commit -m "Implement grant access whitelist"
git commit -m "Implement grant application endpoint"
git commit -m "Add Vue grant application form"
```

Done when:

- non-whitelisted user cannot submit.
- whitelisted user can submit.
- JSONB fields round-trip.
- Vue review page displays the same data.

## Milestone 5: Admin Reports

Goal: learn real data querying.

Build:

- admin token verification.
- applicant report endpoint.
- filters, sort allow-list, pagination.
- admin report table.
- CSV export query token.

Theory:

- joins.
- count queries.
- pagination.
- SQL injection prevention.
- streaming responses.

Portal feature:

- admins can filter applicants by district, sector, status, language, gender, and search.

Git:

```bash
git checkout -b feature/admin-reports
git commit -m "Add applicant report query"
git commit -m "Add report filters and pagination"
git commit -m "Add Vue admin applicant report"
```

Done when:

- unauthorized users cannot access reports.
- invalid sort field is rejected or replaced by a safe default.
- pagination response shape is exactly `{data,total,page,per_page}`.

## Milestone 6: HFC and Approval

Goal: learn deterministic business logic, auditability, and side effects.

Build:

- HFC scoring rules.
- `hfc_evaluations` writes.
- admin HFC queue.
- approval check endpoint.
- approval transaction.
- email enqueue interface.

Theory:

- pure functions.
- risk bands.
- audit logs.
- transactions.
- interfaces for side effects.

Portal feature:

- grant submission triggers HFC scoring.
- approver can approve grants.
- shadow mode means HFC does not block approval.

Git:

```bash
git checkout -b feature/hfc-approval
git commit -m "Add deterministic HFC scoring"
git commit -m "Store HFC evaluations"
git commit -m "Implement grant approval transaction"
```

Done when:

- scoring tests prove each rule.
- approval writes both grant and log.
- non-approver cannot approve.
- shadow mode behavior is tested.

## Milestone 7: Production Readiness

Goal: make it runnable and maintainable.

Build:

- Dockerfile.
- migration runner.
- Redis cache.
- worker process.
- S3 upload integration.
- structured logs.
- smoke tests.

Theory:

- deployment units.
- process lifecycle.
- graceful shutdown.
- observability.
- rollback.

Portal feature:

- full applicant workflow and admin workflow run on the Go + Vue stack.

Git:

```bash
git checkout -b release/v0.1.0
git tag -a v0.1.0 -m "First Go and Vue portal milestone"
```

Done when:

- backend starts from clean environment.
- migrations apply once.
- Vue build succeeds.
- critical tests pass.
- release tag exists.

