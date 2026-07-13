"""Erome upload governance — private staging → human review → public.

Playwright uploads land as private (default) so titles/tags/direction can be
fixed manually before the album is discoverable. Ledger rows track visibility
and review status; promote-to-public remains a human (or later Playwright) step.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.erome_upload_policy import ledger_path
from app.services.mega_erome_staging import erome_staging_dir

VISIBILITY_PRIVATE = "private"
VISIBILITY_PUBLIC = "public"

STATUS_NEEDS_REVIEW = "needs_review"
STATUS_APPROVED = "approved_public"
STATUS_REJECTED = "rejected"
STATUS_STAGED = "staged_private"

_VALID_STATUS = frozenset(
    {STATUS_NEEDS_REVIEW, STATUS_APPROVED, STATUS_REJECTED, STATUS_STAGED}
)


def default_upload_visibility() -> str:
    """Default album visibility for Playwright uploads.

    Private is the governance default so automated batches stay hidden until
    a human pass. Set ``TBCC_EROME_DEFAULT_VISIBILITY=public`` to restore the
    old always-publish behavior.
    """
    raw = (os.getenv("TBCC_EROME_DEFAULT_VISIBILITY") or "private").strip().lower()
    if raw in ("public", "pub", "open"):
        return VISIBILITY_PUBLIC
    return VISIBILITY_PRIVATE


def governance_enabled() -> bool:
    return (os.getenv("TBCC_EROME_UPLOAD_GOVERNANCE") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _read_ledger() -> list[dict[str, Any]]:
    path = ledger_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _rewrite_ledger(rows: list[dict[str, Any]]) -> None:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def list_pending_review(*, limit: int = 50) -> list[dict[str, Any]]:
    """Private / needs_review uploads awaiting the human governance pass."""
    out: list[dict[str, Any]] = []
    for row in reversed(_read_ledger()):
        if not row.get("ok"):
            continue
        status = str(row.get("governance_status") or "")
        visibility = str(row.get("visibility") or VISIBILITY_PUBLIC)
        if status in (STATUS_NEEDS_REVIEW, STATUS_STAGED) or (
            visibility == VISIBILITY_PRIVATE and status not in (STATUS_APPROVED, STATUS_REJECTED)
        ):
            out.append(row)
        if len(out) >= max(1, limit):
            break
    return out


def mark_governance(
    *,
    album_url: str,
    status: str,
    notes: str | None = None,
    title: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Update ledger row after manual title/tag/privacy pass."""
    status_n = str(status or "").strip().lower()
    if status_n not in _VALID_STATUS:
        return {"ok": False, "error": f"invalid_status:{status_n}"}
    needle = (album_url or "").strip().rstrip("/")
    if not needle:
        return {"ok": False, "error": "album_url_required"}

    rows = _read_ledger()
    matched = False
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for row in reversed(rows):
        url = str(row.get("album_url") or "").rstrip("/")
        if url != needle and not url.endswith(needle.split("/")[-1]):
            continue
        matched = True
        row["governance_status"] = status_n
        row["governance_reviewed_at"] = now
        if notes:
            row["governance_notes"] = str(notes)[:500]
        if title:
            row["title"] = str(title)[:200]
        if tags is not None:
            row["tags"] = [str(t).strip() for t in tags if str(t).strip()][:30]
        if status_n == STATUS_APPROVED:
            row["visibility"] = VISIBILITY_PUBLIC
        elif status_n in (STATUS_NEEDS_REVIEW, STATUS_STAGED):
            row["visibility"] = VISIBILITY_PRIVATE
        break

    if not matched:
        return {"ok": False, "error": "album_not_in_ledger"}
    _rewrite_ledger(rows)
    return {"ok": True, "album_url": needle, "governance_status": status_n}


def intel_week_staging_dir(*, week: str | None = None) -> Path:
    """Folder for pre-approved media drawn from last week's intel."""
    if week:
        slug = re.sub(r"[^\w.-]+", "-", week.strip())[:32]
    else:
        iso = datetime.now(timezone.utc).isocalendar()
        slug = f"{iso.year}-W{iso.week:02d}"
    root = erome_staging_dir() / "intel-week" / slug
    root.mkdir(parents=True, exist_ok=True)
    return root


