"""
Optional Telethon client — redirects users to the real checkout bot (python-telegram-bot).

The production shop runs as `python -m bots.payment_bot` (e.g. @aofsubscriptions_bot) with
BOT_TOKEN. This script is only useful if you still run a separate Telethon userbot that should
not duplicate catalog logic.

Env:
  TBCC_PAYMENT_BOT_USERNAME — bot username without @ (default: aofsubscriptions_bot)
  API_ID, API_HASH — my.telegram.org (Telethon)
"""
from __future__ import annotations

import os
import sys

from bots import __init__  # noqa: F401 - loads .env from tbcc/

from telethon import TelegramClient, events

API_ID = (os.environ.get("API_ID") or "").strip()
API_HASH = (os.environ.get("API_HASH") or "").strip()
BOT_USERNAME = (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@")


def _payment_bot_url() -> str:
    return f"https://t.me/{BOT_USERNAME}"


def _redirect_md() -> str:
    url = _payment_bot_url()
    return (
        f"**Checkout & membership tiers** are on [**@{BOT_USERNAME}**]({url}).\n\n"
        "Open that bot → **Start** → **/subscribe** (premium) or **/shop** (full store).\n\n"
        "_Telegram Stars_ and _Wallet / crypto_ (automatic when NOWPayments is on the API) "
        "both use the same products from the dashboard."
    )


if not API_ID or not API_HASH:
    print("Set API_ID and API_HASH for Telethon, or run `python -m bots.payment_bot` instead.", file=sys.stderr)
    sys.exit(1)

client = TelegramClient("subscription", int(API_ID), API_HASH)


@client.on(events.NewMessage(pattern=r"^/(start|subscribe|pay_stars|pay_crypto)\s*$"))
async def cmd_redirect(event):
    await event.reply(_redirect_md(), link_preview=False)


if __name__ == "__main__":
    import asyncio

    async def main():
        await client.start()
        print(f"subscription_bot (redirect only) — pointing to {_payment_bot_url()}")
        await client.run_until_disconnected()

    asyncio.run(main())
