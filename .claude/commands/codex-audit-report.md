You are running a code audit report using the Codex Bug Audit MCP tools. You will audit the code and present findings, but NOT fix anything.

**Target directory:** $ARGUMENTS (if empty, use the current working directory)

## Workflow

1. Call the `audit_code` MCP tool with the target directory.
2. Read the findings and cross-reference each one by reading the actual source files.
3. Classify each finding as **confirmed bug** or **false positive** based on your own analysis.
4. Present a clean, organized report grouped by severity.

## Output Format

```
## Code Audit Report

**Target:** <directory>
**Model:** <model used>

### Critical
- [file:line] Bug type — description

### High
- [file:line] Bug type — description

### Medium
- [file:line] Bug type — description

### Low
- [file:line] Bug type — description

### False Positives (Codex reported, but not real bugs)
- [file:line] Why this is not a bug

### Summary
X confirmed bugs found (Y critical, Z high, ...)
```

Do NOT fix any bugs. This is a read-only report.
