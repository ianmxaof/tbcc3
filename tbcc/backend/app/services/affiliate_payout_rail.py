"""Classify promo affiliates by payout rail for cash/crypto-first rotation."""

from __future__ import annotations

from app.models.promo_affiliate_link import PromoAffiliateLink

# Lower index = higher rotation priority.
RAIL_ORDER: tuple[str, ...] = (
    "cash",
    "crypto",
    "subscription",
    "usd_revshare",
    "revshare_unknown",
    "platform_credits",
    "referral_credits",
    "funnel",
    "other",
)

RAIL_SORT_KEY: dict[str, int] = {rail: i for i, rail in enumerate(RAIL_ORDER)}

_DETAIL_TO_RAIL: dict[str, str] = {
    "usd_cash": "cash",
    "cash": "cash",
    "crypto": "crypto",
    "subscription": "subscription",
    "usd_revshare": "usd_revshare",
    "platform_credits": "platform_credits",
    "referral_credits": "referral_credits",
    "funnel": "funnel",
}

_KIND_TO_RAIL: dict[str, str] = {
    "pps": "cash",
    "cpa": "cash",
    "subscription": "subscription",
    "funnel": "funnel",
}

_CREDIT_HINTS = ("credit", "coin", "invite", "free ")
_CRYPTO_HINTS = ("wallet", "crypto", "ton", "usdt")
_USD_REVSHARE_HINTS = (
    "revshare on purchases",
    "musebox",
    "nakedly",
    "playbun",
    "fapify",
    "pornmaker",
    "botynude",
    "10%",
    "usd",
)


def infer_payout_rail(row: PromoAffiliateLink) -> str:
    detail = (getattr(row, "payout_detail", None) or "").strip().lower()
    if detail in _DETAIL_TO_RAIL:
        return _DETAIL_TO_RAIL[detail]

    kind = (row.payout_kind or "other").strip().lower()
    if kind in _KIND_TO_RAIL:
        return _KIND_TO_RAIL[kind]

    blob = f"{row.label or ''} {row.copy_template or ''} {detail}".lower()
    if any(h in blob for h in _CRYPTO_HINTS):
        return "crypto"
    if kind == "revshare":
        if any(h in blob for h in _CREDIT_HINTS):
            return "platform_credits"
        if any(h in blob for h in _USD_REVSHARE_HINTS):
            return "usd_revshare"
        return "revshare_unknown"
    if kind == "other" and ("referral" in blob or "cursor" in blob or "claude" in blob):
        return "referral_credits"
    return "other"


def affiliate_sort_key(row: PromoAffiliateLink) -> tuple[int, int, int]:
    rail = infer_payout_rail(row)
    return (
        RAIL_SORT_KEY.get(rail, len(RAIL_ORDER)),
        int(row.priority_tier or 99),
        int(row.id or 0),
    )
