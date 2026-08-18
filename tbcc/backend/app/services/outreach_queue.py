import asyncio
import logging
import random
from app.models.userbot_account import UserbotAccount

logger = logging.getLogger(__name__)


class OutreachQueue:
    def __init__(self, fleet):
        self.fleet = fleet
        self._tasks: list = []

    async def schedule_cold_dm(
        self,
        account: UserbotAccount,
        target_id: str,
        text: str,
        delay_seconds: int,
    ):
        if account.daily_message_count >= account.max_daily_limit:
            logger.info(
                "Userbot %s reached daily limit (%s/%s)",
                account.id, account.daily_message_count, account.max_daily_limit,
            )
            return

        jitter = random.uniform(-0.2, 0.2)
        actual_delay = max(1, int(delay_seconds * (1.0 + jitter)))

        task = asyncio.create_task(
            self._execute_after_delay(account, target_id, text, actual_delay)
        )
        self._tasks.append(task)

    async def _execute_after_delay(
        self,
        account: UserbotAccount,
        target: str,
        text: str,
        delay: float,
    ):
        await asyncio.sleep(delay)
        try:
            await self.fleet.send_message(account, target, text)
        except Exception as e:
            logger.error(
                "Failed to send DM via account %s: %s", account.id, e, exc_info=True
            )
            account.is_banned = True
