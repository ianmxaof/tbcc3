"""
One-off helper: find Telegram forum topic/thread id by title.

Usage:
  cd tbcc/backend
  python find_forum_thread_id.py --channel "<@channel_username_or_-100id>" --title "Reception / Party Room"

Or set env:
  CHANNEL_IDENTIFIER="-100123..." (or "@AOF")
  TOPIC_TITLE="Reception / Party Room"

Notes:
- This is for "forum topics" (topic-enabled groups/supergroups).
- Telethon returns a ForumTopic object that includes an `id` field that corresponds
  to Bot API's `message_thread_id` in most cases.
- We also print the full `to_dict()` for the matched topic so you can confirm
  what to use when sending messages.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from telethon import TelegramClient, functions

# Loads tbcc/.env or backend/.env (see tbcc/backend/bots/__init__.py)
from bots import __init__ as _load_env  # noqa: F401


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _print_key_values(label: str, data: dict[str, Any]) -> None:
    keep_keys = [
        "id",
        "title",
        "top_message",
        "icon_color",
        "closed",
        "hidden",
        "unread_count",
        "notify_settings",
        "to_dict",
    ]
    print(f"\n--- {label} ---")
    for k in keep_keys:
        if k in data:
            print(f"{k}: {data[k]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--channel",
        default=os.getenv("CHANNEL_IDENTIFIER", "").strip(),
        help="Telegram channel/group identifier: '@AOF' or '-100123...'. Defaults to env CHANNEL_IDENTIFIER.",
    )
    parser.add_argument(
        "--title",
        default=os.getenv("TOPIC_TITLE", "Reception / Party Room").strip(),
        help='Forum topic title to match. Defaults to env TOPIC_TITLE (or "Reception / Party Room").',
    )
    parser.add_argument("--limit", type=int, default=100, help="Max forum topics to fetch.")
    args = parser.parse_args()

    if not args.channel:
        raise SystemExit("Missing --channel (or set CHANNEL_IDENTIFIER).")

    api_id = os.environ.get("API_ID")
    api_hash = os.environ.get("API_HASH")
    if not api_id or not api_hash:
        raise SystemExit("Missing API_ID/API_HASH in env (tbcc/.env or backend/.env).")

    client = TelegramClient("admin", int(api_id), api_hash)

    async def run() -> None:
        await client.start()
        try:
            entity = await client.get_input_entity(args.channel)
            # TL: messages.GetForumTopicsRequest(peer, offset_date, offset_id, offset_topic, limit, q=None)
            resp = await client(
                functions.messages.GetForumTopicsRequest(
                    peer=entity,
                    offset_date=None,
                    offset_id=0,
                    offset_topic=0,
                    limit=args.limit,
                    q=None,
                )
            )

            topics = getattr(resp, "topics", None)
            if topics is None:
                # Print raw response to figure out structure
                print("Unexpected GetForumTopicsResponse shape. resp= ", type(resp))
                if hasattr(resp, "to_dict"):
                    print(resp.to_dict())
                raise SystemExit("Could not find resp.topics.")

            want = _norm(args.title)
            matches = []
            for t in topics:
                t_dict = t.to_dict() if hasattr(t, "to_dict") else {}
                t_title = _norm(str(t_dict.get("title", "")))
                if want and want in t_title:
                    matches.append((t, t_dict))

            if not matches:
                print(f'No forum topic matches title containing: "{args.title}"')
                print("Available topic titles (first 50):")
                for idx, t in enumerate(topics[:50]):
                    t_dict = t.to_dict() if hasattr(t, "to_dict") else {}
                    print(f"{idx+1}. {t_dict.get('title')}")
                return

            # Prefer exact-ish match, otherwise first partial match.
            def score(tup: tuple[Any, dict[str, Any]]) -> int:
                _t, t_dict = tup
                t_title = _norm(str(t_dict.get("title", "")))
                # Higher is better
                if t_title == want:
                    return 100
                if want in t_title:
                    return 50
                return 0

            matches.sort(key=score, reverse=True)
            topic_obj, topic_dict = matches[0]

            _print_key_values("Matched topic summary", topic_dict)
            # Print full dict so you can identify which id corresponds to Bot API message_thread_id
            print("\nFull topic to_dict():")
            print(topic_dict)
            print("\nLikely candidates:")
            print(f"- topic.id (usually Bot API message_thread_id): {topic_dict.get('id')}")
            if "top_message" in topic_dict:
                print(f"- topic.top_message.message_id (sometimes useful for reply_to): {topic_dict.get('top_message', {}).get('id') if isinstance(topic_dict.get('top_message'), dict) else None}")
        finally:
            await client.disconnect()

    import asyncio

    asyncio.run(run())


if __name__ == "__main__":
    main()

