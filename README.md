# codex-bug-audit-mcp

MCP server that uses [OpenAI Codex CLI](https://github.com/openai/codex) for iterative source code bug auditing. Built on the [codex-agent-sdk](https://github.com/caprinux/codex-agent-sdk-python) for multi-turn context — Codex remembers previous findings across audit rounds.

## How It Works

```
audit_code → Codex finds bugs → You fix bugs → audit_iterate → Codex verifies fixes & finds more
     ↑                                                                          │
     └──────────────── repeat until clean ──────────────────────────────────────┘
```

1. **`audit_code`** — Start a new audit. Codex analyzes your codebase in read-only sandbox mode and reports bugs with file locations, severity, and suggested fixes.
2. **Fix the bugs** — Claude (or you) fixes the reported issues.
3. **`audit_iterate`** — Re-audit. Codex verifies previous fixes, checks for regressions, and digs deeper for additional bugs. Multi-turn context means Codex remembers what it found before.
4. **Repeat** until Codex reports the code is clean.

## Quick Start

### 1. Install prerequisites

```bash
# Codex CLI
npm install -g @openai/codex

# Set your OpenAI API key
export OPENAI_API_KEY="sk-..."
```

### 2. Install the MCP server

```bash
pip install git+https://github.com/caprinux/mcp-codex-cli-code-audit.git
```

### 3. Register with Claude Code

```bash
claude mcp add codex-bug-audit -- codex-bug-audit-mcp
```

### 4. Install the slash commands

```bash
codex-bug-audit-mcp --install-commands
```

This copies the commands to `~/.claude/commands/` so they're available in every project.

### 5. Run it

```bash
claude

# Inside Claude Code:
> /user:codex-audit-run
```

That's it. Claude will ask Codex to audit your code, fix the bugs, re-audit, and iterate until clean.

## Slash Commands

### `/user:codex-audit-run [target_dir]`

**Fully automated audit-fix-iterate loop.** Claude will:
1. Ask Codex to audit the code
2. Fix all real bugs found
3. Re-audit (same session -- Codex remembers previous findings)
4. Fix new/remaining bugs
5. Repeat until clean (max 5 rounds)

### `/user:codex-audit-report [target_dir]`

**Read-only audit report.** Codex audits the code and Claude cross-references each finding, but nothing is modified. Outputs a clean report grouped by severity.

## MCP Tools (Advanced)

If you prefer manual control over the audit loop, the MCP server exposes three tools directly:

### `audit_code`

Start a new source code audit.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `target_dir` | string | yes | Absolute path to the directory to audit |
| `focus_areas` | string | no | Comma-separated areas to focus on (e.g. "auth, SQL, input validation") |
| `file_patterns` | string | no | File glob patterns to focus on (e.g. "src/**/*.ts") |
| `model` | string | no | OpenAI model for Codex (default: "o3") |

### `audit_iterate`

Re-audit after fixing bugs. Continues an existing session with multi-turn context.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `session_id` | string | yes | Session ID from previous audit |
| `fix_description` | string | no | What was fixed (helps Codex focus verification) |

### `audit_status`

Get session history and findings.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `session_id` | string | no | Session ID for details. Omit to list all sessions |

## Example Manual Workflow

```
You: Use audit_code to audit /path/to/my/project focusing on authentication

Claude: [calls audit_code] → Codex found 3 bugs:
  1. SQL injection in login query (critical)
  2. Missing null check in session handler (high)
  3. Race condition in token refresh (medium)

You: Fix these bugs

Claude: [fixes the 3 bugs]

You: Now re-audit with audit_iterate

Claude: [calls audit_iterate] → Codex reports:
  - SQL injection: FIXED ✓
  - Null check: FIXED ✓
  - Race condition: FIXED but introduced regression — new deadlock possible
  - NEW BUG: Unvalidated redirect in OAuth callback

You: Fix the remaining issues

Claude: [fixes remaining bugs]

You: Re-audit again

Claude: [calls audit_iterate] → "NO BUGS FOUND — all issues resolved"
```

## License

MIT
