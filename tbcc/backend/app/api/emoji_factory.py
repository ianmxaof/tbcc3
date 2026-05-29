"""Emoji pack factory — prerequisites check + manifest upload (local paths)."""

from __future__ import annotations

from datetime import datetime
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.custom_emoji_preset import CustomEmojiPreset
from app.models.emoji_factory_sketch import EmojiFactorySketchPage
from app.schemas.common import orm_to_dict
from app.services.emoji_factory_jobs import run_create_from_upload
from app.services.emoji_pack_telethon import (
    load_manifest,
    normalize_short_name,
    slug_short_name_base,
    upload_custom_emoji_pack_from_manifest,
)
from app.services.media_frame_sample import ffmpeg_available
from app.services.telegram_admin import friendly_telegram_error, get_telegram_client, import_lock
from app.services.telegram_custom_emoji import validate_telethon_html

router = APIRouter()

SKETCH_BODY_MAX = 32000


class UploadPackBody(BaseModel):
    manifest_path: str = Field(..., min_length=1, description="Absolute path to pack-out/manifest.json on the API host")
    title: str = Field("TBCC emoji pack", min_length=1, max_length=64)
    short_name: str = Field(..., min_length=1, max_length=64)
    dry_run: bool = False


class RunSplitBody(BaseModel):
    input_path: str = Field(..., min_length=1, description="Master MP4/WebM/GIF on API host")
    out_dir: str = Field(..., min_length=1)
    cols: int = Field(4, ge=1, le=10)
    rows: int = Field(4, ge=1, le=10)
    tile_px: int = Field(100, ge=64, le=512)
    margin_pct: float = Field(8.0, ge=0, le=30)
    loop_sec: float = Field(3.0, ge=0.5, le=10)
    crf: int = Field(44, ge=20, le=52)
    static: bool = False


def _emoji_factory_root() -> Path:
    return Path(__file__).resolve().parents[3] / "services" / "emoji-factory"


