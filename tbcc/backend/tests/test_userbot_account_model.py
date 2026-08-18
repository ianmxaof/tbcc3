import pytest
from datetime import datetime
from app.models.userbot_account import UserbotAccount, WarmupState


class TestUserbotAccountModel:
    def test_create_account_defaults(self, db):
        acc = UserbotAccount(
            phone_number="+15550001111",
            session_file_path="/tmp/sessions/test.session",
        )
        db.add(acc)
        db.commit()
        assert acc.id is not None
        assert acc.warmup_state == WarmupState.cold
        assert acc.daily_message_count == 0
        assert acc.max_daily_limit == 30
        assert acc.is_banned is False
        assert acc.is_active is True

    def test_phone_number_unique(self, db):
        acc1 = UserbotAccount(phone_number="+15550002222", session_file_path="/tmp/a.session")
        acc2 = UserbotAccount(phone_number="+15550002222", session_file_path="/tmp/b.session")
        db.add(acc1)
        db.commit()
        db.add(acc2)
        with pytest.raises(Exception):
            db.commit()
        db.rollback()

    def test_reset_daily_counts(self, db):
        acc = UserbotAccount(
            phone_number="+15550003333",
            session_file_path="/tmp/c.session",
            daily_message_count=25,
        )
        db.add(acc)
        db.commit()
        acc.reset_daily_counts()
        assert acc.daily_message_count == 0

    def test_warmup_state_transition(self, db):
        acc = UserbotAccount(phone_number="+15550004444", session_file_path="/tmp/d.session")
        acc.warmup_state = WarmupState.warming
        db.add(acc)
        db.commit()
        assert acc.warmup_state == WarmupState.warming

        acc.warmup_state = WarmupState.warm
        db.commit()
        assert acc.warmup_state == WarmupState.warm
