#!/usr/bin/env python3
"""Re-encode emoji pack tiles to 100×100 VP9 WebM (Telegram custom emoji spec). No API restart needed."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

TBCC_ROOT = Path(__file__).resolve().parents[1]
FACTORY_ROOT = TBCC_ROOT / "services" / "emoji-factory"
JOBS_DIR = TBCC_ROOT / ".tbcc-run" / "emoji-factory-jobs"
TARGET_PX = 100
MAX_BYTES = 240 * 1024


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("ffmpeg not on PATH")
    return exe


def recompress_webm(path: Path, *, crf: int, fps: int = 24) -> int:
    ffmpeg = _ffmpeg()
    tmp = path.with_suffix(".tmp.webm")
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(path),
        "-an",
        "-vf",
        f"scale={TARGET_PX}:{TARGET_PX}:flags=lanczos,fps={fps}",
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuva420p",
        "-b:v",
        "0",
        "-crf",
        str(crf),
        str(tmp),
    ]
    subprocess.run(cmd, check=True)
    tmp.replace(path)
    return path.stat().st_size


def recompress_pack(pack_dir: Path) -> None:
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"No manifest.json in {pack_dir}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    tiles = data.get("tiles") or []
    print(f"Recompressing {len(tiles)} tiles in {pack_dir} -> {TARGET_PX}x{TARGET_PX} ...")
    for tile in tiles:
        rel = tile.get("file") or ""
        p = pack_dir / rel
        if not p.is_file():
            raise SystemExit(f"Missing {p}")
        size = p.stat().st_size
        for crf in (44, 48, 52, 56):
            size = recompress_webm(p, crf=crf)
            if size <= MAX_BYTES:
                break
        tile["bytes"] = size
        tile["tile_px_used"] = TARGET_PX
        tile["over_soft_limit"] = size > MAX_BYTES
        tile["over_telegram_limit"] = size > 256 * 1024
        print(f"  {p.name}: {size // 1024} KB (crf~{crf})")
    params = data.get("params") or {}
    params["tile_px"] = TARGET_PX
    data["params"] = params
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Done. Manifest updated: {manifest_path}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "pack_dir",
        nargs="?",
        help="Path to pack-out folder (default: newest job under .tbcc-run/emoji-factory-jobs)",
    )
    args = p.parse_args()
    if args.pack_dir:
        pack = Path(args.pack_dir).resolve()
    else:
        jobs = sorted(JOBS_DIR.glob("*/pack-out"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not jobs:
            raise SystemExit(f"No jobs in {JOBS_DIR}")
        pack = jobs[0]
        print(f"Using newest job: {pack}")
    recompress_pack(pack)


if __name__ == "__main__":
    main()
