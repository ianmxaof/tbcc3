# ============================================================================
# TBCC / FE-LLMv4 — Userbot Outreach Infrastructure Bootstrap
# Creates: models, services, Alembic migration, requirements entry.
# Does NOT start bots, does NOT run alembic upgrade (cloud-only-DB policy).
# ============================================================================

$ErrorActionPreference = "Stop"

# --- Path setup ---
$BackendDir = "tbcc/backend"
$ModelsDir = "$BackendDir/app/models"
$ServicesDir = "$BackendDir/app/services"
$TestsDir = "$BackendDir/tests"

if (-not (Test-Path $BackendDir)) {
    Write-Host "ERROR: Backend dir not found at $BackendDir" -ForegroundColor Red
    Write-Host "Run this from the repository root (telegram_bot2/)." -ForegroundColor Yellow
    exit 1
}

# --- Ensure subdirs exist ---
foreach ($dir in @($ModelsDir, $ServicesDir, $TestsDir)) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
}

# ============================================================================
# 1. Model: userbot_account.py
# ============================================================================
$UserbotAccountModel = @'
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Text
from app.models.base import Base


class WarmupState(enum.Enum):
    cold = "cold"
    warming = "warming"
    warm = "warm"


class UserbotAccount(Base):
    __tablename__ = "userbot_accounts"

    id = Column(Integer, primary_key=True)
    phone_number = Column(String, unique=True, nullable=False)
    session_file_path = Column(String, nullable=False)
    proxy_json = Column(Text, nullable=True)  # {host, port, username, password}

    warmup_state = Column(Enum(WarmupState), default=WarmupState.cold, nullable=False)
    daily_message_count = Column(Integer, default=0, nullable=False)
    max_daily_limit = Column(Integer, default=30, nullable=False)

    is_banned = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity_at = Column(DateTime, default=datetime.utcnow)

    def reset_daily_counts(self):
        self.daily_message_count = 0
'@

# ============================================================================
# 2. Model: cold_target.py
# ============================================================================
$ColdTargetModel = @'
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey
from app.models.base import Base


class TargetStatus(enum.Enum):
    new = "new"
    contacted = "contacted"
    engaging = "engaging"
    converted = "converted"
    dead = "dead"


class ColdTarget(Base):
    __tablename__ = "cold_targets"

    id = Column(Integer, primary_key=True)
    telegram_username = Column(String, nullable=True)
    telegram_user_id = Column(String, nullable=True)

    source = Column(String, nullable=True)  # e.g., "scrape_group_x", "import_y"
    assigned_userbot_id = Column(Integer, ForeignKey("userbot_accounts.id"), nullable=True)

    status = Column(Enum(TargetStatus), default=TargetStatus.new, nullable=False)
    first_contact_at = Column(DateTime, nullable=True)
    last_contact_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(String, nullable=True)
'@

# ============================================================================
# 3. Service: userbot_fleet.py
# ============================================================================
$UserbotFleetService = @'
import os
import json
import logging
from typing import Optional
from telethon import TelegramClient
from app.models.userbot_account import UserbotAccount

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
'@

# ============================================================================
# 4. Service: outreach_queue.py
# ============================================================================
$OutreachQueueService = @'
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
'@

# ============================================================================
# 5. Test: test_userbot_account_model.py
# ============================================================================
$UserbotAccountTest = @'
import pytest
from datetime import datetime
from app.models.userbot_account import UserbotAccount, WarmupState


class TestUserbotAccountModel:
    def test_create_account_defaults(self, db_session):
        acc = UserbotAccount(
            phone_number="+15550001111",
            session_file_path="/tmp/sessions/test.session",
        )
        db_session.add(acc)
        db_session.commit()
        assert acc.id is not None
        assert acc.warmup_state == WarmupState.cold
        assert acc.daily_message_count == 0
        assert acc.max_daily_limit == 30
        assert acc.is_banned is False
        assert acc.is_active is True

    def test_phone_number_unique(self, db_session):
        acc1 = UserbotAccount(phone_number="+15550002222", session_file_path="/tmp/a.session")
        acc2 = UserbotAccount(phone_number="+15550002222", session_file_path="/tmp/b.session")
        db_session.add(acc1)
        db_session.commit()
        db_session.add(acc2)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_reset_daily_counts(self, db_session):
        acc = UserbotAccount(
            phone_number="+15550003333",
            session_file_path="/tmp/c.session",
            daily_message_count=25,
        )
        db_session.add(acc)
        db_session.commit()
        acc.reset_daily_counts()
        assert acc.daily_message_count == 0

    def test_warmup_state_transition(self, db_session):
        acc = UserbotAccount(phone_number="+15550004444", session_file_path="/tmp/d.session")
        acc.warmup_state = WarmupState.warming
        db_session.add(acc)
        db_session.commit()
        assert acc.warmup_state == WarmupState.warming

        acc.warmup_state = WarmupState.warm
        db_session.commit()
        assert acc.warmup_state == WarmupState.warm
