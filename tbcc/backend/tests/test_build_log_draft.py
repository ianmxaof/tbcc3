"""Weekly build log draft helpers."""

from app.services.build_log_draft import (
    draft_mainhub_snippet_html,
    draft_patch_notes_html,
    extract_build_log_items,
    patch_notes_topic_link,
)
from app.services.ship_log_sources import ShipLogContext


def _ctx(lines: list[str], notes: str = "") -> ShipLogContext:
    return ShipLogContext(
        since_label="7 days ago",
        commit_count=len(lines),
        commit_lines=lines,
        improvement_notes_excerpt=notes,
        repo_root=__import__("pathlib").Path("."),
    )


def test_extract_build_log_items_prefers_feat_over_chore():
    ctx = _ctx(
        [
            "abc1234 chore: bump deps (2 days ago)",
            "def5678 feat: loot reveal video path (1 day ago)",
            "abc9012 fix: album delivery session lock (3 hours ago)",
        ]
    )
    items = extract_build_log_items(ctx, top_k=5)
    labels = [i.label for i in items]
    assert labels[0] == "loot reveal video path"
    assert "album delivery session lock" in labels
    assert not any("bump deps" in x for x in labels)


def test_patch_notes_html_includes_topic_link():
    ctx = _ctx(["abc1234 feat: link hub menus (1 day ago)"])
    items = extract_build_log_items(ctx, top_k=3)
    html = draft_patch_notes_html(items, week_key="2026-W31", commit_count=1, since_label="7 days ago")
    assert "PATCH NOTES" in html
    assert patch_notes_topic_link() in html
    assert "link hub menus" in html.lower()


def test_mainhub_snippet_truncates_top_k():
    ctx = _ctx(
        [
            f"aaa{i:04d} feat: item {i} (1 day ago)"
            for i in range(10)
        ]
    )
    items = extract_build_log_items(ctx, top_k=8)
    html = draft_mainhub_snippet_html(items, week_key="2026-W31", top_k=3)
    assert html.count("item ") <= 3
    assert "PATCH NOTES" in html


def test_is_weekly_build_log_due_monday_930_la():
    from datetime import datetime, timezone
    from app.services.weekly_build_log import is_weekly_build_log_due

    # 2026-08-03 is a Monday; 16:30 UTC = 09:30 PDT
    due = datetime(2026, 8, 3, 16, 30, tzinfo=timezone.utc)
    assert is_weekly_build_log_due(due) is True
    not_due = datetime(2026, 8, 3, 16, 0, tzinfo=timezone.utc)
    assert is_weekly_build_log_due(not_due) is False
