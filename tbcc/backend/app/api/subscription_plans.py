import json
import os
import uuid

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.models.subscription_plan import SubscriptionPlan
from app.models.tbcc_tag import TbccTag
from app.services.bundle_parts import (
    append_bundle_filename,
    bundle_parts_for_api,
    delete_all_bundle_part_files,
    delete_bundle_part_at,
    get_bundle_parts,
)
from app.services.bundle_storage import (
    MAX_BUNDLE_PARTS,
    MAX_BUNDLE_ZIP_BYTES,
    bundle_zip_nth_path,
    ensure_bundle_dir,
    is_zip_magic,
)
from app.services.promo_image_convert import normalize_promo_image_bytes
from app.services.promo_storage import MAX_PROMO_IMAGE_BYTES, ensure_promo_dir
from app.utils.promo_url_normalize import normalize_promo_image_url
from app.utils.telegram_promo_url import is_public_https_for_telegram, promo_hint

router = APIRouter()


def _public_base_url() -> str:
    """
    Base URL prepended to /static/promo/... after dashboard upload.

    Set **TBCC_PROMO_PUBLIC_BASE_URL** once to your public https:// host (ngrok, Cloudflare Tunnel,
    production domain) so uploads work without pasting ImgBB URLs. Falls back to TBCC_PUBLIC_BASE_URL
    then TBCC_API_URL (often localhost — not reachable by Telegram).
    """
    return (
        (os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_API_URL") or "").strip()
        or "http://127.0.0.1:8000"
    ).rstrip("/")


MAX_PROMO_IMAGES = 5
MAX_DESC_VARIANTS = 15  # primary description + extras in JSON (total pool size for bot)
ALLOWED_BOT_SECTIONS = {"main", "loot", "packs"}


def _normalize_bot_section(raw: object) -> str:
    s = str(raw or "main").strip().lower()
    if s not in ALLOWED_BOT_SECTIONS:
        return "main"
    return s


def _plan_tag_ids_list(p: SubscriptionPlan) -> list[int]:
    raw = getattr(p, "plan_tag_ids_json", None)
    if not raw:
        return []
    try:
        arr = json.loads(raw)
        if not isinstance(arr, list):
            return []
        out: list[int] = []
        for x in arr:
            try:
                i = int(x)
                if i not in out:
                    out.append(i)
            except (TypeError, ValueError):
                continue
        return out
    except (json.JSONDecodeError, TypeError):
        return []


def _apply_plan_tag_ids(plan: SubscriptionPlan, ids: list[int] | None, db: Session) -> None:
    if ids is None:
        return
    clean: list[int] = []
    for x in ids:
        try:
            i = int(x)
            if i not in clean:
                clean.append(i)
        except (TypeError, ValueError):
            continue
    if not clean:
        plan.plan_tag_ids_json = None
        return
    found = db.query(TbccTag.id).filter(TbccTag.id.in_(clean)).all()
    ok = {row[0] for row in found}
    filtered = [i for i in clean if i in ok]
    plan.plan_tag_ids_json = json.dumps(filtered) if filtered else None


def _attach_tags_to_plan_dicts(db: Session, plans: list[SubscriptionPlan], dicts: list[dict]) -> None:
    all_ids: set[int] = set()
    for p in plans:
        for tid in _plan_tag_ids_list(p):
            all_ids.add(tid)
    if not all_ids:
        for d in dicts:
            d["tag_ids"] = []
            d["tags"] = []
        return
    rows = db.query(TbccTag).filter(TbccTag.id.in_(all_ids)).all()
    id_to_tag = {t.id: t for t in rows}
    for p, d in zip(plans, dicts):
        ids = _plan_tag_ids_list(p)
        d["tag_ids"] = ids
        d["tags"] = []
        for tid in ids:
            t = id_to_tag.get(tid)
            if t:
                d["tags"].append(
                    {"id": t.id, "slug": t.slug, "name": t.name, "category": t.category}
                )


def _extras_list_from_plan(p: SubscriptionPlan) -> list[str]:
    raw = getattr(p, "description_variations_json", None)
    if not raw:
        return []
    try:
        arr = json.loads(raw)
        if not isinstance(arr, list):
            return []
        out: list[str] = []
        for x in arr:
            s = str(x or "").strip()
            if s and s not in out:
                out.append(s)
            if len(out) >= MAX_DESC_VARIANTS:
                break
        return out
    except (json.JSONDecodeError, TypeError):
        return []


def _apply_description_extras(plan: SubscriptionPlan, extras: list[str] | None) -> None:
    if extras is None:
        return
    clean: list[str] = []
    for x in extras:
        s = str(x or "").strip()
        if s and s not in clean:
            clean.append(s)
        if len(clean) >= MAX_DESC_VARIANTS:
            break
    plan.description_variations_json = json.dumps(clean) if clean else None

def _promo_url_or_raise(v: object) -> str | None:
    s = normalize_promo_image_url(str(v or ""))
    s = s or None
    if not s:
        return None
    if len(s) > 1024:
        raise HTTPException(
            status_code=400,
            detail="promo_image_url: single HTTPS URL only, max 1024 characters (no comma-separated lists)",
        )
    return s


def _urls_from_plan_row(p: SubscriptionPlan) -> list[str]:
    """Ordered promo URLs (max 5); JSON column wins, else legacy single column."""
    out: list[str] = []
    raw = getattr(p, "promo_image_urls_json", None)
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                for x in data:
                    u = _promo_url_or_raise(x)
                    if u and u not in out:
                        out.append(u)
                    if len(out) >= MAX_PROMO_IMAGES:
                        break
        except (json.JSONDecodeError, TypeError):
            pass
    if not out and p.promo_image_url:
        u = _promo_url_or_raise(p.promo_image_url)
        if u:
            out.append(u)
    return out[:MAX_PROMO_IMAGES]


def _apply_promo_urls_to_plan(plan: SubscriptionPlan, urls: list[str]) -> None:
    clean: list[str] = []
    for x in urls[:MAX_PROMO_IMAGES]:
        u = _promo_url_or_raise(x)
        if u and u not in clean:
            clean.append(u)
    plan.promo_image_url = clean[0] if clean else None
    plan.promo_image_urls_json = json.dumps(clean) if clean else None


def _parse_promo_from_body(data: dict, *, for_patch: bool) -> list[str] | None:
    """
    If for_patch and neither key present, return None (skip update).
    Otherwise return list (possibly empty) of up to MAX_PROMO_IMAGES URLs.
    """
    has_urls = "promo_image_urls" in data
    has_legacy = "promo_image_url" in data
    if for_patch and not has_urls and not has_legacy:
        return None
    if has_urls:
        raw = data.get("promo_image_urls")
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise HTTPException(
                status_code=400,
                detail="promo_image_urls must be a JSON array of HTTPS URL strings (max 5)",
            )
        out: list[str] = []
        for x in raw:
            u = _promo_url_or_raise(x)
            if u:
                out.append(u)
            if len(out) >= MAX_PROMO_IMAGES:
                break
        return out
    if has_legacy:
        v = data.get("promo_image_url")
        if v is None or str(v).strip() == "":
            return []
        u = _promo_url_or_raise(v)
        return [u] if u else []
    return []


def _plan_dict(p: SubscriptionPlan) -> dict:
    d = orm_to_dict(p)
    d.pop("promo_image_urls_json", None)
    d.pop("bundle_zip_parts_json", None)
    d.pop("description_variations_json", None)
    d.pop("plan_tag_ids_json", None)
    d["description_variations"] = _extras_list_from_plan(p)
    parts = bundle_parts_for_api(p)
    n = len(parts)
    d["bundle_zip_parts"] = parts
    d["bundle_zip_part_count"] = n
    d["bundle_zip_available"] = n > 0
    d["bundle_zip1_available"] = n >= 1
    d["bundle_zip2_available"] = n >= 2
    urls = _urls_from_plan_row(p)
    d["promo_image_urls"] = urls
    d["promo_image_url"] = urls[0] if urls else None
    return d


@router.get("/")
def list_plans(db: Session = Depends(get_db)):
    plans = db.query(SubscriptionPlan).all()
    dicts = [_plan_dict(p) for p in plans]
    _attach_tags_to_plan_dicts(db, plans, dicts)
    return dicts


@router.post("/upload-promo-image")
async def upload_promo_image(file: UploadFile = File(...)):
    """
    Save one image under tbcc/uploads/promo and return a public HTTPS-ready URL path.
    Uploads are normalized server-side (JPEG or PNG, oriented, resized if huge) for Telegram compatibility.
    Telegram's servers must be able to GET this URL — set TBCC_PROMO_PUBLIC_BASE_URL when not on localhost.
    """
    try:
        raw = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read upload: {e}") from e
    if len(raw) > MAX_PROMO_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail=f"Image too large (max {MAX_PROMO_IMAGE_BYTES // (1024 * 1024)} MB)")
    try:
        raw_out, ext = normalize_promo_image_bytes(raw)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read or convert image (use a normal photo file): {e}",
        ) from e
    try:
        root = ensure_promo_dir()
        name = f"{uuid.uuid4().hex}{ext}"
        path = root / name
        path.write_bytes(raw_out)
    except OSError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not write promo file to disk ({e!s}). Check TBCC_PROMO_DIR permissions.",
        ) from e
    base = _public_base_url()
    url = f"{base}/static/promo/{name}"
    if len(url) > 1024:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Generated URL too long; set a shorter TBCC_PROMO_PUBLIC_BASE_URL")
    reachable = is_public_https_for_telegram(url)
    return {
        "url": url,
        "filename": name,
        "telegram_reachable": reachable,
        "telegram_hint": promo_hint(url),
    }


