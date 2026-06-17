# Chapter 2: Git Foundations for a Rewrite

## Purpose

Git is not separate from the rewrite. It is the safety system that lets you change a large application in controlled steps without losing track of intent. Every decision you make about what to build next, what is ready to merge, and what to discard is mediated through Git.

This chapter teaches Git from first principles through to advanced techniques you will use every day on this project.

---

## Theory: Git as a Graph

### Git is a Directed Acyclic Graph (DAG)

Git stores history as a **Directed Acyclic Graph** of commit objects. Each commit contains:

- A cryptographic SHA-1 hash identifying the commit uniquely (based on file contents, metadata, parent hashes, author, and timestamp).
- A pointer to zero or more parent commits.
- A snapshot of the **entire directory tree** at that moment (not just the changed lines).

Understanding the graph structure helps you visualize operations:

- A **Branch** is simply a mutable pointer (a label) to a specific commit.
- **HEAD** is a pointer to the currently checked-out commit or branch.

```
main:     A → B → C → D
                    \
feature:             E → F → G
```

In this graph, `D` is the tip of `main`. `G` is the tip of `feature`. The feature branch shares commits `A`, `B`, `C` with main and diverges at `D`.

### The Three-State Architecture

Git projects consist of three primary zones:

```
[ Working Directory ]
         |
      git add
         |
         ↓
[ Staging Area (Index) ]
         |
     git commit
         |
         ↓
[ Commit History (.git) ]
         |
      git push
         |
         ↓
[ Remote Repository ]
```

1. **Working Directory**: The local sandbox where you edit files on disk.
2. **Staging Area (Index)**: A binary file tracking the changes prepared for the next commit. This acts as a deliberate preparation area — you choose exactly what goes into each commit.
3. **Commit History**: The permanent graph database storing all commits (`.git/objects/`).

### Why Three Zones?

The staging area exists so you can make several related changes in a work session and then organize them into logical, reviewable commits. You might edit five files while implementing the HFC scorer, but commit them in three separate commits: "Add HFC rule engine", "Add HFC repository queries", "Add HFC admin endpoints".

---

## Core Workflow Loop

Use this loop for every feature:

```bash
# 1. Always start from main, updated
git checkout main
git pull origin main

# 2. Create a focused branch
git checkout -b feature/user-login

# 3. Work, then stage specific files
git add internal/user/repository.go
git diff --staged                      # review before committing
git commit -m "Add user repository with FindByEmail"

# 4. Repeat for each logical chunk
git add internal/user/service.go
git commit -m "Add user service Login method with bcrypt"

# 5. Review the whole branch before merging
git log --oneline main..HEAD
git diff main...HEAD

# 6. Merge or push for review
git checkout main
git merge feature/user-login
```

### Good Commit Messages

A commit message answers: "What behavior does this commit add or change, and why?"

| Bad | Good |
|---|---|
| `updates` | `Add grant whitelist gate middleware` |
| `fix` | `Fix blocked user returning 401 instead of 403` |
| `wip` | `[WIP] HFC scoring rules 1-4 (incomplete)` |
| `final` | `Add POST /api/grant handler with validation` |
| `changes` | `Remove duplicate CNIC check from registration` |

The format: `<Verb> <what> [because <why if non-obvious>]`

Examples from this project:
- `Add Go configuration loader with toggle parsing`
- `Implement user login endpoint with JWT issuance`
- `Add grant access whitelist check before submission`
- `Fix HFC debounce not resetting timer on rapid resubmit`
- `Add CSV export endpoint for admin applicant report`

---

## Branching Strategies

### Git Flow

Git Flow defines a branching model with specific branch types:

```
main         Production-ready code only
develop      Integration branch for features
feature/*    Individual feature development
release/*    Release preparation
hotfix/*     Emergency production fixes
```

