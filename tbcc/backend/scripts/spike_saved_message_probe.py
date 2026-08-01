"""Probe Saved Messages ids via admin Telethon session."""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")


async def main() -> int:
    ids = [int(x) for x in sys.argv[1:]] or [17827, 16727, 18091, 106372]
    from app.services.telegram_admin import get_telegram_storage, run_telegram_io

    async def _fn(storage):
        client = storage.client
        me = await client.get_me()
        print(f"session_user={getattr(me, 'username', None)} id={getattr(me, 'id', None)}")
        for mid in ids:
            raw = await client.get_messages("me", ids=mid)
            msg = raw[0] if isinstance(raw, list) else raw
            if not msg or not getattr(msg, "media", None):
                print(f"{mid} MISSING")
                continue
            print(f"{mid} OK date={getattr(msg, 'date', None)}")

    await run_telegram_io(_fn)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
