"""Inject global promo text file and/or image into zip archives."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.services.zip_promo_storage import zip_promo_image_path

logger = logging.getLogger(__name__)

ROW_ID = 1
DEFAULT_TEXT_NAME = "TBCC_README.txt"


def _ensure_settings_row(db: Session):
    from app.models.zip_bundle_settings import ZipBundleSettings

    r = db.query(ZipBundleSettings).filter(ZipBundleSettings.id == ROW_ID).first()
    if r:
        return r
    r = ZipBundleSettings(id=ROW_ID)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def get_effective_zip_promo_settings(db: Session) -> dict:
    """Merged DB row + env defaults (env can enable without dashboard)."""
    import os

    row = _ensure_settings_row(db)
    env_on = os.getenv("TBCC_ZIP_PROMO_ENABLED", "").strip().lower() in ("1", "true", "yes")
    enabled = bool(row.enabled) or env_on
    text_body = (row.text_body or "").strip()
    if not text_body:
        text_body = (os.getenv("TBCC_ZIP_PROMO_TEXT") or "").strip()
    text_name = (row.text_filename or DEFAULT_TEXT_NAME).strip() or DEFAULT_TEXT_NAME
    if "/" in text_name or "\\" in text_name:
        text_name = DEFAULT_TEXT_NAME
    img_fn = (row.image_filename or "").strip() or None
    return {
        "enabled": enabled,
        "include_text_file": bool(row.include_text_file),
        "include_image": bool(row.include_image),
        "text_filename": text_name[:128],
        "text_body": text_body,
        "image_filename": img_fn,
        "has_image_on_disk": bool(img_fn and zip_promo_image_path(img_fn)),
    }


def _collect_injection_payload(settings: dict) -> tuple[dict[str, bytes], list[str]]:
    """Map archive path -> bytes to add. Skips names already handled by caller."""
    out: dict[str, bytes] = {}
    notes: list[str] = []
    if not settings.get("enabled"):
        return out, notes
    if settings.get("include_text_file") and (settings.get("text_body") or "").strip():
        name = settings.get("text_filename") or DEFAULT_TEXT_NAME
        out[name] = (settings["text_body"] + "\n").encode("utf-8")
        notes.append(name)
    if settings.get("include_image") and settings.get("has_image_on_disk"):
        fn = settings.get("image_filename")
        p = zip_promo_image_path(fn)
        if p and fn:
            out[fn] = p.read_bytes()
            notes.append(fn)
    return out, notes


def inject_promo_into_zip_bytes(data: bytes, settings: dict) -> tuple[bytes, list[str]]:
    """Return new zip bytes with promo files added (skip paths that already exist)."""
    to_add, added_names = _collect_injection_payload(settings)
    if not to_add:
        return data, []

    inp = io.BytesIO(data)
    out_io = io.BytesIO()
    injected: list[str] = []
    with zipfile.ZipFile(inp, "r") as zin, zipfile.ZipFile(out_io, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        existing = set(zin.namelist())
        for item in zin.infolist():
            buf = zin.read(item.filename)
            zout.writestr(item, buf)
        for name, payload in to_add.items():
            if name in existing:
                continue
            zout.writestr(name, payload)
            injected.append(name)
    if not injected:
        return data, []
    return out_io.getvalue(), injected


def inject_promo_into_zip_path(path: Path, db: Session, *, include_promo: bool = True) -> dict:
    """Rewrite zip on disk when promo is enabled. Safe no-op if disabled or missing file."""
    path = Path(path)
    if not path.is_file():
        return {"ok": False, "error": "not_found"}
    if not include_promo:
        return {"ok": True, "skipped": True, "reason": "include_promo_false"}
    settings = get_effective_zip_promo_settings(db)
    if not settings.get("enabled"):
        return {"ok": True, "skipped": True, "reason": "disabled"}
    try:
        raw = path.read_bytes()
        new_bytes, injected = inject_promo_into_zip_bytes(raw, settings)
        if not injected:
            return {"ok": True, "injected": [], "note": "already_present_or_empty"}
        path.write_bytes(new_bytes)
        return {"ok": True, "injected": injected}
    except zipfile.BadZipFile as e:
        logger.warning("zip promo inject bad zip %s: %s", path, e)
        return {"ok": False, "error": "bad_zip"}
    except Exception as e:
        logger.exception("zip promo inject failed %s", path)
        return {"ok": False, "error": str(e)}