```bash
# Git Flow example
git checkout develop
git checkout -b feature/hfc-scoring
# ... work ...
git checkout develop
git merge feature/hfc-scoring
git branch -d feature/hfc-scoring

# Prepare a release
git checkout -b release/v1.0.0 develop
# ... fix release bugs ...
git checkout main
git merge release/v1.0.0
git tag -a v1.0.0 -m "PEACE SME Portal v1.0.0"
git checkout develop
git merge release/v1.0.0
```

**Use Git Flow when:** The project has multiple developers, parallel releases, and scheduled deployments.

### Trunk-Based Development

In trunk-based development, everyone commits to `main` (or a shared branch) frequently. Features are hidden behind feature flags rather than long-lived branches.

```bash
# Trunk-based: short-lived branches, merged within a day or two
git checkout -b feature/login-endpoint
# ... implement in one session ...
git checkout main
git merge feature/login-endpoint   # merged same day
git branch -d feature/login-endpoint
```

**Use trunk-based when:** Working alone or in a small team where rapid integration is more important than long parallel feature streams.

### This Project's Strategy

For the PEACE SME rewrite, use chapter-based branches:

```
main
└── chapter-01-system-reading
└── chapter-02-git-foundations
└── chapter-03-go-project-structure
└── chapter-04-configuration
...
└── feature/user-login         (mid-chapter feature)
└── feature/grant-submission   (mid-chapter feature)
└── fix/blocked-user-403       (bug fixes)
```

---

## Branch Naming Conventions

| Branch type | Format | Example |
|---|---|---|
| Chapter work | `chapter-<N>-<topic>` | `chapter-06-auth-middleware` |
| Feature | `feature/<short-description>` | `feature/user-login` |
| Bug fix | `fix/<what-was-wrong>` | `fix/hfc-scoring-duplicate-cnic` |
| Release | `release/v<major>.<minor>.<patch>` | `release/v1.0.0` |
| Hotfix | `hotfix/<description>` | `hotfix/blocked-user-login` |
| Experiment | `experiment/<name>` | `experiment/bulk-html-pdf` |

Avoid: `my-branch`, `test`, `temp`, `aftab-working`, `final-v2`, `new-new-final`.

---

## Reading History Like an Engineer

Git history is a narrative of the project's construction. Reading it well is as valuable as writing good commits.

### The Essential History Commands

```bash
# Compact one-line graph of all branches
git log --oneline --graph --all --decorate

# Example output:
# * a1b2c3d (HEAD -> chapter-04-configuration) Add S3 config vars
# * d4e5f6a Add database connection URL builder
# * e7f8g9b (main) Add Go project structure
# * c1d2e3f Add CLAUDE.md system specification
# * a4b5c6d First commit

# What changed in a specific commit?
git show a1b2c3d

# What did a specific file look like at a commit?
git show a1b2c3d:internal/config/config.go

# Who last changed each line of a file, and when?
git blame internal/user/service.go

# What changed between two commits?
git diff HEAD~3 HEAD

# What changed in a specific file between two commits?
git diff HEAD~3 HEAD -- internal/grant/service.go

# Search history for when a string was added or removed
git log -S "ErrUserBlocked" --oneline

# Search history by commit message
git log --grep="HFC" --oneline

# What branches exist?
git branch -a

# What commits are on feature branch but not on main?
git log main..feature/hfc-scoring --oneline

# What does this branch change vs main?
git diff main...HEAD
```

### Blame: Understanding Code Ownership

`git blame` shows who wrote each line and when. Use it when you find a confusing piece of code and want to understand the context in which it was written:

```bash
git blame internal/grant/service.go

# Output:
# a1b2c3d (Zeeshan Hayat 2026-05-10 14:32:11) func (s *Service) Apply(...) {
# d4e5f6a (Zeeshan Hayat 2026-05-10 14:32:11)     if s.cfg.GrantRequireSelection {
# e7f8g9b (Zeeshan Hayat 2026-05-11 09:15:44)         row, err := s.repo.GetWhitelistEntry(ctx, userID)
```

