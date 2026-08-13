"""Master capture archive: URLs and usernames (extension sync + media library merge)."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from functools import cmp_to_key
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.capture_archive_entry import CaptureArchiveEntry
from app.models.media import Media
from app.services.archive_username_filter import normalize_archive_username

router = APIRouter(prefix="/archive", tags=["archive"])

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{2,64}$")


@dataclass
class _UpsertResult:
    created: bool
    entry_id: int | None = None
    try_pack_queue: bool = False


def _normalize_kind(raw: str | None) -> str:
    return "username" if (raw or "").strip().lower() in ("username", "user", "handle") else "url"


def _normalize_value(kind: str, raw: str) -> str | None:
    v = (raw or "").strip()
    if not v:
        return None
    if kind == "username":
        return normalize_archive_username(v)
    if v.startswith(("http://", "https://")) and not v.startswith(("blob:", "data:")):
        return v[:4096]
    return None


def _url_class_and_route(url: str) -> tuple[str, str]:
    """Machine class + human routing hint for master archive curation."""
    from app.services.mega_link_extract import classify_url_host

    kind = classify_url_host(url)
    routes = {
        "direct_video": "Import queue → AOF content pool (milf, bj, etc.)",
        "gallery_erome": "Resolve page → file host or loot modifier",
        "gallery_bunkr": "Resolve gallery → loot modifier or pool import",
        "file_host": "Mega/file pipeline → loot modifier (LV wrap)",
        "paste": "Unwrap paste → re-classify inner links",
        "obfuscated": "Bypass/LV unwrap → re-classify",
        "sophon": "Sophon folder → mega pipeline",
        "telegram": "Telegram import / channel scrape (not a direct file URL)",
        "affiliate": "Skip or manual review",
        "other": "Auto-tag or manual review",
    }
    return kind, routes.get(kind, routes["other"])


def _heuristic_url_summary(url: str) -> str:
    """Short human hint from host + path (no LLM)."""
    try:
        from urllib.parse import urlparse

        u = urlparse(url)
        host = (u.hostname or "").replace("www.", "")
        if not host:
            return ""
        segs = [s for s in (u.path or "").split("/") if s]
        tail = segs[-1] if segs else ""
        if tail:
            tail = tail.split("?")[0]
            tail = tail.replace("-", " ").replace("_", " ")[:100]
        return f"{host}" + (f" - {tail}" if tail and tail.lower() not in host.lower() else "")
    except Exception:
        return ""


def _entry_summary(entry: dict[str, Any]) -> str:
    desc = (entry.get("description") or "").strip()
    if desc:
        return desc[:400]
    note = (entry.get("note") or "").strip()
    if note and not note.startswith("ref:"):
        return note[:400]
    if entry.get("kind") == "url":
        return _heuristic_url_summary(str(entry.get("value") or ""))
    return ""


def _row_to_dict(row: CaptureArchiveEntry) -> dict[str, Any]:
    d = {
        "id": row.id,
        "kind": row.kind,
        "value": row.value,
        "source": row.source or "",
        "ref": row.ref or "",
        "note": row.note or "",
        "description": getattr(row, "description", None) or "",
        "tags": row.tags or "",
        "origin": row.origin or "",
        "status": getattr(row, "status", None) or "approved",
        "submitted_by": getattr(row, "submitted_by", None) or "",
        "added_at": row.added_at.isoformat() if row.added_at else None,
        "addedAt": int(row.added_at.timestamp() * 1000) if row.added_at else None,
    }
    d["summary"] = _entry_summary(d)
    if d.get("kind") == "url" and d.get("value"):
        url_class, route_hint = _url_class_and_route(str(d["value"]))
        d["url_class"] = url_class
        d["route_hint"] = route_hint
    return d


def _upsert_entry(db: Session, payload: dict[str, Any]) -> _UpsertResult:
    kind = _normalize_kind(payload.get("kind") or payload.get("type"))
    value = _normalize_value(kind, str(payload.get("value") or payload.get("url") or payload.get("username") or ""))
    if not value:
        return _UpsertResult(created=False)
    existing = (
        db.query(CaptureArchiveEntry)
        .filter(CaptureArchiveEntry.kind == kind, CaptureArchiveEntry.value == value)
        .first()
    )
    added_at = payload.get("added_at") or payload.get("addedAt")
    ts = None
    if added_at:
        try:
            if isinstance(added_at, (int, float)):
                ts = datetime.utcfromtimestamp(float(added_at) / 1000.0 if added_at > 1e12 else float(added_at))
            else:
                ts = datetime.fromisoformat(str(added_at).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            ts = None
    if not ts:
        ts = datetime.utcnow()
    source = str(payload.get("source") or "")[:80] or None
    ref = str(payload.get("ref") or "")[:2000] or None
    note = str(payload.get("note") or "")[:400] or None
    tags_raw = str(payload.get("tags") or payload.get("tagsCsv") or "")[:500].strip()
    tags = tags_raw or None
    origin = str(payload.get("origin") or "import")[:32] or None
    status_raw = str(payload.get("status") or "approved").strip().lower()
    status = status_raw if status_raw in ("approved", "pending", "rejected") else "approved"
    submitted_by = str(payload.get("submitted_by") or "")[:32].strip() or None
    try_pack = kind == "url" and status == "approved"
    if existing:
        prev_status = str(getattr(existing, "status", None) or "approved").lower()
        existing.added_at = max(existing.added_at or ts, ts)
        if source:
            existing.source = source
        if ref:
            existing.ref = ref
        if note:
            existing.note = note
        if tags:
            existing.tags = tags
        if status and getattr(existing, "status", None) != "approved":
            existing.status = status
        if submitted_by and not getattr(existing, "submitted_by", None):
            existing.submitted_by = submitted_by
        db.flush()
        became_approved = try_pack and prev_status != "approved" and status == "approved"
        return _UpsertResult(created=False, entry_id=existing.id, try_pack_queue=became_approved)
    row = CaptureArchiveEntry(
        kind=kind,
        value=value,
        source=source,
        ref=ref,
        note=note,
        tags=tags,
        origin=origin,
        status=status,
        submitted_by=submitted_by,
        added_at=ts,
    )
    db.add(row)
    db.flush()
    return _UpsertResult(created=True, entry_id=row.id, try_pack_queue=try_pack)


_SORT_FIELDS = frozenset({"added_at", "value", "kind", "source", "host", "summary", "tags"})


def _entry_host(entry: dict[str, Any]) -> str:
    if entry.get("kind") != "url":
        return ""
    try:
        from urllib.parse import urlparse

        return (urlparse(str(entry.get("value") or "")).hostname or "").replace("www.", "").lower()
    except Exception:
        return ""


def _sort_value(entry: dict[str, Any], field: str) -> Any:
    f = field if field in _SORT_FIELDS else "added_at"
    if f == "added_at":
        return entry.get("addedAt") or 0
    if f == "kind":
        return 1 if entry.get("kind") == "username" else 0
    if f == "host":
        return _entry_host(entry)
    if f == "summary":
        return (entry.get("summary") or _entry_summary(entry) or "").lower()
    if f == "source":
        return str(entry.get("source") or "").lower()
    if f == "tags":
        return str(entry.get("tags") or "").lower()
    return str(entry.get("value") or "").lower()


def _sort_archive_items(
    items: list[dict[str, Any]],
    *,
    sort: str | None = "added_at",
    order: str | None = "desc",
    sort2: str | None = None,
    order2: str | None = "asc",
) -> list[dict[str, Any]]:
    primary = (sort or "added_at").strip().lower()
    if primary not in _SORT_FIELDS:
        primary = "added_at"
    dir1 = "asc" if (order or "").strip().lower() == "asc" else "desc"
    secondary = (sort2 or "").strip().lower()
    if secondary and secondary not in _SORT_FIELDS:
        secondary = ""
    dir2 = "asc" if (order2 or "").strip().lower() == "asc" else "desc"

    def _cmp_pair(a: dict[str, Any], b: dict[str, Any], field: str, direction: str) -> int:
        av = _sort_value(a, field)
        bv = _sort_value(b, field)
        if av < bv:
            return -1 if direction == "asc" else 1
        if av > bv:
            return 1 if direction == "asc" else -1
        return 0

    def _cmp_all(a: dict[str, Any], b: dict[str, Any]) -> int:
        c = _cmp_pair(a, b, primary, dir1)
        if c:
            return c
        if secondary:
            c = _cmp_pair(a, b, secondary, dir2)
            if c:
                return c
        return _cmp_pair(a, b, "value", "asc")

    items.sort(key=cmp_to_key(_cmp_all))
    return items


def _entry_matches_tags(entry: dict[str, Any], tags_filter: str | None) -> bool:
    raw = (tags_filter or "").strip()
    if not raw:
        return True
    hay = str(entry.get("tags") or "").lower()
    tokens = [t.strip().lower() for t in raw.split(",") if t.strip()]
    if not tokens:
        return True
    return all(t in hay for t in tokens)


def _build_merged_list(
    db: Session,
    *,
    q: str | None = None,
    kind: str | None = None,
    tags: str | None = None,
    status: str | None = None,
    include_media: bool = True,
    sort: str | None = "added_at",
    order: str | None = "desc",
    sort2: str | None = None,
    order2: str | None = "asc",
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    rows = db.query(CaptureArchiveEntry).order_by(CaptureArchiveEntry.added_at.desc()).all()
    for row in rows:
        key = f"{row.kind}|{row.value.lower()}"
        merged[key] = _row_to_dict(row)

    if include_media:
        media_rows = (
            db.query(Media.source_channel, Media.created_at)
            .filter(Media.source_channel.isnot(None))
            .order_by(Media.created_at.desc())
            .limit(5000)
            .all()
        )
        for src, created_at in media_rows:
            url = (src or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            key = f"url|{url.lower()}"
            if key in merged:
                continue
            merged[key] = {
                "id": None,
                "kind": "url",
                "value": url[:4096],
                "source": "media_library",
                "ref": "",
                "note": "",
                "origin": "media_library",
                "added_at": created_at.isoformat() if created_at else None,
                "addedAt": int(created_at.timestamp() * 1000) if created_at else None,
            }

    items = list(merged.values())
    for entry in items:
        if "summary" not in entry:
            entry["summary"] = _entry_summary(entry)
    if kind:
        items = [x for x in items if x["kind"] == _normalize_kind(kind)]
    if status:
        st = status.strip().lower()
        items = [x for x in items if str(x.get("status") or "approved").lower() == st]
    else:
        items = [x for x in items if str(x.get("status") or "approved").lower() == "approved"]
    if q:
        ql = q.strip().lower()
        tokens = [t for t in ql.split() if t]

        def _matches(entry: dict[str, Any]) -> bool:
            hay = " ".join(
                [
                    str(entry.get("value") or ""),
                    _entry_host(entry),
                    str(entry.get("source") or ""),
                    str(entry.get("ref") or ""),
                    str(entry.get("note") or ""),
                    str(entry.get("description") or ""),
                    str(entry.get("tags") or ""),
                    str(entry.get("summary") or _entry_summary(entry)),
                    str(entry.get("origin") or ""),
                ]
            ).lower()
            return all(t in hay for t in tokens)

        items = [x for x in items if _matches(x)]
    if tags:
        items = [x for x in items if _entry_matches_tags(x, tags)]
    return _sort_archive_items(items, sort=sort, order=order, sort2=sort2, order2=order2)


@router.get("/entries/handles")
def list_archive_handles(db: Session = Depends(get_db)):
    """Distinct username handles for dashboard tabs."""
    rows = (
        db.query(CaptureArchiveEntry.value)
        .filter(CaptureArchiveEntry.kind == "username")
        .distinct()
        .limit(500)
        .all()
    )
    handles = sorted({str(v[0]).strip().lstrip("@").lower() for v in rows if v and v[0]})
    return {"handles": [h for h in handles if normalize_archive_username(h)]}


@router.get("/entries/sync-bundle")
def extension_sync_bundle(
    limit: int = Query(12000, ge=1, le=12000),
    db: Session = Depends(get_db),
):
    """All persisted approved archive rows for extension pull (no virtual media merge)."""
    rows = (
        db.query(CaptureArchiveEntry)
        .filter(CaptureArchiveEntry.status == "approved")
        .order_by(CaptureArchiveEntry.added_at.desc())
        .limit(limit)
        .all()
    )
    entries = [_row_to_dict(r) for r in rows]
    return {"entries": entries, "total": len(entries)}


@router.get("/entries/insert-menu")
def archive_insert_menu(
    limit: int = Query(200, ge=1, le=500),
    q: str | None = Query(None, description="Filter by label, tags, or URL substring"),
    db: Session = Depends(get_db),
):
    """Approved archive URLs for the global Insert dropdown (scheduler, relay, gallery)."""
    rows = (
        db.query(CaptureArchiveEntry)
        .filter(CaptureArchiveEntry.kind == "url", CaptureArchiveEntry.status == "approved")
        .order_by(CaptureArchiveEntry.added_at.desc())
        .limit(min(limit * 3, 1500))
        .all()
    )
    ql = (q or "").strip().lower()
    items: list[dict[str, Any]] = []
    for row in rows:
        d = _row_to_dict(row)
        label = (d.get("description") or d.get("summary") or _heuristic_url_summary(row.value) or row.value).strip()
        if ql:
            hay = " ".join([label, d.get("tags") or "", row.value]).lower()
            if ql not in hay and not all(t in hay for t in ql.split() if t):
                continue
        items.append(
            {
                "id": row.id,
                "url": row.value,
                "label": label[:80],
                "description": d.get("description") or "",
                "tags": d.get("tags") or "",
            }
        )
        if len(items) >= limit:
            break
    return {"items": items, "total": len(items)}


@router.post("/entries/bulk/auto-tag")
def bulk_auto_tag_archive(body: dict, db: Session = Depends(get_db)):
    """Semantic auto-tag for archive URLs (page sweep + tag labels)."""
    from app.services.archive_url_enrich import bulk_enrich_archive_urls

    raw_ids = body.get("ids") or body.get("entry_ids") or []
    if not isinstance(raw_ids, list):
        raw_ids = []
    ids = [int(x) for x in raw_ids if x is not None and str(x).isdigit()]
    return bulk_enrich_archive_urls(
        db,
        entry_ids=ids or None,
        missing_only=bool(body.get("missing_only", not ids)),
        limit=min(int(body.get("limit") or 16), 48),
        fast=bool(body.get("fast", True)),
        force=bool(body.get("force")),
    )


@router.post("/entries/{entry_id}/auto-tag")
def auto_tag_archive_entry(entry_id: int, body: dict | None = None, db: Session = Depends(get_db)):
    from app.services.archive_url_enrich import enrich_archive_entry_by_id

    payload = body or {}
    result = enrich_archive_entry_by_id(
        db,
        entry_id,
        fast=bool(payload.get("fast", True)),
        force=bool(payload.get("force")),
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404 if result.get("error") == "not_found" else 400, detail=result.get("error"))
    row = db.query(CaptureArchiveEntry).filter(CaptureArchiveEntry.id == entry_id).first()
    entry = _row_to_dict(row) if row else None
    return {"ok": True, "entry": entry, **{k: v for k, v in result.items() if k != "ok"}}


@router.get("/entries")
def list_entries(
    q: str | None = Query(None),
    kind: str | None = Query(None),
    tags: str | None = Query(None, description="Comma-separated tag tokens (all must match)"),
    status: str | None = Query(None, description="approved | pending | rejected (omit = approved only)"),
    username: str | None = Query(None, description="Filter URLs linked to this model handle"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
    include_media: bool = Query(True, description="Merge http(s) Media.source_channel URLs into listing"),
    sort: str | None = Query("added_at", description="added_at | value | host | source | kind | summary"),
    order: str | None = Query("desc", description="asc | desc"),
    sort2: str | None = Query(None, description="Secondary sort field"),
    order2: str | None = Query("asc", description="Secondary sort order"),
    db: Session = Depends(get_db),
):
    """Paginated archive list (max 100 per page)."""
    items = _build_merged_list(
        db,
        q=q,
        kind=kind,
        tags=tags,
        status=status,
        include_media=include_media,
        sort=sort,
        order=order,
        sort2=sort2,
        order2=order2,
    )
    if username:
        u = username.strip().lstrip("@").lower()
        if u:

            def _linked(entry: dict[str, Any]) -> bool:
                if entry.get("kind") == "username" and str(entry.get("value") or "").lower() == u:
                    return True
                blob = " ".join(
                    [
                        str(entry.get("value") or ""),
                        str(entry.get("ref") or ""),
                        str(entry.get("note") or ""),
                        str(entry.get("source") or ""),
                    ]
                ).lower()
                return u in blob or f"@{u}" in blob

            items = [x for x in items if _linked(x)]
    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.post("/entries/bulk")
def bulk_upsert(body: dict, db: Session = Depends(get_db)):
    entries = body.get("entries") or body.get("items") or []
    merge = body.get("merge", True)
    auto_tag = bool(body.get("auto_tag"))
    auto_pack = body.get("auto_pack_queue") if "auto_pack_queue" in body else None
    wire_packs = bool(body.get("wire_packs_scheduler"))
    if not merge:
        db.query(CaptureArchiveEntry).delete()
    added = 0
    added_values: list[str] = []
    pack_queue_ids: list[int] = []
    for raw in entries:
        if isinstance(raw, str):
            raw = {"kind": "url", "value": raw}
        kind = _normalize_kind(raw.get("kind") or raw.get("type"))
        value = _normalize_value(kind, str(raw.get("value") or raw.get("url") or ""))
        upsert = _upsert_entry(db, raw)
        if upsert.created:
            added += 1
            if auto_tag and value and kind == "url":
                added_values.append(value)
        if upsert.try_pack_queue and upsert.entry_id:
            pack_queue_ids.append(int(upsert.entry_id))
    db.commit()
    enrich_result = None
    if auto_tag and added_values:
        from app.services.archive_url_enrich import bulk_enrich_archive_urls

        added_ids = [
            int(r.id)
            for r in db.query(CaptureArchiveEntry)
            .filter(CaptureArchiveEntry.kind == "url", CaptureArchiveEntry.value.in_(added_values[:24]))
            .all()
            if r.id
        ]
        if added_ids:
            enrich_result = bulk_enrich_archive_urls(
                db,
                entry_ids=added_ids,
                missing_only=False,
                limit=min(len(added_ids), 24),
                fast=True,
            )
    pack_result = None
    if pack_queue_ids:
        from app.services.archive_pack_autopilot import bulk_auto_queue_archive_entries

        pack_result = bulk_auto_queue_archive_entries(
            db,
            pack_queue_ids,
            enabled=auto_pack,
            wire_scheduler=wire_packs or None,
        )
    total = db.query(func.count(CaptureArchiveEntry.id)).scalar() or 0
    out: dict[str, Any] = {"ok": True, "added": added, "total": total}
    if enrich_result:
        out["auto_tag"] = enrich_result
    if pack_result:
        out["pack_pool"] = pack_result
    return out


@router.post("/entries/sync-from-media")
def sync_from_media(
    limit: int = Query(2000, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    """Import distinct http(s) source_channel values from Media into archive."""
    rows = (
        db.query(Media.source_channel)
        .filter(Media.source_channel.isnot(None))
        .distinct()
        .limit(limit)
        .all()
    )
    added = 0
    for (src,) in rows:
        if _upsert_entry(
            db,
            {
                "kind": "url",
                "value": src,
                "source": "media_library",
                "origin": "media_library",
            },
        ).created:
            added += 1
    db.commit()
    return {"ok": True, "added": added, "scanned": len(rows)}


@router.delete("/entries")
def clear_archive(
    confirm: str = Query(..., description='Must be exactly "DELETE ARCHIVE"'),
    db: Session = Depends(get_db),
):
    if confirm.strip() != "DELETE ARCHIVE":
        raise HTTPException(
            status_code=400,
            detail='Confirmation required: pass confirm=DELETE ARCHIVE (extension local archive is not affected)',
        )
    n = db.query(CaptureArchiveEntry).delete()
    db.commit()
    return {"ok": True, "deleted": n}


@router.get("/entries/export")
def export_entries(
    export_format: str = Query("json", alias="format", pattern="^(json|csv|txt)$"),
    q: str | None = Query(None),
    kind: str | None = Query(None),
    tags: str | None = Query(None),
    include_media: bool = Query(True),
    sort: str | None = Query("added_at"),
    order: str | None = Query("desc"),
    sort2: str | None = Query(None),
    order2: str | None = Query("asc"),
    db: Session = Depends(get_db),
):
    items = _build_merged_list(
        db,
        q=q,
        kind=kind,
        tags=tags,
        include_media=include_media,
        sort=sort,
        order=order,
        sort2=sort2,
        order2=order2,
    )
    if export_format == "json":
        return Response(
            content=json.dumps(items, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="tbcc-master-archive.json"'},
        )
    if export_format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["kind", "value", "added_at", "source", "ref", "note", "description", "tags", "origin"])
        for e in items:
            w.writerow(
                [
                    e.get("kind"),
                    e.get("value"),
                    e.get("added_at"),
                    e.get("source"),
                    e.get("ref"),
                    e.get("note"),
                    e.get("description"),
                    e.get("tags"),
                    e.get("origin"),
                ]
            )
        return PlainTextResponse(
            buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="tbcc-master-archive.csv"'},
        )
    lines = [e["value"] for e in items if e.get("kind") == "url"]
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="tbcc-master-archive.txt"'},
    )


@router.post("/entries/submit")
def submit_archive_entry(body: dict, db: Session = Depends(get_db)):
    """Submit a URL/username to the archive inbox (community = pending until approved)."""
    from app.services.archive_governance import submit_archive_url

    auto = bool(body.get("auto_approve"))
    result = submit_archive_url(
        db,
        value=str(body.get("value") or body.get("url") or ""),
        source=str(body.get("source") or "telegram")[:80],
        ref=str(body.get("ref") or "")[:2000] or None,
        note=str(body.get("note") or "")[:400] or None,
        tags=str(body.get("tags") or body.get("tagsCsv") or "")[:500] or None,
        origin=str(body.get("origin") or "telegram")[:32],
        submitted_by=str(body.get("submitted_by") or "")[:32] or None,
        auto_approve=auto,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "submit_failed")
    return result


@router.get("/governance/pending")
def list_pending_archive(db: Session = Depends(get_db), limit: int = Query(100, ge=1, le=500)):
    from app.services.archive_governance import list_pending_archive_entries

    items = list_pending_archive_entries(db, limit=limit)
    return {"items": items, "total": len(items)}


@router.post("/entries/{entry_id}/governance")
def govern_archive_entry(entry_id: int, body: dict, db: Session = Depends(get_db)):
    from app.services.archive_governance import set_archive_entry_status

    status = str(body.get("status") or "").strip().lower()
    if status not in ("approved", "rejected", "pending"):
        raise HTTPException(status_code=400, detail="status must be approved, rejected, or pending")
    result = set_archive_entry_status(
        db,
        entry_id,
        status,
        reviewed_by=str(body.get("reviewed_by") or "")[:32] or None,
        review_note=str(body.get("review_note") or "")[:400] or None,
        queue_pack_pool=body.get("queue_pack_pool") if "queue_pack_pool" in body else None,
        wire_packs_scheduler=body.get("wire_packs_scheduler") if "wire_packs_scheduler" in body else None,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "not_found")
    return result
