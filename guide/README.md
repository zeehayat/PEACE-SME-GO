# Master Go, Vue, and Git by Rebuilding the PEACE SME Grant Portal

This guide is a chapter-by-chapter book for converting the existing Flask-based PEACE SME Grant Portal into a Go backend and a Vue 3 frontend while learning Git through disciplined, real project work. It is written for a coder who is new to Go: every backend concept is introduced theoretically, then immediately attached to a feature from the portal.

The source of truth for the application behavior is [Claude.md](../Claude.md). Every chapter ties a technical concept to one part of the portal: authentication, applicant profiles, grants, admin reports, HFC fraud scoring, uploads, queues, caching, bilingual UI, and deployment.

## Learning Goals

By the end of the book, you should be able to:

- Design and implement production Go HTTP services.
- Model PostgreSQL schemas and JSONB data in Go.
- Build secure authentication with JWT and bcrypt.
- Use middleware for auth, geo-blocking, access control, logging, and recovery.
- Implement Redis caching, concurrency controls, and background jobs.
- Integrate S3-compatible object storage and Brevo email delivery.
- Build a Vue 3 SPA using Composition API, Vue Router, Axios, Tailwind CSS, and Chart.js.
- Preserve an existing API contract while replacing the backend implementation.
- Use Git branches, commits, diffs, merges, tags, rebases, and pull requests as part of daily engineering work.

## Recommended Repository Layout

The Go backend can evolve from the current minimal module into this structure:

```text
cmd/server/
  main.go
internal/
  app/
  auth/
  cache/
  config/
  db/
  httpx/
  security/
  user/
  business/
  grant/
  admin/
  report/
  hfc/
  status/
  content/
  storage/
  mail/
migrations/
frontend/
  src/
```

## Chapters

Use the [Concept Index](concept-index.md) when you want to study by topic instead of chapter order.

1. [Read the Existing System Like an Engineer](chapters/01-read-the-system.md)
2. [Git Foundations for a Rewrite](chapters/02-git-foundations.md)
3. [Go Project Structure and HTTP Server](chapters/03-go-project-structure.md)
4. [Configuration, Environment, and Application Toggles](chapters/04-configuration.md)
5. [PostgreSQL, Migrations, and Data Modeling](chapters/05-postgresql-and-models.md)
6. [Authentication, JWT, bcrypt, and Middleware](chapters/06-authentication-and-middleware.md)
7. [Applicant Registration, Login, and Business Profiles](chapters/07-users-and-business-profiles.md)
8. [Grant Applications and Workflow Rules](chapters/08-grants-workflow.md)
9. [Uploads, S3-Compatible Storage, and Media References](chapters/09-storage-and-uploads.md)
10. [Redis, Caching, Access Slots, and Background Jobs](chapters/10-redis-cache-jobs.md)
11. [Admin, Reports, CSV, and Database Browser](chapters/11-admin-and-reports.md)
12. [HFC Fraud Detection and Approval Authority](chapters/12-hfc-and-approval.md)
13. [Vue 3 Frontend Foundations](chapters/13-vue-foundations.md)
14. [Vue Applicant and Admin Interfaces](chapters/14-vue-application-ui.md)
15. [Testing, Debugging, and API Compatibility](chapters/15-testing-and-compatibility.md)
16. [Deployment, Release Git, and Mastery Roadmap](chapters/16-deployment-and-mastery.md)

17. [Go Beginner Primer Through Portal Features](chapters/17-go-beginner-primer.md)
18. [Project Parallel Workbook](chapters/18-project-parallel-workbook.md)
19. [Vue and Git Practice Lab](chapters/19-vue-git-practice-lab.md)
20. [Error Handling and Observability](chapters/20-error-handling-and-observability.md)
21. [Go Concurrency Patterns](chapters/21-go-concurrency-patterns.md)
22. [Advanced Go Mastery and Runtime Internals](chapters/22-go-advanced-mastery.md)
23. [Go GUI Desktop Applications](chapters/23-go-gui-desktop-applications.md)

## Building the Book

Run from the `guide/` directory:

```bash
go run build.go
```

This regenerates `index.html` from the markdown chapters. Open `index.html` in any browser. The book includes:
- **Table of contents** with chapter filter (press `/` to focus)
- **Bookmarks** — hover any chapter and click ★
- **Highlights** — select text to get a color picker toolbar
- **Notes** — hover a chapter and click 📝, or add a note from selected text
- All data stored in your browser's localStorage

## Standalone Desktop Help Window

You can launch the book as a native standalone desktop application (resembling MS Office Help).

### Running in Development

Run from the root of the repository:

```bash
go run ./guide
```

### Compiling to Binary

To compile the application into standalone, zero-dependency binaries:

**For Windows (Executable):**
```bash
go build -ldflags="-H windowsgui" -o PEACE_Help.exe ./guide
```
The `-ldflags="-H windowsgui"` flag prevents the terminal console window from popping up behind the application when executed on Windows.

**For Linux:**
```bash
GOOS=linux GOARCH=amd64 go build -o PEACE_Help_linux ./guide
```

## How to Work Through the Book

Use one branch per chapter:

```bash
git checkout -b chapter-03-go-server
```

Make small commits:

```bash
git add .
git commit -m "Add Go server bootstrap"
```

At the end of each chapter, compare your work against the contract in [Claude.md](../Claude.md). The goal is not merely to make something work. The goal is to reproduce the same API paths, request shapes, response shapes, business rules, and frontend behavior with a Go + Vue implementation you understand deeply.

## The Learning Pattern Used in Every Chapter

Each chapter should be read in this order:

1. Theory: learn the language or engineering concept.
2. Application parallel: identify where the PEACE SME portal needs that concept.
3. Backend implementation: build the Go package, handler, service, repository, or worker piece.
4. Frontend implementation: connect the Vue screen or component to the matching API behavior.
5. Git practice: save the work as a small, reviewable commit.
6. Mastery check: prove you can explain and modify the concept without copying code.

For example, you do not learn Go structs in isolation. You learn structs by modeling `users`, `businesses`, and `grants`. You do not learn Vue reactivity in isolation. You learn reactivity by building the grant form where changing contribution type reveals cash or in-kind fields. You do not learn Git branches abstractly. You learn branches by creating `feature/grant-access-whitelist`, reviewing its diff, and merging it after tests pass.
