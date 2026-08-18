"""X caption copy for the Telegram → Erome → Buffer flywheel."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.buffer_x_caption import finalize_buffer_x_caption
from app.services.buffer_x_hashtags import append_x_hashtags
from app.services.buffer_x_promo_image import pick_promo_image


def build_flywheel_x_caption(
    lane: str,
    *,
    erome_album_url: str | None = None,
    telegram_invite: str | None = None,
    hub_url: str | None = None,
    promo_viewer_url: str | None = None,
    db: Session | None = None,
    advance_link_cycle: bool = False,
) -> str:
    """
    Top-of-funnel X post: lane tease + optional Erome gallery + Telegram/hub exits.
    Never claims Erome unless erome_album_url is present.
    """
    from app.services.aof_social_links import aof_hub_invite_url, loot_free_start_url, x_outbound_url
    from app.services.utm_links import allmylinks_tracked_url, slug_utm_value

    name = (lane or "AOF").strip()
    erome = (erome_album_url or "").strip()
    has_erome = erome.startswith("https://")

    if has_erome:
        opener = f"New drop on {name} — preview on Erome, full stack on Telegram."
    else:
        opener = f"New drop on {name} — full stack on Telegram. Hub map below."

    lines: list[str] = [opener]

    loot = (loot_free_start_url() or "").strip()
    if loot.startswith("https://"):
        lines.append(loot)

    if has_erome:
        lines.append(erome)

    viewer = (promo_viewer_url or "").strip()
    if viewer.startswith("https://") and viewer != erome and viewer != loot:
        lines.append(viewer)

    tg = (telegram_invite or "").strip()
    if tg and tg not in (loot,):
        lines.append(tg)

    hub = (hub_url or "").strip() or allmylinks_tracked_url(
        source="buffer",
        medium="x",
        campaign="flywheel",
        content=slug_utm_value(name, fallback="pool"),
    )
    if not hub:
        hub = aof_hub_invite_url()
    overflow = x_outbound_url() or hub
    body = "\n".join(x for x in lines if x)
    text = finalize_buffer_x_caption(
        body,
        db=db,
        overflow_url=overflow,
        advance_link_cycle=advance_link_cycle,
    )
    from app.services.buffer_x_caption import buffer_x_max_chars

    return append_x_hashtags(text, lane=name, max_chars=buffer_x_max_chars())
