"""Heuristic ship-log tweet drafts from git context — no LLM (cron-safe)."""

from __future__ import annotations

import re

from app.services.ship_log_sources import ShipLogContext

_MAX = 260
_SKIP_PREFIXES = ("merge ", "wip", "fixup", "squash")


def _subject(line: str) -> str:
    # "abc1234 subject (2 days ago)" -> subject
    m = re.match(r"^[0-9a-f]+\s+(.+?)\s+\(", line.strip())
    return (m.group(1) if m else line).strip()


def _clean_subject(s: str) -> str:
    s = re.sub(r"^(tbcc|fix|feat|chore|docs):\s*", "", s, flags=re.I).strip()
    if any(s.lower().startswith(p) for p in _SKIP_PREFIXES):
        return ""
    return s


def draft_ship_log_tweet(ctx: ShipLogContext, *, angle: str = "week") -> str:
    """Return tweet text or empty if nothing worth posting."""
    themes: list[str] = []
    for line in ctx.commit_lines:
        subj = _clean_subject(_subject(line))
        if subj and subj not in themes:
            themes.append(subj)
        if len(themes) >= 3:
            break

    if not themes and not ctx.improvement_notes_excerpt:
        return ""

    if angle == "milestone":
        lead = themes[0] if themes else "ops and tooling milestone"
        body = (
            f"TBCC milestone: {lead}. "
            "Scheduling steady again — less firefighting, more shipping. "
            "#buildinpublic"
        )
    else:
        if themes:
            body = f"TBCC week: {themes[0]}"
            if len(themes) > 1:
                body += f" · {themes[1]}"
            body += ". Building the Telegram ops stack in public."
        else:
            body = "TBCC week: tooling and ops passes. Building in public."

    if len(body) > _MAX:
        body = body[: _MAX - 1].rstrip() + "…"
    return body


def draft_scheduler_steady_milestone() -> str:
    """Outcome-focused milestone — no scheduler IP/architecture."""
    return (
        "TBCC ops note: content scheduling went from constant firefighting to steady — "
        "posts land on time again. Plus agent workflow automation (gates, sprint state, "
        "ship-log ticks). Outcomes > internals. #buildinpublic"
    )
