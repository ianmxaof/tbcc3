"""TBCC Milestone Ship — status, push, Buffer post. Run from tbcc/backend."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
env_path = ROOT / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.buffer_graphql import buffer_target_channel_ids, create_idea, create_post, find_channel_id_by_service
from app.services.buffer_post_result import buffer_create_post_error_message, buffer_create_post_succeeded

POST_VARIANTS = [
    (
        "Shipped a big TBCC milestone: GSP milestone-ship protocol, Buffer build-in-public pipeline, "
        "secretary RAG + format engine, album composer bot, watermarks, ops alerts, and 9 DB migrations. "
        "Telegram content ops stack, in public."
    ),
    (
        "Weeks of TBCC work finally on GitHub — ship-log automation, macro search bot, archive governance, "
        "scheduler overhaul, extension gallery UX. Building a Telegram-first content control center."
    ),
    (
        "TBCC milestone: protocols + Buffer ship log + secretary/album composer bots + poster hardening. "
        "Less sitting on local diffs, more shipping. #buildinpublic"
    ),
]


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd or REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def _branch() -> str:
    r = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return (r.stdout or "").strip() or "unknown"


def _status() -> dict:
    branch = _branch()
    ahead_n: int | None = None
    if branch != "unknown":
        ahead = _run(["git", "rev-list", "--count", f"origin/{branch}..HEAD"])
        if ahead.returncode == 0:
            ahead_n = int((ahead.stdout or "0").strip() or 0)
    porcelain = _run(["git", "status", "--porcelain"])
    dirty = len([ln for ln in (porcelain.stdout or "").splitlines() if ln.strip()])
    last_origin = _run(["git", "log", f"origin/{branch}", "-1", "--format=%h %ci %s"])
    if last_origin.returncode != 0:
        last_origin = _run(["git", "log", "-1", "--format=%h %ci %s"])
    return {
        "branch": branch,
        "commits_ahead_of_origin": ahead_n,
        "dirty_paths": dirty,
        "last_origin_commit": (last_origin.stdout or "").strip(),
    }


def _print_status() -> None:
    s = _status()
    print(json.dumps(s, indent=2))
    if s["dirty_paths"]:
        print(f"\n{s['dirty_paths']} path(s) changed/untracked.", file=sys.stderr)
    if s["commits_ahead_of_origin"] is not None:
        print(f"Commits ahead of origin/{s['branch']}: {s['commits_ahead_of_origin']}", file=sys.stderr)


def _commit(message: str) -> str:
    r = _run(["git", "commit", "-m", message])
    if r.returncode != 0:
        print(r.stdout, r.stderr, file=sys.stderr)
        raise SystemExit(r.returncode)
    out = _run(["git", "rev-parse", "--short", "HEAD"])
    return (out.stdout or "").strip()


def _push() -> None:
    branch = _branch()
    r = _run(["git", "push", "-u", "origin", branch])
    if r.stdout:
        print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def _post_buffer(text: str, *, idea: bool, share_now: bool, title: str) -> dict:
    if idea:
        t = title or f"TBCC milestone {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        return create_idea(title=t, text=text)
    chans = buffer_target_channel_ids(x_primary_only=True)
    cid = chans[0] if chans else find_channel_id_by_service("twitter")
    if not cid:
        raise SystemExit("Set TBCC_BUFFER_CHANNEL_ID_PRIMARY")
    mode = "shareNow" if share_now else "addToQueue"
    return create_post(cid, text, mode=mode)


def _resolve_post_text(args: argparse.Namespace) -> str:
    text = (args.text or "").strip()
    if text:
        return text
    if args.post_variant:
        return POST_VARIANTS[args.post_variant - 1]
    return ""


def _do_post(args: argparse.Namespace) -> None:
    text = _resolve_post_text(args)
    if not text:
        print("--text or --post-variant required", file=sys.stderr)
        sys.exit(1)
    use_idea = bool(args.idea) and not args.queue and not args.share_now
    share_now = bool(args.share_now) or (bool(args.execute) and not args.idea and not args.queue)
    res = _post_buffer(text, idea=use_idea, share_now=share_now, title=args.message)
    print(json.dumps(res, indent=2))
    if use_idea:
        idea = (res.get("data") or {}).get("createIdea")
        if isinstance(idea, dict) and idea.get("id"):
            print(f"Idea: {idea['id']} https://publish.buffer.com", file=sys.stderr)
        return
    if buffer_create_post_succeeded(res):
        mode = "shareNow" if share_now else "addToQueue"
        print(f"X post ({mode}) — https://publish.buffer.com", file=sys.stderr)
    else:
        print(buffer_create_post_error_message(res), file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="TBCC milestone ship pipeline")
    p.add_argument("--status", action="store_true")
    p.add_argument("--commit-only", action="store_true")
    p.add_argument("--push", action="store_true")
    p.add_argument("--post", action="store_true")
    p.add_argument("--execute", action="store_true", help="commit + push + post (stage files first)")
    p.add_argument("--message", "-m", default="", help="Commit message / Idea title")
    p.add_argument("--text", default="", help="Buffer post text")
    p.add_argument("--post-variant", type=int, choices=(1, 2, 3), default=1)
    p.add_argument("--idea", action="store_true")
    p.add_argument("--queue", action="store_true")
    p.add_argument("--share-now", action="store_true")
    p.add_argument("--list-variants", action="store_true")
    args = p.parse_args()

    if args.list_variants:
        for i, v in enumerate(POST_VARIANTS, 1):
            print(f"--- Variant {i} ({len(v)} chars) ---\n{v}\n")
        return

    if args.status or not any([args.commit_only, args.push, args.post, args.execute]):
        _print_status()
        return

    if args.execute:
        msg = (args.message or "").strip()
        if not msg:
            print("--message required for --execute", file=sys.stderr)
            sys.exit(1)
        sha = _commit(msg)
        print(f"committed {sha}")
        _push()
        print(f"pushed {_branch()}")
        _do_post(args)
        return

    if args.commit_only:
        msg = (args.message or "").strip()
        if not msg:
            print("--message required", file=sys.stderr)
            sys.exit(1)
        print(f"committed {_commit(msg)}")
        return

    if args.push:
        _push()
        print(f"pushed {_branch()}")
        return

    if args.post:
        _do_post(args)


if __name__ == "__main__":
    main()
