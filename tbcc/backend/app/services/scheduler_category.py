"""Dashboard lean-group category for scheduled_text_posts rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.scheduled_text_post import ScheduledTextPost

SCHEDULER_CATEGORIES = frozenset(
    {"main_lane", "bot_commands", "liveness", "promo_bulletin", "manual"}
)


def infer_scheduler_category(name: str | None, category: str | None = None) -> str:
    """Mirror dashboard inferSchedulerGroup — explicit category wins."""
    cat = (category or "").strip().lower()
    if cat in SCHEDULER_CATEGORIES:
        return cat

    n = (name or "").lower()
    if "bot commands" in n:
        return "bot_commands"
    if "network liveness" in n or "drop ticker" in n or "spotlight" in n:
        return "liveness"
    if (
        "packs" in n
        or "links hub" in n
        or "cross-channel" in n
        or "celebration" in n
        or "bulletin" in n
        or "drop live" in n
        or "feed rhythm" in n
    ):
        return "promo_bulletin"
    if n.endswith(" scheduler") or "main group" in n:
        return "main_lane"
    return "manual"


def apply_scheduler_category(post: ScheduledTextPost, category: str | None = None) -> str:
    """Set scheduler_category from explicit value or inferred name."""
    value = infer_scheduler_category(post.name, category)
    post.scheduler_category = value
    return value
