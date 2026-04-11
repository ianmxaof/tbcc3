"""Record outbound post events for analytics (Step 1 metrics pipeline)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.post_outbound_event import PostOutboundEvent


def record_post_outbound_event(
    db: Session,
    *,
    event_type: str,
    channel_id: int | None = None,
    scheduled_post_id: int | None = None,
    pool_id: int | None = None,
    ok: bool = True,
    error_message: str | None = None,
    extra: dict[str, Any] | None = None,
) -> PostOutboundEvent:
    extra_json = json.dumps(extra, separators=(",", ":"), default=str) if extra else None
    ev = PostOutboundEvent(
        event_type=event_type,
        channel_id=channel_id,
        scheduled_post_id=scheduled_post_id,
        pool_id=pool_id,
        ok=ok,
        error_message=(error_message[:4000] if error_message else None),
        extra_json=extra_json,
    )
    db.add(ev)
    return ev
