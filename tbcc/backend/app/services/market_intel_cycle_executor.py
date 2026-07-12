"""Execute gated actions when a weekly market-intel cycle completes."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def auto_post_mode() -> str:
    """``0`` observe only; ``queue`` Buffer addToQueue; ``execute`` reserved."""
    return (os.getenv("TBCC_MARKET_INTEL_AUTO_POST") or "0").strip().lower()


def cycle_pool_id() -> int | None:
    raw = (os.getenv("TBCC_MARKET_INTEL_CYCLE_POOL_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def execute_cycle_actions(db: Session, cycle: dict[str, Any]) -> dict[str, Any]:
    """Run post-cycle actions when ``complete`` and mode allows."""
    if not cycle.get("complete"):
        return {"ok": True, "skipped": True, "reason": "cycle_not_complete"}

    mode = auto_post_mode()
    if mode in ("0", "false", "off", "observe", ""):
        return {"ok": True, "skipped": True, "reason": "observe_only", "mode": mode}

    leader = cycle.get("leader_tag")
    out: dict[str, Any] = {
        "ok": True,
        "mode": mode,
        "leader_tag": leader,
        "actions": [],
    }

    pool_id = cycle_pool_id()
    if pool_id is None:
        try:
            from app.services.export_flywheel_service import pool_depth_by_lane

            lanes = pool_depth_by_lane(db)
            for lane in lanes:
                pid = lane.get("pool_id")
                depth = int(lane.get("approved_depth") or 0)
                if pid and depth > 0:
                    pool_id = int(pid)
                    out["pool_network_key"] = lane.get("network_key")
                    break
        except Exception as e:
            logger.debug("cycle pool resolve: %s", e)

    if pool_id:
        try:
            from app.services.export_flywheel_service import rank_pool_media, rank_picks_enabled

            if rank_picks_enabled():
                picks = rank_pool_media(db, pool_id, 3, randomize=False)
                out["recommended_media_ids"] = [m.id for m in picks]
                out["actions"].append(
                    {
                        "kind": "rank_pool_media",
                        "pool_id": pool_id,
                        "media_ids": out["recommended_media_ids"],
                    }
                )
        except Exception as e:
            logger.warning("cycle rank_pool_media failed: %s", e)
            out["rank_error"] = str(e)[:200]

    if mode == "queue":
        try:
            from app.services.buffer_graphql import (
                buffer_target_channel_ids,
                create_post,
                find_channel_id_by_service,
            )

            chans = buffer_target_channel_ids(x_primary_only=True)
            channel_id = chans[0] if chans else find_channel_id_by_service("twitter")
            if channel_id and leader:
                tags = cycle.get("top_tags") or []
                tag_names = [str(t.get("tag") or "") for t in tags[:3] if t.get("tag")]
                hashtag = " ".join(f"#{t}" for t in tag_names if t)
                text = (
                    f"Weekly intel pick: {leader}. "
                    f"Tags rising on Erome + Reddit this week. {hashtag}".strip()
                )[:280]
                post = create_post(channel_id, text, mode="addToQueue")
                out["actions"].append({"kind": "buffer_queue", "post_id": post.get("id")})
                out["buffer_post"] = post
            else:
                out["actions"].append(
                    {
                        "kind": "buffer_queue",
                        "skipped": True,
                        "reason": "no_channel_or_leader",
                    }
                )
        except Exception as e:
            logger.warning("cycle buffer queue failed: %s", e)
            out["buffer_error"] = str(e)[:200]

    return out
