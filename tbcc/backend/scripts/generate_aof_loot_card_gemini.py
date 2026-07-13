"""Generate AOF Loot rarity card images via Gemini API.

Run from tbcc/backend:

  py -3.13 scripts/generate_aof_loot_card_gemini.py --list-presets
  py -3.13 scripts/generate_aof_loot_card_gemini.py --tier 7 --preview
  py -3.13 scripts/generate_aof_loot_card_gemini.py --preset tier-10-godroll --execute
  py -3.13 scripts/generate_aof_loot_card_gemini.py --all-tiers --preview

Requires GEMINI_API_KEY in tbcc/.env and: py -m pip install google-genai
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.gemini_loot_card_prompt import (  # noqa: E402
    FORMAT_SPECS,
    build_prompt,
    build_prompt_for_tier,
    list_presets,
    list_scenes,
    resolve_preset,
    tier_scene_id,
)
from app.services.gemini_promo_generate import (  # noqa: E402
    gemini_api_key,
    gemini_image_model,
    generate_image_bytes,
    save_generated_image,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Generate AOF Loot card images via Gemini API")
    p.add_argument("--preset", help="Named preset from aof_loot_card_presets.json")
    p.add_argument("--tier", type=int, help="Tier 1–10 (builds card-1x1 prompt)")
    p.add_argument("--all-tiers", action="store_true", help="Preview or generate tiers 1–10")
    p.add_argument(
        "--format",
        choices=sorted(FORMAT_SPECS.keys()),
        help="Output layout (overrides preset format when both set)",
    )
    p.add_argument("--scenes", help="Comma-separated scene ids, e.g. tier-01,tier-05")
    p.add_argument("--style", default="", help="Optional style line")
    p.add_argument("--prompt-file", type=Path, help="Use raw prompt from file")
    p.add_argument("--aspect", help="Override API aspect ratio (e.g. 1:1)")
    p.add_argument("--out", type=Path, help="Save path (single job only)")
    p.add_argument(
        "--out-dir",
        type=Path,
        help="Directory for multi-tier saves (writes tier-N.png when --all-tiers/--tier)",
    )
    p.add_argument("--slug", default="", help="Filename slug")
    p.add_argument("--preview", action="store_true", help="Print prompt only — no API call")
    p.add_argument("--execute", action="store_true", help="Call Gemini and save image")
    p.add_argument("--list-presets", action="store_true")
    p.add_argument("--list-scenes", action="store_true")
    p.add_argument("--list-formats", action="store_true")
    args = p.parse_args()

    if args.list_presets:
        for name in list_presets():
            print(name)
        return
    if args.list_scenes:
        for sid in list_scenes():
            print(sid)
        return
    if args.list_formats:
        for key, spec in sorted(FORMAT_SPECS.items()):
            print(f"{key}\t{spec['aspect_ratio']}")
        return

    jobs: list[tuple[str, str, str]] = []  # prompt, aspect, slug

    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8")
        aspect = args.aspect or "1:1"
        jobs.append((prompt, aspect, args.slug or "loot-card-raw"))
    elif args.all_tiers:
        for t in range(1, 11):
            prompt, aspect = build_prompt_for_tier(t, format_key=args.format or "card-1x1", style=args.style)
            if args.aspect:
                aspect = args.aspect
            jobs.append((prompt, aspect, args.slug or f"loot-tier-{t:02d}"))
    elif args.tier is not None:
        prompt, aspect = build_prompt_for_tier(
            args.tier, format_key=args.format or "card-1x1", style=args.style
        )
        if args.aspect:
            aspect = args.aspect
        jobs.append((prompt, aspect, args.slug or f"loot-tier-{args.tier:02d}"))
    else:
        fmt = args.format
        scenes: list[str] = []
        style = args.style
        if args.preset:
            p_fmt, p_scenes, p_style = resolve_preset(args.preset)
            fmt = fmt or p_fmt
            scenes = p_scenes
            style = style or p_style
        if args.scenes:
            scenes = [s.strip().lower() for s in args.scenes.split(",") if s.strip()]
        if not fmt or not scenes:
            p.error("Provide --tier, --preset, --all-tiers, or --format + --scenes")
        prompt, aspect = build_prompt(format_key=fmt, scene_ids=scenes, style=style)
        if args.aspect:
            aspect = args.aspect
        slug = args.slug or (args.preset or "-".join(scenes))
        jobs.append((prompt, aspect, slug))

    if args.preview or not args.execute:
        for i, (prompt, aspect, slug) in enumerate(jobs):
            if len(jobs) > 1:
                print(f"\n===== {slug} ({aspect}) =====\n")
            print(prompt)
            if not args.execute and i == 0 and len(jobs) == 1:
                print(f"\n# aspect: {aspect}", file=sys.stderr)
                print(f"# model: {gemini_image_model()}", file=sys.stderr)
        if not args.execute:
            if not args.preview:
                print("\n(pass --execute to call Gemini)", file=sys.stderr)
            return

    if not gemini_api_key():
        print("ERROR: set TBCC_GEMINI_API_KEY (or GEMINI_API_KEY) in tbcc/.env", file=sys.stderr)
        sys.exit(1)

    for prompt, aspect, slug in jobs:
        print(f"Generating {slug} ({aspect}) via {gemini_image_model()}…", file=sys.stderr)
        data = generate_image_bytes(prompt=prompt, aspect_ratio=aspect)
        out_path: Path | None = None
        if args.out is not None and len(jobs) == 1:
            out_path = args.out
        elif args.out_dir is not None:
            # Prefer stable names for key-roll reveal: tier-7.png
            tier_num = None
            if slug.startswith("loot-tier-") and slug[10:].isdigit():
                tier_num = int(slug[10:])
            elif args.tier is not None and len(jobs) == 1:
                tier_num = int(args.tier)
            if tier_num is not None:
                out_path = Path(args.out_dir) / f"tier-{tier_num}.png"
            else:
                out_path = Path(args.out_dir) / f"{slug}.png"
        path = save_generated_image(data, slug=slug, out=out_path)
        print(str(path))


if __name__ == "__main__":
    main()
