"""List completed emoji-factory splits and import tiles as post-divider PNGs."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.services.emoji_factory_jobs import emoji_factory_jobs_dir
from app.services.main_channel_post_divider import MAX_IMAGES, _ensure_row, _parse_images, _serialize_images
from app.services.post_divider_storage import save_post_divider_image

logger = logging.getLogger(__name__)


def _api_base_url() -> str:
    import os

    return (
        (os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_API_URL") or "").strip()
        or "http://127.0.0.1:8000"
    ).rstrip("/")


def _ffmpeg_first_frame_png(path: Path) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not on PATH — required to extract divider previews from emoji tiles")
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "pipe:1",
        ],
        capture_output=True,
        timeout=90,
    )
    if proc.returncode != 0 or not proc.stdout:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[:240]
        raise RuntimeError(err or "ffmpeg frame extract failed")
    return proc.stdout


def _load_job_manifest(job_dir: Path) -> tuple[dict, Path] | None:
    manifest = job_dir / "pack-out" / "manifest.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("tiles"):
        return None
    return data, manifest.parent


def _probe_video_size(path: Path) -> tuple[int, int]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not on PATH (install ffmpeg bundle)")
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    line = (proc.stdout or "").strip().splitlines()[0]
    w, h = line.split("x")
    return int(w), int(h)


def _row_crop_box(
    *,
    frame_w: int,
    frame_h: int,
    cols: int,
    rows: int,
    margin_pct: float,
    row: int,
) -> tuple[int, int, int, int]:
    if row < 0 or row >= rows:
        raise ValueError(f"row must be 0..{rows - 1}")
    cell_w = frame_w // cols
    cell_h = frame_h // rows
    margin_pct = max(0.0, min(40.0, margin_pct))
    inset_x = int(cell_w * margin_pct / 100.0 / 2)
    inset_y = int(cell_h * margin_pct / 100.0 / 2)
    x = inset_x
    y = row * cell_h + inset_y
    w = frame_w - 2 * inset_x
    h = cell_h - 2 * inset_y
    if w < 8 or h < 8:
        raise ValueError("margin_pct too large for row crop")
    return x, y, w, h


def _ffmpeg_crop_first_frame_png(path: Path, *, x: int, y: int, w: int, h: int) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not on PATH — required to export row divider PNGs")
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(path),
            "-vf",
            f"crop={w}:{h}:{x}:{y}",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "pipe:1",
        ],
        capture_output=True,
        timeout=90,
    )
    if proc.returncode != 0 or not proc.stdout:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[:240]
        raise RuntimeError(err or "ffmpeg row crop failed")
    return proc.stdout


def _stitch_tile_row_png(data: dict, pack_dir: Path, row: int) -> bytes:
    import io

    from PIL import Image

    tiles = sorted(
        [t for t in (data.get("tiles") or []) if isinstance(t, dict) and int(t.get("row", -1)) == row],
        key=lambda t: int(t.get("col") or 0),
    )
    if not tiles:
        raise ValueError(f"no tiles in row {row}")
    frames: list[Image.Image] = []
    for tile in tiles:
        rel = str(tile.get("file") or "").replace("\\", "/").strip()
        if not rel:
            continue
        png = _ffmpeg_first_frame_png(pack_dir / rel)
        frames.append(Image.open(io.BytesIO(png)).convert("RGBA"))
    if not frames:
        raise ValueError(f"could not read tiles for row {row}")
    height = max(im.height for im in frames)
    width = sum(im.width for im in frames)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x = 0
    for im in frames:
        canvas.paste(im, (x, (height - im.height) // 2))
        x += im.width
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def _row_export_path(pack_dir: Path, row: int) -> Path:
    return pack_dir / "dividers" / f"row_{row:02d}.png"


def export_emoji_factory_row_divider_png(job_id: str, row: int) -> bytes:
    """Stitched horizontal strip for one grid row (crop from normalized master, else tile concat)."""
    job_id = (job_id or "").strip()
    if not job_id or ".." in job_id or "/" in job_id or "\\" in job_id:
        raise ValueError("invalid job_id")
    job_dir = emoji_factory_jobs_dir() / job_id
    loaded = _load_job_manifest(job_dir)
    if not loaded:
        raise FileNotFoundError("emoji factory job not found")
    data, pack_dir = loaded
    cols = int(data.get("cols") or 0)
    rows = int(data.get("rows") or 0)
    if cols < 1 or rows < 1:
        raise ValueError("invalid grid in manifest")
    row = int(row)
    if row < 0 or row >= rows:
        raise ValueError(f"row must be 0..{rows - 1}")
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    margin_pct = float(params.get("margin_pct") or 0.0)
    normalized = pack_dir / "normalized.mp4"
    if normalized.is_file():
        frame_w, frame_h = _probe_video_size(normalized)
        x, y, w, h = _row_crop_box(
            frame_w=frame_w,
            frame_h=frame_h,
            cols=cols,
            rows=rows,
            margin_pct=margin_pct,
            row=row,
        )
        return _ffmpeg_crop_first_frame_png(normalized, x=x, y=y, w=w, h=h)
    logger.info("job %s row %s: normalized.mp4 missing — stitching tile webms", job_id, row)
    return _stitch_tile_row_png(data, pack_dir, row)


def save_emoji_factory_row_divider_export(job_id: str, row: int) -> Path:
    png = export_emoji_factory_row_divider_png(job_id, row)
    job_dir = emoji_factory_jobs_dir() / job_id
    loaded = _load_job_manifest(job_dir)
    if not loaded:
        raise FileNotFoundError("emoji factory job not found")
    _data, pack_dir = loaded
    out_dir = pack_dir / "dividers"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = _row_export_path(pack_dir, int(row))
    path.write_bytes(png)
    return path


def import_emoji_factory_row_as_divider(
    db: Session,
    *,
    job_id: str,
    row: int,
    label: str = "",
) -> dict:
    png = export_emoji_factory_row_divider_png(job_id, row)
    default_label = f"row {row} · {job_id[:8]}"[:64]
    meta = _register_divider_png(db, png, label.strip() or default_label)
    return {"ok": True, "imported": meta, "source": {"job_id": job_id, "row": int(row)}}


def _row_strip_meta(job_id: str, pack_dir: Path, rows: int, base: str) -> list[dict]:
    strips: list[dict] = []
    for row in range(rows):
        saved = _row_export_path(pack_dir, row)
        strips.append(
            {
                "row": row,
                "preview_url": f"{base}/emoji-factory/jobs/{job_id}/rows/{row}/divider-png",
                "saved_path": str(saved) if saved.is_file() else None,
                "export_filename": saved.name,
            }
        )
    return strips


def list_emoji_factory_divider_sources() -> list[dict]:
    """Completed emoji-factory jobs on disk (pack-out/manifest.json present)."""
    root = emoji_factory_jobs_dir()
    if not root.is_dir():
        return []
    jobs: list[dict] = []
    for job_dir in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime if p.is_dir() else 0, reverse=True):
        if not job_dir.is_dir():
            continue
        loaded = _load_job_manifest(job_dir)
        if not loaded:
            continue
        data, pack_dir = loaded
        tiles: list[dict] = []
        for tile in data.get("tiles") or []:
            if not isinstance(tile, dict):
                continue
            rel = str(tile.get("file") or "").replace("\\", "/").strip()
            if not rel:
                continue
            tile_path = pack_dir / rel
            if not tile_path.is_file():
                continue
            stem = Path(rel).stem
            tiles.append(
                {
                    "tile": stem,
                    "row": tile.get("row"),
                    "col": tile.get("col"),
                    "emoji": tile.get("emoji"),
                    "bytes": tile.get("bytes"),
                }
            )
        if not tiles:
            continue
        base = _api_base_url()
        params = data.get("params") if isinstance(data.get("params"), dict) else {}
        for t in tiles:
            t["preview_url"] = f"{base}/main-channel-divider/emoji-factory-preview/{job_dir.name}/{t['tile']}"
        jobs.append(
            {
                "job_id": job_dir.name,
                "cols": int(data.get("cols") or 0),
                "rows": int(data.get("rows") or 0),
                "tile_px": params.get("tile_px"),
                "static": bool(params.get("static")),
                "tile_count": len(tiles),
                "tiles": tiles,
                "has_normalized": (pack_dir / "normalized.mp4").is_file(),
                "normalized_preview_url": f"{base}/main-channel-divider/emoji-factory-preview/{job_dir.name}/normalized",
                "row_strips": _row_strip_meta(job_dir.name, pack_dir, int(data.get("rows") or 0), base),
            }
        )
    return jobs


def resolve_emoji_factory_preview_path(job_id: str, tile: str) -> Path:
    job_id = (job_id or "").strip()
    tile = (tile or "").strip()
    if not job_id or not tile or ".." in job_id or "/" in job_id or "\\" in job_id:
        raise ValueError("invalid job_id or tile")
    job_dir = emoji_factory_jobs_dir() / job_id
    if not job_dir.is_dir():
        raise FileNotFoundError("emoji factory job not found")
    if tile == "normalized":
        path = job_dir / "pack-out" / "normalized.mp4"
        if not path.is_file():
            raise FileNotFoundError("normalized master not found for job")
        return path
    rel = f"tiles/{tile}.webm"
    path = job_dir / "pack-out" / rel
    if not path.is_file():
        raise FileNotFoundError("tile not found")
    return path


def emoji_factory_preview_png(job_id: str, tile: str) -> bytes:
    path = resolve_emoji_factory_preview_path(job_id, tile)
    return _ffmpeg_first_frame_png(path)


def _register_divider_png(db: Session, png_bytes: bytes, label: str) -> dict:
    row = _ensure_row(db)
    images = _parse_images(row.images_json)
    if len(images) >= MAX_IMAGES:
        raise ValueError(f"Maximum {MAX_IMAGES} divider images — delete one first")
    image_id, fname, _ = save_post_divider_image(png_bytes, label or "divider.png")
    images.append({"id": image_id, "filename": fname, "label": (label or "").strip()[:64]})
    row.images_json = _serialize_images(images)
    if not row.active_image_id:
        row.active_image_id = image_id
    db.commit()
    return {"id": image_id, "filename": fname, "label": (label or "").strip()[:64]}


def import_emoji_factory_tile_as_divider(
    db: Session,
    *,
    job_id: str,
    tile: str,
    label: str = "",
) -> dict:
    png = emoji_factory_preview_png(job_id, tile)
    default_label = f"emoji {job_id[:8]} {tile}"[:64]
    meta = _register_divider_png(db, png, label.strip() or default_label)
    return {"ok": True, "imported": meta, "source": {"job_id": job_id, "tile": tile}}
