"""Poll Buffer GraphQL for post metrics → post_delivery_metrics."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.post_delivery_metric import PostDeliveryMetric
from app.services.content_performance import _apply_view_update

logger = logging.getLogger(__name__)


def buffer_metrics_sync_enabled() -> bool:
    return (os.getenv("TBCC_BUFFER_METRICS_SYNC_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def sync_buffer_post_metrics(db: Session, *, limit: int = 40) -> dict[str, Any]:
    if not buffer_metrics_sync_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    from app.services.buffer_graphql import fetch_post_impressions
    from app.services.buffer_post_result import buffer_create_post_id

    since = datetime.utcnow() - timedelta(days=14)
    rows = (
        db.query(PostDeliveryMetric)
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.surface == "buffer_x",
            PostDeliveryMetric.external_post_id.isnot(None),
        )
        .order_by(PostDeliveryMetric.id.desc())
        .limit(max(1, min(200, limit)))
        .all()
    )
    from app.services.buffer_graphql import BufferRateLimitError

    updated = 0
    scanned = 0
    for row in rows:
        post_id = (row.external_post_id or "").strip()
        if not post_id:
            continue
        scanned += 1
        try:
            views = fetch_post_impressions(post_id)
        except BufferRateLimitError as e:
            logger.warning(
                "buffer metrics sync: rate limited after %s scans (retry_after=%s)",
                scanned,
                e.retry_after_s,
            )
            return {
                "ok": True,
                "updated": updated,
                "scanned": scanned,
                "rate_limited": True,
                "retry_after_s": e.retry_after_s,
            }
        except Exception as e:
            logger.debug("buffer metrics fetch failed post=%s: %s", post_id[:20], e)
            continue
        if views is None:
            continue
        if _apply_view_update(row, int(views), None):
            updated += 1
    if updated:
        db.commit()
    return {"ok": True, "updated": updated, "scanned": scanned}