'@

# ============================================================================
# 6. Test: test_cold_target_model.py
# ============================================================================
$ColdTargetTest = @'
import pytest
from datetime import datetime
from app.models.cold_target import ColdTarget, TargetStatus
from app.models.userbot_account import UserbotAccount


class TestColdTargetModel:
    def test_create_target_defaults(self, db_session):
        t = ColdTarget(telegram_username="testuser1")
        db_session.add(t)
        db_session.commit()
        assert t.id is not None
        assert t.status == TargetStatus.new
        assert t.source is None
        assert t.first_contact_at is None

    def test_status_transitions(self, db_session):
        t = ColdTarget(telegram_username="testuser2")
        db_session.add(t)
        db_session.commit()

        t.status = TargetStatus.contacted
        db_session.commit()
        assert t.status == TargetStatus.contacted

        t.status = TargetStatus.engaging
        db_session.commit()
        assert t.status == TargetStatus.engaging

        t.status = TargetStatus.converted
        db_session.commit()
        assert t.status == TargetStatus.converted

    def test_assign_userbot(self, db_session):
        acc = UserbotAccount(phone_number="+15550005555", session_file_path="/tmp/e.session")
        db_session.add(acc)
        db_session.commit()

        t = ColdTarget(telegram_username="testuser3", assigned_userbot_id=acc.id)
        db_session.add(t)
        db_session.commit()
        assert t.assigned_userbot_id == acc.id

    def test_string_user_id(self, db_session):
        t = ColdTarget(telegram_user_id="9876543210")
        db_session.add(t)
        db_session.commit()
        assert t.telegram_user_id == "9876543210"
'@

# ============================================================================
# 7. Test: test_outreach_queue.py
# ============================================================================
$OutreachQueueTest = @'
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.models.userbot_account import UserbotAccount, WarmupState
from app.services.outreach_queue import OutreachQueue


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

        asyncio.run(queue.schedule_cold_dm(account, "12345", "hello", 1))
        assert len(queue._tasks) == 1
        # Let the task run
        asyncio.run(asyncio.sleep(2))
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

        asyncio.run(queue.schedule_cold_dm(account, "12345", "hello", 1))
        asyncio.run(asyncio.sleep(2))
        assert account.is_banned is True
'@

