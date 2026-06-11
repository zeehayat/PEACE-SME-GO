# Chapter 1: Read the Existing System Like an Engineer

## Purpose

Before writing Go or Vue code, learn to extract behavior from an existing application. The PEACE SME Grant Portal is not just a set of pages. It is a workflow:

1. Applicant registration and login.
2. Business profile entry.
3. Document and media uploads.
4. Admin eligibility decisions.
5. Whitelisted grant application submission.
6. HFC fraud scoring.
7. Approval by an approving authority.
8. Notifications, reports, exports, FAQs, updates, and operational controls.

The rewrite succeeds only if these behaviors remain compatible.

For a beginner, this chapter teaches an important professional habit: do not start a rewrite by opening an editor and inventing code. Start by reading the system until you can describe what must remain true after the rewrite.

## Theory: What Is a Rewrite?

A rewrite is not "build a new app that looks similar." A rewrite is a controlled replacement of implementation while preserving required behavior.

In this project:

- Old implementation: Flask backend plus Vue frontend.
- New implementation: Go backend plus Vue 3 frontend.
- Stable contract: PostgreSQL schema, API paths, JSON shapes, auth behavior, business rules, and user workflows.

Think of the rewrite as changing the engine of a running system. The outside controls should still work. The frontend expects the same endpoints. The database stores the same business facts. Admins expect the same reports. Applicants expect the same workflow.

## Application Parallel: The First Task You Are Really Building

Your first project task is not a route or a page. It is a map.

Build a map that answers:

- Which frontend view calls which endpoint?
- Which endpoint uses which service?
- Which service reads or writes which table?
- Which business rule protects that operation?
- Which Git branch will contain that work?

Example:

| User action | Vue view | API endpoint | Go package | Tables | Rule |
|---|---|---|---|---|---|
| Applicant logs in | `UserLogin.vue` | `POST /api/login` | `internal/user`, `internal/auth` | `users` | blocked users cannot login |
| Applicant saves business | `SmeBusinessProfile.vue` | `POST /api/business` | `internal/business` | `businesses` | one business per user |
| Admin approves grant | `AdminGrantDetail.vue` | `POST /api/admin/grants/<user_id>/approve` | `internal/grant`, `internal/admin` | `grants`, `grant_approval_logs` | approver role required |

This map becomes your implementation checklist.

## What to Read

Start with:

- `Claude.md`
- `README.md`
- `go.mod`
- `cmd/server/main.go`

The current Go service is only a health-check stub. That is useful: the project is clean enough to grow in deliberate layers.

## System Map

The original application has these major boundaries:

| Boundary | Flask module | Go package to create | Vue area |
|---|---|---|---|
| Auth | `auth_service.py`, `security.py` | `internal/auth`, `internal/security` | Login views, route guards |
| Users | `user_service.py` | `internal/user` | Registration, login, dashboard |
| Business profile | `user_service.py` | `internal/business` | `SmeBusinessProfile.vue` |
| Grants | `grant_service.py` | `internal/grant` | `SmeGrantApplication.vue` |
| Reports | `report_service.py` | `internal/report` | Admin report views |
| Admin | `admin_service.py` | `internal/admin` | Admin dashboard and tools |
| HFC | `hfc_service.py`, `hfc_admin_service.py` | `internal/hfc` | HFC admin views |
| Applicant status | `status_service.py` | `internal/status` | Applicant status admin view |
| Content | updates, FAQs | `internal/content` | Landing page, FAQ bot |
| Storage | `s3_service.py` | `internal/storage` | Upload components |
| Mail | `mail_service.py` | `internal/mail` | Approval side effects |

## API Contract Thinking

The Vue frontend depends on:

- Exact endpoint paths under `/api`.
- Exact localStorage keys: `userToken`, `adminToken`, `language`.
- Exact pagination shapes such as `{data, total, page, per_page}`.
- JWTs sent as `Authorization: Bearer <token>`.
- Admin JWT fields such as `is_admin` and `is_approver`.
- English stored values even when the UI is Urdu.

When converting Flask to Go, you are not free to invent a cleaner public contract until you also migrate the frontend.

### Contract vs Implementation

The contract is what other parts of the system depend on. The implementation is how you satisfy it.

| Contract | Implementation detail |
|---|---|
| `POST /api/login` returns `{token,user_id,language}` | Go may use `net/http`, `chi`, or another router |
| Passwords use bcrypt | Repository structure is up to you |
| JWT uses HS256 and `JWT_SECRET_KEY` | Token service can be written as a small package |
| Reports return `{data,total,page,per_page}` | SQL can be optimized later |
| `GRANT_REQUIRE_SELECTION=1` gates grant submission | The check can live in `GrantService` |

As a learner, this distinction prevents a common mistake: changing the public behavior while trying to improve the internal design.

## Beginner Go Lens

This system will teach Go in layers:

1. Structs model data such as users and grants.
2. Functions and methods implement operations such as login and approval.
3. Interfaces separate side effects such as S3 and email from business logic.
4. Errors make invalid states explicit.
5. Context carries request cancellation and identity.
6. Goroutines and workers handle slow work such as email and HFC scoring.

Do not try to master all Go features before building. Learn each feature when the application gives you a reason to use it.

## Exercise

Create a file named `guide/app-contract-notes.md` while studying. Capture:

- Every endpoint you plan to implement.
- Every table you plan to migrate.
- Every feature toggle.
- Every auth rule.
- Every response shape that the frontend depends on.

Add one more section called "parallel learning notes." For every feature, write the Go concept it teaches:

| Feature | Go concept | Vue concept | Git concept |
|---|---|---|---|
| Login | structs, bcrypt, JWT, errors | form state, localStorage | small auth branch |
| Business profile | validation, repository methods | reactive form | commit create and update separately |
| Reports | SQL filters, maps, pagination | table state, query params | review staged diff carefully |

## Git Practice

Initialize your learning branch:

```bash
git status
git checkout -b chapter-01-system-reading
git add guide
git commit -m "Add system reading notes"
```

Use `git diff --staged` before committing. This teaches you to review your own work before Git records it.

## Mastery Check

You understand this chapter when you can explain:

- Why the Go rewrite must preserve the Flask API contract.
- Which modules belong in backend packages.
- Which parts of the frontend are public, applicant-only, and admin-only.
- Why `Claude.md` is a behavioral specification, not just documentation.
