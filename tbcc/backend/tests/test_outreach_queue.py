import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.models.userbot_account import UserbotAccount, WarmupState
from app.services.outreach_queue import OutreachQueue


async def _run_and_wait(coro, tasks_list):
    """Helper to schedule a task and wait for all background tasks to finish."""
    await coro
    if tasks_list:
        await asyncio.gather(*tasks_list, return_exceptions=True)


class TestOutreachQueue:
    def test_schedule_respects_daily_limit(self):
        account = UserbotAccount(
            phone_number="+15550006666",
            session_file_path="/tmp/f.session",
            daily_message_count=30,
            max_daily_limit=30,
        )
        fleet_mock = MagicMock()
        fleet_mock.send_message = AsyncMock(return_value=None)
        queue = OutreachQueue(fleet_mock)

        asyncio.run(queue.schedule_cold_dm(account, "12345", "hello", 1))
        # Should not create any tasks because limit is reached
        assert len(queue._tasks) == 0
        fleet_mock.send_message.assert_not_called()

    def test_schedule_creates_task_when_under_limit(self):
        account = UserbotAccount(
            phone_number="+15550007777",
            session_file_path="/tmp/g.session",
            daily_message_count=5,
            max_daily_limit=30,
        )
        fleet_mock = MagicMock()
        fleet_mock.send_message = AsyncMock(return_value=None)
        queue = OutreachQueue(fleet_mock)

        coro = queue.schedule_cold_dm(account, "12345", "hello", 1)
        asyncio.run(_run_and_wait(coro, queue._tasks))
        
        assert len(queue._tasks) == 1
        fleet_mock.send_message.assert_called_once()

    def test_send_failure_marks_banned(self):
        account = UserbotAccount(
            phone_number="+15550008888",
            session_file_path="/tmp/h.session",
            daily_message_count=0,
            max_daily_limit=30,
        )
        fleet_mock = MagicMock()
        fleet_mock.send_message = AsyncMock(side_effect=Exception("flood wait"))
        queue = OutreachQueue(fleet_mock)

        coro = queue.schedule_cold_dm(account, "12345", "hello", 1)
        asyncio.run(_run_and_wait(coro, queue._tasks))
        
        assert account.is_banned is True
