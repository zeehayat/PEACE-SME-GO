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

## Mastery Check

You understand this chapter when you can:
- Create a branch per chapter.
- Review staged changes before committing.
- Explain the difference between working tree, staging area, and commit history.
- Recover from accidental staging.
- Resolve a simple conflict without panic.
