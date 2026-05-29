"""Master capture archive: URLs and usernames (extension sync + media library merge)."""

from __future__ import annotations

import csv
import io
import json
import re
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

router = APIRouter(prefix="/archive", tags=["archive"])

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{2,64}$")


def _normalize_kind(raw: str | None) -> str:
    return "username" if (raw or "").strip().lower() in ("username", "user", "handle") else "url"


def _normalize_value(kind: str, raw: str) -> str | None:
    v = (raw or "").strip()
    if not v:
        return None
    if kind == "username":
        v = v.lstrip("@")
        return v if _USERNAME_RE.match(v) else None
    if v.startswith(("http://", "https://")) and not v.startswith(("blob:", "data:")):
        return v[:4096]
    return None


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
        "origin": row.origin or "",
        "added_at": row.added_at.isoformat() if row.added_at else None,
        "addedAt": int(row.added_at.timestamp() * 1000) if row.added_at else None,
    }
    d["summary"] = _entry_summary(d)
    return d


def _upsert_entry(db: Session, payload: dict[str, Any]) -> bool:
    kind = _normalize_kind(payload.get("kind") or payload.get("type"))
    value = _normalize_value(kind, str(payload.get("value") or payload.get("url") or payload.get("username") or ""))
    if not value:
        return False
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
    origin = str(payload.get("origin") or "import")[:32] or None
    if existing:
        existing.added_at = max(existing.added_at or ts, ts)
        if source:
            existing.source = source
        if ref:
            existing.ref = ref
        if note:
            existing.note = note
        return False
    db.add(
        CaptureArchiveEntry(
            kind=kind,
            value=value,
            source=source,
            ref=ref,
            note=note,
            origin=origin,
            added_at=ts,
        )
    )
    return True


_SORT_FIELDS = frozenset({"added_at", "value", "kind", "source", "host", "summary"})


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


def _build_merged_list(
    db: Session,
    *,
    q: str | None = None,
    kind: str | None = None,
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
                    str(entry.get("summary") or _entry_summary(entry)),
                    str(entry.get("origin") or ""),
                ]
            ).lower()
            return all(t in hay for t in tokens)

        items = [x for x in items if _matches(x)]
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
    return {"handles": [h for h in handles if h]}


@router.get("/entries/sync-bundle")
def extension_sync_bundle(
    limit: int = Query(12000, ge=1, le=12000),
    db: Session = Depends(get_db),
):
    """All persisted archive rows for extension pull (no virtual media merge)."""
    rows = (
        db.query(CaptureArchiveEntry)
        .order_by(CaptureArchiveEntry.added_at.desc())
        .limit(limit)
        .all()
    )
    entries = [_row_to_dict(r) for r in rows]
    return {"entries": entries, "total": len(entries)}


@router.get("/entries")
def list_entries(
    q: str | None = Query(None),
    kind: str | None = Query(None),
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
    if not merge:
        db.query(CaptureArchiveEntry).delete()
    added = 0
    for raw in entries:
        if isinstance(raw, str):
            raw = {"kind": "url", "value": raw}
        if _upsert_entry(db, raw):
            added += 1
    db.commit()
    total = db.query(func.count(CaptureArchiveEntry.id)).scalar() or 0
    return {"ok": True, "added": added, "total": total}


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
        ):
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
        w.writerow(["kind", "value", "added_at", "source", "ref", "note", "origin"])
        for e in items:
            w.writerow(
                [
                    e.get("kind"),
                    e.get("value"),
                    e.get("added_at"),
                    e.get("source"),
                    e.get("ref"),
                    e.get("note"),
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