# ============================================================================
# Write files
# ============================================================================
$FileMap = [ordered]@{
    "$ModelsDir/userbot_account.py"     = $UserbotAccountModel
    "$ModelsDir/cold_target.py"        = $ColdTargetModel
    "$ServicesDir/userbot_fleet.py"     = $UserbotFleetService
    "$ServicesDir/outreach_queue.py"     = $OutreachQueueService
    "$TestsDir/test_userbot_account_model.py" = $UserbotAccountTest
    "$TestsDir/test_cold_target_model.py"    = $ColdTargetTest
    "$TestsDir/test_outreach_queue.py"       = $OutreachQueueTest
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " FE-LLMv4 Userbot Outreach Bootstrap" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

foreach ($path in $FileMap.Keys) {
    $content = $FileMap[$path]
    $relPath = $path -replace [regex]::Escape("tbcc/"), ""
    if (Test-Path $path) {
        Write-Host "  [SKIP] $relPath (already exists)" -ForegroundColor Yellow
    } else {
        [System.IO.File]::WriteAllText($path, $content.Trim() + "`n")
        Write-Host "  [CREATED] $relPath" -ForegroundColor Green
    }
}

# ============================================================================
# 8. Requirements: telethon
# ============================================================================
Write-Host ""
Write-Host "--- Requirements ---" -ForegroundColor Cyan

$RequirementsPath = "$BackendDir/requirements.txt"
$PyprojectPath = "tbcc/pyproject.toml"

$telethonAdded = $false

if (Test-Path $RequirementsPath) {
    $content = Get-Content $RequirementsPath -Raw
    if ($content -notmatch "telethon") {
        Add-Content -Path $RequirementsPath -Value "telethon>=1.36.0"
        Write-Host "  [ADDED] telethon to requirements.txt" -ForegroundColor Green
        $telethonAdded = $true
    } else {
        Write-Host "  [SKIP] telethon already in requirements.txt" -ForegroundColor Yellow
    }
} elseif (Test-Path $PyprojectPath) {
    $content = Get-Content $PyprojectPath -Raw
    if ($content -notmatch "telethon") {
        Write-Host "  [WARN] Found pyproject.toml — add telethon manually:" -ForegroundColor Yellow
        Write-Host "         pip install telethon && <add to pyproject dependencies>" -ForegroundColor Yellow
    } else {
        Write-Host "  [SKIP] telethon already in pyproject.toml" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [WARN] No requirements.txt or pyproject.toml found" -ForegroundColor Yellow
    Write-Host "         Run: pip install telethon" -ForegroundColor White
}

# ============================================================================
# 9. Alembic migration generation
# ============================================================================
Write-Host ""
Write-Host "--- Alembic Migration ---" -ForegroundColor Cyan

$AlembicIni = "$BackendDir/alembic.ini"
$AlembicDir = "$BackendDir/alembic"
if (-not (Test-Path $AlembicIni) -and -not (Test-Path $AlembicDir)) {
    Write-Host "  [WARN] No alembic configuration found in $BackendDir" -ForegroundColor Yellow
    Write-Host "         Generate migration manually after models are importable." -ForegroundColor White
    Write-Host "         Ensure both models are imported in your models __init__.py" -ForegroundColor White
} else {
    Write-Host "  Generating migration..." -ForegroundColor Cyan
    Push-Location $BackendDir
    try {
        $output = & py -3.13 -m alembic revision --autogenerate -m "add_userbot_outreach" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] Migration generated" -ForegroundColor Green
            if ($output -match "Generating\s+(.*\.py)") {
                Write-Host "  File: $($matches[1])" -ForegroundColor White
            }
        } else {
            Write-Host "  [WARN] alembic revision failed (models may need __init__ import)" -ForegroundColor Yellow
            Write-Host "  Output: $output" -ForegroundColor DarkGray
            Write-Host ""
            Write-Host "  Ensure these are in your models/__init__.py or equivalent:" -ForegroundColor Yellow
            Write-Host "    from app.models.userbot_account import UserbotAccount" -ForegroundColor White
            Write-Host "    from app.models.cold_target import ColdTarget" -ForegroundColor White
        }
    } catch {
        Write-Host "  [WARN] alembic error: $_" -ForegroundColor Yellow
    } finally {
        Pop-Location
    }
}

# ============================================================================
# 10. Run tests
# ============================================================================
Write-Host ""
Write-Host "--- Tests ---" -ForegroundColor Cyan

Push-Location $BackendDir
try {
    Write-Host "  Running: py -3.13 -m pytest tests/test_userbot_account_model.py tests/test_cold_target_model.py tests/test_outreach_queue.py -q --tb=short" -ForegroundColor DarkGray
    Write-Host ""
    & py -3.13 -m pytest tests/test_userbot_account_model.py tests/test_cold_target_model.py tests/test_outreach_queue.py -q --tb=short 2>&1 | Write-Output

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "  [WARN] Tests had issues. Common fixes:" -ForegroundColor Yellow
        Write-Host "    - Ensure 'from app.models.base import Base' matches your repo's Base import" -ForegroundColor White
        Write-Host "    - Ensure db_session fixture exists in conftest.py" -ForegroundColor White
        Write-Host "    - pip install telethon" -ForegroundColor White
    }
} finally {
    Pop-Location
}

# ============================================================================
# Summary
# ============================================================================
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Models:" -ForegroundColor White
Write-Host "    - app/models/userbot_account.py" -ForegroundColor Gray
Write-Host "    - app/models/cold_target.py" -ForegroundColor Gray
Write-Host ""
Write-Host "  Services:" -ForegroundColor White
Write-Host "    - app/services/userbot_fleet.py" -ForegroundColor Gray
Write-Host "    - app/services/outreach_queue.py" -ForegroundColor Gray
Write-Host ""
Write-Host "  Tests:" -ForegroundColor White
Write-Host "    - tests/test_userbot_account_model.py" -ForegroundColor Gray
Write-Host "    - tests/test_cold_target_model.py" -ForegroundColor Gray
Write-Host "    - tests/test_outreach_queue.py" -ForegroundColor Gray
Write-Host ""
Write-Host "  What to check:" -ForegroundColor Yellow
Write-Host "    1. 'from app.models.base import Base' — match your repo's actual Base import" -ForegroundColor White
Write-Host "    2. Add to models/__init__.py if alembic didn't detect them" -ForegroundColor White
Write-Host "    3. Run: pip install telethon" -ForegroundColor White
Write-Host "    4. Do NOT run alembic upgrade (cloud-only-DB policy)" -ForegroundColor White
Write-Host "    5. Do NOT start any bots" -ForegroundColor White
Write-Host ""
