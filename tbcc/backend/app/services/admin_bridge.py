"""Short-lived HMAC tokens for dashboard ↔ AOF Forum admin deep-links."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any, Literal

Audience = Literal["forum_admin", "dashboard"]

DEFAULT_TTL_SECONDS = 120
MAX_TTL_SECONDS = 600


def _bridge_secret() -> str:
    secret = (os.getenv("TBCC_ADMIN_BRIDGE_SECRET") or "").strip()
    if secret:
        return secret
    # Same key the dashboard proxy already uses — fine for island-only bridge.
    fallback = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if fallback:
        return fallback
    raise RuntimeError(
        "TBCC_ADMIN_BRIDGE_SECRET (or TBCC_INTERNAL_API_KEY) required for admin bridge"
    )


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def mint_bridge_token(
    *,
    audience: Audience,
    next_path: str = "/",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Return opaque token: base64url(payload).hex_hmac."""
    ttl = max(30, min(int(ttl_seconds), MAX_TTL_SECONDS))
    next_clean = (next_path or "/").strip() or "/"
    if not next_clean.startswith("/"):
        next_clean = "/" + next_clean
    payload: dict[str, Any] = {
        "aud": audience,
        "exp": int(time.time()) + ttl,
        "next": next_clean,
        "nonce": uuid.uuid4().hex,
        "v": 1,
    }
    body = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(_bridge_secret().encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_bridge_token(token: str, *, expected_audience: Audience) -> dict[str, Any]:
    """Validate token; raise ValueError on failure. Returns payload dict."""
    raw = (token or "").strip()
    if not raw or "." not in raw:
        raise ValueError("malformed_token")
    body, sig = raw.rsplit(".", 1)
    if not body or not sig or len(sig) != 64:
        raise ValueError("malformed_token")
    expect = hmac.new(_bridge_secret().encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig.lower()):
        raise ValueError("bad_signature")
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("bad_payload") from exc
    if not isinstance(payload, dict):
        raise ValueError("bad_payload")
    if payload.get("aud") != expected_audience:
        raise ValueError("wrong_audience")
    try:
        exp = int(payload.get("exp") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("bad_exp") from exc
    if exp < int(time.time()):
        raise ValueError("expired")
    next_path = str(payload.get("next") or "/")
    if not next_path.startswith("/"):
        next_path = "/"
    payload["next"] = next_path
    return payload


def forum_public_base() -> str:
    return (os.getenv("TBCC_FORUM_PUBLIC_URL") or "https://forum.powercore.app").strip().rstrip("/")


def dashboard_public_base() -> str:
    return (os.getenv("TBCC_DASHBOARD_PUBLIC_URL") or "https://dash.powercore.app").strip().rstrip("/")


def build_forum_bridge_url(*, next_path: str = "/admin", ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    token = mint_bridge_token(audience="forum_admin", next_path=next_path, ttl_seconds=ttl_seconds)
    return f"{forum_public_base()}/auth/bridge?t={token}"


def build_dashboard_bridge_url(*, next_path: str = "/", ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    from urllib.parse import quote

    token = mint_bridge_token(audience="dashboard", next_path=next_path, ttl_seconds=ttl_seconds)
    # Prefer root with bridge query so the SPA can consume before client routing.
    q_next = quote(next_path if next_path.startswith("/") else f"/{next_path}", safe="/")
    return f"{dashboard_public_base()}/?bridge={token}&next={q_next}"