### Log Search: Finding When a Bug Was Introduced

```bash
# When was the HFC debounce logic added?
git log -S "HFC_ENQUEUE_DEBOUNCE_SEC" --oneline --all

# When did we last change the grant handler?
git log --oneline -- internal/grant/handler.go

# Show all commits that touched the whitelist feature
git log --oneline --all -- "*whitelist*"
```

---

## Interactive Rebasing

Interactive rebase lets you rewrite your local commits before sharing them. Use it to:
- Squash "fixup" commits into the main commit they fix
- Reorder commits into a logical sequence
- Edit a commit message
- Split a commit into smaller pieces

> [!WARNING]
> Never rebase commits that have been pushed to a shared repository. Rebasing rewrites SHA hashes, causing diverged history for anyone who pulled the original commits.

### Squashing Commits

You have been working on HFC scoring and made 5 commits, but commits 2 and 4 are just typo fixes:

```bash
git log --oneline
# f1a2b3c Add HFC tests
# d4e5f6a Fix typo in risk level constant
# g7h8i9j Add HFC repository queries
# j1k2l3m Fix wrong variable name in rule check
# n4o5p6q Add HFC rule engine with 10 rules
```

Start an interactive rebase for the last 5 commits:

```bash
git rebase -i HEAD~5
```

Your editor opens with:

```text
pick n4o5p6q Add HFC rule engine with 10 rules
pick j1k2l3m Fix wrong variable name in rule check
pick g7h8i9j Add HFC repository queries
pick d4e5f6a Fix typo in risk level constant
pick f1a2b3c Add HFC tests
```

Change it to:

```text
pick n4o5p6q Add HFC rule engine with 10 rules
fixup j1k2l3m Fix wrong variable name in rule check
pick g7h8i9j Add HFC repository queries
fixup d4e5f6a Fix typo in risk level constant
pick f1a2b3c Add HFC tests
```

Save and close. Git squashes the `fixup` commits silently into the previous `pick` commits. Result:

```bash
git log --oneline
# a9b8c7d Add HFC tests
# e6f5g4h Add HFC repository queries
# h3i2j1k Add HFC rule engine with 10 rules
```

### Reordering Commits

If you realized a commit is in the wrong order (e.g., you added tests before adding the implementation), reorder the lines in the rebase file:

```text
# Before
pick a1b2c3d Add HFC tests            # was first
pick d4e5f6a Add HFC rule engine      # was second

# After (swap the lines)
pick d4e5f6a Add HFC rule engine
pick a1b2c3d Add HFC tests
```

### Editing a Commit Message

```text
# In the rebase file
reword a1b2c3d Add hfc rulez     # typo in message
pick   d4e5f6a Add HFC tests
```

Git will pause and open your editor to let you write the corrected message.

---

## Cherry-Pick: Grabbing Specific Commits

`git cherry-pick` applies a specific commit from one branch to another. Use it when:
- A bug fix is on a feature branch but needs to go to main immediately
- You want to copy one commit from an abandoned experiment

```bash
# You found a fix for the blocked-user bug on feature/login
# The commit hash is a1b2c3d
# But the whole feature is not ready to merge yet

git checkout main
git cherry-pick a1b2c3d

# Git applies that single commit to main
# The feature branch is unchanged
```

```bash
# Cherry-pick a range of commits
git cherry-pick a1b2c3d..f4g5h6i

# Cherry-pick without committing (apply changes, stage, but don't commit)
git cherry-pick --no-commit a1b2c3d
```

---

## The Reflog: Your Safety Net

The reflog records every change to HEAD, including moves, checkouts, resets, and rebases. It is your emergency undo system.

