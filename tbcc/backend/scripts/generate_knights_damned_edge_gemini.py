"""Generate Knights of the Damned Edge images via Gemini API.

Run from tbcc/backend:

  py -3.13 scripts/generate_knights_damned_edge_gemini.py --list
  py -3.13 scripts/generate_knights_damned_edge_gemini.py --scene 01 --preview
  py -3.13 scripts/generate_knights_damned_edge_gemini.py --scene 01,02,03 --execute
  py -3.13 scripts/generate_knights_damned_edge_gemini.py --scene all --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.gemini_promo_generate import (  # noqa: E402
    gemini_api_key,
    gemini_image_model,
    generate_image_bytes,
    save_generated_image,
)

ROOT = Path(__file__).resolve().parents[2] / "docs" / "samples" / "knights_damned_edge"
OUT_CINEMATIC = Path(__file__).resolve().parents[2] / "assets" / "promo-generated" / "knights-damned-edge"
OUT_PROMO = OUT_CINEMATIC / "aof-composite"

CINEMATIC_SCENES: dict[str, str] = {
    "01": "01_round_table_underpass.txt",
    "02": "02_the_fetch_quest.txt",
    "03": "03_locked_sanctum.txt",
    "04": "04_fever_oath.txt",
    "05": "05_bridge_oracle.txt",
    "06": "06_filmstrip_5x.txt",
}

PROMO_SCENES: dict[str, str] = {
    "01": "01_sunroom_static.txt",
    "02": "02_tea_party_overhead.txt",
    "03": "03_manic_breach.txt",
    "04": "04_porta_sanctum_wide.txt",
    "05": "05_walker_worm_eye.txt",
    "06": "06_couch_glow_trays.txt",
    "07": "07_underpass_round_table.txt",
    "08": "08_grid_2x2.txt",
}


def _load_prompt(scene: str, *, promo: bool) -> str:
    scenes = PROMO_SCENES if promo else CINEMATIC_SCENES
    samples = ROOT / ("promo" if promo else "")
    fname = scenes.get(scene)
    if not fname:
        raise SystemExit(f"Unknown scene {scene!r}. Use: {', '.join(scenes)}")
    path = samples / fname
    if not path.exists():
        raise SystemExit(f"Missing prompt file: {path}")
    if promo:
        layout = (samples / "LAYOUT_LOCK.txt").read_text(encoding="utf-8").strip()
        body = path.read_text(encoding="utf-8").strip()
        if "LAYOUT LOCK" not in body.upper():
            return f"{layout}\n\n---\n\n{body}"
        return body
    style = (ROOT / "STYLE_LOCK.txt").read_text(encoding="utf-8").strip()
    body = path.read_text(encoding="utf-8").strip()
    return f"{style}\n\n---\n\n{body}"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Generate Knights of the Damned Edge via Gemini")
    p.add_argument("--scene", default="", help="Scene id(s): 01,02 or all")
    p.add_argument(
        "--promo",
        action="store_true",
        help="AOF MEGA PACKS composite overlay promos (docs/samples/knights_damned_edge/promo/)",
    )
    p.add_argument("--aspect", default="9:16", help="API aspect ratio")
    p.add_argument("--preview", action="store_true", help="Print prompt only")
    p.add_argument("--execute", action="store_true", help="Call Gemini and save")
    p.add_argument("--list", action="store_true", help="List scene ids")
    args = p.parse_args()

    scenes = PROMO_SCENES if args.promo else CINEMATIC_SCENES
    out_root = OUT_PROMO if args.promo else OUT_CINEMATIC
    prefix = "kode-promo" if args.promo else "kode"

    if args.list:
        mode = "promo" if args.promo else "cinematic"
        print(f"# mode: {mode}")
        for sid, fname in scenes.items():
            print(f"{sid}\t{fname}")
        return

    if not args.scene:
        p.error("pass --scene or --list")

    keys = list(scenes.keys()) if args.scene.strip().lower() == "all" else [
        s.strip().zfill(2) if s.strip().isdigit() else s.strip()
        for s in args.scene.split(",")
        if s.strip()
    ]

    if args.preview or not args.execute:
        if not args.preview:
            p.error("pass --preview or --execute")
        for sid in keys:
            prompt = _load_prompt(sid, promo=args.promo)
            print(f"# scene: {sid} ({'promo' if args.promo else 'cinematic'})")
            print(f"# model: {gemini_image_model()}")
            print(f"# aspect: {args.aspect}")
            print("---")
            print(prompt[:8000])
            if len(prompt) > 8000:
                print("… (truncated)")
            print("\n")
        return

    if not gemini_api_key():
        print("ERROR: TBCC_GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    out_root.mkdir(parents=True, exist_ok=True)
    for sid in keys:
        prompt = _load_prompt(sid, promo=args.promo)
        slug = f"{prefix}-{sid}"
        print(f"Generating {slug} …", flush=True)
        data = generate_image_bytes(prompt=prompt, aspect_ratio=args.aspect)
        out = save_generated_image(data, slug=slug, out=out_root / f"{slug}.png")
        print(f"  saved {out} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
