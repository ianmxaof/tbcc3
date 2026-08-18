"""Resolve AOF social / gate URLs for X Buffer armory (from env)."""

from __future__ import annotations

import os


def x_linkvertise_enabled() -> bool:
    """When false (default), Buffer/X must not use Linkvertise gates — Telegram only."""
    return (os.getenv("TBCC_X_USE_LINKVERTISE") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def loot_bot_username() -> str:
    return (os.getenv("TBCC_LOOT_BOT_USERNAME") or "aof_lootgod_bot").strip().lstrip("@")


def payment_bot_username() -> str:
    return (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@")


def companion_bot_username() -> str:
    return (os.getenv("TBCC_COMPANION_BOT_USERNAME") or "aof_spicybot_bot").strip().lstrip("@")


def loot_public_cta_url() -> str:
    """
    Public top-of-funnel — bare AOF LOOT GOD bot profile (no deep-link params).
    Prefer https://telegram.me/aof_lootgod_bot over room invites / start= payloads.
    """
    explicit = (os.getenv("TBCC_LOOT_PUBLIC_CTA_URL") or "").strip()
    if explicit:
        return explicit
    un = loot_bot_username()
    return f"https://telegram.me/{un}" if un else ""


def loot_paid_checkout_url() -> str:
    """Payment-bot Loot Room key checkout (24h access)."""
    un = payment_bot_username()
    return f"https://t.me/{un}?start=loot" if un else ""


def loot_free_start_url() -> str:
    un = loot_bot_username()
    return f"https://telegram.me/{un}?start=loot_free" if un else loot_public_cta_url()


def aof_hub_invite_url() -> str:
    """
    Primary public hub CTA for Buffer/X/{hub} templates.
    Defaults to loot overseer (not banned Main invite, not bare Loot Room invite).
    """
    return (os.getenv("TBCC_AOF_HUB_INVITE_URL") or "").strip() or loot_public_cta_url()


def x_outbound_url() -> str:
    """Primary CTA for Buffer/X — hub invite or non-LV overflow, not Linkvertise by default."""
    if x_linkvertise_enabled():
        return aof_gate_url()
    from app.services.link_gate_provider import is_linkvertise_host

    overflow = (os.getenv("TBCC_BUFFER_X_OVERFLOW_URL") or "").strip()
    if overflow and not is_linkvertise_host(overflow):
        return overflow
    return loot_free_start_url() or aof_hub_invite_url()


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


def gumroad_vip_url() -> str:
    """AOF VIP subscription product (ynnulc) — card/PayPal checkout, distinct from coffee tips."""
    from app.data.aof_vip_membership import GUMROAD_VIP_PRODUCT_URL

    u = (os.getenv("TBCC_GUMROAD_PRODUCT_URL") or "").strip()
    if u.startswith("https://"):
        return u
    return GUMROAD_VIP_PRODUCT_URL


def gumroad_vip_link_html(*, label: str | None = None) -> str:
    from app.services.fiat_checkout_labels import fiat_vip_link_label

    url = gumroad_vip_url()
    if not url:
        return ""
    from app.services.aof_growth_hub import _a_tag

    return _a_tag(url, label or fiat_vip_link_label())


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


def affiliate_primary_fallback_url() -> str:
    """Default affiliate when rotation pool is empty — undress credits."""
    return affiliate_undress_primary_url()


def affiliate_undress_primary_url() -> str:
    return (
        (os.getenv("TBCC_AFFILIATE_UNDRESS_URL") or "").strip()
        or "https://ndfy.store/tg/bot?username=Luciddreamstobot&ref_id=7787282561"
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

    from app.services.buffer_x_promo_image import direct_url_for_buffer, pick_promo_image

    promo = direct_url_for_buffer(pick_promo_image())
    if promo:
        return promo

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
    from app.services.promo_affiliate_rotation import pick_affiliate_pair, resolve_affiliate_url

    gate = x_outbound_url() if for_x else aof_gate_url()
    hub = aof_hub_invite_url()
    if db is not None:
        aff, aff2 = pick_affiliate_pair(db, "x_buffer", advance=advance_affiliate)
    else:
        aff = resolve_affiliate_url(
            None,
            "x_buffer",
            advance=False,
            fallback=affiliate_primary_fallback_url(),
        )
        aff2 = affiliate_drawai_url() or aff
    aml_base = allmylinks_url()
    if aml_base:
        aml = allmylinks_tracked_url(
            source=utm_source or "buffer",
            medium=utm_medium or "x",
            campaign=utm_campaign or "armory",
            content=utm_content,
            base_url=aml_base,
        )
    elif for_x:
        # Never collapse map slots to {hub} on X — that triple-stacks lootgod.
        aml = aff2 or aff
    else:
        aml = hub
    grav_profile = gravatar_profile_url()
    if grav_profile:
        grav = grav_profile
    elif for_x:
        grav = aff if aff != aml else aff2
    else:
        grav = aml
    donate = donation_url() or aml
    gumroad_vip = gumroad_vip_url()
    from app.services.promo_affiliate_rotation import resolve_spicy_companion_url

    spicy = resolve_spicy_companion_url(db, placement="x_buffer") if db is not None else resolve_spicy_companion_url(None)
    lootgod = loot_public_cta_url()
    lootgod_free = loot_free_start_url()
    return (
        (text or "")
        .replace("{gate}", gate)
        .replace("{hub}", hub)
        .replace("{allmylinks}", aml)
        .replace("{gravatar}", grav)
        .replace("{affiliate}", aff)
        .replace("{affiliate2}", aff2)
        .replace("{affiliate_undress}", aff)
        .replace("{affiliate_drawai}", affiliate_drawai_url())
        .replace("{affiliate_botynude}", affiliate_botynude_url())
        .replace("{spicy}", spicy)
        .replace("{lootgod}", lootgod)
        .replace("{lootgod_free}", lootgod_free)
        .replace("{donate}", donate)
        .replace("{donation}", donate)
        .replace("{gumroad_vip}", gumroad_vip)
        .replace("{gumroad}", gumroad_vip)
        .strip()
    )