```bash
# See the reflog
git reflog

# Example output:
# a1b2c3d HEAD@{0}: commit: Add HFC rule engine
# d4e5f6a HEAD@{1}: checkout: moving from main to feature/hfc-scoring
# e7f8g9b HEAD@{2}: merge feature/user-login: Merge made by the 'ort' strategy
# c1d2e3f HEAD@{3}: commit: Add user login handler
# a4b5c6d HEAD@{4}: commit: Add user repository

# Recover a commit you accidentally reset away
git reset --hard HEAD@{2}

# Recover a branch you accidentally deleted
git checkout -b feature/deleted-branch d4e5f6a
```

### Scenario: Recovering from a Bad Reset

You accidentally ran `git reset --hard HEAD~3` and lost three commits:

```bash
# Find the commits in the reflog
git reflog
# a1b2c3d HEAD@{0}: reset: moving to HEAD~3
# d4e5f6a HEAD@{1}: commit: Add HFC tests          ← this is what you want
# e7f8g9b HEAD@{2}: commit: Add HFC repository queries
# c1d2e3f HEAD@{3}: commit: Add HFC rule engine

# Recover: reset HEAD to where you were before the bad reset
git reset --hard d4e5f6a

# Or, more safely: create a new branch from the lost commit
git checkout -b recovery/hfc-work d4e5f6a
```

> [!NOTE]
> The reflog is local only — it does not exist on the remote. Pushed commits are also protected because the remote retains them even if you reset locally.

---

## Resolving Merge Conflicts Step by Step

Merge conflicts occur when two branches change the same lines of the same file.

### Step 1: Trigger the Conflict

```bash
git checkout main
git merge feature/grant-handler

# Output:
# Auto-merging internal/grant/handler.go
# CONFLICT (content): Merge conflict in internal/grant/handler.go
# Automatic merge failed; fix conflicts and then commit the result.
```

### Step 2: Identify Conflicted Files

```bash
git status

# Both modified:   internal/grant/handler.go
```

### Step 3: Open the File and Read the Markers

```go
// internal/grant/handler.go
<<<<<<< HEAD
func (h *Handler) Apply(w http.ResponseWriter, r *http.Request) {
    userID := middleware.GetUserID(r.Context())
    var req ApplyRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        http.Error(w, `{"error":"invalid request body"}`, http.StatusBadRequest)
        return
    }
=======
func (h *Handler) Apply(w http.ResponseWriter, r *http.Request) {
    userID := auth.UserIDFromContext(r.Context())
    body, err := io.ReadAll(r.Body)
    if err != nil {
        http.Error(w, `{"error":"could not read body"}`, http.StatusBadRequest)
        return
    }
    var req ApplyRequest
    if err := json.Unmarshal(body, &req); err != nil {
        http.Error(w, `{"error":"invalid JSON"}`, http.StatusBadRequest)
        return
    }
>>>>>>> feature/grant-handler
```

The section between `<<<<<<< HEAD` and `=======` is what `main` has. The section between `=======` and `>>>>>>>` is what `feature/grant-handler` has.

### Step 4: Decide the Resolution

You need to choose: keep HEAD, keep the feature, or write a combined version. Here, the feature branch approach (reading body bytes then unmarshaling) is more explicit. But the middleware helper from HEAD for extracting user ID is better.

Resolved version:

```go
func (h *Handler) Apply(w http.ResponseWriter, r *http.Request) {
    userID := middleware.GetUserID(r.Context())   // from HEAD
    body, err := io.ReadAll(r.Body)               // from feature
    if err != nil {
        http.Error(w, `{"error":"could not read body"}`, http.StatusBadRequest)
        return
    }
    var req ApplyRequest
    if err := json.Unmarshal(body, &req); err != nil {
        http.Error(w, `{"error":"invalid JSON"}`, http.StatusBadRequest)
        return
    }
```

### Step 5: Stage and Complete the Merge

```bash
git add internal/grant/handler.go
git status
# All conflicts fixed but you are still merging.
# (use "git commit" to conclude merge)

git commit -m "Merge feature/grant-handler: resolve handler body parsing conflict"
```

