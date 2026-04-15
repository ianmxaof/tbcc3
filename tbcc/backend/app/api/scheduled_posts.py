import json
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.models.scheduled_text_post import ScheduledTextPost
from app.models.channel import Channel
from app.workers.poster_worker import post_scheduled_text

router = APIRouter()


def _normalize_variations(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for x in raw:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


def _normalize_attachment_urls(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for x in raw:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out[:10]


def _normalize_album_variants(raw: list | None) -> list[dict]:
    if not raw or not isinstance(raw, list):
        return []
    out: list[dict] = []
    for x in raw:
        if isinstance(x, dict):
            out.append(ScheduledTextPost._normalize_album_variant_entry(x))
    return out


def _has_media_or_promo(body) -> bool:
    av = _normalize_album_variants(getattr(body, "album_variants", None))
    for v in av:
        if v.get("media_ids") or v.get("attachment_urls"):
            return True
    att = _normalize_attachment_urls(getattr(body, "attachment_urls", None))
    if att:
        return True
    mids = getattr(body, "media_ids", None)
    if mids:
        return True
    if getattr(body, "pool_id", None):
        return True
    return False


def scheduled_post_to_api_dict(post: ScheduledTextPost) -> dict:
    """JSON-serializable dict with parsed content_variations, attachment_urls, album_variants."""
    d = orm_to_dict(post)
    d.pop("attachment_urls_json", None)
    d.pop("album_variants_json", None)
    d["content_variations"] = post.get_content_variations()
    d["attachment_urls"] = post.get_attachment_urls()
    d["album_variants"] = post.get_album_variants()
    d["album_order_mode"] = post.album_order_mode or "static"
    raw_btn = d.get("buttons")
    if isinstance(raw_btn, str) and raw_btn.strip():
        try:
            parsed = json.loads(raw_btn)
            d["buttons"] = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            d["buttons"] = []
    elif isinstance(raw_btn, list):
        d["buttons"] = raw_btn
    else:
        d["buttons"] = []
    return d


def _patch_scheduled_post_core(
    post: ScheduledTextPost,
    body: ScheduledPostUpdate,
    fs: set,
    *,
    allow_channel_id: bool = True,
) -> None:
    if body.name is not None:
        post.name = body.name
    if allow_channel_id and body.channel_id is not None:
        post.channel_id = body.channel_id
    if "message_thread_id" in fs:
        post.message_thread_id = body.message_thread_id

    if "content_variations" in fs:
        nv = _normalize_variations(body.content_variations)
        if len(nv) >= 2:
            post.content_variations = json.dumps(nv)
            post.content = nv[0]
            post.caption_rotation_index = None
        elif len(nv) == 1:
            post.content_variations = None
            post.content = nv[0]
            post.caption_rotation_index = None
        else:
            post.content_variations = None
            post.caption_rotation_index = None

    if body.content is not None:
        if "content_variations" not in fs:
            post.content = body.content
        else:
            nv2 = _normalize_variations(body.content_variations)
            if len(nv2) < 2:
                post.content = body.content

    # Schedule mode: allow explicit null to clear one-time vs recurring (see model_fields_set).
    if "scheduled_at" in fs:
        post.scheduled_at = body.scheduled_at
    if "interval_minutes" in fs:
        post.interval_minutes = body.interval_minutes
    # Keep modes mutually exclusive when switching.
    if "interval_minutes" in fs and body.interval_minutes is not None:
        post.scheduled_at = None
    if "scheduled_at" in fs and body.scheduled_at is not None:
        post.interval_minutes = None
    if hasattr(body, "media_ids") and body.media_ids is not None:
        post.media_ids = json.dumps(body.media_ids)
    if hasattr(body, "pool_id"):
        post.pool_id = body.pool_id
    if hasattr(body, "buttons") and body.buttons is not None:
        post.buttons = json.dumps(body.buttons)
    if "album_size" in fs:
        v = body.album_size
        post.album_size = min(10, max(1, int(v))) if v is not None else None
    if "pool_randomize" in fs:
        post.pool_randomize = body.pool_randomize
    if "pool_only_mode" in fs:
        post.pool_only_mode = bool(body.pool_only_mode) if post.pool_id else False
    if "album_variants" in fs:
        av = _normalize_album_variants(body.album_variants)
        post.album_variants_json = json.dumps(av) if av else None
        if av:
            post.attachment_urls_json = None
    elif "attachment_urls" in fs:
        au = _normalize_attachment_urls(body.attachment_urls)
        post.attachment_urls_json = json.dumps(au) if au else None
    if "album_order_mode" in fs:
        m = (body.album_order_mode or "").strip().lower()
        if m not in ("static", "shuffle", "carousel", ""):
            raise HTTPException(400, "album_order_mode must be static, shuffle, or carousel")
        post.album_order_mode = m if m else None
    if "send_silent" in fs:
        post.send_silent = bool(body.send_silent)
    if "pin_after_send" in fs:
        post.pin_after_send = bool(body.pin_after_send)


class ScheduledPostCreate(BaseModel):
    name: str | None = None
    channel_id: int | None = None
    channel_ids: list[int] | None = Field(
        default=None,
        description="Multiple channels: creates one scheduled row per id with the same payload; ignores channel_id.",
    )
    message_thread_id: int | None = None  # forum topic; applied to every row in a multi-channel create
    content: str = ""
    scheduled_at: datetime | None = Field(default=None, description="Required for one-time; omit for recurring")
    interval_minutes: int | None = Field(default=None, description="Required for recurring")
    media_ids: list[int] | None = None
    pool_id: int | None = None
    buttons: list[dict] | None = None
    # When pool_id is set: per-job album size / randomize (overrides pool defaults if set)
    album_size: int | None = None
    pool_randomize: bool | None = None
    pool_only_mode: bool | None = None
    # 2+ non-empty strings: captions rotate in order each time the job runs (e.g. hourly A, B, A, …)
    content_variations: list[str] | None = None
    # Dashboard promo uploads (/static/promo/…) — same store as Bot Shop; used when pool/media_ids yield no media
    attachment_urls: list[str] | None = None
    # Per-caption album variants (aligned with rotating captions via index % len); overrides flat attachment_urls when set
    album_variants: list[dict] | None = None
    album_order_mode: str | None = None  # static | shuffle | carousel
    send_silent: bool | None = None
    pin_after_send: bool | None = None


class ScheduledPostUpdate(BaseModel):
    name: str | None = None
    channel_id: int | None = None
    message_thread_id: int | None = None
    content: str | None = None
    scheduled_at: datetime | None = None
    interval_minutes: int | None = None
    media_ids: list[int] | None = None
    pool_id: int | None = None
    buttons: list[dict] | None = None
    album_size: int | None = None
    pool_randomize: bool | None = None
    pool_only_mode: bool | None = None
    content_variations: list[str] | None = None
    attachment_urls: list[str] | None = None
    album_variants: list[dict] | None = None
    album_order_mode: str | None = None
    send_silent: bool | None = None
    pin_after_send: bool | None = None


def _resolve_create_channel_ids(body: ScheduledPostCreate) -> list[int]:
    raw = body.channel_ids
    if raw:
        out = sorted({int(x) for x in raw if x is not None})
        if not out:
            raise HTTPException(400, "channel_ids must contain at least one channel id")
        return out
    if body.channel_id is not None:
        return [int(body.channel_id)]
    raise HTTPException(400, "channel_id or channel_ids required")


@router.get("/")
def list_scheduled_posts(db: Session = Depends(get_db)):
    posts = db.query(ScheduledTextPost).order_by(ScheduledTextPost.scheduled_at).all()
    result = []
    for p in posts:
        d = scheduled_post_to_api_dict(p)
        channel = db.query(Channel).filter(Channel.id == p.channel_id).first()
        d["channel_name"] = channel.name or channel.identifier if channel else None
        result.append(d)
    return result


@router.post("/", status_code=201)
def create_scheduled_post(body: ScheduledPostCreate, db: Session = Depends(get_db)):
    if body.interval_minutes is None and body.scheduled_at is None:
        raise HTTPException(400, "Either scheduled_at (one-time) or interval_minutes (recurring) required")
    vars_norm = _normalize_variations(body.content_variations)
    if len(vars_norm) >= 2:
        content_val = vars_norm[0]
        variations_json = json.dumps(vars_norm)
    elif len(vars_norm) == 1:
        content_val = vars_norm[0]
        variations_json = None
    else:
        content_val = (body.content or "").strip()
        variations_json = None

    if not content_val and not _has_media_or_promo(body):
        raise HTTPException(
            400,
            "Provide caption text, at least two caption variations, media/pool, promotional URLs, or album variants",
        )

    asize = body.album_size
    if asize is not None:
        asize = min(10, max(1, int(asize)))
    av_norm = _normalize_album_variants(body.album_variants)
    att_urls = _normalize_attachment_urls(body.attachment_urls)
    mode = (body.album_order_mode or "").strip().lower()
    if mode not in ("static", "shuffle", "carousel", ""):
        raise HTTPException(400, "album_order_mode must be static, shuffle, or carousel")
    order_mode = mode if mode else None
    try:
        ch_ids = _resolve_create_channel_ids(body)
        for cid in ch_ids:
            c = db.query(Channel).filter(Channel.id == cid).first()
            if not c:
                raise HTTPException(400, f"Channel id {cid} not found")
        campaign_group_id = str(uuid.uuid4()) if len(ch_ids) > 1 else None
        created: list[ScheduledTextPost] = []
        for cid in ch_ids:
            post = ScheduledTextPost(
                name=body.name,
                channel_id=cid,
                campaign_group_id=campaign_group_id,
                message_thread_id=body.message_thread_id,
                content=content_val,
                scheduled_at=body.scheduled_at,
                interval_minutes=body.interval_minutes,
                media_ids=json.dumps(body.media_ids) if body.media_ids else None,
                pool_id=body.pool_id if body.pool_id else None,
                buttons=json.dumps(body.buttons) if body.buttons else None,
                album_size=asize,
                pool_randomize=body.pool_randomize,
                pool_only_mode=bool(body.pool_only_mode) if body.pool_id else False,
                content_variations=variations_json,
                caption_rotation_index=None,
                attachment_urls_json=None if av_norm else (json.dumps(att_urls) if att_urls else None),
                album_variants_json=json.dumps(av_norm) if av_norm else None,
                album_order_mode=order_mode,
                album_carousel_index=None,
                send_silent=bool(body.send_silent),
                pin_after_send=bool(body.pin_after_send),
            )
            db.add(post)
            created.append(post)
        db.commit()
        result_posts = []
        for p in created:
            db.refresh(p)
            d = scheduled_post_to_api_dict(p)
            ch = db.query(Channel).filter(Channel.id == p.channel_id).first()
            d["channel_name"] = ch.name or ch.identifier if ch else None
            result_posts.append(d)
        return {"posts": result_posts, "campaign_group_id": campaign_group_id}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"{type(e).__name__}: {str(e)}")


@router.patch("/campaign/{campaign_group_id}")
def update_scheduled_campaign(campaign_group_id: str, body: ScheduledPostUpdate, db: Session = Depends(get_db)):
    rows = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.campaign_group_id == campaign_group_id)
        .order_by(ScheduledTextPost.id)
        .all()
    )
    if not rows:
        return {"error": "Campaign not found"}
    for p in rows:
        if p.interval_minutes is None and p.sent_at:
            return {"error": "Cannot edit campaign: already sent"}
    fs = getattr(body, "model_fields_set", None) or getattr(body, "__fields_set__", None) or set()
    for p in rows:
        _patch_scheduled_post_core(p, body, fs, allow_channel_id=False)
    db.commit()
    result_posts = []
    for p in rows:
        db.refresh(p)
        d = scheduled_post_to_api_dict(p)
        ch = db.query(Channel).filter(Channel.id == p.channel_id).first()
        d["channel_name"] = ch.name or ch.identifier if ch else None
        result_posts.append(d)
    return {"posts": result_posts, "campaign_group_id": campaign_group_id}


