import logging

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.models.channel import Channel
from app.services.telegram_admin import get_telegram_client
from telethon import functions

logger = logging.getLogger(__name__)

router = APIRouter()


class ChannelCreate(BaseModel):
    name: str
    identifier: str
    invite_link: str | None = None


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
        client = await get_telegram_client()
    except Exception as e:
        logger.warning("forum-topics: no telegram client: %s", e)
        return {"topics": [], "error": str(e)}
    try:
        entity = await client.get_input_entity(ch.identifier)
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
    db.commit()
    db.refresh(ch)
    return orm_to_dict(ch)