### Step 6: Verify

```bash
go build ./...      # must compile
go test ./...       # tests must pass
git log --oneline --graph -5   # confirm clean merge commit
```

---

## Stashing: Context-Switching Without Losing Work

`git stash` saves your uncommitted changes to a temporary stack so you can switch context without losing work.

### Scenario: Bug Report While Mid-Feature

You are implementing the HFC scoring rules (halfway through), when someone reports a critical bug: blocked users are getting 401 instead of 403.

```bash
# You are mid-work on HFC scoring
git status
# modified: internal/hfc/rules.go
# modified: internal/hfc/service.go

# Save your in-progress work
git stash push -m "WIP: HFC scoring rules 5-8 (incomplete)"

# Your working directory is now clean
git status
# nothing to commit, working tree clean

# Switch to fix the bug
git checkout -b fix/blocked-user-403
# ... make the fix in internal/user/service.go ...
git add internal/user/service.go
git commit -m "Fix blocked user returning 401 instead of 403"

# Merge the fix
git checkout main
git merge fix/blocked-user-403
git branch -d fix/blocked-user-403

# Return to your HFC work
git checkout feature/hfc-scoring
git stash pop
# Your HFC changes are restored

git status
# modified: internal/hfc/rules.go
# modified: internal/hfc/service.go
```

### Stash Commands Reference

```bash
git stash list                      # list all stashed items
git stash show -p stash@{0}         # show diff of most recent stash
git stash show -p stash@{1}         # show diff of second stash
git stash pop                       # restore and delete most recent stash
git stash apply stash@{1}           # restore without deleting
git stash drop stash@{0}            # delete a specific stash
git stash clear                     # delete all stashes

# Stash only staged changes
git stash push --staged -m "Half-done grant validation"

# Stash including untracked files
git stash push --include-untracked -m "WIP including new files"
```

> [!NOTE]
> Stash is for context switches, not long-term storage. If work-in-progress needs to last more than a day, commit it on a branch with a `[WIP]` prefix in the message. Stashes do not exist on the remote.

---

## Interactive Staging: Committing Exactly What You Mean

`git add -p` (patch mode) lets you stage individual chunks (hunks) of a file, rather than the entire file.

### Scenario: Mixed Work Session

You spent the afternoon touching `internal/grant/service.go` and `internal/grant/handler.go`. The changes belong to two different commits:

- "Add grant validation rules" (changes in `service.go`)
- "Add grant HTTP handler" (changes in `handler.go`)

```bash
# Stage only service.go first
git add -p internal/grant/service.go

# Git shows each hunk interactively:
# @@ -45,6 +45,12 @@ func (s *Service) Apply(...)
# +    if req.GrantRequired <= 0 {
# +        return ErrInvalidAmount
# +    }
# Stage this hunk [y,n,q,a,d,/,e,?]?
```

Answer keys:
- `y` — stage this hunk
- `n` — skip this hunk (leave it unstaged)
- `s` — split this hunk into smaller pieces
- `e` — manually edit the hunk in your editor
- `q` — quit, leaving remaining hunks unstaged
- `?` — show full help

```bash
# Stage only the validation hunks (answer y to them, n to others)
git diff --staged        # confirm only validation changes are staged
git commit -m "Add grant application amount and district validation"

# Now stage the handler changes
git add internal/grant/handler.go
git commit -m "Add POST /api/grant handler"
```

---

## Tagging Releases

Tags mark specific commits as significant milestones. Unlike branches, tags do not move.

```bash
# Lightweight tag (just a pointer)
git tag v1.0.0

# Annotated tag (with message and signature)
git tag -a v1.0.0 -m "Initial Go backend with auth, user, and business endpoints"

# List tags
git tag -l

# Push tags to remote
git push origin v1.0.0
git push origin --tags    # push all tags

# Check out a specific tag (detached HEAD)
git checkout v1.0.0

# Diff between tags
git diff v0.9.0..v1.0.0 --stat

# Find when a tag was created
git show v1.0.0
```

