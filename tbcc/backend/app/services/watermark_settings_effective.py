"""Effective promo watermark settings: tbcc/.env + dashboard row + per-request overrides."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from app.models.watermark_settings import WatermarkSettings
from app.schemas.watermark_options import WatermarkOptions
from app.services import media_watermark as wm

ROW_ID = 1


def _ensure_row(db: Session) -> WatermarkSettings:
    row = db.query(WatermarkSettings).filter(WatermarkSettings.id == ROW_ID).first()
    if row is None:
        row = WatermarkSettings(id=ROW_ID)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _env_enabled() -> bool:
    if (os.getenv("TBCC_WATERMARK_ENABLED") or "").strip().lower() in ("0", "false", "no", "off"):
        return False
    return bool((wm.watermark_text() or "").strip())


def _row_texts(row: WatermarkSettings | None) -> tuple[str, str, str]:
    primary = (row.text_primary or "").strip() if row else ""
    secondary = (row.text_secondary or "").strip() if row else ""
    tertiary = (row.text_tertiary or "").strip() if row else ""
    if not primary:
        primary = wm.watermark_text()
    env2 = (os.getenv("TBCC_WATERMARK_TEXT_SECONDARY") or "").strip()
    env3 = (os.getenv("TBCC_WATERMARK_TEXT_TERTIARY") or "").strip()
    if not secondary and env2:
        secondary = env2
    if not tertiary and env3:
        tertiary = env3
    return primary[:120], secondary[:120], tertiary[:120]


def get_effective_watermark_settings(db: Session | None = None) -> dict[str, Any]:
    row = _ensure_row(db) if db is not None else None
    primary, secondary, tertiary = _row_texts(row)
    enabled = _env_enabled()
    if row is not None and row.enabled is not None:
        enabled = bool(row.enabled) and bool(primary or secondary or tertiary)

    opacity = wm.watermark_opacity()
    if row is not None and row.opacity is not None:
        opacity = max(0.15, min(1.0, float(row.opacity)))

    color = (os.getenv("TBCC_WATERMARK_COLOR") or "#FFFFFF").strip()
    if row is not None and (row.color or "").strip():
        color = (row.color or "").strip()

    strip_previous = (os.getenv("TBCC_WATERMARK_STRIP_PREVIOUS") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if row is not None and row.strip_previous is not None:
        strip_previous = bool(row.strip_previous)

    texts = [t for t in (primary, secondary, tertiary) if t]
    return {
        "enabled": enabled and bool(texts),
        "text": primary,
        "text_secondary": secondary,
        "text_tertiary": tertiary,
        "texts": texts,
        "mode": wm.watermark_mode(),
        "position": wm.watermark_fixed_position(),
        "opacity": opacity,
        "color": color,
        "strip_previous": strip_previous,
        "apply_on_saved_import": bool(row.apply_on_saved_import) if row else False,
        "apply_on_album_composer": bool(row.apply_on_album_composer) if row else True,
    }


def build_apply_config(
    db: Session | None = None,
    *,
    override: WatermarkOptions | dict[str, Any] | None = None,
) -> wm.WatermarkApplyConfig:
    base = get_effective_watermark_settings(db)
    opts = override
    if isinstance(opts, dict):
        opts = WatermarkOptions.model_validate(opts)
    if opts is not None:
        if opts.skip:
            return wm.WatermarkApplyConfig(enabled=False, skip=True)
        if opts.enabled is not None:
            base["enabled"] = bool(opts.enabled)
        if opts.text is not None:
            base["text"] = (opts.text or "").strip()[:120]
        if opts.text_secondary is not None:
            base["text_secondary"] = (opts.text_secondary or "").strip()[:120]
        if opts.text_tertiary is not None:
            base["text_tertiary"] = (opts.text_tertiary or "").strip()[:120]
        texts = [t for t in (base["text"], base["text_secondary"], base["text_tertiary"]) if t]
        base["texts"] = texts
        base["enabled"] = base["enabled"] and bool(texts)
        if opts.opacity is not None:
            base["opacity"] = max(0.15, min(1.0, float(opts.opacity)))
        if opts.color is not None and (opts.color or "").strip():
            base["color"] = (opts.color or "").strip()
        if opts.strip_previous is not None:
            base["strip_previous"] = bool(opts.strip_previous)

    return wm.WatermarkApplyConfig(
        enabled=bool(base.get("enabled")),
        texts=tuple(base.get("texts") or ()),
        opacity=float(base.get("opacity") or 0.58),
        color_hex=str(base.get("color") or "#FFFFFF"),
        mode=str(base.get("mode") or "rotate"),
        position=base.get("position") or "bottom_right",
        strip_previous=bool(base.get("strip_previous", False)),
        skip=False,
    )


def row_to_dict(row: WatermarkSettings) -> dict[str, Any]:
    return {
        "enabled": row.enabled,
        "text_primary": row.text_primary,
        "text_secondary": row.text_secondary,
        "text_tertiary": row.text_tertiary,
        "opacity": row.opacity,
        "color": row.color,
        "strip_previous": row.strip_previous,
        "apply_on_saved_import": row.apply_on_saved_import,
        "apply_on_album_composer": row.apply_on_album_composer,
    }
