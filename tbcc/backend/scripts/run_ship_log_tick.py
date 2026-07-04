"""Automated ship-log tick — Buffer Idea weekly, X queue on milestone. Run from tbcc/backend."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.buffer_graphql import buffer_target_channel_ids, create_idea, create_post, find_channel_id_by_service
from app.services.buffer_post_result import buffer_create_post_error_message, buffer_create_post_succeeded
from app.services.ship_log_autodraft import draft_scheduler_steady_milestone, draft_ship_log_tweet
from app.services.ship_log_sources import collect_ship_log_context

STATE_REL = Path(".tbcc-run/ship_log_tick_state.json")
MILESTONE_COMMIT_THRESHOLD = int(os.environ.get("TBCC_SHIP_LOG_MILESTONE_COMMITS", "5"))
AUTO_MODE = (os.environ.get("TBCC_SHIP_LOG_AUTO_MODE") or "idea").strip().lower()  # idea | queue | share_now


def _tbcc_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _state_path() -> Path:
    p = _tbcc_root() / STATE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_state() -> dict:
    p = _state_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_state(state: dict) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")


def _git_head() -> str:
    import subprocess

    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_tbcc_root().parent,
        capture_output=True,
        text=True,
    )
    return (r.stdout or "").strip()


def _is_milestone(ctx, state: dict) -> bool:
    if ctx.commit_count >= MILESTONE_COMMIT_THRESHOLD:
        return True
    head = _git_head()
    if head and head != state.get("last_head"):
        # first run after many commits
        if ctx.commit_count >= 3:
            return True
    notes = ctx.improvement_notes_excerpt or ""
    if "Agent workflow" in notes or "v3.0" in notes or "scheduler" in notes.lower():
        if not state.get("milestone_scheduler_posted"):
            return True
    return False


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="TBCC automated ship-log tick")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force-milestone", action="store_true", help="Queue scheduler-steady milestone draft")
    p.add_argument("--since", default="14 days ago")
    args = p.parse_args()

    ctx = collect_ship_log_context(since=args.since, max_commits=30)
    state = _load_state()
    milestone = args.force_milestone or _is_milestone(ctx, state)

    if milestone:
        text = draft_scheduler_steady_milestone() if args.force_milestone or not ctx.commit_lines else draft_ship_log_tweet(ctx, angle="milestone")
        title = f"TBCC milestone {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        mode = AUTO_MODE
    else:
        text = draft_ship_log_tweet(ctx, angle="week")
        title = f"TBCC ship log {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        mode = "idea"

    if not text:
        print(json.dumps({"action": "skip", "reason": "no draftable content"}, indent=2))
        return

    result: dict = {"action": mode, "chars": len(text), "text": text, "milestone": milestone}

    if args.dry_run:
        print(json.dumps({**result, "dry_run": True}, indent=2))
        return

    if mode == "idea":
        res = create_idea(title=title, text=text)
        result["buffer"] = res
        idea = (res.get("data") or {}).get("createIdea") if isinstance(res.get("data"), dict) else None
        if isinstance(idea, dict) and idea.get("id"):
            state["last_idea_id"] = idea["id"]
            state["last_idea_at"] = datetime.now(timezone.utc).isoformat()
    elif mode in ("queue", "share_now"):
        chans = buffer_target_channel_ids(x_primary_only=True)
        cid = chans[0] if chans else find_channel_id_by_service("twitter")
        if not cid:
            print("TBCC_BUFFER_CHANNEL_ID_PRIMARY not set", file=sys.stderr)
            sys.exit(1)
        share_mode = "shareNow" if mode == "share_now" else "addToQueue"
        res = create_post(cid, text, mode=share_mode)
        result["buffer"] = res
        if not buffer_create_post_succeeded(res):
            print(buffer_create_post_error_message(res), file=sys.stderr)
            sys.exit(1)
        state["last_queue_at"] = datetime.now(timezone.utc).isoformat()
        if milestone:
            state["milestone_scheduler_posted"] = True
    else:
        print(f"Unknown TBCC_SHIP_LOG_AUTO_MODE={mode}", file=sys.stderr)
        sys.exit(1)

    state["last_head"] = _git_head()
    state["last_text"] = text
    _save_state(state)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
