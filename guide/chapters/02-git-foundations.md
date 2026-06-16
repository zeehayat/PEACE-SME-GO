# Chapter 2: Git Foundations for a Rewrite

## Purpose

Git is not separate from the rewrite. It is the safety system that lets you change a large application without losing track of intent.

## Theoretical Background

### Git as a Directed Acyclic Graph (DAG)
Git stores history not as a list of changes, but as a Directed Acyclic Graph (DAG) of commit objects. Each commit contains:
- A cryptographic SHA-1 hash (identifying the commit uniquely based on file contents, metadata, parent hashes, author, and timestamp).
- A pointer to zero or more parent commits.
- A snapshot of the entire directory tree (not delta changes).

Understanding this graph structure helps you visualize operations:
- A **Branch** is simply a mutable pointer to a specific commit.
- **HEAD** is a pointer to the currently checked-out commit or branch.

### The Three-State Architecture
Git projects consist of three primary zones:
1. **Working Directory (Workspace):** The local sandbox where you edit files on disk.
2. **Staging Area (Index):** A binary file tracking the changes prepared for the next commit. This acts as a preparation area.
3. **Commit History (Repository/Git Directory):** The permanent metadata database storing the commit graph (`.git/objects/`).

```text
[ Working Directory ] --- git add ---> [ Staging Area (Index) ] --- git commit ---> [ Commit History (.git) ]
[                   ] <--- checkout --- [                     ] <--- commit -------- [                        ]
```

### Merging vs. Rebasing
- **Merge (`git merge`):** Integrates two branches by creating a special "merge commit" that has two parent commits. This preserves the exact historical timeline and order of changes, but can make the history cluttered with merge commits.
- **Rebase (`git rebase`):** Rewrites commit history by moving the base of your branch to a new starting point. It applies your commits sequentially as new commits on top of the target branch. This creates a clean, linear history but alters the SHA-1 hashes of the original commits.
  > [!WARNING]
  > Never rebase commits that have been pushed to a shared public repository. Doing so rewrites history that others depend on.

