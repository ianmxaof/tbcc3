"""Multi-provider link gates: Linkvertise, LootLabs, AdMaven, Work.ink override API."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from base64 import b64encode
from dataclasses import dataclass
from random import random
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.services.link_resolver_policy import normalize_input_url

logger = logging.getLogger(__name__)

GATE_HOST_SUFFIXES: tuple[str, ...] = (
    "linkvertise.com",
    "link-center.net",
    "link-hub.net",
    "link-target.net",
    "link-to.net",
    "direct-link.net",
    "up-to-down.net",
    "work.ink",
    "loot-link.com",
    "lootlinks.com",
    "lootlabs.gg",
    "onepiecered.co",
    "speedy-links.com",
)

PROVIDER_LINKVERTISE = "linkvertise"
PROVIDER_LOOTLABS = "lootlabs"
PROVIDER_ADMAVEN = "admaven"
PROVIDER_WORKINK = "workink"

_KNOWN_GATE_PROVIDERS: tuple[str, ...] = (
    PROVIDER_LINKVERTISE,
    PROVIDER_LOOTLABS,
    PROVIDER_ADMAVEN,
    PROVIDER_WORKINK,
)

_LOOTLABS_API = "https://creators.lootlabs.gg/api/public/content_locker"
_ADMAVEN_API = "https://publishers.ad-maven.com/api/public/content_locker"
_WORKINK_OVERRIDE_API = "https://work.ink/_api/v2/override"

_rotation_index = 0


@dataclass
class GateWrapDecision:
    original: str
    wrapped: str | None
    action: str  # wrap | skip
    reason: str
    provider: str | None = None


def publisher_id_from_env() -> str:
    raw = (os.getenv("TBCC_LINKVERTISE_PUBLISHER_ID") or "").strip()
    if not raw:
        raise ValueError("Set TBCC_LINKVERTISE_PUBLISHER_ID in tbcc/.env (e.g. 1367336)")
    return raw


def linkvertise_base_from_env() -> str:
    return (os.getenv("TBCC_LINKVERTISE_BASE_URL") or "https://link-center.net").rstrip("/")


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


_LINKVERTISE_HOST_SUFFIXES: tuple[str, ...] = (
    "linkvertise.com",
    "link-center.net",
    "link-hub.net",
    "link-target.net",
    "link-to.net",
    "direct-link.net",
    "up-to-down.net",
)


def is_linkvertise_host(url: str) -> bool:
    host = _host(url)
    if not host:
        return False
    return any(host == s or host.endswith("." + s) for s in _LINKVERTISE_HOST_SUFFIXES)


def is_gate_host(url: str) -> bool:
    host = _host(url)
    if not host:
        return False
    return any(host == s or host.endswith("." + s) for s in GATE_HOST_SUFFIXES)


def _parse_provider_list(raw: str) -> list[str]:
    out: list[str] = []
    for part in (raw or "").split(","):
        p = part.strip().lower()
        if p in _KNOWN_GATE_PROVIDERS and p not in out:
            out.append(p)
    return out


def configured_gate_providers() -> list[str]:
    """Providers that have required env configured."""
    raw = (os.getenv("TBCC_LINK_GATE_PROVIDERS") or "linkvertise").strip()
    requested = _parse_provider_list(raw) or [PROVIDER_LINKVERTISE]
    out: list[str] = []
    for p in requested:
        if p == PROVIDER_LINKVERTISE:
            if (os.getenv("TBCC_LINKVERTISE_PUBLISHER_ID") or "").strip():
                out.append(p)
        elif p == PROVIDER_LOOTLABS:
            if (os.getenv("TBCC_LOOTLABS_API_TOKEN") or "").strip():
                out.append(p)
        elif p == PROVIDER_ADMAVEN:
            if (os.getenv("TBCC_ADMAVEN_API_TOKEN") or "").strip():
                out.append(p)
        elif p == PROVIDER_WORKINK:
            if (os.getenv("TBCC_WORKINK_BASE_LINK") or "").strip():
                out.append(p)
    if not out and (os.getenv("TBCC_LINKVERTISE_PUBLISHER_ID") or "").strip():
        out.append(PROVIDER_LINKVERTISE)
    return out


def _stable_provider_index(seed: str, n: int) -> int:
    """Process-stable index (Python hash() is salted per process)."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % max(1, int(n))