@router.get("/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    p = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    if not p:
        return {"error": "Not found"}
    d = _plan_dict(p)
    _attach_tags_to_plan_dicts(db, [p], [d])
    return d


@router.post("/")
def create_plan(data: dict = Body(...), db: Session = Depends(get_db)):
    ptype = (data.get("product_type") or "subscription").strip().lower()
    if ptype not in ("subscription", "bundle"):
        ptype = "subscription"
    plan = SubscriptionPlan(
        name=data.get("name", "New plan"),
        price_stars=int(data.get("price_stars", 0)),
        duration_days=int(data.get("duration_days", 30)),
        channel_id=data.get("channel_id"),
        description=data.get("description"),
        is_active=bool(data.get("is_active", True)),
        product_type=ptype,
        bot_section=_normalize_bot_section(data.get("bot_section")),
    )
    if "description_variations" in data:
        dv = data.get("description_variations")
        if dv is not None and not isinstance(dv, list):
            raise HTTPException(
                status_code=400,
                detail="description_variations must be a JSON array of strings or null",
            )
        _apply_description_extras(plan, dv if isinstance(dv, list) else [])
    if "tag_ids" in data:
        raw = data.get("tag_ids")
        if raw is not None and not isinstance(raw, list):
            raise HTTPException(status_code=400, detail="tag_ids must be a JSON array of integers or null")
        _apply_plan_tag_ids(plan, raw if isinstance(raw, list) else None, db)
    urls = _parse_promo_from_body(data, for_patch=False)
    _apply_promo_urls_to_plan(plan, urls)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    d = _plan_dict(plan)
    _attach_tags_to_plan_dicts(db, [plan], [d])
    return d


@router.patch("/{plan_id}")
def update_plan(plan_id: int, data: dict = Body(...), db: Session = Depends(get_db)):
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    if not plan:
        return {"error": "Not found"}
    if "name" in data:
        plan.name = data["name"]
    if "price_stars" in data:
        plan.price_stars = int(data["price_stars"])
    if "duration_days" in data:
        plan.duration_days = int(data["duration_days"])
    if "channel_id" in data:
        plan.channel_id = data["channel_id"]
    if "description" in data:
        plan.description = data["description"]
    if "description_variations" in data:
        raw = data.get("description_variations")
        if raw is None:
            plan.description_variations_json = None
        elif isinstance(raw, list):
            _apply_description_extras(plan, raw)
        else:
            raise HTTPException(status_code=400, detail="description_variations must be a JSON array of strings or null")
    if "is_active" in data:
        plan.is_active = bool(data["is_active"])
    if "product_type" in data and data["product_type"]:
        ptype = str(data["product_type"]).strip().lower()
        if ptype in ("subscription", "bundle"):
            old_pt = (plan.product_type or "").lower()
            plan.product_type = ptype
            if ptype == "subscription" and old_pt == "bundle":
                delete_all_bundle_part_files(plan_id)
                plan.bundle_zip_original_name = None
                plan.bundle_zip2_original_name = None
                plan.bundle_zip_parts_json = None
    if "bot_section" in data:
        plan.bot_section = _normalize_bot_section(data.get("bot_section"))
    if "tag_ids" in data:
        raw = data.get("tag_ids")
        if raw is None:
            plan.plan_tag_ids_json = None
        elif isinstance(raw, list):
            _apply_plan_tag_ids(plan, raw, db)
        else:
            raise HTTPException(status_code=400, detail="tag_ids must be a JSON array of integers or null")
    promo_urls = _parse_promo_from_body(data, for_patch=True)
    if promo_urls is not None:
        _apply_promo_urls_to_plan(plan, promo_urls)
    db.commit()
    db.refresh(plan)
    d = _plan_dict(plan)
    _attach_tags_to_plan_dicts(db, [plan], [d])
    return d


@router.post("/{plan_id}/bundle-zip")
async def upload_bundle_zip(plan_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Append a .zip part for digital-pack bundles (split across multiple ~50 MB files)."""
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if (plan.product_type or "").lower() != "bundle":
        raise HTTPException(status_code=400, detail="Only bundle (digital pack) products accept a zip upload")
    existing = get_bundle_parts(plan)
    if len(existing) >= MAX_BUNDLE_PARTS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_BUNDLE_PARTS} zip parts per product",
        )
    slot = len(existing)
    raw = await file.read()
    if len(raw) > MAX_BUNDLE_ZIP_BYTES:
        raise HTTPException(status_code=400, detail="Zip too large (max ~50 MB for Telegram bot delivery)")
    if not is_zip_magic(raw[:512]):
        raise HTTPException(status_code=400, detail="Not a valid zip file")
    ensure_bundle_dir()
    path = bundle_zip_nth_path(plan_id, slot)
    path.write_bytes(raw)
    fn = (file.filename or f"pack_{plan_id}_{slot + 1}.zip").strip()[:500]
    try:
        append_bundle_filename(plan, fn)
    except ValueError as e:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    db.refresh(plan)
    d = _plan_dict(plan)
    _attach_tags_to_plan_dicts(db, [plan], [d])
    return d


@router.delete("/{plan_id}/bundle-zip")
def delete_bundle_zip(
    plan_id: int,
    index: int | None = Query(None, description="0-based part index; omit to remove all parts"),
    db: Session = Depends(get_db),
):
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    if not plan:
        return {"error": "Not found"}
    if index is None:
        delete_all_bundle_part_files(plan_id)
        plan.bundle_zip_original_name = None
        plan.bundle_zip2_original_name = None
        plan.bundle_zip_parts_json = None
    else:
        try:
            delete_bundle_part_at(plan, index)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid part index") from None
    db.commit()
    return {"deleted": plan_id}


@router.delete("/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    if not plan:
        return {"error": "Not found"}
    delete_all_bundle_part_files(plan_id)
    db.delete(plan)
    db.commit()
    return {"deleted": plan_id}
