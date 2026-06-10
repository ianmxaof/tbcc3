import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.scheduled_text_post import ScheduledTextPost
from app.models.subscription_plan import SubscriptionPlan
from app.services.pool_cleanup import cascade_delete_pool
from app.services.telegram_admin import get_telegram_client
from app.utils.telegram_peer import normalize_telethon_peer_identifier, resolve_poster_peer
from telethon import functions

logger = logging.getLogger(__name__)


class ChannelPinBody(BaseModel):
    """Pin or unpin a message in the channel/supergroup (Telegram message id from that chat)."""

    message_id: int
    unpin: bool = False

router = APIRouter()


async def _resolve_channel_entity(client, ch: Channel):
    """
    Resolve Channel.identifier for Telethon (admin.session).

    Numeric -100… ids fail until the account has joined the chat; use invite_link fallback.
    """
    return await resolve_poster_peer(
        client,
        ch.identifier,
        invite_fallback=getattr(ch, "invite_link", None),
    )


async def _telegram_client_for_channel_ops():
    """Poster session first (same account that sends scheduled/relay posts)."""
    try:
        from app.workers.poster_worker import _get_poster_client

        return await _get_poster_client()
    except Exception as poster_err:
        logger.warning("forum/channel ops: poster client unavailable (%s), trying admin", poster_err)
        return await get_telegram_client()


class ChannelCreate(BaseModel):
    name: str
    identifier: str
    invite_link: str | None = None


class ChannelRotateInviteBody(BaseModel):
    """
    Create a fresh Telegram invite with optional join-request gate and limits.
    """

    request_needed: bool = True
    usage_limit: int | None = None
    expire_hours: int | None = None
    title: str | None = None
    revoke_previous: bool = True


@router.get("/")
def list_channels(db: Session = Depends(get_db)):
    return [orm_to_dict(c) for c in db.query(Channel).all()]


@router.get("/{channel_id}/forum-topics")
async def list_channel_forum_topics(channel_id: int, db: Session = Depends(get_db)):
    """
    List forum topics for a supergroup (e.g. AOF). Topic `id` is what you pass as message_thread_id when posting.
    """
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        return {"topics": [], "error": "Channel not found"}
    try:
        client = await _telegram_client_for_channel_ops()
    except Exception as e:
        logger.warning("forum-topics: no telegram client: %s", e)
        return {"topics": [], "error": str(e)}
    try:
        entity = await _resolve_channel_entity(client, ch)
        resp = await client(
            functions.messages.GetForumTopicsRequest(
                peer=entity,
                offset_date=None,
                offset_id=0,
                offset_topic=0,
                limit=200,
                q=None,
            )
        )
    except Exception as e:
        logger.info("GetForumTopics failed channel_id=%s: %s", channel_id, e)
        return {"topics": [], "error": f"Could not load forum topics (forum-enabled group only): {e}"}

    raw = getattr(resp, "topics", None) or []
    topics: list[dict] = []
    seen: set[int] = set()
    for t in raw:
        d = t.to_dict() if hasattr(t, "to_dict") else {}
        tid = d.get("id")
        if tid is None:
            continue
        tid = int(tid)
        if tid in seen:
            continue
        seen.add(tid)
        title = d.get("title", "")
        if isinstance(title, dict):
            title = title.get("text") or ""
        topics.append({"id": tid, "title": str(title).strip() or f"Topic {tid}"})
    return {"topics": topics, "error": None}


@router.post("/{channel_id}/pin-message")
async def pin_channel_message(channel_id: int, body: ChannelPinBody, db: Session = Depends(get_db)):
    """
    Pin a post by numeric Telegram message id (visible in message links or client “Copy link”).
    Requires the admin session to have pin rights in that chat. Use unpin=true to remove that pin.
    """
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    try:
        client = await _telegram_client_for_channel_ops()
    except Exception as e:
        logger.warning("pin-message: no telegram client: %s", e)
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        entity = await _resolve_channel_entity(client, ch)
        if body.unpin:
            await client(
                functions.messages.UpdatePinnedMessageRequest(
                    peer=entity,
                    id=body.message_id,
                    unpin=True,
                    silent=True,
                )
            )
        else:
            await client.pin_message(entity, body.message_id, notify=False)
    except Exception as e:
        logger.info("pin-message failed channel_id=%s: %s", channel_id, e)
        return {"ok": False, "error": str(e)}
    return {"ok": True, "error": None}


