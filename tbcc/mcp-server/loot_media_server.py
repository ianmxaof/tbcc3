#!/usr/bin/env python3
"""
TBCC Loot God media MCP — Gemini image gen + border/frame bulk export pipeline.

Does NOT require TBCC API. Uses tbcc/.env for GEMINI_API_KEY and local asset paths.

Cursor mcp.json:
  "tbcc-loot-media": {
    "command": "py",
    "args": ["-3.13", "C:/.../tbcc/mcp-server/loot_media_server.py"],
    "env": {
      "TBCC_LOOT_TIER_CARD_DIR": "C:/.../tbcc/backend/app/data/loot_tier_cards"
    }
  }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

for _p in (
    Path(__file__).resolve().parent.parent / ".env",
    BACKEND / ".env",
):
    if _p.exists():
        load_dotenv(_p, override=False)
        break

mcp = FastMCP(
    "tbcc-loot-media",
    instructions=(
        "Loot God card asset pipeline: Gemini image generation, magenta-marquee border "
        "animation prompts (25 variants), staging import to borders/open/*.mp4 for Telegram "
        "border reveal mux. Video borders are exported from Gemini manually or dropped in "
        "_staging/borders/incoming — this server writes prompts and runs ffmpeg import. "
        "Requires GEMINI_API_KEY in tbcc/.env for image tools; ffmpeg on PATH for import."
    ),
)


def _pretty(data: Any, *, max_chars: int = 28_000) -> str:
    text = json.dumps(data, indent=2, default=str)
    if len(text) > max_chars:
        return text[: max_chars - 80] + "\n… (truncated)"
    return text


@mcp.tool()
def loot_pipeline_spec() -> str:
    """Output specs: 1024² magenta matte borders, 512px import, staging paths, center bands."""
    from app.services.loot_card_mcp_pipeline import ensure_staging_dirs, pipeline_spec

    return _pretty({"spec": pipeline_spec().to_dict(), "staging": ensure_staging_dirs()})


@mcp.tool()
def loot_list_border_variants() -> str:
    """List 25 border animation variants (stem, production mp4 exists?)."""
    from app.services.loot_card_mcp_pipeline import list_border_variants_summary

    return _pretty(list_border_variants_summary())


@mcp.tool()
def loot_build_border_prompt(variant: str) -> str:
    """
    Build full 4s border animation prompt for Gemini video export.
    variant: stem (brushed_vault_steel), number (01), or name substring.
    """
    from app.services.loot_border_prompt_builder import build_border_animation_prompt, resolve_border_variant

    v = resolve_border_variant(variant)
    return json.dumps(
        {
            "variant": v.stem,
            "name": v.name,
            "production_mp4": f"borders/open/{v.stem}.mp4",
            "prompt": build_border_animation_prompt(v),
        },
        indent=2,
    )


@mcp.tool()
def loot_bulk_write_border_prompts(variants: str = "") -> str:
    """
    Write one prompt .txt per variant to loot_tier_cards/_staging/prompts/borders/.
    variants: comma-separated stems/numbers, or empty for all 25.
    """
    from app.services.loot_card_mcp_pipeline import write_border_prompt_pack

    keys = [s.strip() for s in variants.split(",") if s.strip()] or None
    return _pretty(write_border_prompt_pack(variants=keys))


@mcp.tool()
def loot_generate_gemini_image(
    prompt: str,
    subfolder: str = "generated",
    filename: str = "",
    aspect_ratio: str = "1:1",
    execute: bool = True,
) -> str:
    """
    Generate image via Gemini API (TBCC_GEMINI_API_KEY). Saves under _staging/gemini/{subfolder}/.
    Set execute=false to preview without API call.
    """
    from app.services.loot_card_mcp_pipeline import generate_gemini_image

    return _pretty(
        generate_gemini_image(
            prompt,
            subfolder=subfolder,
            filename=filename or None,
            aspect_ratio=aspect_ratio,
            execute=execute,
        )
    )


@mcp.tool()
def loot_generate_border_preview(variant: str, execute: bool = True) -> str:
    """
    Generate 1024² still preview of a border variant (QA before video export).
    Not a substitute for the 4s animation — use loot_build_border_prompt for video.
    """
    from app.services.loot_card_mcp_pipeline import generate_border_preview

    return _pretty(generate_border_preview(variant, execute=execute))


@mcp.tool()
def loot_generate_tier_center(tier: int, execute: bool = True) -> str:
    """Generate tier center still (card-1x1) via Gemini for centers/ band folders."""
    from app.services.gemini_loot_card_prompt import build_prompt_for_tier
    from app.services.loot_card_mcp_pipeline import generate_gemini_image

    prompt, aspect = build_prompt_for_tier(tier, format_key="card-1x1")
    band = "godroll" if tier >= 10 else ("high" if tier >= 6 else "low")
    return _pretty(
        {
            "tier": tier,
            "band": band,
            "aspect": aspect,
            **generate_gemini_image(
                prompt,
                subfolder=f"centers/{band}",
                filename=f"tier-{tier:02d}",
                aspect_ratio=aspect,
                execute=execute,
            ),
        }
    )


@mcp.tool()
def loot_import_border_file(
    src_path: str,
    size: int = 512,
    trim_seconds: float = 4.0,
    preserve_name: bool = True,
) -> str:
    """
    Import one border clip: magenta crop, scale, H.264 → borders/open/{stem}.mp4.
    src_path: absolute path to .mp4/.webm/.mov from Gemini export.
    """
    from app.services.loot_card_mcp_pipeline import import_border_file

    return _pretty(
        import_border_file(
            src_path,
            size=size,
            trim_s=trim_seconds,
            preserve_name=preserve_name,
        )
    )


@mcp.tool()
def loot_import_border_staging(size: int = 512, trim_seconds: float = 4.0) -> str:
    """
    Bulk import all videos in loot_tier_cards/_staging/borders/incoming/
    → production borders/open/*.mp4 (badge-ready for roll mux).
    """
    from app.services.loot_card_mcp_pipeline import import_border_staging

    return _pretty(import_border_staging(size=size, trim_s=trim_seconds))


@mcp.tool()
def loot_import_frame_staging(backend: str = "chroma") -> str:
    """
    Import frame sheets from _staging/frames/incoming with magenta chroma (preferred) or rembg.
    backend: chroma | local | replicate
    """
    from app.services.loot_card_mcp_pipeline import import_frame_staging

    if backend not in ("chroma", "local", "replicate"):
        raise ValueError("backend must be chroma, local, or replicate")
    return _pretty(import_frame_staging(backend=backend))  # type: ignore[arg-type]


@mcp.tool()
def loot_bulk_greenlight(
    variants: str = "",
    write_prompts: bool = True,
    generate_previews: bool = False,
    import_incoming: bool = True,
    preview_execute: bool = False,
) -> str:
    """
    Operator one-shot: staging dirs + prompt pack + optional previews + import incoming clips.
    variants: comma-separated filter or empty for all 25.
  Drop Gemini exports as {stem}.mp4 in _staging/borders/incoming before import_incoming=true.
    """
    from app.services.loot_card_mcp_pipeline import bulk_greenlight_border_set

    keys = [s.strip() for s in variants.split(",") if s.strip()] or None
    return _pretty(
        bulk_greenlight_border_set(
            variants=keys,
            write_prompts=write_prompts,
            generate_previews=generate_previews,
            import_incoming=import_incoming,
            preview_execute=preview_execute,
        )
    )


if __name__ == "__main__":
    mcp.run()