### External Resources
- [Git Book - Git Internals](https://git-scm.com/book/en/v2/Git-Internals-Plumbing-and-Porcelain)
- [Git Book - Git Branching and Rebasing](https://git-scm.com/book/en/v2/Git-Branching-Rebasing)

---

## Core Workflow

Use this loop for every chapter:

```bash
git status
git checkout -b chapter-XX-short-name
git diff
git add <files>
git diff --staged
git commit -m "Describe the completed behavior"
```

Good commits are small, reviewable, and named after behavior:
- `Add Go configuration loader`
- `Implement user login endpoint`
- `Add Vue admin route guards`
- `Add HFC scoring tests`

Avoid vague messages:
- `updates`
- `fix`
- `changes`

---

## Practical Examples

### Example 1: Creating and Merging a Feature Branch
To start a new feature and safely integrate it back into the main branch:

```bash
# 1. Ensure you are on main and up to date
git checkout main
git pull origin main

# 2. Create and switch to the new feature branch
git checkout -b feature/auth-service

# 3. (After making changes to internal/auth/auth.go)
# Check what has changed in the working directory
git status

# 4. Stage your changes
git add internal/auth/auth.go

# 5. Review the staged diff before committing
git diff --staged

# 6. Commit the staged changes
git commit -m "Implement authentication service skeleton"

# 7. Merge the changes back into main
git checkout main
git merge feature/auth-service
```

### Example 2: Interactive Rebase to Clean Up Commits
Before submitting a pull request, you may want to squash minor "fixup" commits into a single logical commit:

```bash
# Start an interactive rebase for the last 3 commits
git rebase -i HEAD~3
```

This will open an editor showing:
```text
pick a1b2c3d Add user registration validator
pick d4e5f6g Fix typo in registration validator
pick h7i8j9k Add tests for registration validation
```

To squash the typo fix into the main commit, change the file to:
```text
pick a1b2c3d Add user registration validator
squash d4e5f6g Fix typo in registration validator
pick h7i8j9k Add tests for registration validation
```
Save and close the editor. Git will combine the first two commits and prompt you for a new commit message.

### Example 3: Resolving a Merge Conflict
If you and another developer edit the same line of a file, Git will report a conflict:

```text
Auto-merging cmd/server/main.go
CONFLICT (content): Merge conflict in cmd/server/main.go
Automatic merge failed; fix conflicts and then commit the result.
```

Opening `cmd/server/main.go` will show the conflict markers:
```go
<<<<<<< HEAD
    addr := ":8080"
=======
    addr := ":9000"
>>>>>>> feature/custom-port
```

To resolve this conflict:
1. Discuss or decide which value is correct (or combine them).
2. Delete the conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) and edit the code to the desired state:
   ```go
       addr := ":9000"
   ```
3. Stage the resolved file:
   ```bash
   git add cmd/server/main.go
   ```
4. Complete the merge commit:
   ```bash
   git commit -m "Resolve merge conflict, standardizing on port 9000"
   ```

---

## Reading History

Use:

```bash
git log --oneline --decorate --graph --all
git show <commit>
git diff main...HEAD
```

`git show` answers "what changed in this commit?"  
`git diff main...HEAD` answers "what does this branch change compared with main?"

---

## Handling Mistakes

Unstage a file:

```bash
git restore --staged path/to/file
```

Discard changes in one file only when you are sure:

```bash
git restore path/to/file
```

Inspect before undoing:

```bash
git diff path/to/file
```

---

## Stashing: Saving Unfinished Work

You are halfway through implementing the HFC scorer when a critical bug is reported in the login flow. You have uncommitted changes. You cannot switch branches cleanly. `git stash` saves your work-in-progress to a temporary stack so you can context-switch without losing anything.

```bash
# Save all uncommitted changes to the stash
git stash push -m "WIP: HFC scorer rules 5-8"

# Your working directory is now clean
git status   # nothing to commit, working tree clean

# Switch to fix the bug
git checkout -b fix/login-blocked-users
# ... make the fix, commit it, merge it ...

# Return to your original branch
git checkout feature/hfc-scoring

# Restore your stashed work
git stash pop
# Your HFC changes are back in the working directory
```

Stash commands:
```bash
git stash list                     # see all stashed items
git stash show -p stash@{0}        # inspect the most recent stash diff
git stash pop                      # restore and delete most recent stash
git stash apply stash@{1}          # restore a specific stash without deleting it
git stash drop stash@{0}           # delete a specific stash entry
git stash clear                    # delete all stashes
```

Rule: stash is for context switches, not long-term storage. Stashes do not survive `git clone`. If work-in-progress needs to last more than a day, commit it on a branch — even with a `[WIP]` prefix in the message.

---

## Interactive Staging: Committing Exactly What You Mean

You have just finished a session that touched `internal/grant/handler.go`, `internal/grant/service.go`, and `internal/grant/repository.go`. These changes belong to different logical commits:
- "Add grant validation rules" (service changes only)
- "Add grant repository INSERT" (repository changes only)

Use `git add -p` (patch mode) to stage only the lines you want:

```bash
git add -p internal/grant/service.go
```

Git will walk through each change "hunk" and ask what to do:
```
@@ -45,6 +45,12 @@ func (s *Service) Apply(...)
+    if req.GrantRequired <= 0 {
+        return ErrInvalidAmount
+    }
Stage this hunk [y,n,q,a,d,/,e,?]?
```

Answer keys:
- `y` — stage this hunk
- `n` — skip this hunk (leave it unstaged)
- `s` — split this hunk into smaller pieces
- `e` — manually edit the hunk in your editor
- `q` — quit, leaving remaining hunks unstaged
- `?` — show help

This lets you create focused commits from a messy working session without losing work.

Another useful pattern — stage a complete file but exclude one method you are not ready to commit:

```bash
git add -p internal/grant/handler.go
# Answer 'y' to all validation change hunks
# Answer 'n' to the bulk-pdf handler hunk you are still working on
git commit -m "Add grant application validation"
# The bulk-pdf changes remain unstaged
```

---

## Branch Naming Conventions for This Project

Consistent branch names make it obvious what work is in progress at a glance:

| Branch type | Format | Example |
|---|---|---|
| Feature | `feature/<short-description>` | `feature/user-login` |
| Feature (chapter) | `chapter-<N>-<topic>` | `chapter-06-auth-middleware` |
| Bug fix | `fix/<what-was-wrong>` | `fix/hfc-scoring-duplicate-cnic` |
| Release | `release/v<major>.<minor>.<patch>` | `release/v1.0.0` |
| Hotfix | `hotfix/<description>` | `hotfix/blocked-user-login` |
| Experiment | `experiment/<name>` | `experiment/bulk-html-pdf` |

Avoid: `my-branch`, `test`, `temp`, `aftab-working`, `final-v2`.

---

## Complete Login Feature Git Workflow

Here is a real sequence you will use when implementing the login feature:

```bash
# Start from main
git checkout main
git pull origin main

# Create the feature branch
git checkout -b feature/user-login

# === Commit 1: Repository layer ===
# Write internal/user/repository.go (FindByEmail SQL query)
git add internal/user/repository.go
git commit -m "Add user repository with FindByEmail query"

# === Commit 2: Service layer ===
# Write internal/user/service.go (Login method with bcrypt)
git add internal/user/service.go
git commit -m "Add user service Login method"

# === Commit 3: Handler layer ===
# Write internal/user/handler.go (HTTP decode + error mapping)
git add internal/user/handler.go
git commit -m "Add POST /api/login handler"

# === Commit 4: Wire into router ===
git add internal/app/app.go
git commit -m "Register login route in app"

# === Commit 5: Tests ===
git add internal/user/service_test.go
git add internal/user/handler_test.go
git commit -m "Add login tests: invalid credentials, blocked user, success"

# Review the full branch before merging
git log --oneline main..HEAD
# a1b2c3d Add login tests
# d4e5f6a Register login route in app
# e7f8g9b Add POST /api/login handler
# c1d2e3f Add user service Login method
# a4b5c6d Add user repository with FindByEmail query

git diff main...HEAD   # see everything the branch adds vs main
```

---

## Exploration Commands

Reading history is as important as writing it:

```bash
# Compact one-line graph of all branches
git log --oneline --graph --all --decorate

# What did a specific commit change?
git show a1b2c3d

# Who last changed this line and when?
git blame internal/user/service.go

# What changed between two commits?
git diff HEAD~3 HEAD

# Search the history for when a string was added
git log -S "ErrUserBlocked" --oneline

# Find which commit introduced a bug (binary search)
git bisect start
git bisect bad                  # current HEAD has the bug
git bisect good v0.9.0          # this tag was clean
# Git checks out middle commits, you run tests, mark good/bad
git bisect run go test ./internal/user -run TestLogin
git bisect reset                # finish bisect session
```

---

## Mastery Check

You understand this chapter when you can:
- Create a branch per chapter and per logical feature.
- Use `git add -p` to stage only the changes you want in a commit.
- Use `git stash` to save unfinished work and restore it after a context switch.
- Read `git log --oneline --graph` and describe what you see.
- Resolve a merge conflict by editing the file and completing the merge commit.
- Explain the difference between `merge` and `rebase` and when each is appropriate.
