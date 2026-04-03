import os
import uuid

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.models.subscription_plan import SubscriptionPlan
from app.services.bundle_storage import (
    MAX_BUNDLE_ZIP_BYTES,
    bundle_zip_path,
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


def _plan_dict(p: SubscriptionPlan) -> dict:
    d = orm_to_dict(p)
    path = bundle_zip_path(p.id)
    d["bundle_zip_available"] = bool(p.bundle_zip_original_name) and path.is_file()
    return d


@router.get("/")
def list_plans(db: Session = Depends(get_db)):
    plans = db.query(SubscriptionPlan).all()
    return [_plan_dict(p) for p in plans]


@router.post("/upload-promo-image")
async def upload_promo_image(file: UploadFile = File(...)):
    """
    Save one image under tbcc/uploads/promo and return a public HTTPS-ready URL path.
    Uploads are normalized server-side (JPEG or PNG, oriented, resized if huge) for Telegram compatibility.
    Telegram's servers must be able to GET this URL — set TBCC_PROMO_PUBLIC_BASE_URL when not on localhost.
    """
    raw = await file.read()
    if len(raw) > MAX_PROMO_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail=f"Image too large (max {MAX_PROMO_IMAGE_BYTES // (1024 * 1024)} MB)")
    try:
        raw_out, ext = normalize_promo_image_bytes(raw)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read or convert image (use a normal photo file): {e}",
        ) from e
    root = ensure_promo_dir()
    name = f"{uuid.uuid4().hex}{ext}"
    path = root / name
    path.write_bytes(raw_out)
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
    return _plan_dict(p)


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
        promo_image_url=_promo_url_or_raise(data.get("promo_image_url")),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _plan_dict(plan)


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
    if "is_active" in data:
        plan.is_active = bool(data["is_active"])
    if "product_type" in data and data["product_type"]:
        ptype = str(data["product_type"]).strip().lower()
        if ptype in ("subscription", "bundle"):
            old_pt = (plan.product_type or "").lower()
            plan.product_type = ptype
            if ptype == "subscription" and old_pt == "bundle":
                zp = bundle_zip_path(plan_id)
                if zp.is_file():
                    zp.unlink()
                plan.bundle_zip_original_name = None
    if "promo_image_url" in data:
        v = data.get("promo_image_url")
        plan.promo_image_url = _promo_url_or_raise(v) if v is not None else None
    db.commit()
    db.refresh(plan)
    return _plan_dict(plan)


@router.post("/{plan_id}/bundle-zip")
async def upload_bundle_zip(plan_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a .zip for digital-pack (bundle) products; delivered via Telegram after Stars payment."""
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if (plan.product_type or "").lower() != "bundle":
        raise HTTPException(status_code=400, detail="Only bundle (digital pack) products accept a zip upload")
    raw = await file.read()
    if len(raw) > MAX_BUNDLE_ZIP_BYTES:
        raise HTTPException(status_code=400, detail="Zip too large (max ~50 MB for Telegram bot delivery)")
    if not is_zip_magic(raw[:512]):
        raise HTTPException(status_code=400, detail="Not a valid zip file")
    ensure_bundle_dir()
    path = bundle_zip_path(plan_id)
    path.write_bytes(raw)
    plan.bundle_zip_original_name = (file.filename or f"pack_{plan_id}.zip").strip()[:500]
    db.commit()
    db.refresh(plan)
    return _plan_dict(plan)


@router.delete("/{plan_id}/bundle-zip")
def delete_bundle_zip(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    if not plan:
        return {"error": "Not found"}
    p = bundle_zip_path(plan_id)
    if p.is_file():
        p.unlink()
    plan.bundle_zip_original_name = None
    db.commit()
    return {"deleted": plan_id}


@router.delete("/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    if not plan:
        return {"error": "Not found"}
    zp = bundle_zip_path(plan_id)
    if zp.is_file():
        zp.unlink()
    db.delete(plan)
    db.commit()
    return {"deleted": plan_id}
