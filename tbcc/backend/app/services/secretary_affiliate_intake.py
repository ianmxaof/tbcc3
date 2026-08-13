"""Secretary bot: one-shot affiliate / sponsor URL intake → promo_affiliate_links + circulation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.affiliate_content_lane import (
    AffiliateLane,
    classify_affiliate_lane,
    lane_display,
    placements_for_lane,
)
from app.services.aof_growth_hub import sync_affiliate_network
from app.services.promo_affiliate_rotation import AFFILIATE_PLACEMENTS

# FOMO-first copy for Telegram/HTML surfaces ({link} {url} {label} placeholders).
DEFAULT_FOMO_COPY_TEMPLATE = "⏳ {link} — window closing. the clock is real."
DEFAULT_SFW_COPY_TEMPLATE = "🛒 {link} — curated deal"

# Full AOF circulation (not manual_only, not Checkout List silo).
DEFAULT_SPONSOR_PLACEMENTS: list[str] = sorted(
    p for p in AFFILIATE_PLACEMENTS if p not in ("manual_only", "links_hub_sfw")
)

ForceLane = Literal["auto", "sfw", "nsfw"]

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


@dataclass(frozen=True)
class AffiliateIntakeResult:
    ok: bool
    message: str
    link_id: int | None = None
    label: str | None = None
    url: str | None = None
    created: bool = False
    sync_report: dict | None = None
    lane: AffiliateLane | None = None


def _encode_json_list(values: list[str]) -> str:
    return json.dumps([str(v).strip().lower() for v in values if str(v).strip()])


def label_from_url(url: str) -> str:
    """Derive a human label from hostname (cometapi.com → Comet API)."""
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return "Sponsor"
    root = host.split(".")[0]
    if root in {"t", "telegram", "link"}:
        return host.replace(".", " ").title()
    return root.replace("-", " ").replace("_", " ").title()


def parse_affiliate_intake_text(raw: str) -> tuple[str, str] | None:
    """Parse admin paste: optional ``Label|https://…`` or bare URL."""
    text = (raw or "").strip()
    if not text:
        return None
    if "|" in text:
        label, url = text.split("|", 1)
        label, url = label.strip(), url.strip()
        if label and url.lower().startswith(("http://", "https://")):
            return label[:512], url[:8192]
    m = _URL_RE.search(text)
    if not m:
        return None
    url = m.group(0).rstrip(".,);]")
    if not url.lower().startswith(("http://", "https://")):
        return None
    return label_from_url(url), url[:8192]


def parse_affiliate_intake_args(args: list[str]) -> tuple[ForceLane, str]:
    """Parse ``/addsponsor [sfw|aof|nsfw] …`` prefix and remaining text."""
    rest = " ".join(args or []).strip()
    if not rest:
        return "auto", ""
    head = rest.split()[0].lower()
    if head in ("sfw", "checkout", "deals"):
        return "sfw", rest[len(head) :].strip()
    if head in ("aof", "nsfw", "spicy"):
        return "nsfw", rest[len(head) :].strip()
    return "auto", rest


def resolve_intake_lane(
    url: str,
    label: str,
    *,
    force: ForceLane = "auto",
) -> AffiliateLane:
    if force == "sfw":
        return "sfw"
    if force == "nsfw":
        return "nsfw"
    return classify_affiliate_lane(url, label)


def _copy_template_for_lane(lane: AffiliateLane) -> str:
    return DEFAULT_SFW_COPY_TEMPLATE if lane == "sfw" else DEFAULT_FOMO_COPY_TEMPLATE


def _find_by_url(db: Session, url: str) -> PromoAffiliateLink | None:
    norm = url.strip().rstrip("/")
    rows = db.query(PromoAffiliateLink).filter(PromoAffiliateLink.active.is_(True)).all()
    for row in rows:
        if (row.url or "").strip().rstrip("/") == norm:
            return row
    return None


def intake_affiliate_sponsor(
    db: Session,
    *,
    label: str,
    url: str,
    sync: bool = True,
    priority_tier: int = 8,
    force_lane: ForceLane = "auto",
) -> AffiliateIntakeResult:
    """Create or refresh a sponsor row and optionally rebuild rotation schedulers."""
    label = label.strip()[:512]
    url = url.strip()[:8192]
    if not label or not url.lower().startswith(("http://", "https://")):
        return AffiliateIntakeResult(ok=False, message="Need a label and https URL.")

    lane = resolve_intake_lane(url, label, force=force_lane)
    placements = placements_for_lane(lane, force_sfw=(force_lane == "sfw"))
    copy_template = _copy_template_for_lane(lane)

    existing = _find_by_url(db, url)
    created = existing is None
    if existing:
        row = existing
        row.label = label
        row.active = True
        row.priority_tier = min(int(row.priority_tier or 99), int(priority_tier))
    else:
        row = PromoAffiliateLink(
            label=label,
            url=url,
            payout_kind="other",
            priority_tier=int(priority_tier),
            active=True,
            placements_json=_encode_json_list(placements),
            copy_template=copy_template,
        )
        db.add(row)

    row.placements_json = _encode_json_list(placements)
    if not (getattr(row, "copy_template", None) or "").strip():
        row.copy_template = copy_template

    db.commit()
    db.refresh(row)

    sync_report = None
    if sync:
        try:
            sync_report = sync_affiliate_network(db, execute=True)
        except Exception as e:
            return AffiliateIntakeResult(
                ok=False,
                message=f"Saved link #{row.id} but circulation sync failed: {e}",
                link_id=row.id,
                label=row.label,
                url=row.url,
                created=created,
                lane=lane,
            )

    verb = "Added" if created else "Updated"
    placement_text = ", ".join(placements)
    tone = "deal board" if lane == "sfw" else "FOMO scarcity"
    return AffiliateIntakeResult(
        ok=True,
        message=(
            f"{verb} <b>{label}</b> (#{row.id}).\n"
            f"Lane: <b>{lane_display(lane)}</b>\n"
            f"Circulating: <code>{placement_text}</code>.\n"
            f"Copy tone: {tone}."
        ),
        link_id=row.id,
        label=row.label,
        url=row.url,
        created=created,
        sync_report=sync_report,
        lane=lane,
    )
