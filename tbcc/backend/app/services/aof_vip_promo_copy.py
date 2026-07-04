"""AOF VIP upsell copy — delegates to deal stack for network rotation."""

from __future__ import annotations

import html

from sqlalchemy.orm import Session

from app.services.aof_main_group_copy import vip_promo_minimal_bodies
from app.services.aof_vip_deal_copy import build_vip_deal_caption_html


def vip_promo_post_bodies() -> list[str]:
    """HTML bodies (no footer) — short rotation variants pointing at Pay ⭐ checkout."""
    return vip_promo_minimal_bodies()


def vip_promo_with_lane(lane_name: str) -> str:
    lane_name = html.escape(lane_name.strip() or "this lane")
    return (
        f"⭐ <b>{lane_name}</b> hits VIP first — unwrapped in the paid channel. "
        f"God roll + mega + companion credits. Pay ⭐ below."
    )


def vip_checkout_caption_for_plan(db: Session, plan_id: int) -> str:
    """Full deal seller for payment modal follow-up."""
    return build_vip_deal_caption_html(db, plan_id, include_urgency=True)
