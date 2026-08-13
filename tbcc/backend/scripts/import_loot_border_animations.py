"""
Import + normalize Gemini border animations for loot reveals.

Auto-crops letterboxed magenta gutters to tight chrome bbox, then scales to square.

  cd tbcc/backend
  py -3 scripts/import_loot_border_animations.py --src "C:\\Users\\ianmp\\Downloads"
  py -3 scripts/import_loot_border_animations.py --src clip.mp4 --trim 7.6 --size 512
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.loot_border_plates import card_crop_bbox_for_clip, ffmpeg_chrome_crop_scale_chain
from app.services.loot_border_reveal import border_clips_dir
from app.services.media_frame_sample import ffmpeg_available

DEFAULT_SRC = Path(
    r"C:\Users\ianmp\Downloads\tbcc\AOF NETWORK\AOF RESOURCES (ZIPS)\AOF LOGOS"
    r"\_transparent border_gemini\OPEN & STASIS ANIMATIONS\BORDER OPEN ANIMATIONS"
)


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    return s[:64] or "border"


def _encode(
    src: Path,
    dest: Path,
    *,
    size: int,
    trim_s: float | None,
    start_s: float = 0.0,
    auto_crop: bool = True,
) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    crop_bbox = card_crop_bbox_for_clip(src) if auto_crop else None
    if crop_bbox:
        x0, y0, x1, y1 = crop_bbox
        print(f"  crop chrome {x1 - x0}x{y1 - y0} @ ({x0},{y0})")
    vf = ffmpeg_chrome_crop_scale_chain(crop_bbox, size=size, fps=24)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(start_s),
        "-i",
        str(src),
    ]
    if trim_s is not None and trim_s > 0:
        cmd.extend(["-t", str(trim_s)])
    cmd.extend(
        [
            "-an",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    try:
        subprocess.run(cmd, check=True, timeout=180)
    except Exception as e:
        print(f"FAIL {src.name}: {e}")
        return False
    kb = dest.stat().st_size // 1024
    print(f"OK {dest.name} ({kb} KB)")
    return True


def _import_files(
    files: list[Path],
    out: Path,
    *,
    size: int,
    trim_s: float | None,
    preserve_names: bool,
    auto_crop: bool,
) -> int:
    ok = 0
    for i, fp in enumerate(files, 1):
        if preserve_names:
            dest = out / f"{fp.stem}.mp4"
        else:
            slug = _slug(fp.stem)
            dest = out / f"border-{i:03d}-{slug}.mp4"
        print(fp.name)
        if _encode(fp, dest, size=size, trim_s=trim_s, auto_crop=auto_crop):
            ok += 1
    return ok


def _collect_sources(src: Path) -> list[Path]:
    if src.is_file():
        return [src] if src.suffix.lower() in {".mp4", ".mov", ".webm"} else []
    if not src.is_dir():
        return []
    return sorted(p for p in src.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".webm"})


def main() -> int:
    p = argparse.ArgumentParser(description="Import border animations with auto chrome crop")
    p.add_argument("--src", type=Path, default=DEFAULT_SRC, help="File or folder of clips")
    p.add_argument("--size", type=int, default=512)
    p.add_argument(
        "--trim",
        type=float,
        default=0.0,
        help="Optional max seconds to keep (0 = full clip length)",
    )
    p.add_argument(
        "--no-crop",
        action="store_true",
        help="Disable auto crop-to-chrome (legacy center-crop only)",
    )
    p.add_argument(
        "--preserve-names",
        action="store_true",
        default=True,
        help="Keep source stems (default)",
    )
    p.add_argument(
        "--legacy-names",
        action="store_true",
        help="Use border-001-slug.mp4 naming",
    )
    args = p.parse_args()
    preserve = not args.legacy_names
    trim = args.trim if args.trim and args.trim > 0 else None
    if not ffmpeg_available():
        print("ffmpeg not on PATH")
        return 1

    files = _collect_sources(args.src)
    if not files:
        print(f"No video files under {args.src}")
        return 1

    out = border_clips_dir()
    print(f"clips -> {out}  auto_crop={not args.no_crop}  size={args.size}")
    n = _import_files(
        files,
        out,
        size=args.size,
        trim_s=trim,
        preserve_names=preserve,
        auto_crop=not args.no_crop,
    )
    print(f"Done imported={n}")
    return 0 if n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
