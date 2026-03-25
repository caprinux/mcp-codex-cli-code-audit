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

## Prerequisites

- [Codex CLI](https://github.com/openai/codex) installed and on `$PATH` (`npm install -g @openai/codex`)
- `OPENAI_API_KEY` or `CODEX_API_KEY` set in your environment
- Python 3.10+

## Installation

```bash
pip install git+https://github.com/caprinux/mcp-codex-cli-code-audit.git
```

Or clone and install locally:

```bash
git clone https://github.com/caprinux/mcp-codex-cli-code-audit.git
cd mcp-codex-cli-code-audit
pip install -e .
```

## Claude Code Configuration

Add to your Claude Code MCP settings (`~/.claude/settings.json` or project `.claude/settings.json`):

```json
{
  "mcpServers": {
    "codex-bug-audit": {
      "command": "codex-bug-audit-mcp",
      "args": []
    }
  }
}
```

Or if running from source:

```json
{
  "mcpServers": {
    "codex-bug-audit": {
      "command": "python3",
      "args": ["-m", "codex_bug_audit_mcp.server"]
    }
  }
}
```

## Tools

### `audit_code`

Start a new source code audit.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `target_dir` | string | yes | Absolute path to the directory to audit |
| `focus_areas` | string | no | Comma-separated areas to focus on (e.g. "auth, SQL, input validation") |
| `file_patterns` | string | no | File glob patterns to focus on (e.g. "src/**/*.ts") |
| `model` | string | no | OpenAI model for Codex (default: "o3") |

Returns a session ID and structured bug report.

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

## Slash Commands (Automated Workflows)

This project includes Claude Code slash commands in `.claude/commands/` that automate the full audit loop. To use them, copy the `.claude/` directory into your target project, or symlink it.

### `/project:codex-audit:run [target_dir]`

**Fully automated audit-fix-iterate loop.** Claude will:
1. Ask Codex to audit the code
2. Fix all real bugs found
3. Re-audit (same session — Codex remembers previous findings)
4. Fix new/remaining bugs
5. Repeat until clean (max 5 rounds)

```
You: /project:codex-audit:run ./src
Claude: [autonomously audits, fixes, re-audits, fixes... until clean]
```

### `/project:codex-audit:report [target_dir]`

**Read-only audit report.** Codex audits the code and Claude cross-references each finding, but nothing is modified. Outputs a clean report grouped by severity.

```
You: /project:codex-audit:report
Claude: [produces severity-grouped bug report with confirmed vs false positive classifications]
```

### Setup for Slash Commands

Copy the commands into your project:

```bash
# From within your target project:
cp -r /path/to/mcp-codex-cli-code-audit/.claude .
```

Or symlink for automatic updates:

```bash
ln -s /path/to/mcp-codex-cli-code-audit/.claude/commands .claude/commands
```

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
