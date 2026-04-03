import os
from bots import __init__  # noqa: F401 - loads .env from tbcc/
from telethon import TelegramClient, events

client = TelegramClient("subscription", int(os.environ["API_ID"]), os.environ["API_HASH"])


@client.on(events.NewMessage(pattern=r"^/subscribe$"))
async def cmd_subscribe(event):
    await event.reply(
        "💎 **Premium Access**\n\n"
        "Choose your plan:\n"
        "• 1 month — $10\n"
        "• 3 months — $25\n\n"
        "Send /pay_crypto or /pay_stars to proceed."
    )


@client.on(events.NewMessage(pattern=r"^/pay_stars$"))
async def cmd_pay_stars(event):
    await event.reply(
        "⭐ Telegram Stars payment flow: configure your bot with a Stars payment provider in BotFather, "
        "then use the invoice API here."
    )


@client.on(events.NewMessage(pattern=r"^/pay_crypto$"))
async def cmd_pay_crypto(event):
    await event.reply(
        "🪙 Crypto payment: integrate NOWPayments or similar webhook, then send payment link here."
    )


if __name__ == "__main__":
    import asyncio

    async def main():
        await client.start()
        await client.run_until_disconnected()

    asyncio.run(main())
