"""
Pending companion generation jobs (undress / nudify) → Telegram delivery.

Redis-backed when REDIS_URL is set; in-process fallback for local dev.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)

_JOB_TTL_SEC = 3600
_MEM: dict[str, tuple[float, dict[str, Any]]] = {}


def _redis() -> Any | None:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception as e:
        logger.warning("companion_jobs: redis unavailable: %s", e)
        return None


def _key(job_id: str) -> str:
    return f"tbcc:companion:job:{job_id}"


@dataclass
class CompanionJob:
    job_id: str
    chat_id: int
    user_id: int
    provider: str  # undress | nudify
    created_at: float
    pending_pose: str = ""
    hold_delivery: bool = False
    pending_body_refine: bool = False
    refine_breast_size: str = ""
    refine_body_type: str = ""
    refine_butt_size: str = ""
    refine_age: str = ""
    character_look: str = ""
    character_pose: str = ""
    media_type: str = "photo"  # photo | video
    video_pose_id: str = ""
    video_pose_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def wants_bimbo_refine(self) -> bool:
        return (self.refine_breast_size or "").strip() == "big"


def new_job_id(*, chat_id: int, user_id: int) -> str:
    return f"tg_{chat_id}_{user_id}_{uuid.uuid4().hex[:12]}"


def put_job(job: CompanionJob) -> None:
    payload = json.dumps(job.to_dict())
    r = _redis()
    if r is not None:
        try:
            r.setex(_key(job.job_id), _JOB_TTL_SEC, payload)
            return
        except Exception as e:
            logger.warning("companion_jobs put redis failed: %s", e)
    _MEM[job.job_id] = (time.time() + _JOB_TTL_SEC, job.to_dict())


def get_job(job_id: str) -> CompanionJob | None:
    r = _redis()
    if r is not None:
        try:
            raw = r.get(_key(job_id))
            if raw:
                data = json.loads(raw)
                return _from_dict(data)
        except Exception as e:
            logger.warning("companion_jobs get redis failed: %s", e)
    entry = _MEM.get(job_id)
    if not entry:
        return None
    expires, data = entry
    if time.time() > expires:
        _MEM.pop(job_id, None)
        return None
    return _from_dict(data)


def count_pending_jobs() -> int:
    """Approximate pending companion jobs (Redis keys or in-memory)."""
    r = _redis()
    if r is not None:
        try:
            n = 0
            for _ in r.scan_iter(match="tbcc:companion:job:*", count=100):
                n += 1
            return n
        except Exception:
            pass
    now = time.time()
    return sum(1 for exp, _ in _MEM.values() if exp > now)


def pop_job(job_id: str) -> CompanionJob | None:
    job = get_job(job_id)
    if not job:
        return None
    r = _redis()
    if r is not None:
        try:
            r.delete(_key(job_id))
        except Exception:
            pass
    _MEM.pop(job_id, None)
    return job


def _from_dict(data: dict[str, Any]) -> CompanionJob | None:
    try:
        return CompanionJob(
            job_id=str(data["job_id"]),
            chat_id=int(data["chat_id"]),
            user_id=int(data["user_id"]),
            provider=str(data.get("provider") or "undress"),
            created_at=float(data.get("created_at") or time.time()),
            pending_pose=str(data.get("pending_pose") or ""),
            hold_delivery=bool(data.get("hold_delivery")),
            pending_body_refine=bool(data.get("pending_body_refine")),
            refine_breast_size=str(data.get("refine_breast_size") or ""),
            refine_body_type=str(data.get("refine_body_type") or ""),
            refine_butt_size=str(data.get("refine_butt_size") or ""),
            refine_age=str(data.get("refine_age") or ""),
            character_look=str(data.get("character_look") or ""),
            character_pose=str(data.get("character_pose") or ""),
            media_type=str(data.get("media_type") or "photo"),
            video_pose_id=str(data.get("video_pose_id") or ""),
            video_pose_name=str(data.get("video_pose_name") or ""),
        )
    except (KeyError, TypeError, ValueError):
        return None


def parse_telegram_job_id(raw: str) -> str | None:
    """Accept id_gen from undress webhook or our tg_* job id."""
    s = (raw or "").strip()
    if s.startswith("tg_"):
        return s
    return s or None