@router.delete("/campaign/{campaign_group_id}")
def delete_scheduled_campaign(campaign_group_id: str, db: Session = Depends(get_db)):
    n = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.campaign_group_id == campaign_group_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    if not n:
        return {"error": "Campaign not found"}
    return {"deleted": n, "campaign_group_id": campaign_group_id}


@router.post("/campaign/{campaign_group_id}/trigger")
def trigger_scheduled_campaign(
    campaign_group_id: str,
    db: Session = Depends(get_db),
    reshuffle: bool = Query(
        False,
        description="Randomize album/promo order for this send only; allows reposting one-time jobs that already ran.",
    ),
):
    rows = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.campaign_group_id == campaign_group_id)
        .order_by(ScheduledTextPost.id)
        .all()
    )
    if not rows:
        return {"error": "Campaign not found"}
    leader = rows[0]
    is_recurring = leader.interval_minutes is not None
    if not is_recurring and leader.sent_at and not reshuffle:
        return {"error": "Post already sent"}
    for p in rows:
        ch = db.query(Channel).filter(Channel.id == p.channel_id).first()
        if not ch:
            return {"error": "Channel not found"}
    if is_recurring:
        now = datetime.utcnow()
        for p in rows:
            p.last_posted_at = now
        db.commit()
    post_scheduled_text.delay(leader.id, reshuffle_album=reshuffle)
    return {
        "status": "scheduled",
        "post_id": leader.id,
        "campaign_group_id": campaign_group_id,
        "reshuffle": reshuffle,
    }


