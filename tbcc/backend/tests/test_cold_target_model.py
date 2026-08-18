import pytest
from datetime import datetime
from app.models.cold_target import ColdTarget, TargetStatus
from app.models.userbot_account import UserbotAccount


class TestColdTargetModel:
    def test_create_target_defaults(self, db):
        t = ColdTarget(telegram_username="testuser1")
        db.add(t)
        db.commit()
        assert t.id is not None
        assert t.status == TargetStatus.new
        assert t.source is None
        assert t.first_contact_at is None

    def test_status_transitions(self, db):
        t = ColdTarget(telegram_username="testuser2")
        db.add(t)
        db.commit()

        t.status = TargetStatus.contacted
        db.commit()
        assert t.status == TargetStatus.contacted

        t.status = TargetStatus.engaging
        db.commit()
        assert t.status == TargetStatus.engaging

        t.status = TargetStatus.converted
        db.commit()
        assert t.status == TargetStatus.converted

    def test_assign_userbot(self, db):
        acc = UserbotAccount(phone_number="+15550005555", session_file_path="/tmp/e.session")
        db.add(acc)
        db.commit()

        t = ColdTarget(telegram_username="testuser3", assigned_userbot_id=acc.id)
        db.add(t)
        db.commit()
        assert t.assigned_userbot_id == acc.id

    def test_string_user_id(self, db):
        t = ColdTarget(telegram_user_id="9876543210")
        db.add(t)
        db.commit()
        assert t.telegram_user_id == "9876543210"
