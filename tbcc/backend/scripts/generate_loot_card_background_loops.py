"""
Generate placeholder loot card background loops (procedural ffmpeg lavfi).

Replace with authored art later — same filenames, drop into backgrounds/.

  cd tbcc/backend
  py -3.13 scripts/generate_loot_card_background_loops.py
  py -3.13 scripts/generate_loot_card_background_loops.py --size 720
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.loot_reveal_video import backgrounds_dir
from app.services.media_frame_sample import ffmpeg_available

LOOPS: list[tuple[str, str]] = [
    (
        "loop-pulse-grid.mp4",
        "color=c=0x08080a:s={size}x{size}:d={dur},format=rgb24,"
        "geq=r='r(X,Y)+8*sin(2*PI*X/32+T*3)':g='g(X,Y)+4*sin(2*PI*Y/24+T*2)':b='b(X,Y)+12*sin(T*4)'",
    ),
    (
        "loop-neon-blue.mp4",
        "color=c=0x050818:s={size}x{size}:d={dur},format=rgb24,"
        "geq=r='20+40*sin(T*2+Y/40)':g='40+60*sin(T*1.5+X/50)':b='120+80*sin(T*3)'",
    ),
    (
        "loop-acid-green.mp4",
        "color=c=0x040a06:s={size}x{size}:d={dur},format=rgb24,"
        "geq=r='10+20*sin(T+X/30)':g='80+100*sin(T*2.5+Y/35)':b='20+30*sin(T*1.2)'",
    ),
    (
        "loop-copper-sparks.mp4",
        "color=c=0x0a0604:s={size}x{size}:d={dur},format=rgb24,"
        "geq=r='60+90*sin(T*4+hypot(X-{cx},Y-{cy})/20)':g='30+50*sin(T*3)':b='10+20*sin(T)'",
    ),
    (
        "loop-violet-data.mp4",
        "color=c=0x0c0414:s={size}x{size}:d={dur},format=rgb24,"
        "geq=r='40+50*sin(T*2+X/18)':g='15+25*sin(T*1.8)':b='90+110*sin(T*2.2+Y/22)'",
    ),
]


def _render(name: str, lavfi: str, *, size: int, dur: float, out_dir: Path) -> bool:
    out = out_dir / name
    cx = cy = size // 2
    filt = lavfi.format(size=size, dur=dur, cx=cx, cy=cy)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        filt,
        "-t",
        str(dur),
        "-vf",
        f"fps=24,scale={size}:{size}",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "26",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, timeout=120)
    except Exception as e:
        print(f"FAIL {name}: {e}")
        return False
    print(f"OK {out} ({out.stat().st_size // 1024} KB)")
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Generate 5 loot card background MP4 loops")
    p.add_argument("--size", type=int, default=512)
    p.add_argument("--duration", type=float, default=4.0)
    args = p.parse_args()
    if not ffmpeg_available():
        print("ffmpeg not on PATH — install ffmpeg first.")
        return 1
    out_dir = backgrounds_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = sum(1 for name, lavfi in LOOPS if _render(name, lavfi, size=args.size, dur=args.duration, out_dir=out_dir))
    print(f"Wrote {ok}/{len(LOOPS)} loops -> {out_dir}")
    return 0 if ok == len(LOOPS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