def pick_gate_provider(*, seed: str | None = None) -> str:
    """
    Select gate provider per TBCC_LINK_GATE_ROTATION:
      round_robin (default) | random | first
    Optional seed stabilizes round_robin/random per URL/key.
    """
    providers = configured_gate_providers()
    if not providers:
        raise ValueError("No link gate providers configured")
    if len(providers) == 1:
        return providers[0]

    mode = (os.getenv("TBCC_LINK_GATE_ROTATION") or "round_robin").strip().lower()
    if mode == "first":
        return providers[0]
    if mode == "random":
        if seed:
            return providers[_stable_provider_index(seed, len(providers))]
        return providers[int(random() * len(providers)) % len(providers)]

    global _rotation_index
    if seed:
        return providers[_stable_provider_index(seed, len(providers))]
    idx = _rotation_index % len(providers)
    _rotation_index += 1
    return providers[idx]


def wrap_linkvertise_url(
    publisher_id: str | int,
    target_url: str,
    *,
    base_url: str | None = None,
) -> str:
    norm, reason = normalize_input_url(target_url)
    if not norm:
        raise ValueError(f"Invalid target URL ({reason or 'blocked'})")
    root = (base_url or linkvertise_base_from_env()).rstrip("/")
    dynamic_base = f"{root}/{publisher_id}/{random() * 1000}/dynamic"
    quoted = quote(norm, safe="~@#$&()*!+=:;,.?/'")
    token = b64encode(quoted.encode("ascii")).decode("ascii")
    return f"{dynamic_base}?r={token}"


def _lootlabs_settings() -> tuple[str, int, int]:
    token = (os.getenv("TBCC_LOOTLABS_API_TOKEN") or "").strip()
    try:
        tier = int(os.getenv("TBCC_LOOTLABS_TIER_ID") or "3")
    except ValueError:
        tier = 3
    try:
        tasks = int(os.getenv("TBCC_LOOTLABS_NUMBER_OF_TASKS") or "3")
    except ValueError:
        tasks = 3
    tier = max(1, min(4, tier))
    tasks = max(1, min(5, tasks))
    return token, tier, tasks


def wrap_lootlabs_url(target_url: str) -> str:
    token, tier_id, number_of_tasks = _lootlabs_settings()
    if not token:
        raise ValueError("Set TBCC_LOOTLABS_API_TOKEN for LootLabs gate wrapping")
    norm, reason = normalize_input_url(target_url)
    if not norm:
        raise ValueError(f"Invalid target URL ({reason or 'blocked'})")
    payload = {
        "url": norm,
        "tier_id": tier_id,
        "number_of_tasks": number_of_tasks,
        "title": (os.getenv("TBCC_LOOTLABS_LINK_TITLE") or "AOF")[:120],
    }
    timeout = 45.0
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                _LOOTLABS_API,
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or "")[:300]
        raise RuntimeError(f"LootLabs API HTTP {e.response.status_code}: {detail}") from e
    except Exception as e:
        raise RuntimeError(f"LootLabs API failed: {e}") from e

    link = _lootlabs_link_from_response(data)
    if not link:
        raise RuntimeError(f"LootLabs API returned no locker URL: {str(data)[:300]}")
    return link


