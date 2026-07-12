"""X caption copy for the Telegram → Erome → Buffer flywheel."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.buffer_x_caption import finalize_buffer_x_caption
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
    Top-of-funnel X post: lane tease + Erome gallery (view monetization) + Telegram/hub exits.
    """
    from app.services.aof_social_links import aof_hub_invite_url, x_outbound_url
    from app.services.utm_links import allmylinks_tracked_url, slug_utm_value

    name = (lane or "AOF").strip()
    lines: list[str] = [f"New drop on {name} — preview on Erome, full stack on Telegram."]

    erome = (erome_album_url or "").strip()
    if erome.startswith("https://"):
        lines.append(erome)

    viewer = (promo_viewer_url or "").strip()
    if viewer.startswith("https://") and viewer != erome:
        lines.append(viewer)

    tg = (telegram_invite or "").strip()
    if tg:
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
    return finalize_buffer_x_caption(
        body,
        db=db,
        overflow_url=overflow,
        advance_link_cycle=advance_link_cycle,
    )


def pick_flywheel_promo_image() -> tuple[str | None, str | None]:
    """Returns (direct_url for Buffer embed, optional monetized viewer URL for caption)."""
    entry = pick_promo_image()
    if not entry:
        return None, None
    direct = str(entry.get("direct_url") or "").strip() or None
    viewer = str(entry.get("viewer_url") or "").strip() or None
    return direct, viewer
