"""Record Erome upload parameters + outcomes for performance learning loops."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.erome_upload_policy import append_ledger_row
from app.services.import_pipeline import tbcc_run_dir
from app.services.media_watermark import ffmpeg_available

_VIDEO_EXTS = frozenset({".mp4", ".mov", ".webm", ".avi", ".mkv"})
_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})


@dataclass
class EromeUploadParams:
    title: str | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    source: str = "unknown"
    network_key: str | None = None
    staging_path: str | None = None
    watermark: dict[str, Any] | None = None
    crop: dict[str, Any] | None = None
    content_notes: str | None = None
    file_count: int = 0
    force_policy: bool = False
    visibility: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analytics_dir() -> Path:
    d = tbcc_run_dir() / "erome-analytics"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sidecar_path(folder: Path) -> Path:
    return folder / "erome.params.json"


def read_erome_sidecar(folder: str | Path) -> dict[str, Any]:
    """Load optional erome.params.json beside staged media."""
    root = Path(folder).expanduser().resolve()
    path = sidecar_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def parse_erome_caption(caption: str) -> tuple[str | None, list[str], str | None]:
    """Album Composer caption → title, tags, description.

    Line 1: album title
    Line 2+: optional ``tags: milf, webcam, big tits`` or freeform description
    """
    lines = [ln.strip() for ln in (caption or "").splitlines() if ln.strip()]
    if not lines:
        return None, [], None
    title = lines[0][:120]
    tags: list[str] = []
    desc_parts: list[str] = []
    for line in lines[1:]:
        low = line.lower()
        if low.startswith("tags:"):
            raw = line.split(":", 1)[-1]
            tags.extend(t.strip() for t in re.split(r"[,;]+", raw) if t.strip())
        elif low.startswith("#"):
            tags.extend(t.lstrip("#").strip() for t in line.split() if t.startswith("#"))
        else:
            desc_parts.append(line)
    description = "\n".join(desc_parts).strip() or None
    return title, tags[:30], description


def merge_sidecar_params(folder: str | Path, params: EromeUploadParams) -> EromeUploadParams:
    side = read_erome_sidecar(folder)
    if not side:
        return params
    title = (side.get("title") or params.title or "").strip() or params.title
    desc = (side.get("description") or params.description or "").strip() or params.description
    tags_raw = side.get("tags") or params.tags or []
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in re.split(r"[,;]+", tags_raw) if t.strip()]
    else:
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    network = (side.get("network_key") or params.network_key or "").strip() or params.network_key
    notes = (side.get("content_notes") or params.content_notes or "").strip() or params.content_notes
    wm = side.get("watermark") if isinstance(side.get("watermark"), dict) else params.watermark
    crop = side.get("crop") if isinstance(side.get("crop"), dict) else params.crop
    vis = (side.get("visibility") or params.visibility or "").strip() or params.visibility
    return EromeUploadParams(
        title=title,
        description=desc,
        tags=tags or params.tags,
        source=params.source or str(side.get("source") or "sidecar"),
        network_key=network,
        staging_path=params.staging_path or str(folder),
        watermark=wm,
        crop=crop,
        content_notes=notes,
        file_count=params.file_count,
        force_policy=bool(params.force_policy or side.get("force")),
        visibility=vis,
    )


def _probe_video_duration_sec(path: Path) -> float | None:
    if not ffmpeg_available():
        return None
    try:
        import subprocess

        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return None
        val = float(proc.stdout.strip())
        return round(val, 2) if val > 0 else None
    except Exception:
        return None


def collect_staging_metadata(files: list[Path]) -> dict[str, Any]:
    """Summarize staged files for analytics (types, sizes, video duration)."""
    videos: list[dict[str, Any]] = []
    photos: list[dict[str, Any]] = []
    total_bytes = 0
    for path in files:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        total_bytes += size
        ext = path.suffix.lower()
        row = {"name": path.name, "bytes": size, "ext": ext}
        if ext in _VIDEO_EXTS:
            dur = _probe_video_duration_sec(path)
            if dur is not None:
                row["duration_sec"] = dur
            videos.append(row)
        elif ext in _IMAGE_EXTS:
            photos.append(row)
    meta: dict[str, Any] = {
        "file_count": len(files),
        "video_count": len(videos),
        "photo_count": len(photos),
        "total_bytes": total_bytes,
        "videos": videos[:20],
        "photos": photos[:20],
    }
    durs = [v["duration_sec"] for v in videos if v.get("duration_sec")]
    if durs:
        meta["primary_duration_sec"] = max(durs)
        meta["total_video_duration_sec"] = round(sum(durs), 2)
    if len(videos) == 1 and not photos:
        meta["format_hint"] = "single_video"
    elif len(videos) >= 1 and photos:
        meta["format_hint"] = "mixed_album"
    elif photos and not videos:
        meta["format_hint"] = "photo_album"
    return meta


def record_erome_upload(
    params: EromeUploadParams,
    result: dict[str, Any],
    *,
    staging_meta: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    db=None,
) -> Path:
    """Append JSONL ledger row + per-upload manifest; optionally growth attribution."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    visibility = str(result.get("visibility") or params.visibility or "public").strip().lower()
    gov = result.get("governance_status")
    if not gov and visibility == "private":
        gov = "needs_review"
    row: dict[str, Any] = {
        "recorded_at": now,
        "published_at": now if result.get("ok") and visibility == "public" else None,
        "ok": bool(result.get("ok")),
        "album_url": result.get("album_url"),
        "title": params.title or result.get("title"),
        "description": params.description,
        "tags": list(params.tags or []),
        "source": params.source,
        "network_key": params.network_key,
        "staging_path": params.staging_path or result.get("staging_path"),
        "file_count": params.file_count or result.get("file_count") or 0,
        "watermark": params.watermark,
        "crop": params.crop,
        "content_notes": params.content_notes,
        "staging_meta": staging_meta or {},
        "policy": policy or {},
        "error": result.get("error"),
        "visibility": visibility,
        "governance_status": gov,
    }
    append_ledger_row(row)

    slug = re.sub(r"[^\w.-]+", "_", (params.title or "untitled")[:40]).strip("_") or "upload"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    manifest_path = analytics_dir() / f"{ts}_{slug}.json"
    manifest_path.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Growth attribution only for public albums — private staging is not discoverable yet
    if db is not None and result.get("ok") and result.get("album_url") and visibility == "public":
        try:
            from app.services.growth_attribution import EVENT_EROME_ALBUM_PUBLISHED, record_growth_attribution

            record_growth_attribution(
                db,
                event_type=EVENT_EROME_ALBUM_PUBLISHED,
                attach_latest_delivery=False,
                extra={
                    "album_url": result.get("album_url"),
                    "title": row["title"],
                    "tags": row["tags"],
                    "source": params.source,
                    "network_key": params.network_key,
                    "staging_meta": staging_meta,
                    "content_notes": params.content_notes,
                    "visibility": visibility,
                },
            )
        except Exception:
            pass

    return manifest_path