def _lootlabs_link_from_response(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    msg = data.get("message")
    if isinstance(msg, dict):
        for k in ("loot_url", "short_url", "short", "url"):
            v = msg.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v.strip()
    for k in ("loot_url", "short_url", "url"):
        v = data.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v.strip()
    return None


def wrap_admaven_url(target_url: str) -> str:
    token = (os.getenv("TBCC_ADMAVEN_API_TOKEN") or "").strip()
    if not token:
        raise ValueError("Set TBCC_ADMAVEN_API_TOKEN for AdMaven gate wrapping")
    norm, reason = normalize_input_url(target_url)
    if not norm:
        raise ValueError(f"Invalid target URL ({reason or 'blocked'})")
    payload: dict[str, str] = {
        "title": (os.getenv("TBCC_ADMAVEN_LINK_TITLE") or "AOF")[:30],
        "url": norm,
    }
    background = (os.getenv("TBCC_ADMAVEN_BACKGROUND") or "").strip()
    if background:
        payload["background"] = background
    sub_id = (os.getenv("TBCC_ADMAVEN_SUB_ID") or "").strip()
    if sub_id:
        payload["sub_id"] = sub_id[:7]
    timeout = 45.0
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                _ADMAVEN_API,
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or "")[:300]
        raise RuntimeError(f"AdMaven API HTTP {e.response.status_code}: {detail}") from e
    except Exception as e:
        raise RuntimeError(f"AdMaven API failed: {e}") from e

    link = _admaven_link_from_response(data)
    if not link:
        raise RuntimeError(f"AdMaven API returned no locker URL: {str(data)[:300]}")
    return link


def _admaven_link_from_response(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    if data.get("type") == "error":
        msg = data.get("message")
        if isinstance(msg, str) and msg.strip():
            raise RuntimeError(f"AdMaven API error: {msg.strip()}")
        return None
    msg = data.get("message")
    if isinstance(msg, list) and msg:
        first = msg[0]
        if isinstance(first, dict):
            for k in ("full_short", "desturl", "short_url"):
                v = first.get(k)
                if isinstance(v, str) and v.startswith("http"):
                    return v.strip()
    if isinstance(msg, dict):
        for k in ("full_short", "desturl", "short_url", "short"):
            v = msg.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v.strip()
    return None


def wrap_workink_url(target_url: str) -> str:
    base_link = (os.getenv("TBCC_WORKINK_BASE_LINK") or "").strip().rstrip("/")
    if not base_link or not base_link.startswith("http"):
        raise ValueError("Set TBCC_WORKINK_BASE_LINK (your work.ink template link)")
    norm, reason = normalize_input_url(target_url)
    if not norm:
        raise ValueError(f"Invalid target URL ({reason or 'blocked'})")
    timeout = 30.0
    headers: dict[str, str] = {}
    api_key = (os.getenv("TBCC_WORKINK_API_KEY") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(
                _WORKINK_OVERRIDE_API,
                params={"destination": norm},
                headers=headers or None,
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise RuntimeError(f"Work.ink override API failed: {e}") from e
    sr = data.get("sr") if isinstance(data, dict) else None
    if not sr or not isinstance(sr, str):
        raise RuntimeError(f"Work.ink override missing sr token: {str(data)[:200]}")
    join = "&" if "?" in base_link else "?"
    return f"{base_link}{join}sr={quote(sr, safe='')}"


def wrap_gate_url(
    target_url: str,
    *,
    provider: str | None = None,
    publisher_id: str | int | None = None,
    seed: str | None = None,
) -> tuple[str, str]:
    """Returns (wrapped_url, provider_id)."""
    prov = (provider or pick_gate_provider(seed=seed or target_url)).strip().lower()
    if prov == PROVIDER_LINKVERTISE:
        pub = publisher_id if publisher_id is not None else publisher_id_from_env()
        return wrap_linkvertise_url(pub, target_url), prov
    if prov == PROVIDER_LOOTLABS:
        return wrap_lootlabs_url(target_url), prov
    if prov == PROVIDER_ADMAVEN:
        return wrap_admaven_url(target_url), prov
    if prov == PROVIDER_WORKINK:
        return wrap_workink_url(target_url), prov
    raise ValueError(f"Unknown link gate provider: {provider}")


def gate_payout_kind(provider: str) -> str:
    return {
        PROVIDER_LINKVERTISE: "linkvertise",
        PROVIDER_LOOTLABS: "lootlabs",
        PROVIDER_ADMAVEN: "admaven",
        PROVIDER_WORKINK: "workink",
    }.get(provider, provider)


def is_monetized_gate_host(host: str) -> bool:
    return any(host == s or host.endswith("." + s) for s in GATE_HOST_SUFFIXES)
