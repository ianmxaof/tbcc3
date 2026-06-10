"""Semantic auto-tag + short description for master archive URLs."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.capture_archive_entry import CaptureArchiveEntry

logger = logging.getLogger(__name__)


def _heuristic_description(url: str) -> str:
    try:
        u = urlparse(url.strip().split("#")[0])
        host = (u.hostname or "").replace("www.", "")
        if not host:
            return ""
        segs = [s for s in (u.path or "").split("/") if s]
        tail = segs[-1] if segs else ""
        if tail:
            tail = tail.split("?")[0].replace("-", " ").replace("_", " ")[:100]
        return f"{host}" + (f" — {tail}" if tail and tail.lower() not in host.lower() else "")
    except Exception:
        return ""


def enrich_archive_url(url: str, *, ref_url: str | None = None, fast: bool = False) -> dict[str, Any]:
    """
    Page semantic sweep (Lustpress + heuristics) for a single archive URL.
    Returns short description + comma-separated tag labels.
    """
    from app.services.send_tag_enrich import enrich_send_batch

    page = (ref_url or url or "").strip()
    raw_url = (url or "").strip()
    if not raw_url.startswith(("http://", "https://")):
        return {"ok": False, "error": "invalid_url", "description": "", "tags": ""}

    batch = enrich_send_batch(
        [{"source_page_url": page, "media_url": raw_url}],
        fast=fast,
        max_lustpress_pages=1 if fast else 3,
        max_nsfw_samples=0,
    )
    labels = [str(x).strip() for x in (batch.get("labels") or []) if str(x).strip()]
    caption = (batch.get("caption_line") or "").strip()

    description = caption
    if not description and labels:
        description = " · ".join(labels[:4])
    if not description:
        description = _heuristic_description(raw_url)

    tags = ", ".join(labels[:24])[:500] if labels else ""
    return {
        "ok": True,
        "description": description[:400] if description else "",
        "tags": tags,
        "labels": labels[:40],
        "sources": batch.get("sources") or [],
    }


def _merge_tags(existing: str | None, incoming: str) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for chunk in ((existing or ""), incoming):
        for part in chunk.split(","):
            token = part.strip()
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(token)
    return ", ".join(out)[:500]


def apply_enrich_to_entry(
    row: CaptureArchiveEntry,
    *,
    ref_url: str | None = None,
    fast: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    if row.kind != "url":
        return {"ok": False, "error": "not_url"}
    if row.description and not force:
        return {"ok": True, "skipped": True, "reason": "already_described"}

    result = enrich_archive_url(row.value, ref_url=ref_url or row.ref or None, fast=fast)
    if not result.get("ok"):
        return result

    desc = (result.get("description") or "").strip()
    if desc:
        row.description = desc[:400]
    tags = (result.get("tags") or "").strip()
    if tags:
        row.tags = _merge_tags(row.tags, tags)

    return {
        "ok": True,
        "description": row.description or "",
        "tags": row.tags or "",
        "sources": result.get("sources") or [],
    }


def enrich_archive_entry_by_id(
    db: Session,
    entry_id: int,
    *,
    fast: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    row = db.query(CaptureArchiveEntry).filter(CaptureArchiveEntry.id == entry_id).first()
    if not row:
        return {"ok": False, "error": "not_found"}
    result = apply_enrich_to_entry(row, fast=fast, force=force)
    if result.get("ok") and not result.get("skipped"):
        db.commit()
        db.refresh(row)
    return result


def bulk_enrich_archive_urls(
    db: Session,
    *,
    entry_ids: list[int] | None = None,
    missing_only: bool = True,
    limit: int = 16,
    fast: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    cap = min(max(int(limit or 16), 1), 48)
    q = db.query(CaptureArchiveEntry).filter(
        CaptureArchiveEntry.kind == "url",
        CaptureArchiveEntry.status == "approved",
    )
    if entry_ids:
        q = q.filter(CaptureArchiveEntry.id.in_([int(x) for x in entry_ids if x]))
    elif missing_only and not force:
        q = q.filter(
            (CaptureArchiveEntry.description.is_(None)) | (CaptureArchiveEntry.description == "")
        )
    rows = q.order_by(CaptureArchiveEntry.added_at.desc()).limit(cap).all()
    enriched = 0
    skipped = 0
    errors: list[str] = []
    for row in rows:
        try:
            result = apply_enrich_to_entry(row, fast=fast, force=force)
            if result.get("skipped"):
                skipped += 1
            elif result.get("ok"):
                enriched += 1
            else:
                errors.append(f"{row.id}:{result.get('error') or 'failed'}")
        except Exception as e:
            logger.exception("archive enrich failed id=%s", row.id)
            errors.append(f"{row.id}:{e}")
    if enriched:
        db.commit()
    return {"ok": True, "enriched": enriched, "skipped": skipped, "scanned": len(rows), "errors": errors[:12]}
