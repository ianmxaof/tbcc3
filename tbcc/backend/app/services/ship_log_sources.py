"""Gather git + docs context for TBCC Ship Log protocol."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ShipLogContext:
    since_label: str
    commit_count: int
    commit_lines: list[str]
    improvement_notes_excerpt: str
    repo_root: Path


def _tbcc_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _parse_since(since: str) -> str:
    raw = (since or "7 days ago").strip()
    if re.fullmatch(r"\d+d", raw, flags=re.I):
        return f"{raw[:-1]} days ago"
    return raw


def collect_ship_log_context(*, since: str = "7 days ago", max_commits: int = 25) -> ShipLogContext:
    root = _tbcc_root()
    since_git = _parse_since(since)
    try:
        out = subprocess.check_output(
            [
                "git",
                "log",
                f"--since={since_git}",
                f"--max-count={max_commits}",
                "--pretty=format:%h %s (%cr)",
            ],
            cwd=root,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as e:
        out = (e.output or "").strip()
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    notes_path = root / "docs" / "TBCC_IMPROVEMENT_NOTES.md"
    excerpt = ""
    if notes_path.is_file():
        text = notes_path.read_text(encoding="utf-8", errors="replace")
        excerpt = text[:4000].strip()
    return ShipLogContext(
        since_label=since_git,
        commit_count=len(lines),
        commit_lines=lines,
        improvement_notes_excerpt=excerpt,
        repo_root=root,
    )


def format_ship_log_context(ctx: ShipLogContext) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# TBCC ship log sources ({ts})",
        f"Since: {ctx.since_label}",
        f"Commits: {ctx.commit_count}",
        "",
        "## Recent commits",
    ]
    if ctx.commit_lines:
        parts.extend(f"- {ln}" for ln in ctx.commit_lines)
    else:
        parts.append("- (no commits in range)")
    parts.extend(["", "## TBCC_IMPROVEMENT_NOTES.md (excerpt)", ""])
    if ctx.improvement_notes_excerpt:
        parts.append(ctx.improvement_notes_excerpt)
    else:
        parts.append("(file missing or empty)")
    return "\n".join(parts)
