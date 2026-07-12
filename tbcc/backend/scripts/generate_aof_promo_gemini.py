"""Generate AOF MEGA PACKS promo images via Gemini API (Nano Banana).

Run from tbcc/backend:

  py -3.13 scripts/generate_aof_promo_gemini.py --list-presets
  py -3.13 scripts/generate_aof_promo_gemini.py --preset martyrs-ma07-10 --preview
  py -3.13 scripts/generate_aof_promo_gemini.py --preset martyrs-ma07-10 --execute
  py -3.13 scripts/generate_aof_promo_gemini.py --format grid-2x2-9x16 --scenes ma-07,ma-08,ma-09,ma-10 --execute --upload

Requires TBCC_GEMINI_API_KEY (or GEMINI_API_KEY) in tbcc/.env and: py -m pip install google-genai
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
    output_dir,
    save_generated_image,
)
from app.services.gemini_promo_prompt import (  # noqa: E402
    FORMAT_SPECS,
    build_prompt,
    list_presets,
    list_scenes,
    resolve_preset,
)
from app.services.r2_promo_upload import append_pool_entries, upload_promo_image  # noqa: E402


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Generate AOF promo images via Gemini API")
    p.add_argument("--preset", help="Named preset from aof_promo_scene_presets.json")
    p.add_argument(
        "--format",
        choices=sorted(FORMAT_SPECS.keys()),
        help="Output layout (overrides preset format when both set)",
    )
    p.add_argument("--scenes", help="Comma-separated scene ids, e.g. ma-07,ma-08,ma-09,ma-10")
    p.add_argument("--style", default="", help="Optional style line appended to prompt")
    p.add_argument("--prompt-file", type=Path, help="Use raw prompt from file instead of builder")
    p.add_argument("--aspect", help="Override API aspect ratio (e.g. 9:16)")
    p.add_argument("--out", type=Path, help="Save path (default: assets/promo-generated/)")
    p.add_argument("--slug", default="", help="Filename slug for saved image")
    p.add_argument("--preview", action="store_true", help="Print prompt only — no API call")
    p.add_argument("--execute", action="store_true", help="Call Gemini and save image")
    p.add_argument("--upload", action="store_true", help="After save, upload to R2/ImgBB + append pool JSON")
    p.add_argument("--upload-provider", choices=("auto", "r2", "imgbb"), default="auto")
    p.add_argument("--label", default="", help="Pool label when using --upload")
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

    fmt = args.format
    scene_ids: list[str] = []
    style = args.style

    if args.preset:
        p_fmt, p_scenes, p_style = resolve_preset(args.preset)
        fmt = fmt or p_fmt
        scene_ids = p_scenes if not args.scenes else [s.strip().lower() for s in args.scenes.split(",") if s.strip()]
        if not style and p_style:
            style = p_style
        slug = args.slug or args.preset
    elif args.scenes:
        scene_ids = [s.strip().lower() for s in args.scenes.split(",") if s.strip()]
        slug = args.slug or "-".join(scene_ids[:4])
    else:
        slug = args.slug or "aof-promo"

    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8").strip()
        aspect = args.aspect or "9:16"
    else:
        if not fmt:
            print("ERROR: pass --preset or --format", file=sys.stderr)
            sys.exit(1)
        if not scene_ids:
            print("ERROR: pass --scenes or a preset with scenes", file=sys.stderr)
            sys.exit(1)
        prompt, aspect = build_prompt(format_key=fmt, scene_ids=scene_ids, style=style)
        if args.aspect:
            aspect = args.aspect

    if args.preview or not args.execute:
        if not args.preview and not args.execute:
            print("Pass --preview or --execute", file=sys.stderr)
            sys.exit(1)
        print(f"# model: {gemini_image_model()}")
        print(f"# aspect_ratio: {aspect}")
        print(f"# output_dir: {output_dir()}")
        print("---")
        print(prompt)
        return

    if not gemini_api_key():
        print("ERROR: set TBCC_GEMINI_API_KEY (or GEMINI_API_KEY) in tbcc/.env", file=sys.stderr)
        sys.exit(1)

    print(f"Generating ({aspect}) via {gemini_image_model()}…", file=sys.stderr)
    data = generate_image_bytes(prompt=prompt, aspect_ratio=aspect)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        saved = args.out
        saved.write_bytes(data)
        print(f"Saved {saved} ({len(data)} bytes)", file=sys.stderr)
    else:
        saved = save_generated_image(data, slug=slug)
        print(f"Saved {saved}", file=sys.stderr)

    if args.upload:
        label = args.label or saved.stem
        result = upload_promo_image(saved, provider=args.upload_provider)
        entry: dict[str, str] = {"label": label, "direct_url": result["direct_url"]}
        if result.get("viewer_url"):
            entry["viewer_url"] = result["viewer_url"]
        append_pool_entries([entry])
        print(f"Pool +1: {entry['direct_url']}", file=sys.stderr)


if __name__ == "__main__":
    main()