@router.post("/run-split")
def run_emoji_split(body: RunSplitBody):
    """
    Run emoji_factory split pipeline on the API host (MP4 → VP9 tiles + manifest).
    Blocking; may take minutes for large masters.
    """
    inp = Path(body.input_path.strip()).expanduser()
    out = Path(body.out_dir.strip()).expanduser()
    if not inp.is_file():
        raise HTTPException(status_code=400, detail=f"input not found: {inp}")
    if not ffmpeg_available():
        raise HTTPException(status_code=400, detail="ffmpeg not on PATH")

    root = _emoji_factory_root()
    if not (root / "emoji_factory").is_dir():
        raise HTTPException(status_code=500, detail=f"emoji-factory not found at {root}")

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        from emoji_factory.pipeline import run_pipeline

        manifest = run_pipeline(
            input_path=inp,
            out_dir=out,
            cols=body.cols,
            rows=body.rows,
            tile_px=body.tile_px,
            margin_pct=body.margin_pct,
            loop_sec=body.loop_sec,
            crf=body.crf,
            static=body.static,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    import json

    data = json.loads(manifest.read_text(encoding="utf-8"))
    over = sum(1 for t in data.get("tiles", []) if t.get("over_soft_limit"))
    return {
        "ok": True,
        "manifest_path": str(manifest),
        "out_dir": str(out),
        "tile_count": len(data.get("tiles", [])),
        "over_soft_limit": over,
    }


@router.get("/validate-short-name")
async def validate_pack_short_name(short_name: str):
    """Preview Telegram-normalized pack short name (must start with a letter)."""
    try:
        async with import_lock():
            client = await get_telegram_client()
            me = await client.get_me()
        if me is None:
            raise HTTPException(status_code=400, detail="Telegram session not authorized")
        normalized = normalize_short_name(short_name, user_id=me.id)
        return {
            "ok": True,
            "normalized": normalized,
            "base": slug_short_name_base(short_name),
            "suffix": f"_by_{me.id}",
        }
    except ValueError as e:
        return {"ok": False, "error": str(e), "base": slug_short_name_base(short_name)}


@router.post("/create-from-upload")
async def create_pack_from_upload(
    file: UploadFile = File(..., description="Image (PNG/JPG/WebP) or video (MP4/MOV/WebM/GIF)"),
    cols: int = Form(4, ge=1, le=10),
    rows: int = Form(4, ge=1, le=10),
    tile_px: int = Form(100, ge=64, le=512),
    margin_pct: float = Form(8.0, ge=0, le=30),
    loop_sec: float = Form(3.0, ge=0.5, le=3.0),
    crf: int = Form(44, ge=20, le=52),
    static: bool = Form(False),
    title: str = Form("TBCC emoji pack"),
    short_name: str = Form(""),
    upload_telegram: bool = Form(True),
    dry_run: bool = Form(False),
):
    """
    Upload a local image or video from the dashboard, split into a Telegram custom emoji grid,
    and optionally create the pack on Telegram (admin Telethon session).
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    import tempfile

    suffix = Path(file.filename).suffix.lower() or ".bin"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)
        split_result = run_create_from_upload(
            uploaded_path=tmp_path,
            original_filename=file.filename,
            cols=cols,
            rows=rows,
            tile_px=tile_px,
            margin_pct=margin_pct,
            loop_sec=loop_sec,
            crf=crf,
            static=static,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    manifest_path = Path(split_result["manifest_path"])
    out: dict = {"ok": True, "split": split_result}

    sn = (short_name or split_result.get("suggested_short_name") or "").strip()
    if upload_telegram:
        if not sn:
            raise HTTPException(status_code=400, detail="short_name required for Telegram upload")
        try:
            load_manifest(manifest_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        try:
            async with import_lock():
                client = await get_telegram_client()
                me = await client.get_me()
                if me is None:
                    raise HTTPException(status_code=400, detail="Telegram session not authorized")
                # Fail before uploading tiles to Saved Messages if the pack name is invalid.
                normalize_short_name(sn, user_id=me.id)
                upload_result = await upload_custom_emoji_pack_from_manifest(
                    client,
                    manifest_path=manifest_path,
                    title=title.strip() or "TBCC emoji pack",
                    short_name=sn,
                    dry_run=dry_run,
                )
        except FileNotFoundError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=502, detail=friendly_telegram_error(e)) from e
        out["upload"] = upload_result

    return out


@router.get("/prerequisites")
async def emoji_factory_prerequisites():
    """ffmpeg + Telethon admin session readiness for factory upload."""
    telethon_ok = False
    telethon_error: str | None = None
    try:
        async with import_lock():
            client = await get_telegram_client()
            me = await client.get_me()
            telethon_ok = me is not None
    except Exception as e:
        telethon_error = friendly_telegram_error(e)

    return {
        "ffmpeg": ffmpeg_available(),
        "telethon_session": telethon_ok,
        "telethon_error": telethon_error,
        "docs": {
            "workflow": "tbcc/services/emoji-factory/DESIGN-WORKFLOW.md",
            "cli_encode": "cd tbcc/services/emoji-factory && python -m emoji_factory",
        },
    }


@router.post("/upload-from-manifest")
async def upload_pack_from_manifest(body: UploadPackBody):
    """
    Upload tiles listed in a local manifest.json (paths relative to manifest dir).
    API must run on the same machine as the pack output folder.
    """
    manifest = Path(body.manifest_path.strip()).expanduser()
    if not manifest.is_file():
        raise HTTPException(status_code=400, detail=f"manifest not found: {manifest}")

    try:
        load_manifest(manifest)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        async with import_lock():
            client = await get_telegram_client()
            result = await upload_custom_emoji_pack_from_manifest(
                client,
                manifest_path=manifest,
                title=body.title.strip(),
                short_name=body.short_name.strip(),
                dry_run=body.dry_run,
            )
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=friendly_telegram_error(e)) from e

    return {"ok": True, **result}


class SketchPageOut(BaseModel):
    id: int
    sort_order: int
    title: str | None
    body: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class SketchPageCreate(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    body: str = Field(default="", max_length=SKETCH_BODY_MAX)


class SketchPagePatch(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    body: str | None = Field(default=None, max_length=SKETCH_BODY_MAX)


class SketchSavePresetBody(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    html: str | None = Field(default=None, max_length=SKETCH_BODY_MAX)


def _sketch_pages_ordered(db: Session) -> list[EmojiFactorySketchPage]:
    return (
        db.query(EmojiFactorySketchPage)
        .order_by(EmojiFactorySketchPage.sort_order.asc(), EmojiFactorySketchPage.id.asc())
        .all()
    )


def _next_sketch_sort_order(db: Session) -> int:
    mx = db.query(func.max(EmojiFactorySketchPage.sort_order)).scalar()
    return int(mx or 0) + 1


def _ensure_default_sketch_page(db: Session) -> list[EmojiFactorySketchPage]:
    rows = _sketch_pages_ordered(db)
    if rows:
        return rows
    row = EmojiFactorySketchPage(sort_order=0, title="Page 1", body="")
    db.add(row)
    db.commit()
    db.refresh(row)
    return [row]


@router.get("/sketchbook/pages", response_model=list[SketchPageOut])
def list_sketchbook_pages(db: Session = Depends(get_db)):
    """Paginated design scratchbook — persisted in DB (not browser cache)."""
    rows = _ensure_default_sketch_page(db)
    return [SketchPageOut.model_validate(r) for r in rows]


@router.post("/sketchbook/pages", response_model=SketchPageOut)
def create_sketchbook_page(body: SketchPageCreate, db: Session = Depends(get_db)):
    _ensure_default_sketch_page(db)
    n = len(_sketch_pages_ordered(db)) + 1
    title = (body.title or "").strip() or f"Page {n}"
    row = EmojiFactorySketchPage(
        sort_order=_next_sketch_sort_order(db),
        title=title[:256],
        body=(body.body or "")[:SKETCH_BODY_MAX],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return SketchPageOut.model_validate(row)


@router.patch("/sketchbook/pages/{page_id}", response_model=SketchPageOut)
def patch_sketchbook_page(page_id: int, body: SketchPagePatch, db: Session = Depends(get_db)):
    row = db.query(EmojiFactorySketchPage).filter(EmojiFactorySketchPage.id == page_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Page not found")
    data = body.model_dump(exclude_unset=True)
    if "title" in data:
        t = data["title"]
        row.title = (str(t).strip()[:256] or None) if t is not None else row.title
    if "body" in data and data["body"] is not None:
        row.body = str(data["body"])[:SKETCH_BODY_MAX]
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return SketchPageOut.model_validate(row)


@router.delete("/sketchbook/pages/{page_id}")
def delete_sketchbook_page(page_id: int, db: Session = Depends(get_db)):
    row = db.query(EmojiFactorySketchPage).filter(EmojiFactorySketchPage.id == page_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Page not found")
    db.delete(row)
    db.commit()
    _ensure_default_sketch_page(db)
    return {"deleted": True, "id": page_id}


@router.post("/sketchbook/pages/{page_id}/save-preset")
def sketch_page_save_preset(page_id: int, body: SketchSavePresetBody, db: Session = Depends(get_db)):
    """Save sketch body (or override html) to custom_emoji_presets for Scheduler / relay."""
    row = db.query(EmojiFactorySketchPage).filter(EmojiFactorySketchPage.id == page_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Page not found")
    html = (body.html or row.body or "").strip()
    if not html:
        raise HTTPException(status_code=400, detail="Empty design")
    v = validate_telethon_html(html)
    if not v.get("ok"):
        raise HTTPException(status_code=400, detail=v.get("error") or "Invalid HTML")
    title = (body.title or row.title or "Sketchbook").strip()[:256] or "Sketchbook"
    preset = CustomEmojiPreset(
        title=title,
        html_fragment=html,
        source_note=f"emoji_factory_sketch:{page_id}",
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    d = orm_to_dict(preset)
    d["validation"] = v
    return d
