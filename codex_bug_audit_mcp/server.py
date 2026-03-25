#!/usr/bin/env python3
"""MCP server that invokes OpenAI Codex CLI for iterative source code auditing.

Tools exposed:
  - audit_code      : Start a new audit on a target directory
  - audit_iterate   : Re-audit after fixes (multi-turn, Codex remembers context)
  - audit_status    : Get session history and findings
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from mcp.server.fastmcp import FastMCP

from codex_agent_sdk import (
    AgentMessageItem,
    CodexAgentOptions,
    CodexSDKClient,
    CommandExecutionItem,
    ItemCompletedEvent,
    ReasoningItem,
    SandboxMode,
    TurnCompletedEvent,
    TurnFailedEvent,
)

# ── Types ───────────────────────────────────────────────────────────────────


@dataclass
class AuditRound:
    round: int
    timestamp: str
    findings: str
    status: str  # "clean" | "bugs_found" | "error"
    commands_run: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class AuditSession:
    id: str
    target_dir: str
    model: str
    rounds: list[AuditRound] = field(default_factory=list)
    created_at: str = ""
    # The codex-agent-sdk client for multi-turn
    _client: Optional[CodexSDKClient] = field(default=None, repr=False)
    thread_id: Optional[str] = None


# ── Session Store ───────────────────────────────────────────────────────────

_sessions: dict[str, AuditSession] = {}


def _generate_id() -> str:
    return f"audit_{int(time.time())}_{os.urandom(3).hex()}"


# ── Prompt Builders ─────────────────────────────────────────────────────────


def _build_initial_prompt(
    focus_areas: str | None = None,
    file_patterns: str | None = None,
) -> str:
    prompt = """\
You are performing a thorough static source code audit of this project. \
Your goal is to identify real, actionable bugs — not style issues or minor nitpicks.

Focus on:
- Logic errors, off-by-one errors, incorrect conditions
- Null/undefined dereferences, unhandled edge cases
- Security vulnerabilities (injection, auth bypass, path traversal, SSRF, etc.)
- Race conditions, deadlocks, resource leaks
- Incorrect error handling (swallowed errors, wrong error types)
- Data corruption risks (mutation of shared state, incorrect serialization)
- API contract violations (wrong types, missing validation)"""

    if focus_areas:
        prompt += f"\n\nPay special attention to these areas: {focus_areas}"

    if file_patterns:
        prompt += f"\n\nFocus your review on files matching: {file_patterns}"

    prompt += """

For each bug found, report:
1. **File and line number(s)**
2. **Bug type** (e.g., "logic error", "null dereference", "SQL injection")
3. **Severity** (critical / high / medium / low)
4. **Description** of the bug and why it's wrong
5. **Suggested fix** — concrete code change

If the code is clean and you find no bugs, explicitly state: \
"NO BUGS FOUND — code appears clean."

Do NOT report:
- Style preferences or formatting issues
- Missing documentation or comments
- Performance optimizations that don't affect correctness
- Theoretical issues that can't actually be triggered"""

    return prompt


def _build_iterate_prompt(fix_description: str | None = None) -> str:
    return f"""\
The developer reports they have {"fixed these issues: " + fix_description if fix_description else "addressed the previously identified bugs."}\

Please perform another round of source code audit:

1. Verify that the previously reported bugs have actually been fixed (not just superficially patched)
2. Check if the fixes introduced any NEW bugs (regression)
3. Look for any ADDITIONAL bugs that were not caught in the previous round
4. Look deeper — now that the obvious bugs are fixed, look for subtler issues

For each finding, report:
1. **File and line number(s)**
2. **Bug type**
3. **Severity** (critical / high / medium / low)
4. **Whether this is**: [NEW BUG] / [REGRESSION from fix] / [PREVIOUSLY REPORTED - NOT FIXED]
5. **Description** and **Suggested fix**

If all previous bugs are properly fixed and no new bugs are found, explicitly state: \
"NO BUGS FOUND — all previous issues resolved and no new bugs detected."
"""


# ── Classification ──────────────────────────────────────────────────────────

_CLEAN_PATTERNS = [
    re.compile(r"no bugs found", re.IGNORECASE),
    re.compile(r"code appears clean", re.IGNORECASE),
    re.compile(r"no new bugs", re.IGNORECASE),
    re.compile(r"all previous issues resolved and no new bugs", re.IGNORECASE),
    re.compile(r"no issues found", re.IGNORECASE),
    re.compile(r"code is clean", re.IGNORECASE),
]

_BUG_PATTERNS = [
    re.compile(r"\*\*severity\*\*:\s*(critical|high|medium)", re.IGNORECASE),
    re.compile(r"\[NEW BUG\]", re.IGNORECASE),
    re.compile(r"\[REGRESSION", re.IGNORECASE),
    re.compile(r"\[PREVIOUSLY REPORTED.*NOT FIXED\]", re.IGNORECASE),
]


def _classify(output: str) -> str:
    has_clean = any(p.search(output) for p in _CLEAN_PATTERNS)
    has_bugs = any(p.search(output) for p in _BUG_PATTERNS)
    if has_clean and not has_bugs:
        return "clean"
    return "bugs_found"


