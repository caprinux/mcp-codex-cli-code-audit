You are running a targeted code audit on recent changes using the Codex Bug Audit MCP tools.

Instead of auditing the entire codebase, you will summarize what was recently changed and have Codex audit only those changes.

**Arguments:** $ARGUMENTS
- If a number is given (e.g. "5"), look at the last N commits.
- If a branch name is given (e.g. "main"), look at changes since diverging from that branch.
- If empty, default to the last 5 commits on the current branch.

## Step 1: Identify What Changed

**If inside a git repository:** run `git log` and `git diff` to identify changed files and understand what was modified. Summarize the changes in plain English.

**If NOT in a git repository:** use your conversation context — you already know what you recently implemented or changed. Summarize from memory.

Either way, produce:
- A plain-English summary of each feature or change (1-2 sentences each)
- The list of changed files

## Step 2: Audit with Codex

Call the `audit_code` MCP tool with:
- `target_dir`: the current working directory
- `focus_areas`: your plain-English summary, e.g.:
  "The following features were recently implemented. Audit only these changes, not the rest of the codebase:
  1. Added JWT authentication middleware in auth.py — validates tokens and extracts user claims
  2. New /api/upload endpoint in routes.py — accepts multipart file uploads with size validation
  Check these changes for logic errors, edge cases, security issues, and regressions."
- `file_patterns`: comma-separated list of the changed files

## Step 3: Fix and Iterate

1. Review Codex's findings — skip false positives, confirm real bugs by reading the code
2. Fix confirmed bugs with minimal, surgical changes
3. Call `audit_iterate` describing what you fixed
4. Repeat until clean (max 5 rounds)

## Rules

- **Only audit changed code.** Scope the review to recently modified files.
- **Verify before fixing.** Always read the file and understand context before changing anything.
- **Minimal changes.** Fix only what Codex flagged.
- **Max 5 rounds.**

## Output Format

```
## Recent Changes Audit Complete

**Changes summary:**
- [one-line description of each feature/change]

**Files audited:** [list]

**Rounds:** X
**Bugs found:** X
**Bugs fixed:** X
**False positives skipped:** X
**Status:** CLEAN / REMAINING ISSUES

### Fixed Bugs
- [file:line] description of fix

### False Positives (skipped)
- [file:line] why this was not a real bug

### Remaining Issues (if any)
- [file:line] why this was not fixed
```
