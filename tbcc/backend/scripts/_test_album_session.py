"""Quick check: admin_album session can read album bot DM."""
import asyncio
import os
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_backend))
_root = _backend.parent
_dotenv = _root / ".env"
if _dotenv.is_file():
    for line in _dotenv.read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.strip()
        if not t or t.startswith("#") or "=" not in t:
            continue
        k, _, v = t.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


async def main() -> None:
    from app.services.telegram_admin import get_album_telegram_storage

    token = (os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN") or "").strip()
    bot_user = token.split(":", 1)[0] if token and ":" in token else "?"
    storage = await get_album_telegram_storage()
    try:
        entity = await storage._resolve_album_bot_entity(bot_user)
        print("entity", entity)
        n = 0
        async for msg in storage.client.iter_messages(entity, limit=5, from_user="me"):
            if msg.media:
                n += 1
                print(" msg", msg.id, storage._message_media_bucket(msg))
        print("recent media from me:", n)
    finally:
        from app.services.telegram_admin import reset_album_client

        await reset_album_client()


if __name__ == "__main__":
    asyncio.run(main())
