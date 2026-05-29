"""End-to-end split + encode."""

from __future__ import annotations

from pathlib import Path

from emoji_factory.encode import encode_tile_webm_capped, write_manifest
from emoji_factory.ffmpeg_util import ffmpeg_on_path, probe_video_size
from emoji_factory.grid import compute_tile_rects
from emoji_factory.spec import (
    DEFAULT_CRF,
    DEFAULT_FPS,
    DEFAULT_LOOP_SEC,
    DEFAULT_MARGIN_PCT,
    DEFAULT_AUTHOR_TILE_PX,
    DEFAULT_TILE_PX,
    MAX_TILE_BYTES_SOFT,
    MAX_TILE_BYTES_TELEGRAM,
    SUPPORTED_VIDEO_SUFFIXES,
)

# Default emoji placeholders cycling for upload (Telegram requires one per tile).
_DEFAULT_EMOJI = ("🎬", "✨", "🔥", "💫", "⭐", "🌙", "🎨", "💖")


def run_pipeline(
    *,
    input_path: Path,
    out_dir: Path,
    cols: int,
    rows: int,
    tile_px: int = DEFAULT_TILE_PX,
    margin_pct: float = DEFAULT_MARGIN_PCT,
    fps: int = DEFAULT_FPS,
    loop_sec: float = DEFAULT_LOOP_SEC,
    crf: int = DEFAULT_CRF,
    static: bool = False,
    normalize_canvas: bool = True,
) -> Path:
    if not ffmpeg_on_path():
        raise RuntimeError("ffmpeg not on PATH — install ffmpeg and retry")
    input_path = input_path.resolve()
    if input_path.suffix.lower() not in SUPPORTED_VIDEO_SUFFIXES:
        raise ValueError(f"unsupported input type: {input_path.suffix}")

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tiles_dir = out_dir / "tiles"
    tiles_dir.mkdir(exist_ok=True)

    work_source = input_path
    if normalize_canvas:
        # Normalize master to design resolution (512/cell), then encode each crop at tile_px (100 for emoji).
        author_px = DEFAULT_AUTHOR_TILE_PX
        target_w = author_px * cols
        target_h = author_px * rows
        normalized = out_dir / "normalized.mp4"
        from emoji_factory.ffmpeg_util import run_ffmpeg

        run_ffmpeg(
            [
                "-y",
                "-i",
                str(input_path),
                "-vf",
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h},setsar=1",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-an",
                str(normalized),
            ]
        )
        work_source = normalized

    frame_w, frame_h = probe_video_size(work_source)
    rects = compute_tile_rects(
        frame_w=frame_w,
        frame_h=frame_h,
        cols=cols,
        rows=rows,
        margin_pct=margin_pct,
    )

    tile_records: list[dict] = []
    for i, rect in enumerate(rects):
        out_file = tiles_dir / f"{rect.name}.webm"
        size_b, crf_used, loop_used, px_used, _hit = encode_tile_webm_capped(
            source=work_source,
            rect=rect,
            out_path=out_file,
            tile_px=tile_px,
            fps=fps,
            loop_sec=loop_sec,
            crf=crf,
            static=static,
        )
        emoji = _DEFAULT_EMOJI[i % len(_DEFAULT_EMOJI)]
        tile_records.append(
            {
                "file": str(out_file.relative_to(out_dir)),
                "row": rect.row,
                "col": rect.col,
                "emoji": emoji,
                "bytes": size_b,
                "over_soft_limit": size_b > MAX_TILE_BYTES_SOFT,
                "over_telegram_limit": size_b > MAX_TILE_BYTES_TELEGRAM,
                "crf_used": crf_used,
                "loop_sec_used": loop_used,
                "tile_px_used": px_used,
            }
        )

    manifest_path = out_dir / "manifest.json"
    write_manifest(
        manifest_path,
        source=input_path,
        cols=cols,
        rows=rows,
        tiles=tile_records,
        params={
            "tile_px": tile_px,
            "margin_pct": margin_pct,
            "fps": fps,
            "loop_sec": loop_sec,
            "crf": crf,
            "static": static,
            "normalize_canvas": normalize_canvas,
        },
    )
    return manifest_path
