"""Gather git + docs context for TBCC Ship Log protocol."""

from __future__ import annotations

import json
import os
import re
import shutil
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


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _tbcc_root() -> Path:
    env = (os.getenv("TBCC_ROOT") or "").strip()
    if env:
        return Path(env)
    root = Path(__file__).resolve().parents[3]
    if (root / "docs" / "TBCC_IMPROVEMENT_NOTES.md").is_file():
        return root
    return _backend_root()


def _ship_log_cache_path() -> Path:
    bundled = _backend_root() / "app" / "data" / "ship_log_context.json"
    if bundled.is_file():
        return bundled
    return _backend_root() / ".tbcc-run" / "ship_log_context.json"


def _parse_since(since: str) -> str:
    raw = (since or "7 days ago").strip()
    if re.fullmatch(r"\d+d", raw, flags=re.I):
        return f"{raw[:-1]} days ago"
    return raw


def _git_cwd_candidates() -> list[Path]:
    out: list[Path] = []
    for p in (_tbcc_root(), _backend_root(), _backend_root().parent):
        if p not in out:
            out.append(p)
    return out


def _read_improvement_notes_excerpt() -> str:
    candidates = [
        _tbcc_root() / "docs" / "TBCC_IMPROVEMENT_NOTES.md",
        _backend_root() / "app" / "data" / "TBCC_IMPROVEMENT_NOTES_SNAPSHOT.md",
        _backend_root() / ".tbcc-run" / "TBCC_IMPROVEMENT_NOTES.md",
        _backend_root() / "docs" / "TBCC_IMPROVEMENT_NOTES.md",
    ]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")[:4000].strip()
    return ""


def _load_cached_commit_lines() -> list[str]:
    path = _ship_log_cache_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    lines = data.get("commit_lines")
    if isinstance(lines, list):
        return [str(ln).strip() for ln in lines if str(ln).strip()]
    return []


def _git_commit_lines(*, since_git: str, max_commits: int) -> list[str]:
    if not shutil.which("git"):
        return _load_cached_commit_lines()
    out = ""
    for cwd in _git_cwd_candidates():
        if not (cwd / ".git").exists() and cwd == _backend_root():
            continue
        try:
            out = subprocess.check_output(
                [
                    "git",
                    "log",
                    f"--since={since_git}",
                    f"--max-count={max_commits}",
                    "--pretty=format:%h %s (%cr)",
                ],
                cwd=cwd,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            break
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            out = ""
            continue
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return lines or _load_cached_commit_lines()


def write_ship_log_cache(*, since: str = "7 days ago", max_commits: int = 40) -> Path:
    """Snapshot git log for island deploy (container has no git)."""
    ctx = collect_ship_log_context(since=since, max_commits=max_commits, _allow_cache=False)
    path = _backend_root() / "app" / "data" / "ship_log_context.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "written_at": datetime.now(timezone.utc).isoformat(),
        "since_label": ctx.since_label,
        "commit_lines": ctx.commit_lines,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def collect_ship_log_context(
    *,
    since: str = "7 days ago",
    max_commits: int = 25,
    _allow_cache: bool = True,
) -> ShipLogContext:
    root = _tbcc_root()
    since_git = _parse_since(since)
    lines = _git_commit_lines(since_git=since_git, max_commits=max_commits)
    if not lines and _allow_cache:
        lines = _load_cached_commit_lines()
    excerpt = _read_improvement_notes_excerpt()
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
