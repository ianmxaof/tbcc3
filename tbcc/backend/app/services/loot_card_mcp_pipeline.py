"""Loot God card media bulk export — staging, Gemini, import, production paths."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.services.loot_border_prompt_builder import (
    BorderVariant,
    build_border_animation_prompt,
    border_preview_still_prompt,
    parse_border_variants,
    resolve_border_variant,
)
from app.services.loot_border_reveal import border_clips_dir
from app.services.loot_tier_card_assets import loot_tier_card_dir

FrameBackend = Literal["chroma", "local", "replicate"]


@dataclass(frozen=True)
class LootCardPipelineSpec:
    border_canvas: str = "1024x1024"
    border_duration_s: float = 4.0
    border_fps: int = 24
    magenta_matte: str = "#FF00FF"
    import_size_px: int = 512
    delivery_format: str = "H.264 MP4 yuv420p → borders/open/{stem}.mp4"
    frame_size_px: int = 1024
    center_bands: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["center_bands"] = d["center_bands"] or {
            "low": "centers/low (T1–5)",
            "high": "centers/high (T6–9)",
            "godroll": "centers/godroll (T10)",
        }
        return d


def loot_card_root() -> Path:
    return loot_tier_card_dir()


def staging_root() -> Path:
    return loot_card_root() / "_staging"


def staging_incoming_borders() -> Path:
    return staging_root() / "borders" / "incoming"


def staging_incoming_frames() -> Path:
    return staging_root() / "frames" / "incoming"


def staging_prompts_dir() -> Path:
    return staging_root() / "prompts" / "borders"


def staging_previews_dir() -> Path:
    return staging_root() / "previews" / "borders"


def ensure_staging_dirs() -> dict[str, str]:
    paths = [
        staging_incoming_borders(),
        staging_incoming_frames(),
        staging_prompts_dir(),
        staging_previews_dir(),
    ]
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)
    return {p.name: str(p) for p in paths}


def pipeline_spec() -> LootCardPipelineSpec:
    return LootCardPipelineSpec()


def list_border_variants_summary() -> list[dict[str, Any]]:
    rows = []
    for v in parse_border_variants():
        prod = border_clips_dir() / f"{v.stem}.mp4"
        rows.append(
            {
                "number": v.number,
                "name": v.name,
                "stem": v.stem,
                "production_mp4": str(prod),
                "production_exists": prod.is_file(),
                "prompt_file": str(staging_prompts_dir() / f"{v.stem}.txt"),
            }
        )
    return rows


def write_border_prompt_pack(*, variants: list[str] | None = None) -> dict[str, Any]:
    """Write one .txt prompt per variant for Gemini video export."""
    ensure_staging_dirs()
    out_dir = staging_prompts_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    skipped: list[str] = []
    keys = variants or [v.stem for v in parse_border_variants()]
    for key in keys:
        try:
            v = resolve_border_variant(key)
        except ValueError:
            skipped.append(key)
            continue
        path = out_dir / f"{v.stem}.txt"
        path.write_text(build_border_animation_prompt(v), encoding="utf-8")
        written.append(str(path))
    manifest = {
        "written": written,
        "skipped": skipped,
        "count": len(written),
        "incoming_drop_zone": str(staging_incoming_borders()),
        "note": (
            "Export 4s MP4/WebM from Gemini using each prompt, then name files {stem}.mp4 "
            "and drop in incoming_drop_zone. Run import_border_staging to normalize."
        ),
    }
    (staging_root() / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def generate_gemini_image(
    prompt: str,
    *,
    subfolder: str = "generated",
    filename: str | None = None,
    aspect_ratio: str = "1:1",
    execute: bool = True,
) -> dict[str, Any]:
    from app.services.gemini_promo_generate import generate_image_bytes, save_generated_image

    root = staging_root() / "gemini" / subfolder.strip("/\\")
    root.mkdir(parents=True, exist_ok=True)
    slug = filename or f"asset_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", slug).strip("_")[:80] or "asset"
    out_path = root / f"{slug}.png"
    if not execute:
        return {
            "status": "preview",
            "prompt": prompt[:4000],
            "would_save": str(out_path),
            "aspect_ratio": aspect_ratio,
        }
    data = generate_image_bytes(prompt=prompt, aspect_ratio=aspect_ratio)
    saved = save_generated_image(data, slug=slug, out=out_path)
    return {
        "status": "success",
        "saved_path": str(saved),
        "bytes": len(data),
        "aspect_ratio": aspect_ratio,
    }


def generate_border_preview(variant: str, *, execute: bool = True) -> dict[str, Any]:
    v = resolve_border_variant(variant)
    prompt = border_preview_still_prompt(v)
    ensure_staging_dirs()
    return generate_gemini_image(
        prompt,
        subfolder="previews/borders",
        filename=f"{v.stem}_preview",
        aspect_ratio="1:1",
        execute=execute,
    )


def _run_import_border_script(args: list[str]) -> dict[str, Any]:
    backend = Path(__file__).resolve().parents[1]
    script = backend / "scripts" / "import_loot_border_animations.py"
    cmd = ["py", "-3.13", str(script), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(backend), timeout=600)
    return {
        "ok": proc.returncode == 0,
        "command": " ".join(cmd),
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
        "returncode": proc.returncode,
    }


def import_border_file(
    src: str | Path,
    *,
    size: int = 512,
    trim_s: float | None = 4.0,
    preserve_name: bool = True,
) -> dict[str, Any]:
    src_path = Path(src)
    if not src_path.is_file():
        raise FileNotFoundError(src_path)
    args = ["--src", str(src_path), "--size", str(size), "--out", str(border_clips_dir())]
    if trim_s is not None:
        args.extend(["--trim", str(trim_s)])
    if preserve_name:
        args.append("--preserve-names")
    return _run_import_border_script(args)


def import_border_staging(
    *,
    size: int = 512,
    trim_s: float | None = 4.0,
) -> dict[str, Any]:
    """Import all video files from _staging/borders/incoming → borders/open/."""
    incoming = staging_incoming_borders()
    ensure_staging_dirs()
    files = sorted(
        p for p in incoming.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".webm"} and p.is_file()
    )
    if not files:
        return {
            "status": "empty",
            "incoming": str(incoming),
            "message": "No .mp4/.webm/.mov files in incoming folder.",
        }
    imported: list[dict[str, Any]] = []
    for fp in files:
        result = import_border_file(fp, size=size, trim_s=trim_s, preserve_name=True)
        imported.append({"file": str(fp), **result})
    ok = sum(1 for r in imported if r.get("ok"))
    return {
        "status": "done",
        "incoming": str(incoming),
        "imported_ok": ok,
        "total": len(files),
        "production_dir": str(border_clips_dir()),
        "results": imported,
    }


def _run_rembg_import(args: list[str]) -> dict[str, Any]:
    backend = Path(__file__).resolve().parents[1]
    script = backend / "scripts" / "rembg_import_loot_frames.py"
    cmd = ["py", "-3.13", str(script), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(backend), timeout=900)
    return {
        "ok": proc.returncode == 0,
        "command": " ".join(cmd),
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
        "returncode": proc.returncode,
    }


def import_frame_staging(*, backend: FrameBackend = "chroma") -> dict[str, Any]:
    incoming = staging_incoming_frames()
    ensure_staging_dirs()
    args = ["--src", str(incoming), "--backend", backend]
    result = _run_rembg_import(args)
    result["incoming"] = str(incoming)
    result["staging_out"] = str(loot_card_root() / "frames" / "_rembg")
    return result


def bulk_greenlight_border_set(
    *,
    variants: list[str] | None = None,
    write_prompts: bool = True,
    generate_previews: bool = False,
    import_incoming: bool = True,
    preview_execute: bool = False,
) -> dict[str, Any]:
    """
    One-shot operator flow:
    1. Ensure staging dirs
    2. Write all border animation prompts
    3. Optionally generate Gemini still previews (QA — not the 4s video)
    4. Import any clips already in incoming/
    """
    dirs = ensure_staging_dirs()
    out: dict[str, Any] = {"staging": dirs, "spec": pipeline_spec().to_dict()}
    if write_prompts:
        out["prompts"] = write_border_prompt_pack(variants=variants)
    if generate_previews:
        previews = []
        for v in parse_border_variants():
            if variants and v.stem not in variants and str(v.number) not in variants:
                continue
            previews.append(generate_border_preview(v.stem, execute=preview_execute))
        out["previews"] = previews
    if import_incoming:
        out["import"] = import_border_staging()
    out["variants"] = list_border_variants_summary()
    return out