def seed_intel_week_sidecar(
    folder: str | Path | None = None,
    *,
    title: str | None = None,
    extra_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Write ``erome.params.json`` with intel-suggested tags + private visibility."""
    from app.services.erome_upload_policy import intel_upload_hints

    root = Path(folder).expanduser().resolve() if folder else intel_week_staging_dir()
    root.mkdir(parents=True, exist_ok=True)
    hints = intel_upload_hints()
    suggested = [str(x.get("tag") or "") for x in (hints.get("top_tags") or []) if x.get("tag")]
    tags: list[str] = []
    for t in list(extra_tags or []) + suggested:
        tl = str(t).strip().lower()
        if tl and tl not in tags:
            tags.append(tl)
    tags = tags[:12]
    payload: dict[str, Any] = {
        "visibility": VISIBILITY_PRIVATE,
        "governance_status": STATUS_NEEDS_REVIEW,
        "source": "intel_week",
        "tags": tags,
        "title": (title or "").strip() or None,
        "max_files": 1,
        "videos_only": True,
        "preferred_format_bucket": hints.get("preferred_format_bucket") or "single_video",
        "top_quartile_tags": hints.get("top_quartile_tags") or [],
        "saturated_tags": hints.get("saturated_tags") or [],
        "intel_row_count": hints.get("row_count") or 0,
        "seeded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "content_notes": (
            "Private staging — ONE video per album. Human governance pass before public. "
            "Adjust title/tags to match this week's intel direction."
        ),
    }
    if not payload["title"]:
        payload.pop("title", None)
    path = root / "erome.params.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True, "folder": str(root), "sidecar": str(path), "tags": tags, "hints": hints}


def governance_summary() -> dict[str, Any]:
    pending = list_pending_review(limit=200)
    rows = [r for r in _read_ledger() if r.get("ok")]
    public_n = sum(1 for r in rows if str(r.get("visibility") or "public") == VISIBILITY_PUBLIC)
    private_n = sum(1 for r in rows if str(r.get("visibility")) == VISIBILITY_PRIVATE)
    return {
        "ok": True,
        "default_visibility": default_upload_visibility(),
        "governance_enabled": governance_enabled(),
        "pending_review": len(pending),
        "ledger_ok_total": len(rows),
        "private_count": private_n,
        "public_count": public_n,
        "pending": [
            {
                "album_url": r.get("album_url"),
                "title": r.get("title"),
                "tags": r.get("tags") or [],
                "visibility": r.get("visibility"),
                "governance_status": r.get("governance_status"),
                "recorded_at": r.get("recorded_at"),
                "staging_path": r.get("staging_path"),
            }
            for r in pending[:20]
        ],
    }


def promote_on_main_post_enabled() -> bool:
    """When true, a successful Main-lane Telegram send can release N private albums."""
    return (os.getenv("TBCC_EROME_PROMOTE_ON_MAIN_POST") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def promote_on_main_post_limit() -> int:
    raw = (os.getenv("TBCC_EROME_PROMOTE_ON_MAIN_POST_LIMIT") or "1").strip()
    try:
        return max(0, min(10, int(raw)))
    except ValueError:
        return 1


def release_pending_albums_on_main_post(
    *,
    headed: bool = False,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Promote oldest pending private albums to public (Buffer-style side effect)."""
    if not promote_on_main_post_enabled() and not dry_run:
        return {"ok": True, "skipped": True, "reason": "TBCC_EROME_PROMOTE_ON_MAIN_POST=0"}
    cap = promote_on_main_post_limit() if limit is None else max(0, min(10, int(limit)))
    pending = list_pending_review(limit=cap)
    if not pending:
        return {"ok": True, "promoted": 0, "pending": 0}
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "would_promote": [p.get("album_url") for p in pending],
        }

    from app.services.erome_upload_provision import promote_album_to_public

    results: list[dict[str, Any]] = []
    for row in pending:
        url = str(row.get("album_url") or "")
        if not url:
            continue
        results.append(promote_album_to_public(url, headed=headed))
    ok_n = sum(1 for r in results if r.get("ok"))
    return {"ok": True, "promoted": ok_n, "results": results, "attempted": len(results)}
