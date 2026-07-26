"""
Export Gemini promo + loot prompt builders into Perchance paste packs.

Writes:
  tbcc/userscripts/inbox/perchance/prompt-packs/*.txt
  tbcc/userscripts/packages/perchance-suite/data/jobs.json
  tbcc/userscripts/inbox/perchance/tbcc-aof-gen.modelText.txt  (slim T2I fork)

Usage (from tbcc/backend):
  py -3.13 scripts/export_perchance_prompt_packs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.services import gemini_loot_card_prompt as loot  # noqa: E402
from app.services import gemini_promo_prompt as promo  # noqa: E402

REPO_TBCC = BACKEND.parent
INBOX = REPO_TBCC / "userscripts" / "inbox" / "perchance"
PACKS = INBOX / "prompt-packs"
JOBS_JSON = REPO_TBCC / "userscripts" / "packages" / "perchance-suite" / "data" / "jobs.json"
JOBS_DATA_JS = REPO_TBCC / "userscripts" / "packages" / "perchance-suite" / "data" / "jobs-data.js"
MODEL_TEXT = INBOX / "tbcc-aof-gen.modelText.txt"

DEFAULT_NEGATIVE = (
    "wrong aspect ratio, misspelled text, watermark, random URLs, duplicate identical scenes, "
    "cartoon, childish subjects, low quality, blurry, cropped UI, gibberish HUD overlay covering text"
)

SHAPE_FOR_ASPECT = {
    "9:16": "Portrait = 512x768",
    "1:1": "Square = 512x512",
    "3:4": "Portrait = 512x768",
}


def _safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in s).strip("-") or "job"


def export_promo_jobs() -> list[dict]:
    jobs: list[dict] = []
    for name in promo.list_presets():
        fmt, scenes, style = promo.resolve_preset(name)
        text, aspect = promo.build_prompt(format_key=fmt, scene_ids=scenes, style=style)
        job_id = f"promo-{_safe_name(name)}"
        jobs.append(
            {
                "id": job_id,
                "lane": "promo",
                "label": f"Promo · {name}",
                "preset": name,
                "format": fmt,
                "aspect": aspect,
                "shapeHint": SHAPE_FOR_ASPECT.get(aspect, "Portrait = 512x768"),
                "prompt": text,
                "negative": DEFAULT_NEGATIVE,
            }
        )
        out = PACKS / "promo" / f"{_safe_name(name)}.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            f"# preset={name} format={fmt} aspect={aspect}\n\n{text}\n\n"
            f"# NEGATIVE\n{DEFAULT_NEGATIVE}\n",
            encoding="utf-8",
        )
    # Singles for each scene (dev convenience)
    for sid in promo.list_scenes():
        text, aspect = promo.build_prompt(
            format_key="single-9x16", scene_ids=[sid], style=""
        )
        job_id = f"promo-scene-{_safe_name(sid)}"
        jobs.append(
            {
                "id": job_id,
                "lane": "promo",
                "label": f"Promo scene · {sid}",
                "preset": None,
                "format": "single-9x16",
                "aspect": aspect,
                "shapeHint": SHAPE_FOR_ASPECT.get(aspect, "Portrait = 512x768"),
                "prompt": text,
                "negative": DEFAULT_NEGATIVE,
            }
        )
        out = PACKS / "promo" / f"scene-{_safe_name(sid)}.txt"
        out.write_text(
            f"# scene={sid} format=single-9x16 aspect={aspect}\n\n{text}\n\n"
            f"# NEGATIVE\n{DEFAULT_NEGATIVE}\n",
            encoding="utf-8",
        )
    return jobs


def export_loot_jobs() -> list[dict]:
    jobs: list[dict] = []
    for name in loot.list_presets():
        fmt, scenes, style = loot.resolve_preset(name)
        text, aspect = loot.build_prompt(format_key=fmt, scene_ids=scenes, style=style)
        job_id = f"loot-{_safe_name(name)}"
        jobs.append(
            {
                "id": job_id,
                "lane": "loot",
                "label": f"Loot · {name}",
                "preset": name,
                "format": fmt,
                "aspect": aspect,
                "shapeHint": SHAPE_FOR_ASPECT.get(aspect, "Square = 512x512"),
                "prompt": text,
                "negative": (
                    "minors, childlike subjects, cartoon, cute/wholesome tone, "
                    "QR codes, t.me links, misspelled tier names, softcore-only when explicit requested, "
                    + DEFAULT_NEGATIVE
                ),
            }
        )
        out = PACKS / "loot" / f"{_safe_name(name)}.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            f"# preset={name} format={fmt} aspect={aspect}\n\n{text}\n\n"
            f"# NEGATIVE\n{jobs[-1]['negative']}\n",
            encoding="utf-8",
        )
    for tier in range(1, 11):
        text, aspect = loot.build_prompt_for_tier(tier, format_key="card-1x1")
        sid = loot.tier_scene_id(tier)
        job_id = f"loot-tier-{tier:02d}"
        jobs.append(
            {
                "id": job_id,
                "lane": "loot",
                "label": f"Loot tier {tier} · {sid}",
                "preset": None,
                "format": "card-1x1",
                "aspect": aspect,
                "shapeHint": "Square = 512x512",
                "prompt": text,
                "negative": jobs[0]["negative"] if jobs else DEFAULT_NEGATIVE,
            }
        )
        out = PACKS / "loot" / f"tier-{tier:02d}.txt"
        out.write_text(
            f"# tier={tier} format=card-1x1 aspect={aspect}\n\n{text}\n\n"
            f"# NEGATIVE\n{jobs[-1]['negative']}\n",
            encoding="utf-8",
        )
    return jobs


def write_model_text(jobs: list[dict]) -> None:
    """Slim t2i-framework generator: job select drives prompt/negative."""
    lines: list[str] = [
        "// TBCC AOF generator — Gemini prompt parity (export_perchance_prompt_packs.py)",
        "// Paste into a new/duplicated Perchance generator (t2i-framework-plugin-v2).",
        "// Suggested URL: tbcc-aof-gen (private).",
        "// Prefer perchance-suite job bar for full multiline prompts from jobs.json.",
        "// Gemini CLI remains fallback when layout/QR text fidelity fails.",
        "",
        "background = {import:background-image-plugin}",
        "font = {import:font-plugin}",
        "generateHTML = {import:t2i-framework-plugin-v2}",
        "downloadButton = {import:download-button-plugin}",
        "",
        "title",
        "  TBCC AOF Image Lab",
        "",
        "settings",
        "  pageTitle = Gemini-parity promo + loot cards · $0 Perchance primary",
        "  numImages = [Number(input.numImages)]",
        "  # No forum / public gallery on the generator page (t2i-framework).",
        "  socialFeatures = disabled",
        "  comments = disabled",
        "  gallery = disabled",
        "  # Private lab — do not surface community chrome.",
        "  privateGenerator = true",
        "",
        "  imageOptions",
        "    prompt = [input.artStyle.prompt]",
        "    negativePrompt = [input.artStyle.negative]",
        "    resolution = [input.shape]",
        "    guidanceScale = [input.guidance]",
        "    seed = [input.seed]",
        "",
        "  userInputs",
        "    scratchpad",
        "      label = Notes",
        "      type = textarea",
        "      default = TBCC: capture → gallery → R2 pool or loot_tier_cards. Userscript fills prompts.",
        "",
        "    artStyle",
        "      label = Job (Gemini preset parity)",
        "      type = select",
        "      remember = true",
        "      options",
    ]

    for job in jobs:
        label = job["label"].replace("\n", " ").replace("=", "-")
        p = " ".join(job["prompt"].split())
        n = " ".join(job["negative"].split())
        lines.append(f"        {label}")
        lines.append(f"          prompt = {p}")
        lines.append(f"          negative = {n}")

    lines.extend(
        [
            "",
            "    numImages",
            "      label = How many Pics?",
            "      type = select",
            "      remember = true",
            "      options",
            "        1",
            "        2",
            "        4",
            "        8 = 8",
            "        15 = 15",
            "",
            "    shape",
            "      label = Shape of image(s)",
            "      type = select",
            "      remember = true",
            "      options",
            "        Portrait 512x768 = 512x768",
            "        Square 512x512 = 512x512",
            "        Landscape 768x512 = 768x512",
            "",
            "    guidance",
            "      label = Guidance scale",
            "      type = select",
            "      remember = true",
            "      options",
            "        7",
            "        9",
            "        11",
            "        13",
            "",
            "    seed",
            "      label = Image Seed",
            "      type = text",
            "      default = ",
            "",
        ]
    )

    MODEL_TEXT.parent.mkdir(parents=True, exist_ok=True)
    MODEL_TEXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    PACKS.mkdir(parents=True, exist_ok=True)
    promo_jobs = export_promo_jobs()
    loot_jobs = export_loot_jobs()
    # Prefer unique ids; loot tier exports may duplicate preset tiers — keep both labeled
    all_jobs = promo_jobs + loot_jobs
    # Dedupe by id keeping first
    seen: set[str] = set()
    unique: list[dict] = []
    for j in all_jobs:
        if j["id"] in seen:
            continue
        seen.add(j["id"])
        unique.append(j)

    JOBS_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "source": "export_perchance_prompt_packs.py",
        "geminiFallback": "py -3.13 scripts/generate_aof_promo_gemini.py | generate_aof_loot_card_gemini.py",
        "negativeDefault": DEFAULT_NEGATIVE,
        "jobs": unique,
    }
    JOBS_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    JOBS_DATA_JS.write_text(
        "/* Auto-generated by export_perchance_prompt_packs.py — do not edit */\n"
        "(function (global) {\n"
        "  'use strict';\n"
        "  const PC = (global.__TBCC_US__ = global.__TBCC_US__ || {});\n"
        "  PC.perchance = PC.perchance || {};\n"
        f"  PC.perchance.jobsData = {json.dumps(payload, ensure_ascii=False)};\n"
        "})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);\n",
        encoding="utf-8",
    )
    write_model_text(unique)

    readme = INBOX / "README.md"
    readme.write_text(
        """# Perchance inbox (TBCC)

## Prompt packs

Generated from Gemini builders (source of truth remains backend JSON + layout locks):

```powershell
cd tbcc\\backend
py -3.13 scripts\\export_perchance_prompt_packs.py
```

- `prompt-packs/promo/*.txt` — promo presets + per-scene singles
- `prompt-packs/loot/*.txt` — loot presets + tier-01…10
- `tbcc-aof-gen.modelText.txt` — paste into Perchance edit (fork of t2i-framework)
- `packages/perchance-suite/data/jobs.json` — userscript job bar

## Operator fork

1. Open https://perchance.org/as8aqt61jr (or t2i-framework) → edit → duplicate.
2. Set private URL `tbcc-aof-gen`.
3. Replace lists with `tbcc-aof-gen.modelText.txt` (or keep stock UI and use perchance-suite job bar only).
4. Install `dist/perchance-suite.user.js` via Tampermonkey.

Gemini CLI stays fallback when layout/QR fidelity fails.
""",
        encoding="utf-8",
    )

    print(f"jobs={len(unique)} packs -> {PACKS}")
    print(f"jobs.json -> {JOBS_JSON}")
    print(f"modelText -> {MODEL_TEXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