# ── Codex Interaction ───────────────────────────────────────────────────────


async def _run_codex_turn(
    client: CodexSDKClient,
    prompt: str,
) -> tuple[str, list[str], int, int]:
    """Run a single turn and extract findings, commands, and usage."""
    findings_parts: list[str] = []
    commands: list[str] = []
    input_tokens = 0
    output_tokens = 0

    async for event in client.run_streamed(prompt):
        if isinstance(event, ItemCompletedEvent):
            item = event.item
            if isinstance(item, AgentMessageItem) and item.text:
                findings_parts.append(item.text)
            elif isinstance(item, CommandExecutionItem):
                commands.append(f"$ {item.command}")
                if item.aggregated_output:
                    commands.append(item.aggregated_output[:500])
        elif isinstance(event, TurnCompletedEvent):
            if event.usage:
                input_tokens = event.usage.input_tokens
                output_tokens = event.usage.output_tokens
        elif isinstance(event, TurnFailedEvent):
            findings_parts.append(f"ERROR: {event.error.message}")

    findings = "\n\n".join(findings_parts) if findings_parts else "No output from Codex."
    return findings, commands, input_tokens, output_tokens


# ── MCP Server ──────────────────────────────────────────────────────────────

mcp = FastMCP(
    "codex-bug-audit",
    instructions=(
        "This server provides iterative source code auditing via OpenAI Codex CLI. "
        "Use audit_code to start an audit, audit_iterate to re-audit after fixes, "
        "and audit_status to check session history. The workflow is: "
        "audit → fix bugs → re-audit → fix → ... until clean."
    ),
)


@mcp.tool()
async def audit_code(
    target_dir: str,
    focus_areas: str = "",
    file_patterns: str = "",
    model: str = "o3",
) -> str:
    """Start a new source code audit using OpenAI Codex CLI.

    Codex will analyze the target directory for bugs, security vulnerabilities,
    logic errors, and other defects. Returns a structured bug report.

    After fixing the reported bugs, call audit_iterate with the returned
    session_id to verify fixes and find additional bugs.

    Args:
        target_dir: Absolute path to the directory to audit.
        focus_areas: Optional comma-separated areas to focus on (e.g. "auth, SQL, input validation").
        file_patterns: Optional file patterns to focus on (e.g. "src/**/*.ts").
        model: OpenAI model for Codex. Defaults to "o3".
    """
    # Validate
    resolved = os.path.abspath(target_dir)
    if not os.path.isdir(resolved):
        return f"Error: Directory does not exist: {resolved}"

    session_id = _generate_id()
    prompt = _build_initial_prompt(
        focus_areas=focus_areas or None,
        file_patterns=file_patterns or None,
    )

    # Create codex client with multi-turn support
    options = CodexAgentOptions(
        model=model,
        sandbox=SandboxMode.READ_ONLY,
        approval_policy=None,
        full_auto=True,
        cwd=resolved,
        skip_git_repo_check=True,
    )
    client = CodexSDKClient(options)

    session = AuditSession(
        id=session_id,
        target_dir=resolved,
        model=model,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        _client=client,
    )

    try:
        findings, commands, in_tok, out_tok = await _run_codex_turn(client, prompt)
        status = _classify(findings)
    except Exception as exc:
        findings = f"Codex execution error: {exc}"
        status = "error"
        commands = []
        in_tok = out_tok = 0

    # Save thread_id for multi-turn
    session.thread_id = client.thread_id

    audit_round = AuditRound(
        round=1,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        findings=findings,
        status=status,
        commands_run=commands,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )
    session.rounds.append(audit_round)
    _sessions[session_id] = session

    # Format output
    lines = [
        f"## Codex Audit — Round 1",
        f"**Session ID:** `{session_id}`",
        f"**Target:** {resolved}",
        f"**Model:** {model}",
        f"**Status:** {'CLEAN — No bugs found' if status == 'clean' else 'BUGS FOUND' if status == 'bugs_found' else 'ERROR'}",
        f"**Tokens:** {in_tok:,} in / {out_tok:,} out",
        "",
        "### Findings",
        findings,
        "",
        "---",
    ]

    if status == "bugs_found":
        lines.append(
            f"_Fix the reported bugs, then call `audit_iterate` with "
            f"session_id `{session_id}` to re-audit._"
        )
    elif status == "clean":
        lines.append("_Code appears clean. No further action needed._")
    else:
        lines.append("_An error occurred. Check Codex CLI installation and try again._")

    return "\n".join(lines)


