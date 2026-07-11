"""Resolve AOF social / gate URLs for X Buffer armory (from env)."""

from __future__ import annotations

import os

DEFAULT_LOOT_BOT_USERNAME = "aof_lootgod_bot"
DEFAULT_LOOT_ROOM_PUBLIC_URL = "https://t.me/+NWathiLSqZ1lMzlh"


def x_linkvertise_enabled() -> bool:
    """When false (default), Buffer/X must not use Linkvertise gates — Telegram only."""
    return (os.getenv("TBCC_X_USE_LINKVERTISE") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def aof_hub_invite_url() -> str:
    return (os.getenv("TBCC_AOF_HUB_INVITE_URL") or "").strip() or loot_room_public_url()


def loot_bot_username() -> str:
    return (
        (os.getenv("TBCC_LOOT_BOT_USERNAME") or "").strip().lstrip("@")
        or DEFAULT_LOOT_BOT_USERNAME
    )


def loot_bot_free_pull_url() -> str:
    return (os.getenv("TBCC_LOOT_BOT_FREE_PULL_URL") or "").strip() or (
        f"https://t.me/{loot_bot_username()}?start=loot_free"
    )


def loot_room_public_url() -> str:
    return (
        (os.getenv("TBCC_LOOT_ROOM_PUBLIC_URL") or "").strip()
        or (os.getenv("TBCC_LOOT_ROOM_INVITE_URL") or "").strip()
        or DEFAULT_LOOT_ROOM_PUBLIC_URL
    )


def aof_public_cta_url() -> str:
    """Top-of-funnel public CTA: Loot Bot first, or Loot Room group when explicitly configured."""
    mode = (os.getenv("TBCC_AOF_PUBLIC_CTA_MODE") or "loot_bot").strip().lower()
    if mode in {"loot_room", "room", "group"}:
        return loot_room_public_url()
    return loot_bot_free_pull_url()


def x_outbound_url() -> str:
    """Primary CTA for Buffer/X — Loot Bot/Loot Room unless a safe override is configured."""
    if x_linkvertise_enabled():
        return aof_gate_url()
    from app.services.link_gate_provider import is_linkvertise_host

    overflow = (os.getenv("TBCC_BUFFER_X_OVERFLOW_URL") or "").strip()
    if overflow and not is_linkvertise_host(overflow):
        return overflow
    return aof_public_cta_url()


def aof_gate_url_alt() -> str:
    return (os.getenv("TBCC_AOF_GATE_URL_ALT") or "").strip()


def aof_gate_url() -> str:
    """Monetized gate URL (Work.ink / LootLabs). Falls back to hub invite."""
    primary = (os.getenv("TBCC_AOF_GATE_URL") or "").strip()
    if primary:
        return primary
    alt = aof_gate_url_alt()
    if alt:
        return alt
    return aof_hub_invite_url()


def allmylinks_url() -> str:
    return (os.getenv("TBCC_ALLMYLINKS_URL") or "").strip()


def donation_url() -> str:
    """Optional Gumroad / Ko-fi / support link (shown in footers + payment bot)."""
    return (os.getenv("TBCC_DONATION_URL") or "").strip()


def donation_link_html(*, label: str = "Buy me a coffee") -> str:
    url = donation_url()
    if not url:
        return ""
    from app.services.aof_growth_hub import _a_tag

    return _a_tag(url, label)


def gravatar_profile_url() -> str:
    u = (os.getenv("TBCC_GRAVATAR_PROFILE_USERNAME") or "").strip().lstrip("@")
    if u:
        return f"https://gravatar.com/{u}"
    return (os.getenv("TBCC_GRAVATAR_PROFILE_URL") or "").strip()


def affiliate_undress_primary_url() -> str:
    return (
        (os.getenv("TBCC_AFFILIATE_UNDRESS_URL") or "").strip()
        or "https://nodress.site/tg/bot?username=Aifasteditbot&ref_id=7787282561"
    )


def affiliate_drawai_url() -> str:
    return (
        (os.getenv("TBCC_AFFILIATE_DRAWAI_URL") or "").strip()
        or "https://t.me/drawai_0_bot?start=7787282561"
    )


def affiliate_botynude_url() -> str:
    return (os.getenv("TBCC_AFFILIATE_BOTYNUDE_URL") or "").strip() or "https://botynude.com/ref/39Z9HHK3"


def gravatar_avatar_image_url() -> str | None:
    """Optional https image for Buffer post assets (set explicitly — Gravatar username ≠ avatar CDN)."""
    u = (os.getenv("TBCC_GRAVATAR_AVATAR_URL") or "").strip()
    return u if u.startswith("https://") else None


def buffer_ig_default_image_url() -> str | None:
    """Public https image for Buffer Instagram when armory item has no image_url."""
    u = (os.getenv("TBCC_BUFFER_IG_DEFAULT_IMAGE_URL") or "").strip()
    if u.startswith("https://"):
        return u

    basename = (os.getenv("TBCC_BUFFER_IG_PROMO_BASENAME") or "aof-buffer-ig.png").strip()
    base = (
        (os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_PUBLIC_BASE_URL") or "").strip()
    ).rstrip("/")
    if base.startswith("https://") and basename and ".." not in basename and "/" not in basename:
        from app.services.promo_storage import promo_path_from_public_url

        url = f"{base}/static/promo/{basename}"
        if promo_path_from_public_url(url):
            return url

    return gravatar_avatar_image_url()


def fill_armory_template(
    text: str,
    *,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    utm_content: str | None = None,
    db=None,
    advance_affiliate: bool = False,
    for_x: bool = False,
) -> str:
    from app.services.utm_links import allmylinks_tracked_url
    from app.services.promo_affiliate_rotation import resolve_affiliate_url

    gate = x_outbound_url() if for_x else aof_gate_url()
    hub = aof_public_cta_url() if for_x else aof_hub_invite_url()
    loot_bot = loot_bot_free_pull_url()
    loot_room = loot_room_public_url()
    aml_base = allmylinks_url()
    if aml_base:
        aml = allmylinks_tracked_url(
            source=utm_source or "buffer",
            medium=utm_medium or "x",
            campaign=utm_campaign or "armory",
            content=utm_content,
            base_url=aml_base,
        )
    else:
        aml = hub
    grav = gravatar_profile_url() or aml
    aff = resolve_affiliate_url(
        db,
        "x_buffer",
        advance=advance_affiliate,
        fallback=affiliate_undress_primary_url(),
    )
    donate = donation_url() or aml
    return (
        (text or "")
        .replace("{gate}", gate)
        .replace("{hub}", hub)
        .replace("{loot_bot}", loot_bot)
        .replace("{loot_room}", loot_room)
        .replace("{allmylinks}", aml)
        .replace("{gravatar}", grav)
        .replace("{affiliate}", aff)
        .replace("{affiliate_undress}", aff)
        .replace("{affiliate_drawai}", affiliate_drawai_url())
        .replace("{affiliate_botynude}", affiliate_botynude_url())
        .replace("{donate}", donate)
        .replace("{donation}", donate)
        .strip()
    )
