"""HTTP client for Bypass.vip (premium key or official free tier).

Official snippets: https://github.com/bypass-vip/bypass.vip
  Free:  GET https://api.bypass.vip/bypass?url=<encoded>
  Premium: same path + key query param (or /v1 per plan — tune env).

Website captcha (bypass.vip UI) does not apply to headless API calls; free API is
rate-limited only. Premium: https://bypass.vip/premium
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin

import httpx

logger = logging.getLogger(__name__)


@dataclass
class BypassResolveResult:
    ok: bool
    final_url: str | None
    error_message: str | None
    latency_ms: int
    raw_status_code: int | None


def _bypass_enabled_flag() -> bool:
    return (os.getenv("TBCC_BYPASS_ENABLED") or "1").strip().lower() not in ("0", "false", "no")


def bypass_free_mode() -> bool:
    """Official unauthenticated API (heavy rate limits)."""
    if not _bypass_enabled_flag():
        return False
    if (os.getenv("TBCC_BYPASS_API_KEY") or "").strip():
        return False
    return (os.getenv("TBCC_BYPASS_FREE") or "1").strip().lower() not in ("0", "false", "no")


def bypass_configured() -> bool:
    """True when premium key is set OR free tier is allowed."""
    if not _bypass_enabled_flag():
        return False
    if (os.getenv("TBCC_BYPASS_API_KEY") or "").strip():
        return True
    return bypass_free_mode()


def _base_url() -> str:
    return (os.getenv("TBCC_BYPASS_API_BASE_URL") or "https://api.bypass.vip").rstrip("/")


def _path(*, premium: bool) -> str:
    raw = (os.getenv("TBCC_BYPASS_API_PATH") or "").strip()
    if raw:
        return raw if raw.startswith("/") else f"/{raw}"
    return "/v1" if premium else "/bypass"


def _timeout_s() -> float:
    try:
        return max(5.0, float(os.getenv("TBCC_BYPASS_TIMEOUT_S", "45")))
    except ValueError:
        return 45.0


def _url_param() -> str:
    return (os.getenv("TBCC_BYPASS_URL_QUERY_PARAM") or "url").strip() or "url"


def _key_param() -> str:
    return (os.getenv("TBCC_BYPASS_KEY_QUERY_PARAM") or "key").strip() or "key"


def _parse_provider_payload(data: Any) -> tuple[str | None, str | None]:
    """Returns (final_url, error_message)."""
    if data is None:
        return None, "empty_response"
    if isinstance(data, str):
        s = data.strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s, None
        return None, s[:500] or "non_url_body"
    if not isinstance(data, dict):
        return None, "unexpected_response_shape"
    st = str(data.get("status") or "").lower()
    if st == "success":
        for k in ("result", "url", "destination", "link", "bypassed"):
            v = data.get(k)
            if not isinstance(v, str):
                continue
            s = v.strip()
            if s.startswith("http://") or s.startswith("https://"):
                if "discord" in s.lower() and "bypass" in s.lower() and "shut" in s.lower():
                    return None, "free_api_shutdown_use_premium"
                return s, None
            if "shut down" in s.lower() or "free api" in s.lower():
                return None, "free_api_shutdown_use_premium"
        return None, "success_without_url"
    if st == "error":
        msg = data.get("message") or data.get("error") or data.get("msg")
        return None, str(msg)[:500] if msg else "provider_error"
    # Some APIs return { "url": "..." } without status
    for k in ("result", "url", "destination", "link"):
        v = data.get(k)
        if isinstance(v, str) and v.strip().startswith("http"):
            return v.strip(), None
    return None, str(data)[:300]


def resolve_bypass_url(target_url: str) -> BypassResolveResult:
    """
    Call provider with the normalized HTTPS URL to resolve.
    Premium when TBCC_BYPASS_API_KEY is set; else official free /bypass if TBCC_BYPASS_FREE=1.
    """
    if not bypass_configured():
        return BypassResolveResult(
            ok=False,
            final_url=None,
            error_message="Bypass disabled (set TBCC_BYPASS_API_KEY or TBCC_BYPASS_FREE=1)",
            latency_ms=0,
            raw_status_code=None,
        )
    key = (os.getenv("TBCC_BYPASS_API_KEY") or "").strip()
    premium = bool(key)
    method = (os.getenv("TBCC_BYPASS_HTTP_METHOD") or "GET").upper().strip()
    base = _base_url()
    path = _path(premium=premium)
    full = urljoin(base + "/", path.lstrip("/"))
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=_timeout_s()) as client:
            if method == "POST":
                body: dict[str, str] = {"url": target_url}
                if key:
                    body["key"] = key
                r = client.post(
                    full,
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
            else:
                q = f"{_url_param()}={quote(target_url, safe='')}"
                if key:
                    q += f"&{_key_param()}={quote(key, safe='')}"
                joiner = "&" if "?" in full else "?"
                r = client.get(f"{full}{joiner}{q}")
    except httpx.TimeoutException:
        ms = int((time.perf_counter() - t0) * 1000)
        return BypassResolveResult(False, None, "provider_timeout", ms, None)
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        logger.warning("bypass_vip_client request error: %s", e)
        return BypassResolveResult(False, None, str(e)[:500], ms, None)

    ms = int((time.perf_counter() - t0) * 1000)
    if r.status_code >= 400:
        try:
            data = r.json()
            _, err = _parse_provider_payload(data)
        except Exception:
            err = (r.text or "")[:500] or f"http_{r.status_code}"
        return BypassResolveResult(False, None, err, ms, r.status_code)

    try:
        data = r.json()
    except Exception:
        text = (r.text or "").strip()
        if text.startswith("http://") or text.startswith("https://"):
            return BypassResolveResult(True, text, None, ms, r.status_code)
        return BypassResolveResult(False, None, text[:500] or "non_json_response", ms, r.status_code)

    final, err = _parse_provider_payload(data)
    if final:
        return BypassResolveResult(True, final, None, ms, r.status_code)
    return BypassResolveResult(False, None, err or "resolve_failed", ms, r.status_code)
