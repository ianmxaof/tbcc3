"""Optional outbound URL shortening for promo affiliate rows (dashboard-triggered)."""

from __future__ import annotations

import logging
import os
import secrets
from urllib.parse import quote

import httpx

from app.services.link_resolver_policy import normalize_input_url

logger = logging.getLogger(__name__)

_PIXELDRAIN_API_BASE = (os.environ.get("TBCC_PIXELDRAIN_API_BASE") or "https://pixeldrain.com/api").rstrip("/")


class PromoShortenError(Exception):
    pass


def configured_promo_shortener_provider() -> str | None:
    raw = (os.environ.get("TBCC_PROMO_SHORTEN_PROVIDER") or "").strip().lower()
    if raw in ("isgd", "tinyurl", "pixeldrain"):
        return raw
    return None


def shorten_promo_destination(long_url: str, *, provider: str | None = None) -> str:
    prov = (provider or configured_promo_shortener_provider() or "").strip().lower()
    if prov == "isgd":
        return _shorten_isgd(long_url)
    if prov == "tinyurl":
        token = (os.environ.get("TBCC_TINYURL_API_TOKEN") or "").strip()
        if not token:
            raise PromoShortenError("TBCC_TINYURL_API_TOKEN is not set")
        return _shorten_tinyurl(long_url, token)
    if prov == "pixeldrain":
        key = (os.environ.get("TBCC_PIXELDRAIN_API_KEY") or "").strip()
        if not key:
            raise PromoShortenError("TBCC_PIXELDRAIN_API_KEY is not set")
        return _shorten_pixeldrain_upload_txt(long_url, key)
    raise PromoShortenError(
        "No shortener configured — set TBCC_PROMO_SHORTEN_PROVIDER=isgd | tinyurl | pixeldrain "
        "(tinyurl needs TBCC_TINYURL_API_TOKEN; pixeldrain needs TBCC_PIXELDRAIN_API_KEY — uploads "
        "the URL as a tiny text file and returns https://pixeldrain.com/u/{id}, same idea as ShareX "
        "using Pixeldrain as a link host)"
    )


def _shorten_isgd(long_url: str) -> str:
    q = quote(long_url, safe="")
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get(f"https://is.gd/create.php?format=simple&url={q}")
    except httpx.RequestError as e:
        logger.warning("is.gd shorten request failed: %s", e)
        raise PromoShortenError("is.gd request failed") from e
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise PromoShortenError(f"is.gd HTTP {r.status_code}") from e
    text = (r.text or "").strip()
    if text.lower().startswith("error:"):
        raise PromoShortenError(text)
    if not text.startswith("http"):
        raise PromoShortenError(f"Unexpected is.gd response: {text[:200]}")
    return text


def _shorten_tinyurl(long_url: str, token: str) -> str:
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(
                "https://api.tinyurl.com/create",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"url": long_url},
            )
    except httpx.RequestError as e:
        logger.warning("TinyURL shorten request failed: %s", e)
        raise PromoShortenError("TinyURL request failed") from e
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = (r.text or "")[:300]
        raise PromoShortenError(f"TinyURL HTTP {r.status_code}: {detail}") from e
    try:
        payload = r.json()
    except ValueError as e:
        raise PromoShortenError("TinyURL returned non-JSON") from e
    data = payload.get("data") if isinstance(payload, dict) else None
    tiny = None
    if isinstance(data, dict):
        tiny = data.get("tiny_url") or data.get("url")
    if isinstance(tiny, str) and tiny.strip().startswith("http"):
        return tiny.strip()
    raise PromoShortenError("TinyURL response missing tiny_url")


def _shorten_pixeldrain_upload_txt(long_url: str, api_key: str) -> str:
    """
    Pixeldrain has no dedicated “short URL” API; ShareX-style workflows upload the destination as a
    small text file and share https://pixeldrain.com/u/{id}. Opening the link hits Pixeldrain’s viewer
    (not a silent HTTP redirect).
    """
    fname = f"lnk-{secrets.token_hex(5)}.txt"
    url_put = f"{_PIXELDRAIN_API_BASE}/file/{fname}"
    try:
        with httpx.Client(timeout=40.0) as client:
            r = client.put(
                url_put,
                content=long_url.encode("utf-8"),
                headers={"Content-Type": "text/plain; charset=utf-8"},
                auth=("", api_key),
            )
    except httpx.RequestError as e:
        logger.warning("pixeldrain shorten PUT failed: %s", e)
        raise PromoShortenError("pixeldrain request failed") from e
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = (r.text or "")[:400]
        raise PromoShortenError(f"pixeldrain HTTP {r.status_code}: {detail}") from e
    try:
        payload = r.json()
    except ValueError as e:
        raise PromoShortenError("pixeldrain returned non-JSON") from e
    fid = None
    if isinstance(payload, dict):
        fid = payload.get("id")
    if isinstance(fid, str) and fid.strip():
        host = _PIXELDRAIN_API_BASE.replace("/api", "").rstrip("/")
        if not host.startswith("http"):
            host = "https://pixeldrain.com"
        return f"{host}/u/{fid.strip()}"
    raise PromoShortenError("pixeldrain response missing id")


def validate_and_shorten(raw_url: str) -> str:
    norm, reason = normalize_input_url(raw_url)
    if not norm:
        raise PromoShortenError(f"Blocked or invalid URL ({reason or 'unknown'})")
    return shorten_promo_destination(norm)
