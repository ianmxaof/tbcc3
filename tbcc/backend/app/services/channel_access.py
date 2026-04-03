"""Telethon helpers for adding/removing users from channels."""
import asyncio
import logging
import os
from datetime import datetime, timedelta

from telethon import TelegramClient
from telethon.tl.functions.channels import EditBannedRequest, InviteToChannelRequest
from telethon.tl.types import ChatBannedRights

logger = logging.getLogger(__name__)

# Ban for 1 year - effectively removes from channel; user can be re-added on resubscribe
BAN_DURATION_DAYS = 365


async def add_user_to_channel(user_id: int, channel_identifier: str) -> bool:
    """Add user to channel. Unbans first if previously banned (e.g. after expiry). Returns True on success."""
    client = TelegramClient(
        "admin",
        int(os.environ["API_ID"]),
        os.environ["API_HASH"],
    )
    try:
        await client.start()
        user_entity = await client.get_input_entity(user_id)
        channel_entity = await client.get_input_entity(channel_identifier)
        await client(InviteToChannelRequest(channel_entity, [user_entity]))
        logger.info("Added user %s to channel %s", user_id, channel_identifier)
        return True
    except Exception as e:
        logger.exception("Failed to add user %s to channel %s: %s", user_id, channel_identifier, e)
        return False
    finally:
        await client.disconnect()


async def remove_user_from_channel(user_id: int, channel_identifier: str) -> bool:
    """Remove (kick) user from channel. Returns True on success."""
    client = TelegramClient(
        "admin",
        int(os.environ["API_ID"]),
        os.environ["API_HASH"],
    )
    try:
        await client.start()
        user_entity = await client.get_input_entity(user_id)
        channel_entity = await client.get_input_entity(channel_identifier)
        # Ban with view_messages=True removes from channel (1-year ban; allows re-add on resubscribe)
        until = datetime.utcnow() + timedelta(days=BAN_DURATION_DAYS)
        await client(
            EditBannedRequest(
                channel=channel_entity,
                participant=user_entity,
                banned_rights=ChatBannedRights(
                    until_date=until,
                    view_messages=True,
                    send_messages=True,
                    send_media=True,
                    send_stickers=True,
                    send_gifs=True,
                    send_games=True,
                    send_inline=True,
                    embed_links=True,
                ),
            )
        )
        logger.info("Removed user %s from channel %s", user_id, channel_identifier)
        return True
    except Exception as e:
        logger.exception("Failed to remove user %s from channel %s: %s", user_id, channel_identifier, e)
        return False
    finally:
        await client.disconnect()


def add_user_sync(user_id: int, channel_identifier: str) -> bool:
    """Sync wrapper for add_user_to_channel."""
    return asyncio.run(add_user_to_channel(user_id, channel_identifier))


def remove_user_sync(user_id: int, channel_identifier: str) -> bool:
    """Sync wrapper for remove_user_from_channel."""
    return asyncio.run(remove_user_from_channel(user_id, channel_identifier))
