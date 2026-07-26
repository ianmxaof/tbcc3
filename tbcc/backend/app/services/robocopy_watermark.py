"""Robocopy watermark fan-out: master → promo heavy / lane light / vault clean.

Maps ``WatermarkTier`` to ``WatermarkApplyConfig``. Size ratio is env-based
(``TBCC_WATERMARK_SIZE_RATIO``); opacity + texts + position differentiate tiers.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.data.aof_telegram_links import AOF_LOOTGOD_BOT_SHORT, AOF_MAINHUB_SHORT, AOF_WATERMARK_DEFAULT
from app.data.loot_lane_economy import WatermarkTier
from app.services.local_media_watermark import scan_media_folder, watermark_paths
from app.services.media_watermark import WatermarkApplyConfig, watermark_text

logger = logging.getLogger(__name__)

# Relative size knobs while processing a tier (media_watermark reads env).
_TIER_SIZE_RATIO: dict[WatermarkTier, str] = {
    WatermarkTier.PROMO_HEAVY: "0.055",
    WatermarkTier.LANE_LIGHT: "0.024",
    WatermarkTier.VAULT_CLEAN: "0.024",
}


def _brand_primary() -> str:
    raw = (os.getenv("TBCC_WATERMARK_TEXT") or "").strip()
    if raw:
        return raw
    try:
        return watermark_text() or AOF_WATERMARK_DEFAULT
    except Exception:
        return AOF_WATERMARK_DEFAULT


def _brand_secondary() -> str:
    return (os.getenv("TBCC_WATERMARK_TEXT_SECONDARY") or AOF_LOOTGOD_BOT_SHORT).strip() or AOF_MAINHUB_SHORT


def apply_config_for_tier(tier: WatermarkTier) -> WatermarkApplyConfig:
    """Build a WatermarkApplyConfig for robocopy fan-out."""
    primary = _brand_primary()
    secondary = _brand_secondary()
    if tier == WatermarkTier.VAULT_CLEAN:
        return WatermarkApplyConfig(enabled=False, texts=(), skip=True)
    if tier == WatermarkTier.PROMO_HEAVY:
        texts = tuple(t for t in (primary, secondary, "AOF · PROMO") if t)
        return WatermarkApplyConfig(
            enabled=True,
            texts=texts,
            opacity=0.72,
            color_hex="#FFFFFF",
            mode="rotate",
            position="bottom_right",
            strip_previous=False,
            skip=False,
        )
    # LANE_LIGHT
    texts = tuple(t for t in (primary, secondary) if t)
    return WatermarkApplyConfig(
        enabled=True,
        texts=texts or (primary,),
        opacity=0.38,
        color_hex="#FFFFFF",
        mode="fixed",
        position="bottom_right",
        strip_previous=False,
        skip=False,
    )


@dataclass(frozen=True)
class RobocopyDirs:
    promo: Path
    lane: Path
    vault: Path


def ensure_robocopy_dirs(out_root: Path | str) -> RobocopyDirs:
    root = Path(out_root).expanduser().resolve()
    dirs = RobocopyDirs(
        promo=root / "promo_heavy",
        lane=root / "lane_light",
        vault=root / "vault_clean",
    )
    for d in (dirs.promo, dirs.lane, dirs.vault):
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def _with_size_ratio(tier: WatermarkTier):
    """Temporarily set TBCC_WATERMARK_SIZE_RATIO for the tier."""
    key = "TBCC_WATERMARK_SIZE_RATIO"
    prev = os.environ.get(key)
    os.environ[key] = _TIER_SIZE_RATIO[tier]

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev

    return _Ctx()


def fan_out_master_folder(
    master_dir: Path | str,
    out_root: Path | str,
    *,
    recursive: bool = True,
    max_files: int | None = None,
    max_video_mb: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scan master folder; write promo / lane / vault variants under out_root."""
    master = Path(master_dir).expanduser().resolve()
    dirs = ensure_robocopy_dirs(out_root)
    scan = scan_media_folder(master, recursive=recursive, max_files=max_files)
    paths = list(scan.files)
    report: dict[str, Any] = {
        "ok": True,
        "master": str(master),
        "out_root": str(Path(out_root).expanduser().resolve()),
        "files": len(paths),
        "dry_run": dry_run,
        "tiers": {},
    }
    if not paths:
        report["ok"] = False
        report["reason"] = "no_media"
        report["skipped"] = scan.skipped
        return report

    # Vault: byte-copy (no watermark)
    vault_ok = vault_skip = 0
    for src in paths:
        dest = dirs.vault / src.name
        if dry_run:
            vault_ok += 1
            continue
        try:
            shutil.copy2(src, dest)
            vault_ok += 1
        except OSError as e:
            logger.warning("vault copy failed %s: %s", src, e)
            vault_skip += 1
    report["tiers"][WatermarkTier.VAULT_CLEAN.value] = {
        "dir": str(dirs.vault),
        "copied": vault_ok,
        "failed": vault_skip,
        "config": "skip",
    }

    for tier, out_dir in (
        (WatermarkTier.PROMO_HEAVY, dirs.promo),
        (WatermarkTier.LANE_LIGHT, dirs.lane),
    ):
        cfg = apply_config_for_tier(tier)
        if dry_run:
            report["tiers"][tier.value] = {
                "dir": str(out_dir),
                "planned": len(paths),
                "opacity": cfg.opacity,
                "texts": list(cfg.texts),
                "size_ratio": _TIER_SIZE_RATIO[tier],
            }
            continue
        with _with_size_ratio(tier):
            batch = watermark_paths(
                paths,
                config=cfg,
                output_dir=out_dir,
                max_video_mb=max_video_mb,
            )
        ok = sum(1 for r in batch.results if r.ok)
        report["tiers"][tier.value] = {
            "dir": str(out_dir),
            "ok": ok,
            "failed": len(batch.results) - ok,
            "opacity": cfg.opacity,
            "texts": list(cfg.texts),
            "size_ratio": _TIER_SIZE_RATIO[tier],
        }
    return report