For the PEACE SME rewrite, tag each milestone:

```bash
git tag -a v0.1.0 -m "Auth and user management endpoints complete"
git tag -a v0.2.0 -m "Business profile and document upload endpoints complete"
git tag -a v0.3.0 -m "Grant application workflow complete"
git tag -a v1.0.0 -m "Full backend parity with Flask; all 70+ endpoints implemented"
```

---

## Git Bisect: Finding the Commit That Broke Things

`git bisect` uses binary search to find the commit that introduced a bug. You tell Git a "bad" commit (has the bug) and a "good" commit (does not have the bug), and Git checks out midpoints for you to test.

### Scenario: A Test Broke Somewhere in the Last 20 Commits

```bash
# Start a bisect session
git bisect start

# Mark the current commit as bad (has the bug)
git bisect bad

# Mark a known-good commit (tag or hash)
git bisect good v0.2.0

# Git checks out a midpoint commit
# Run your test
go test ./internal/grant/... -run TestGrantWhitelistGate

# If the test fails (bug is present):
git bisect bad

# If the test passes (no bug):
git bisect good

# Repeat until Git identifies the exact commit:
# a1b2c3d is the first bad commit

# View what changed in that commit
git show a1b2c3d

# Finish the bisect session
git bisect reset
```

### Automated Bisect

If you can express the test as a shell command that exits 0 (pass) or non-zero (fail):

```bash
git bisect start
git bisect bad HEAD
git bisect good v0.2.0

# Let Git run the test automatically for each midpoint
git bisect run go test ./internal/grant/... -run TestGrantWhitelistGate

# Git reports the first bad commit automatically
git bisect reset
```

---

## Git Hooks

Git hooks are scripts that run automatically at specific points in the Git workflow. They live in `.git/hooks/`.

### Pre-commit Hook

Runs before `git commit` records the commit. Use it to enforce code quality:

```bash
# .git/hooks/pre-commit
#!/bin/sh

# Run Go formatting check
unformatted=$(gofmt -l .)
if [ -n "$unformatted" ]; then
    echo "Error: the following files are not gofmt-formatted:"
    echo "$unformatted"
    echo "Run: gofmt -w ."
    exit 1
fi

# Run Go vet
go vet ./...
if [ $? -ne 0 ]; then
    echo "Error: go vet failed"
    exit 1
fi

echo "Pre-commit checks passed."
exit 0
```

Make it executable:

```bash
chmod +x .git/hooks/pre-commit
```

### Commit-msg Hook

Validates commit message format:

```bash
# .git/hooks/commit-msg
#!/bin/sh

COMMIT_MSG=$(cat "$1")
PATTERN="^(Add|Fix|Update|Remove|Refactor|Test|Doc|WIP) .{5,}"

if ! echo "$COMMIT_MSG" | grep -qE "$PATTERN"; then
    echo "Error: Commit message must start with a verb (Add/Fix/Update/Remove/...)."
    echo "Your message: $COMMIT_MSG"
    exit 1
fi

exit 0
```

### Post-merge Hook

Runs after a successful merge. Use it to remind yourself to rebuild:

```bash
# .git/hooks/post-merge
#!/bin/sh
echo ""
echo "Merge complete. Run 'go build ./...' to verify the build still passes."
echo ""
```

---

## Complete Feature Git Workflow: User Login

Here is a real step-by-step sequence you will use when implementing the user login feature:

