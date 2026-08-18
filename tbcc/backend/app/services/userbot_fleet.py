import os
import json
import logging
from typing import Optional
from telethon import TelegramClient, events
from app.models.userbot_account import UserbotAccount
from app.services import format_engine

logger = logging.getLogger(__name__)


class UserbotFleet:
    def __init__(self):
        self._clients: dict[int, TelegramClient] = {}
        self._api_id = int(os.getenv("TBCC_USERBOT_API_ID", "0"))
        self._api_hash = os.getenv("TBCC_USERBOT_API_HASH", "")

    async def get_client(self, account: UserbotAccount) -> TelegramClient:
        if account.id in self._clients:
            return self._clients[account.id]

        proxy = None
        if account.proxy_json:
            p = json.loads(account.proxy_json)
            proxy = (
                p.get("type", "socks5"),
                p.get("host", "127.0.0.1"),
                int(p.get("port", 1080)),
                True,
                p.get("username", ""),
                p.get("password", ""),
            )

        client = TelegramClient(
            account.session_file_path,
            api_id=self._api_id,
            api_hash=self._api_hash,
            proxy=proxy,
        )
        await client.connect()
        self._clients[account.id] = client
        return client

    async def send_message(self, account: UserbotAccount, target: str, text: str):
        client = await self.get_client(account)
        sent_msg = await client.send_message(target, text)
        account.daily_message_count = (account.daily_message_count or 0) + 1
        return sent_msg

    async def disconnect_all(self):
        for client in self._clients.values():
            try:
                await client.disconnect()
            except Exception:
                pass
        self._clients.clear()

    def register_inbound_handler(self, callback):
        """Register a handler for inbound private messages across all connected clients.

        The handler fires when event.is_private is True and event.out is False.
        """
        async def _handler(event):
            await callback(event)

        for client in self._clients.values():
            client.add_event_handler(
                _handler,
                events.NewMessage(
                    incoming=True,
                    func=lambda e: e.is_private and not e.out,
                ),
            )
