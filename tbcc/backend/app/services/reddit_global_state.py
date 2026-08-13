"""Global Reddit cadence — daily cap + min gap across all subs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.import_pipeline import tbcc_run_dir
from app.services.reddit_rules import reddit_global_daily_cap, reddit_global_min_gap_hours

logger = logging.getLogger(__name__)


@dataclass
class GlobalRedditEligibility:
    ok: bool
    reason: str | None = None
    posts_today: int = 0
    last_post_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "posts_today": self.posts_today,
            "last_post_at": self.last_post_at,
        }


def _state_path() -> Path:
    d = tbcc_run_dir() / "reddit-promo"
    d.mkdir(parents=True, exist_ok=True)
    return d / "global-state.json"


def _read_state() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("reddit global state read failed: %s", e)
        return {}


def _write_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _utc_day(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def check_global_reddit_eligibility(now: datetime | None = None) -> GlobalRedditEligibility:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    state = _read_state()
    day = _utc_day(now)
    posts_today = int(state.get("posts_today") or 0)
    if state.get("utc_day") != day:
        posts_today = 0

    cap = reddit_global_daily_cap()
    if posts_today >= cap:
        return GlobalRedditEligibility(
            False,
            f"global_daily_cap_{cap}",
            posts_today=posts_today,
            last_post_at=state.get("last_post_at"),
        )

    last_raw = state.get("last_post_at")
    if last_raw:
        try:
            last = datetime.fromisoformat(str(last_raw).replace("Z", "+00:00")).replace(tzinfo=None)
            gap_h = (now - last).total_seconds() / 3600.0
            min_gap = reddit_global_min_gap_hours()
            if gap_h < min_gap:
                return GlobalRedditEligibility(
                    False,
                    f"global_gap_{min_gap}h",
                    posts_today=posts_today,
                    last_post_at=last_raw,
                )
        except ValueError:
            pass

    return GlobalRedditEligibility(
        True,
        None,
        posts_today=posts_today,
        last_post_at=last_raw,
    )


def record_global_reddit_post(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    state = _read_state()
    day = _utc_day(now)
    posts_today = int(state.get("posts_today") or 0)
    if state.get("utc_day") != day:
        posts_today = 0
    posts_today += 1
    state = {
        "utc_day": day,
        "posts_today": posts_today,
        "last_post_at": now.isoformat(),
    }
    _write_state(state)
    return state