```bash
# 1. Start from main, updated
git checkout main
git pull origin main

# 2. Create the feature branch
git checkout -b feature/user-login

# 3. === Commit 1: Repository layer ===
# Write internal/user/repository.go
# Add FindByEmail query:
#   SELECT user_id, email_address, hashed_password, status, language
#   FROM users WHERE email_address = $1
git add internal/user/repository.go
git commit -m "Add user repository with FindByEmail query"

# 4. === Commit 2: Service layer ===
# Write internal/user/service.go
# Add Login method: FindByEmail → check blocked → bcrypt.CompareHashAndPassword → issue JWT
git add internal/user/service.go
git commit -m "Add user service Login method with bcrypt and JWT"

# 5. === Commit 3: Handler layer ===
# Write internal/user/handler.go
# Add Login handler: decode JSON body → call service → return {token, user_id, language}
git add internal/user/handler.go
git commit -m "Add POST /api/login handler"

# 6. === Commit 4: Wire into router ===
git add internal/app/app.go
git commit -m "Register /api/login route in app router"

# 7. === Commit 5: Tests ===
git add internal/user/service_test.go
git add internal/user/handler_test.go
git commit -m "Add login tests: invalid credentials, blocked user, JWT success"

# 8. Review the full branch before merging
git log --oneline main..HEAD
# a1b2c3d Add login tests
# d4e5f6a Register /api/login route in app router
# e7f8g9b Add POST /api/login handler
# c1d2e3f Add user service Login method
# a4b5c6d Add user repository with FindByEmail

git diff main...HEAD   # full diff against main
go test ./internal/user/...   # tests pass?
go build ./...                # builds?

# 9. Merge
git checkout main
git merge feature/user-login
git branch -d feature/user-login

# 10. Tag the milestone
git tag -a v0.1.0-auth -m "User auth endpoints complete"
```

---

## Exploration and Safety Commands Reference

```bash
# Status and diff
git status                          # current state of working directory
git diff                            # unstaged changes
git diff --staged                   # staged changes (what will be in the next commit)
git diff main...HEAD                # all changes this branch adds vs main

# History
git log --oneline --graph --all --decorate   # full graph
git log --oneline -20               # last 20 commits
git log -p -- internal/grant/       # history of changes in a directory
git log --author="Zeeshan"          # commits by author
git log --since="2026-01-01"        # commits since a date

# Inspecting
git show HEAD                       # what the last commit changed
git show HEAD:internal/config/config.go   # file contents at last commit
git blame internal/user/service.go  # who wrote each line

# Undoing
git restore internal/user/service.go         # discard working dir changes for a file
git restore --staged internal/user/service.go  # unstage a file
git revert HEAD                              # create a new commit that undoes the last commit
git reset --soft HEAD~1                      # undo last commit, keep changes staged
git reset --mixed HEAD~1                     # undo last commit, keep changes unstaged
git reset --hard HEAD~1                      # undo last commit and DISCARD all changes

# Branches
git branch                          # list local branches
git branch -a                       # list all branches (local + remote)
git branch -d feature/old-branch    # delete merged branch
git branch -D feature/old-branch    # force delete unmerged branch
git checkout -b new-branch          # create and switch to new branch
git switch main                     # switch to main (newer syntax)

# Remotes
git remote -v                       # show remote URLs
git fetch origin                    # fetch without merging
git pull origin main                # fetch and merge
git push origin feature/my-feature  # push branch to remote
git push --force-with-lease         # safer force push (fails if remote changed)
```

---

## Mastery Check

You understand this chapter when you can:

1. Create a branch, make three logically separate commits, then merge it back to main — and show `git log --oneline --graph` to confirm the clean history.
2. Use `git add -p` to stage only the validation changes in a file that has both validation and handler changes, without using separate files.
3. Use `git stash push -m "WIP"` to save in-progress work, switch to a fix branch, make and commit a fix, then `git stash pop` to restore your work — without losing any changes.
4. Perform an interactive rebase (`git rebase -i HEAD~4`) to squash two "fixup" commits into their parent commit, producing a clean 2-commit history from a messy 4-commit history.
5. Resolve a three-way merge conflict by reading the conflict markers, deciding which version (or a combination) is correct, removing the markers, staging, and completing the merge commit.
