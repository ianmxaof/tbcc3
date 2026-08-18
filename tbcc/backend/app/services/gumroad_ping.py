"""Gumroad Ping (sale webhook) → TBCC external-order fulfill.

Gumroad POSTs ``application/x-www-form-urlencoded`` to ``POST /webhooks/gumroad``.

Primary path (recommended):
  1. Buyer taps Gumroad in ``@aofsubscriptions_bot`` → we create an EPO bound to their Telegram id
  2. Checkout URL includes ``?tbcc_ref=EPO-XXXXXXXX`` (shows up in Gumroad ``url_params``)
  3. Ping arrives → look up EPO → ``fulfill_external_order(..., payment_method=\"gumroad\")``
     → VIP invite DM (same Celery path as crypto)

Fallback: custom field ``telegram_user_id`` / ``Telegram ID`` + ``TBCC_GUMROAD_PRODUCT_MAP``
(permalink or product_id → plan_id) when no EPO is present.

Env:
  TBCC_GUMROAD_SELLER_ID — required match on ping ``seller_id``
  TBCC_GUMROAD_PRODUCT_URL — default product URL for bot CTA (optional per-plan map)
  TBCC_GUMROAD_PRODUCT_MAP — JSON object ``{\"permalink_or_product_id\": plan_id, ...}``
  TBCC_GUMROAD_CHECKOUT_ENABLED — ``1`` to show Gumroad buttons in payment bot
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

_EPO_RE = re.compile(r"\bEPO-[A-F0-9]{8,16}\b", re.I)
_TG_ID_RE = re.compile(r"^\d{5,15}$")


def gumroad_checkout_enabled() -> bool:
    return (os.getenv("TBCC_GUMROAD_CHECKOUT_ENABLED") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def gumroad_seller_id() -> str:
    return (os.getenv("TBCC_GUMROAD_SELLER_ID") or "").strip()


def gumroad_seller_ids() -> set[str]:
    """Ping ``seller_id`` is often the base64 id from Gumroad Advanced settings, not the numeric user id."""
    out: set[str] = set()
    for key in ("TBCC_GUMROAD_SELLER_ID", "TBCC_GUMROAD_PING_SELLER_ID"):
        v = (os.getenv(key) or "").strip()
        if v:
            out.add(v)
    return out


def gumroad_default_product_url() -> str:
    return (os.getenv("TBCC_GUMROAD_PRODUCT_URL") or os.getenv("TBCC_DONATION_URL") or "").strip()


def load_gumroad_product_map() -> dict[str, int]:
    raw = (os.getenv("TBCC_GUMROAD_PRODUCT_MAP") or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("TBCC_GUMROAD_PRODUCT_MAP is not valid JSON")
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in data.items():
        key = str(k).strip()
        try:
            pid = int(v)
        except (TypeError, ValueError):
            continue
        if key and pid > 0:
            out[key] = pid
            # Also index bare permalink slug from gum.co / gumroad URLs
            if "/" in key:
                slug = key.rstrip("/").split("/")[-1]
                if slug:
                    out[slug] = pid
    return out


def product_url_for_plan(plan_id: int) -> str | None:
    """Resolve Gumroad product URL for a plan (map URL keys or default)."""
    pid = int(plan_id)
    mapping = load_gumroad_product_map()
    # Prefer explicit URL in map values? Map is id-only — use reverse lookup via env URL templates
    # Optional: TBCC_GUMROAD_PLAN_URLS={"6":"https://…"}
    raw_urls = (os.getenv("TBCC_GUMROAD_PLAN_URLS") or "").strip()
    if raw_urls:
        try:
            data = json.loads(raw_urls)
            if isinstance(data, dict):
                u = str(data.get(str(pid)) or data.get(pid) or "").strip()
                if u.startswith("https://"):
                    return u
        except json.JSONDecodeError:
            pass
    # If this plan is in the product map, still use default product URL (single VIP SKU common)
    if mapping and pid in mapping.values():
        return gumroad_default_product_url() or None
    # Bundles / one-offs need explicit TBCC_GUMROAD_PLAN_URLS — never fall back to VIP SKU.
    return None


def _merge_query(product_url: str, updates: dict[str, str]) -> str:
    u = urlparse((product_url or "").strip())
    if not u.scheme or not u.netloc:
        return product_url
    q = parse_qs(u.query, keep_blank_values=True)
    for k, v in updates.items():
        if v:
            q[k] = [str(v)]
    flat: list[tuple[str, str]] = []
    for k, vals in q.items():
        for v in vals:
            flat.append((k, v))
    return urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(flat), u.fragment))


def append_tbcc_ref(product_url: str, reference_code: str) -> str:
    """Attach ``tbcc_ref`` so Gumroad Ping echoes it in ``url_params``."""
    return _merge_query(product_url, {"tbcc_ref": str(reference_code).strip()})


def gumroad_vip_option_name() -> str:
    """Must match the Gumroad membership option/tier name (live product uses ``Tiers``)."""
    return (os.getenv("TBCC_GUMROAD_VIP_OPTION_NAME") or "Tiers").strip() or "Tiers"


def append_vip_checkout_hints(
    product_url: str,
    *,
    recurrence: str | None = None,
    option_name: str | None = None,
) -> str:
    """Attach recurrence/option hints for overlay / custom landing preselect.

    Native Gumroad may ignore these query keys; custom ``landing.html`` can read them
    or use ``data-gumroad-recurrence`` buttons instead. EPO still binds duration.
    """
    updates: dict[str, str] = {}
    rec = (recurrence or "").strip().lower()
    if rec:
        updates["recurrence"] = rec
    opt = (option_name if option_name is not None else gumroad_vip_option_name()).strip()
    if opt:
        updates["option"] = opt
    return _merge_query(product_url, updates) if updates else product_url


def recurrence_for_plan(plan: dict | None) -> str | None:
    """
    Map a subscription plan dict to Gumroad recurrence slug.

    Price is checked before duration: the intro SKU is a 90-day $10 offer, the same length as the
    standard "3 Months" tier, so a duration-only lookup can't tell them apart (would mis-resolve the
    intro plan to the $48 quarterly recurrence). Price is the unambiguous identifier — sku_for_price_cents
    special-cases the intro price — so it goes first; duration is only a fallback when price is unknown.
    """
    if not plan:
        return None
    from app.data.aof_vip_membership import sku_for_duration_days, sku_for_price_cents

    usd = plan.get("nowpayments_price_usd")
    if usd is not None:
        try:
            cents = int(round(float(usd) * 100))
        except (TypeError, ValueError):
            cents = 0
        if cents > 0:
            sku = sku_for_price_cents(cents)
            if sku:
                return sku.gumroad_recurrence
    days = plan.get("duration_days")
    if days is not None:
        sku = sku_for_duration_days(int(days))
        if sku:
            return sku.gumroad_recurrence
    return None


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    s = raw.strip()
    if not s:
        return {}
    # JSON
    if s.startswith("{") or s.startswith("["):
        try:
            data = json.loads(s)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
    # Python-ish dict from Gumroad docs: {'a': 'b'}
    try:
        import ast

        data = ast.literal_eval(s)
        return data if isinstance(data, dict) else {}
    except (SyntaxError, ValueError):
        return {}


def extract_tbcc_ref(payload: dict[str, Any]) -> str | None:
    """Find EPO-… in url_params, custom_fields, or free-text fields."""
    candidates: list[Any] = [
        payload.get("url_params"),
        payload.get("custom_fields"),
        payload.get("tbcc_ref"),
        payload.get("order_id"),
        payload.get("message_to_seller"),
    ]
    for c in candidates:
        if isinstance(c, str) and _EPO_RE.search(c):
            m = _EPO_RE.search(c)
            return m.group(0).upper() if m else None
        d = _as_dict(c)
        for key in ("tbcc_ref", "TBCC_REF", "reference_code", "order_id", "EPO", "epo"):
            v = d.get(key)
            if v and _EPO_RE.search(str(v)):
                m = _EPO_RE.search(str(v))
                return m.group(0).upper() if m else None
        # Any value in dict
        for v in d.values():
            if v and _EPO_RE.search(str(v)):
                m = _EPO_RE.search(str(v))
                return m.group(0).upper() if m else None
    return None


def extract_buyer_email(payload: dict[str, Any]) -> str | None:
    """Gumroad ping email field (buyer address for Kit capture)."""
    raw = payload.get("email") or payload.get("purchaser_email")
    if raw is None:
        return None
    email = str(raw).strip()
    return email or None


def extract_telegram_user_id(payload: dict[str, Any]) -> int | None:
    d = _as_dict(payload.get("custom_fields"))
    for key in (
        "telegram_user_id",
        "Telegram ID",
        "telegram id",
        "TelegramID",
        "tg_id",
        "telegram",
    ):
        v = d.get(key)
        if v is None:
            continue
        s = str(v).strip().lstrip("@")
        if _TG_ID_RE.match(s):
            return int(s)
    # url_params
    up = _as_dict(payload.get("url_params"))
    for key in ("telegram_user_id", "tg_id", "userid", "user_id"):
        v = up.get(key)
        if v is None:
            continue
        s = str(v).strip()
        if _TG_ID_RE.match(s):
            return int(s)
    return None


def resolve_plan_id_from_payload(payload: dict[str, Any]) -> int | None:
    mapping = load_gumroad_product_map()
    if not mapping:
        return None
    # Prefer price cents for multi-recurrence membership (one permalink, many terms)
    raw_price = payload.get("price")
    if raw_price is not None:
        try:
            cents = int(round(float(raw_price)))
        except (TypeError, ValueError):
            cents = -1
        if cents >= 0:
            price_key = f"price:{cents}"
            if price_key in mapping:
                return mapping[price_key]
    keys: list[str] = []
    for field in ("product_id", "short_product_id", "product_permalink", "permalink"):
        v = payload.get(field)
        if not v:
            continue
        s = str(v).strip()
        keys.append(s)
        if "/" in s:
            keys.append(s.rstrip("/").split("/")[-1])
    for k in keys:
        if k in mapping:
            return mapping[k]
    return None


def vip_price_map_env_hint() -> dict[str, str]:
    """Document helper: build PRODUCT_MAP price:* keys once plan ids are known."""
    from app.data.aof_vip_membership import VIP_PRICE_CENTS_TO_RECURRENCE

    return {f"price:{c}": rec for c, rec in VIP_PRICE_CENTS_TO_RECURRENCE.items()}


def form_body_to_dict(form: Any) -> dict[str, Any]:
    """Normalize Starlette FormData / dict into a flat str→Any map."""
    out: dict[str, Any] = {}
    if isinstance(form, dict):
        for k, v in form.items():
            out[str(k)] = v
        return out
    # FormData: multi-items
    try:
        for k in form.keys():
            vals = form.getlist(k) if hasattr(form, "getlist") else [form.get(k)]
            if len(vals) == 1:
                out[str(k)] = vals[0]
            else:
                out[str(k)] = vals
    except Exception:
        pass
    return out


def is_refunded_or_test_skip(payload: dict[str, Any]) -> str | None:
    """Return reason to skip fulfill, or None to proceed."""
    refunded = str(payload.get("refunded") or "").strip().lower()
    if refunded in ("true", "1", "yes"):
        return "refunded"
    disputed = str(payload.get("disputed") or "").strip().lower()
    if disputed in ("true", "1", "yes"):
        return "disputed"
    return None


def verify_seller(payload: dict[str, Any]) -> bool:
    expected = gumroad_seller_ids()
    if not expected:
        return False
    got = str(payload.get("seller_id") or "").strip()
    if not got:
        # Gumroad dashboard "Send test ping" often omits seller_id.
        return True
    if got in expected:
        return True
    logger.warning("Gumroad ping: seller_id mismatch (got=%r expected one of %s)", got, expected)
    return False


def sale_charge_id(payload: dict[str, Any], reference: str | None = None) -> str:
    sale_id = str(payload.get("sale_id") or payload.get("order_number") or "").strip()
    if sale_id and reference:
        return f"gumroad_{sale_id}_{reference}"[:128]
    if sale_id:
        return f"gumroad_{sale_id}"[:128]
    if reference:
        return f"gumroad_{reference}"[:128]
    return f"gumroad_{payload.get('email') or 'unknown'}"[:128]


def income_usd_from_payload(payload: dict[str, Any]) -> float | None:
    """Gumroad ``price`` is usually cents as string."""
    raw = payload.get("price")
    if raw is None:
        return None
    try:
        cents = float(raw)
    except (TypeError, ValueError):
        return None
    # Heuristic: values like 999 → $9.99; already-dollar floats rare for ping
    if cents >= 100:
        return round(cents / 100.0, 2)
    return round(cents, 2)
