"""Pack ingest gates: AdMaven via API; Linkvertise via dashboard Playwright (never /dynamic)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from app.services.link_gate_provider import (
    PROVIDER_ADMAVEN,
    is_linkvertise_host,
    wrap_admaven_url,
    wrap_gate_url,
)

logger = logging.getLogger(__name__)

_ADMAVEN_HOST_MARKERS = ("speedy-links.com", "onepiecered.co", "admaven.com")


@dataclass
class PackGateIngestResult:
    destination_url: str
    primary_url: str
    gate_adm_url: str | None = None
    gate_lv_url: str | None = None


def _is_admaven_gate(url: str) -> bool:
    low = (url or "").lower()
    return any(h in low for h in _ADMAVEN_HOST_MARKERS)


def _is_dynamic_linkvertise(url: str) -> bool:
    return is_linkvertise_host(url) and "/dynamic" in (url or "").lower()


def wrap_pack_gates_on_ingest(destination_url: str) -> PackGateIngestResult:
    """
    On pack-pool insert: wrap AdMaven when token is set; leave LV empty for dashboard provisioner.
    primary_url = AdMaven gate if wrapped, else bare destination (until LV is provisioned).
    """
    dest = (destination_url or "").strip()
    if not dest.startswith(("http://", "https://")):
        raise ValueError("invalid_destination_url")

    gate_adm: str | None = None
    token = (os.getenv("TBCC_ADMAVEN_API_TOKEN") or "").strip()
    if token:
        try:
            gate_adm = wrap_admaven_url(dest)
        except Exception:
            logger.warning("pack ingest AdMaven wrap failed dest=%s", dest[:80], exc_info=True)

    primary = gate_adm or dest
    return PackGateIngestResult(
        destination_url=dest,
        primary_url=primary,
        gate_adm_url=gate_adm,
        gate_lv_url=None,
    )


def legacy_wrap_destination(destination_url: str) -> str:
    """Previous single-provider wrap (rotation). Used only when TBCC_PACK_USE_LEGACY_GATE_WRAP=1."""
    wrapped, _ = wrap_gate_url(destination_url, seed=destination_url)
    return wrapped