@router.patch("/{post_id}")
def update_scheduled_post(post_id: int, body: ScheduledPostUpdate, db: Session = Depends(get_db)):
    post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == post_id).first()
    if not post:
        return {"error": "Not found"}
    if post.interval_minutes is None and post.sent_at:
        return {"error": "Cannot edit already sent post"}
    fs = getattr(body, "model_fields_set", None) or getattr(body, "__fields_set__", None) or set()
    cg = getattr(post, "campaign_group_id", None)
    if cg:
        rows = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.campaign_group_id == cg)
            .order_by(ScheduledTextPost.id)
            .all()
        )
        for p in rows:
            if p.interval_minutes is None and p.sent_at:
                return {"error": "Cannot edit campaign: already sent"}
        for p in rows:
            _patch_scheduled_post_core(p, body, fs, allow_channel_id=False)
        db.commit()
        result_posts = []
        for p in rows:
            db.refresh(p)
            d = scheduled_post_to_api_dict(p)
            ch = db.query(Channel).filter(Channel.id == p.channel_id).first()
            d["channel_name"] = ch.name or ch.identifier if ch else None
            result_posts.append(d)
        return {"posts": result_posts, "campaign_group_id": cg}
    _patch_scheduled_post_core(post, body, fs, allow_channel_id=True)
    db.commit()
    db.refresh(post)
    d = scheduled_post_to_api_dict(post)
    ch = db.query(Channel).filter(Channel.id == post.channel_id).first()
    d["channel_name"] = ch.name or ch.identifier if ch else None
    return d