@router.post("/{channel_id}/rotate-invite")
async def rotate_channel_invite(
    channel_id: int,
    body: ChannelRotateInviteBody = Body(default=ChannelRotateInviteBody()),
    db: Session = Depends(get_db),
):
    """
    Programmatically rotate a channel invite link.

    Supports join-request links (`request_needed=true`), usage limits, and expiry windows.
    Saves the new link to channels.invite_link.
    """
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    try:
        client = await _telegram_client_for_channel_ops()
    except Exception as e:
        logger.warning("rotate-invite: no telegram client: %s", e)
        raise HTTPException(status_code=503, detail=str(e)) from e

    peer = normalize_telethon_peer_identifier(ch.identifier)
    usage_limit = body.usage_limit
    if usage_limit is not None and usage_limit <= 0:
        usage_limit = None
    expire_at = None
    if body.expire_hours is not None and body.expire_hours > 0:
        expire_at = datetime.now(timezone.utc) + timedelta(hours=int(body.expire_hours))
    title = (body.title or "").strip() or None

    try:
        entity = await _resolve_channel_entity(client, ch)
    except Exception as e:
        logger.info("rotate-invite: cannot resolve entity channel_id=%s peer=%s: %s", channel_id, peer, e)
        return {"ok": False, "error": f"Cannot resolve channel identifier: {e}"}

    old_link = (ch.invite_link or "").strip() or None
    try:
        invite = await client(
            functions.messages.ExportChatInviteRequest(
                peer=entity,
                legacy=False,
                request_needed=bool(body.request_needed),
                usage_limit=usage_limit,
                expire_date=expire_at,
                title=title,
            )
        )
    except TypeError:
        # Telethon/API compatibility fallback (older signatures may not expose all kwargs).
        invite = await client(
            functions.messages.ExportChatInviteRequest(
                peer=entity,
                legacy=False,
                usage_limit=usage_limit,
                expire_date=expire_at,
                title=title,
            )
        )
    except Exception as e:
        logger.info("rotate-invite failed channel_id=%s peer=%s: %s", channel_id, peer, e)
        return {"ok": False, "error": str(e)}

    new_link = str(getattr(invite, "link", "") or "").strip()
    if not new_link:
        return {"ok": False, "error": "Telegram returned no invite link"}

    # Best effort revoke of previous exported invite (if present and different).
    revoked_previous = False
    revoke_error = None
    if body.revoke_previous and old_link and old_link != new_link:
        try:
            await client(
                functions.messages.EditExportedChatInviteRequest(
                    peer=entity,
                    link=old_link,
                    revoked=True,
                )
            )
            revoked_previous = True
        except Exception as e:
            # Non-fatal: keep new invite even if old could not be revoked (e.g. old wasn't exported by this admin).
            revoke_error = str(e)

    ch.invite_link = new_link
    db.commit()
    db.refresh(ch)
    return {
        "ok": True,
        "channel_id": channel_id,
        "identifier_used": peer,
        "invite_link": new_link,
        "request_needed": bool(body.request_needed),
        "usage_limit": usage_limit,
        "expire_hours": body.expire_hours,
        "title": title,
        "old_invite_link": old_link,
        "revoked_previous": revoked_previous,
        "revoke_error": revoke_error,
    }


@router.get("/{channel_id}")
def get_channel(channel_id: int, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        return {"error": "Not found"}
    return orm_to_dict(ch)


@router.post("/", status_code=201)
def create_channel(body: ChannelCreate, db: Session = Depends(get_db)):
    ch = Channel(name=body.name, identifier=body.identifier, invite_link=body.invite_link)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return orm_to_dict(ch)


@router.patch("/{channel_id}")
def update_channel(channel_id: int, data: dict = Body(...), db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        return {"error": "Not found"}
    if "name" in data:
        ch.name = data["name"]
    if "identifier" in data:
        ch.identifier = data["identifier"]
    if "invite_link" in data:
        ch.invite_link = data["invite_link"] or None
    if "webhook_url" in data:
        w = data.get("webhook_url")
        ch.webhook_url = (str(w).strip()[:1024]) if w else None
    db.commit()
    db.refresh(ch)
    return orm_to_dict(ch)


@router.delete("/{channel_id}")
def delete_channel(channel_id: int, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    pool_rows = db.query(ContentPool).filter(ContentPool.channel_id == channel_id).all()
    removed_pool_ids: list[int] = []
    for p in pool_rows:
        pid = int(p.id)
        if cascade_delete_pool(db, pid):
            removed_pool_ids.append(pid)
    db.query(ScheduledTextPost).filter(ScheduledTextPost.channel_id == channel_id).delete(
        synchronize_session=False
    )
    db.query(SubscriptionPlan).filter(SubscriptionPlan.channel_id == channel_id).update(
        {SubscriptionPlan.channel_id: None}, synchronize_session=False
    )
    db.delete(ch)
    db.commit()
    return {"deleted": channel_id, "pools_removed": removed_pool_ids}
