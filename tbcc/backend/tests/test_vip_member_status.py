"""Tests for VIP member /status home."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.vip_member_status import build_vip_member_status_lines


@patch("app.services.vip_member_status.is_aof_vip_subscriber", return_value=True)
@patch("app.services.vip_member_status.vip_daily_pull_available", return_value=True)
@patch("app.services.vip_member_status.vip_daily_pull_used_today", return_value=False)
def test_vip_status_includes_god_roll_ready(_used, _avail, _vip):
    db = MagicMock()
    with patch("app.services.companion_access.get_access") as mock_acc:
        acc = MagicMock(credits_balance=3, vip_subscriber=True)
        mock_acc.return_value = acc
        lines = build_vip_member_status_lines(
            db,
            42,
            plan_name="AOF VIP — 1 Month",
            expires_at=datetime.utcnow() + timedelta(days=10),
        )
    joined = "\n".join(lines)
    assert "God roll" in joined
    assert "READY" in joined
    assert "Weekly mega" in joined
    assert "day(s) left" in joined