@mcp.tool()
async def audit_iterate(
    session_id: str,
    fix_description: str = "",
) -> str:
    """Re-audit code after fixing bugs from a previous round.

    This continues an existing audit session. Codex remembers the previous
    findings through multi-turn context, verifies fixes, checks for regressions,
    and looks for additional bugs.

    This is the core of the iterative audit loop:
    audit_code → fix bugs → audit_iterate → fix → audit_iterate → ... until clean.

    Args:
        session_id: The session ID from a previous audit_code or audit_iterate call.
        fix_description: Optional description of what was fixed.
    """
    session = _sessions.get(session_id)
    if not session:
        return (
            f"Error: Session `{session_id}` not found. "
            "Start a new audit with `audit_code`."
        )

    client = session._client
    if client is None:
        return "Error: Session client is no longer available. Start a new audit."

    round_num = len(session.rounds) + 1
    prompt = _build_iterate_prompt(fix_description=fix_description or None)

    try:
        findings, commands, in_tok, out_tok = await _run_codex_turn(client, prompt)
        status = _classify(findings)
    except Exception as exc:
        findings = f"Codex execution error: {exc}"
        status = "error"
        commands = []
        in_tok = out_tok = 0

    audit_round = AuditRound(
        round=round_num,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        findings=findings,
        status=status,
        commands_run=commands,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )
    session.rounds.append(audit_round)

    total_in = sum(r.input_tokens for r in session.rounds)
    total_out = sum(r.output_tokens for r in session.rounds)

    lines = [
        f"## Codex Audit — Round {round_num}",
        f"**Session ID:** `{session.id}`",
        f"**Target:** {session.target_dir}",
        f"**Model:** {session.model}",
        f"**Status:** {'CLEAN — All issues resolved, no new bugs' if status == 'clean' else 'BUGS FOUND' if status == 'bugs_found' else 'ERROR'}",
        f"**This round tokens:** {in_tok:,} in / {out_tok:,} out",
        f"**Total tokens across {round_num} rounds:** {total_in:,} in / {total_out:,} out",
        "",
        "### Findings",
        findings,
        "",
        "---",
    ]

    if status == "bugs_found":
        lines.append(
            f"_Fix the reported bugs, then call `audit_iterate` again with "
            f"session_id `{session.id}` to continue the audit loop._"
        )
    elif status == "clean":
        lines.append(
            f"_All clear! Code has passed {round_num} round(s) of audit. "
            "The iterative audit is complete._"
        )
    else:
        lines.append("_An error occurred. Check the error and retry._")

    return "\n".join(lines)


@mcp.tool()
async def audit_status(session_id: str = "") -> str:
    """Get the status and history of audit sessions.

    If session_id is provided, shows detailed history for that session.
    If omitted, lists all active sessions.

    Args:
        session_id: Optional session ID. Omit to list all sessions.
    """
    if not session_id:
        if not _sessions:
            return "No active audit sessions. Start one with `audit_code`."

        listing = []
        for s in _sessions.values():
            last = s.rounds[-1] if s.rounds else None
            status = last.status if last else "no rounds"
            listing.append(
                f"- **`{s.id}`** — {s.target_dir} — "
                f"{len(s.rounds)} round(s) — last status: {status}"
            )

        return f"## Active Audit Sessions\n\n" + "\n".join(listing)

    session = _sessions.get(session_id)
    if not session:
        return f"Session not found: `{session_id}`"

    round_sections = []
    for r in session.rounds:
        section = [
            f"### Round {r.round} ({r.timestamp})",
            f"**Status:** {r.status}",
            f"**Tokens:** {r.input_tokens:,} in / {r.output_tokens:,} out",
        ]
        if r.commands_run:
            section.append(f"**Commands run:** {len(r.commands_run)}")
        section.append("")
        section.append(r.findings)
        round_sections.append("\n".join(section))

    total_in = sum(r.input_tokens for r in session.rounds)
    total_out = sum(r.output_tokens for r in session.rounds)
    last = session.rounds[-1] if session.rounds else None

    lines = [
        f"## Audit Session: `{session.id}`",
        f"**Target:** {session.target_dir}",
        f"**Model:** {session.model}",
        f"**Created:** {session.created_at}",
        f"**Rounds:** {len(session.rounds)}",
        f"**Current status:** {last.status if last else 'N/A'}",
        f"**Total tokens:** {total_in:,} in / {total_out:,} out",
        f"**Thread ID:** `{session.thread_id or 'N/A'}`",
        "",
        "\n\n---\n\n".join(round_sections),
    ]

    return "\n".join(lines)


# ── Command Installer ───────────────────────────────────────────────────────

def install_commands() -> None:
    """Copy slash command files to ~/.claude/commands/."""
    target = os.path.expanduser("~/.claude/commands")
    os.makedirs(target, exist_ok=True)

    # Commands are bundled as package data
    src_dir = os.path.join(os.path.dirname(__file__), "commands")

    copied = []
    for fname in os.listdir(src_dir):
        if not fname.endswith(".md"):
            continue
        src = os.path.join(src_dir, fname)
        dst = os.path.join(target, fname)
        with open(src) as f:
            content = f.read()
        with open(dst, "w") as f:
            f.write(content)
        copied.append(fname)

    if copied:
        print(f"Installed {len(copied)} command(s) to {target}:")
        for f in copied:
            name = f.removesuffix(".md")
            print(f"  /user:{name}")
    else:
        print("No command files found to install.")


# ── Entrypoint ──────────────────────────────────────────────────────────────


def main():
    import sys

    if "--install-commands" in sys.argv:
        install_commands()
        return

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
