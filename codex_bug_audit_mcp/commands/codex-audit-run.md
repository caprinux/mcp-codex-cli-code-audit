You are running an automated iterative code audit loop using the Codex Bug Audit MCP tools.

## Your Task

Audit the code in this project, fix all real bugs found, and keep iterating until the code is clean. You must be autonomous — do not ask the user for confirmation between rounds. Just audit, fix, re-audit, fix, repeat.

**Target directory:** $ARGUMENTS (if empty, use the current working directory)

## Workflow

### Round 1: Initial Audit

1. Call the `audit_code` MCP tool with the target directory. Use model "o3" for deep analysis.
2. Read the findings carefully. Separate **real bugs** from false positives.

### For Each Bug Found

3. Read the relevant source file(s) to understand the full context around the bug.
4. Fix the bug. Make minimal, surgical changes — do not refactor surrounding code.
5. After fixing, briefly note what you changed (one line per fix).

### Re-Audit Round

6. After fixing ALL bugs from the current round, call `audit_iterate` with:
   - The same `session_id` from the initial audit
   - A `fix_description` summarizing what you fixed (e.g. "Fixed SQL injection in login.py:42, added null check in handler.py:88")
7. This uses multi-turn context — Codex remembers what it previously found and can verify your fixes.

### Iterate

8. If Codex finds more bugs (new bugs, regressions, or unfixed issues), go back to step 3.
9. If Codex says the code is clean, stop and report the summary.

## Rules

- **Max 5 rounds.** If after 5 rounds there are still bugs, stop and report what's left.
- **Skip false positives.** If a finding is not a real bug (style nitpick, theoretical issue, or incorrect analysis), note it as a false positive and move on. Do NOT fix non-bugs.
- **Verify before fixing.** Always read the file and understand the context before making changes. Don't blindly apply suggested fixes.
- **Minimal changes.** Fix only what Codex flagged. Don't improve code style, add comments, or refactor.
- **Track everything.** Keep a running tally of: rounds completed, bugs found, bugs fixed, false positives skipped.

## Output Format

After the loop completes, provide a summary:

```
## Audit Complete

**Rounds:** X
**Total bugs found:** X
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
