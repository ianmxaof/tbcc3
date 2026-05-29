"""Crop + VP9 WebM encode per tile."""

from __future__ import annotations

import json
from pathlib import Path

from emoji_factory.ffmpeg_util import run_ffmpeg
from emoji_factory.grid import TileRect
from emoji_factory.spec import (
    DEFAULT_CRF,
    DEFAULT_FPS,
    DEFAULT_LOOP_SEC,
    DEFAULT_TILE_PX,
    MAX_TILE_BYTES_TARGET,
    MAX_TILE_BYTES_TELEGRAM,
)


def encode_tile_webm(
    *,
    source: Path,
    rect: TileRect,
    out_path: Path,
    tile_px: int = DEFAULT_TILE_PX,
    fps: int = DEFAULT_FPS,
    loop_sec: float = DEFAULT_LOOP_SEC,
    crf: int = DEFAULT_CRF,
    static: bool = False,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    crop = f"crop={rect.w}:{rect.h}:{rect.x}:{rect.y}"
    scale = f"scale={tile_px}:{tile_px}:flags=lanczos"
    if static:
        vf = f"{crop},{scale}"
        run_ffmpeg(
            [
                "-y",
                "-i",
                str(source),
                "-vf",
                vf,
                "-frames:v",
                "1",
                "-c:v",
                "libvpx-vp9",
                "-pix_fmt",
                "yuva420p",
                "-b:v",
                "0",
                "-crf",
                str(crf),
                "-an",
                str(out_path),
            ]
        )
    else:
        vf = f"{crop},{scale},fps={fps}"
        run_ffmpeg(
            [
                "-y",
                "-i",
                str(source),
                "-t",
                str(max(0.5, loop_sec)),
                "-vf",
                vf,
                "-c:v",
                "libvpx-vp9",
                "-pix_fmt",
                "yuva420p",
                "-b:v",
                "0",
                "-crf",
                str(crf),
                "-an",
                str(out_path),
            ]
        )
    return out_path


def encode_tile_webm_capped(
    *,
    source: Path,
    rect: TileRect,
    out_path: Path,
    tile_px: int = DEFAULT_TILE_PX,
    fps: int = DEFAULT_FPS,
    loop_sec: float = DEFAULT_LOOP_SEC,
    crf: int = DEFAULT_CRF,
    static: bool = False,
) -> tuple[int, int, float, int, bool]:
    """
    Encode a tile and re-compress until under Telegram's 256 KB cap.
    Returns (bytes, crf_used, loop_sec_used, tile_px_used, hit_target).
    """
    loop_sec = float(loop_sec)
    crf_floor = max(20, crf - 4)
    attempts: list[tuple[int, float, int]] = [(tile_px, loop_sec, crf)]
    for try_crf in range(crf + 4, 53, 4):
        attempts.append((tile_px, loop_sec, try_crf))
    if not static:
        for loop_try in (min(loop_sec, 2.0), 1.5, 1.0):
            if loop_try < loop_sec - 0.01:
                for try_crf in range(max(44, crf_floor), 53, 4):
                    attempts.append((tile_px, loop_try, try_crf))
    for px in (384, 256):
        if px < tile_px:
            for try_crf in range(44, 53, 4):
                attempts.append((px, min(loop_sec, 2.0) if not static else loop_sec, try_crf))

    seen: set[tuple[int, float, int]] = set()
    last_size = 0
    last_crf, last_loop, last_px = crf, loop_sec, tile_px
    for px, loop_use, try_crf in attempts:
        key = (px, round(loop_use, 2), try_crf)
        if key in seen:
            continue
        seen.add(key)
        encode_tile_webm(
            source=source,
            rect=rect,
            out_path=out_path,
            tile_px=px,
            fps=fps,
            loop_sec=loop_use,
            crf=try_crf,
            static=static,
        )
        last_size = out_path.stat().st_size
        last_crf, last_loop, last_px = try_crf, loop_use, px
        if last_size <= MAX_TILE_BYTES_TARGET:
            return last_size, try_crf, loop_use, px, True

    if last_size > MAX_TILE_BYTES_TELEGRAM:
        raise RuntimeError(
            f"{out_path.name}: {last_size / 1024:.0f} KB still exceeds Telegram's 256 KB limit "
            "after compression. Use simpler motion, a shorter loop, or a smaller grid."
        )
    return last_size, last_crf, last_loop, last_px, False


def write_manifest(
    path: Path,
    *,
    source: Path,
    cols: int,
    rows: int,
    tiles: list[dict],
    params: dict,
) -> None:
    payload = {
        "source": str(source.resolve()),
        "cols": cols,
        "rows": rows,
        "params": params,
        "tiles": tiles,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