@router.delete("/{post_id}")
def delete_scheduled_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == post_id).first()
    if not post:
        return {"error": "Not found"}
    cg = getattr(post, "campaign_group_id", None)
    if cg:
        db.query(ScheduledTextPost).filter(ScheduledTextPost.campaign_group_id == cg).delete(
            synchronize_session=False
        )
        db.commit()
        return {"deleted_campaign": cg}
    db.delete(post)
    db.commit()
    return {"deleted": post_id}


@router.post("/{post_id}/trigger")
def trigger_scheduled_post(
    post_id: int,
    db: Session = Depends(get_db),
    reshuffle: bool = Query(
        False,
        description="Randomize album/promo order for this send only; allows reposting one-time jobs that already ran.",
    ),
):
    post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == post_id).first()
    if not post:
        return {"error": "Not found"}
    is_recurring = post.interval_minutes is not None
    if not is_recurring and post.sent_at and not reshuffle:
        return {"error": "Post already sent"}
    cg = getattr(post, "campaign_group_id", None)
    rows = [post]
    leader_id = post_id
    if cg:
        rows = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.campaign_group_id == cg)
            .order_by(ScheduledTextPost.id)
            .all()
        )
        leader_id = rows[0].id
    for p in rows:
        ch = db.query(Channel).filter(Channel.id == p.channel_id).first()
        if not ch:
            return {"error": "Channel not found"}
    if is_recurring:
        now = datetime.utcnow()
        for p in rows:
            p.last_posted_at = now
        db.commit()
    post_scheduled_text.delay(leader_id, reshuffle_album=reshuffle)
    return {"status": "scheduled", "post_id": leader_id, "campaign_group_id": cg, "reshuffle": reshuffle}
