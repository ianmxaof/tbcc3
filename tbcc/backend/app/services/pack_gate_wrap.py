"""Pack ingest gates: Linkvertise → AdMaven → work.ink (first success wins)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from app.services.link_gate_provider import (
    PROVIDER_ADMAVEN,
    PROVIDER_LINKVERTISE,
    PROVIDER_WORKINK,
    is_linkvertise_host,
    wrap_gate_url,
)

logger = logging.getLogger(__name__)

_ADMAVEN_HOST_MARKERS = ("speedy-links.com", "onepiecered.co", "admaven.com")
_WORKINK_HOST_MARKERS = ("work.ink",)

# Prefer LV (dynamic OK for flywheel), then AdMaven, then work.ink.
_INGEST_PROVIDER_ORDER: tuple[str, ...] = (
    PROVIDER_LINKVERTISE,
    PROVIDER_ADMAVEN,
    PROVIDER_WORKINK,
)


@dataclass
class PackGateIngestResult:
    destination_url: str
    primary_url: str
    gate_adm_url: str | None = None
    gate_lv_url: str | None = None
    gate_workink_url: str | None = None
    provider: str | None = None


def _is_admaven_gate(url: str) -> bool:
    low = (url or "").lower()
    return any(h in low for h in _ADMAVEN_HOST_MARKERS)


def _is_workink_gate(url: str) -> bool:
    low = (url or "").lower()
    return any(h in low for h in _WORKINK_HOST_MARKERS)


def _is_dynamic_linkvertise(url: str) -> bool:
    return is_linkvertise_host(url) and "/dynamic" in (url or "").lower()


def _provider_env_ready(provider: str) -> bool:
    if provider == PROVIDER_LINKVERTISE:
        return bool((os.getenv("TBCC_LINKVERTISE_PUBLISHER_ID") or "").strip())
    if provider == PROVIDER_ADMAVEN:
        return bool((os.getenv("TBCC_ADMAVEN_API_TOKEN") or "").strip())
    if provider == PROVIDER_WORKINK:
        return bool((os.getenv("TBCC_WORKINK_BASE_LINK") or "").strip())
    return False


def ingest_gate_provider_order() -> list[str]:
    """Providers to try on ingest: env list if set, else fixed LV→AdMaven→workink (env-ready only)."""
    raw = (os.getenv("TBCC_LINK_GATE_PROVIDERS") or "").strip()
    if raw:
        requested = [p.strip().lower() for p in raw.split(",") if p.strip()]
        out = [p for p in requested if _provider_env_ready(p)]
        if out:
            return out
    return [p for p in _INGEST_PROVIDER_ORDER if _provider_env_ready(p)]


def wrap_pack_gates_on_ingest(destination_url: str) -> PackGateIngestResult:
    """
    On pack-pool / flywheel insert: try Linkvertise → AdMaven → work.ink.
    primary_url = first successful wrap, else bare destination.
    """
    dest = (destination_url or "").strip()
    if not dest.startswith(("http://", "https://")):
        raise ValueError("invalid_destination_url")

    gate_lv: str | None = None
    gate_adm: str | None = None
    gate_wi: str | None = None
    primary = dest
    used: str | None = None

    for prov in ingest_gate_provider_order():
        try:
            wrapped, got = wrap_gate_url(dest, provider=prov, seed=dest)
        except Exception:
            logger.warning(
                "pack ingest %s wrap failed dest=%s",
                prov,
                dest[:80],
                exc_info=True,
            )
            continue
        if not wrapped or not str(wrapped).startswith("http"):
            continue
        used = got
        primary = wrapped
        if got == PROVIDER_LINKVERTISE:
            gate_lv = wrapped
        elif got == PROVIDER_ADMAVEN:
            gate_adm = wrapped
        elif got == PROVIDER_WORKINK:
            gate_wi = wrapped
        break

    return PackGateIngestResult(
        destination_url=dest,
        primary_url=primary,
        gate_adm_url=gate_adm,
        gate_lv_url=gate_lv,
        gate_workink_url=gate_wi,
        provider=used,
    )


def legacy_wrap_destination(destination_url: str) -> str:
    """Previous single-provider wrap (rotation). Used only when TBCC_PACK_USE_LEGACY_GATE_WRAP=1."""
    wrapped, _ = wrap_gate_url(destination_url, seed=destination_url)
    return wrapped
