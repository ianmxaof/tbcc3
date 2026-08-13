"""Weekly build log — git + improvement-notes synopsis for Telegram patch posts."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from app.data.aof_main_group_topic_map import main_group_topic_deep_link
from app.data.aof_network import MAIN_GROUP_PATCH_NOTES_TOPIC_ID
from app.services.ship_log_autodraft import _clean_subject, _subject
from app.services.ship_log_sources import ShipLogContext, collect_ship_log_context

_SKIP_PREFIXES = ("merge ", "wip", "fixup", "squash", "chore:", "docs:")
_FEAT_PREFIX = re.compile(r"^(feat|fix|ux|ops|refactor|perf|test)(?:\([^)]+\))?:\s*", re.I)


@dataclass(frozen=True)
class BuildLogItem:
    label: str
    kind: str  # feature | fix | other
    source: str  # commit | notes


def _normalize_label(raw: str) -> str:
    s = (raw or "").strip()
    s = _FEAT_PREFIX.sub("", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:160]


def _kind_from_subject(subject: str) -> str:
    low = subject.lower()
    if low.startswith("fix"):
        return "fix"
    if low.startswith(("feat", "ux", "add")):
        return "feature"
    return "other"


def extract_build_log_items(
    ctx: ShipLogContext,
    *,
    top_k: int = 8,
    notes_top_k: int = 3,
) -> list[BuildLogItem]:
    """Top-k highlights from commits + improvement notes (commits first)."""
    items: list[BuildLogItem] = []
    seen: set[str] = set()

    for line in ctx.commit_lines:
        raw_subj = _subject(line)
        low_raw = raw_subj.lower()
        if any(low_raw.startswith(p) for p in ("merge ", "wip", "fixup", "squash", "chore:", "docs:")):
            continue
        subj = _clean_subject(raw_subj)
        if not subj:
            continue
        label = _normalize_label(subj)
        key = label.lower()
        if not label or key in seen:
            continue
        seen.add(key)
        items.append(BuildLogItem(label=label, kind=_kind_from_subject(subj), source="commit"))
        if len(items) >= top_k:
            return items

    if ctx.improvement_notes_excerpt and len(items) < top_k:
        for raw in ctx.improvement_notes_excerpt.splitlines():
            line = raw.strip()
            if not line.startswith(("- ", "* ", "• ")):
                continue
            body = re.sub(r"^[-*•]\s*", "", line).strip()
            body = re.sub(r"^\[[ xX]\]\s*", "", body).strip()
            if len(body) < 12:
                continue
            label = _normalize_label(body)
            key = label.lower()
            if not label or key in seen:
                continue
            seen.add(key)
            items.append(BuildLogItem(label=label, kind="other", source="notes"))
            if len(items) >= top_k or sum(1 for i in items if i.source == "notes") >= notes_top_k:
                break

    return items


def patch_notes_topic_link() -> str:
    return main_group_topic_deep_link(MAIN_GROUP_PATCH_NOTES_TOPIC_ID)


def _bullet_lines(items: list[BuildLogItem], *, max_items: int) -> list[str]:
    out: list[str] = []
    for item in items[:max_items]:
        icon = "✨" if item.kind == "feature" else "🩹" if item.kind == "fix" else "•"
        out.append(f"{icon} {html.escape(item.label)}")
    return out


def draft_patch_notes_html(
    items: list[BuildLogItem],
    *,
    week_key: str,
    commit_count: int,
    since_label: str,
) -> str:
    """Full weekly patch notes for Loot Room PATCH NOTES topic."""
    topic_link = patch_notes_topic_link()
    bullets = _bullet_lines(items, max_items=len(items) or 1)
    if not bullets:
        bullets = ["• Ops pass — no major user-facing deltas this week."]

    parts = [
        f"🛠 <b>PATCH NOTES</b> — {html.escape(week_key)}",
        f"<i>Shipped {html.escape(since_label)} · {commit_count} commits</i>",
        "",
        "<b>Highlights</b>",
        *bullets,
        "",
        f'<a href="{html.escape(topic_link, quote=True)}">Stay in PATCH NOTES</a> · '
        f"@aofmainhub for the public synopsis",
    ]
    return "\n".join(parts)[:4096]


def draft_mainhub_snippet_html(
    items: list[BuildLogItem],
    *,
    week_key: str,
    top_k: int = 4,
) -> str:
    """Short synopsis for @aofmainhub — points readers to PATCH NOTES."""
    topic_link = patch_notes_topic_link()
    bullets = _bullet_lines(items, max_items=top_k)
    if not bullets:
        bullets = ["• Weekly ops pass — tap below for full notes."]

    return (
        f"📋 <b>Weekly build log</b> — {html.escape(week_key)}\n"
        "<i>What shipped on the AOF stack this week.</i>\n\n"
        + "\n".join(bullets)
        + "\n\n"
        f'Full patch notes → <a href="{html.escape(topic_link, quote=True)}">Loot Room · PATCH NOTES</a>'
    )[:4096]


def mainhub_patch_notes_buttons() -> list[list[dict[str, str]]]:
    link = patch_notes_topic_link()
    return [[{"text": "📋 PATCH NOTES (full)", "url": link}]]


def collect_weekly_build_log_context(*, since: str = "7 days ago", max_commits: int = 40) -> ShipLogContext:
    return collect_ship_log_context(since=since, max_commits=max_commits)
