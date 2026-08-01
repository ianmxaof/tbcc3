"""Saved Messages deprecation policy for loot."""

from unittest.mock import patch

from app.services.loot_media_deliverable import is_loot_media_roll_candidate
from app.services.saved_messages_policy import loot_local_bytes_only


def test_loot_local_bytes_only_default_on():
    with patch.dict("os.environ", {}, clear=False):
        assert loot_local_bytes_only() is True


def test_saved_ref_excluded_when_local_only():
    from unittest.mock import MagicMock

    from app.models.media import Media

    row = MagicMock(spec=Media)
    row.id = 1
    row.telegram_message_id = 999
    row.file_id = "tg:abc"
    row.status = "approved"
    with patch("app.services.loot_media_deliverable.loot_local_bytes_only", return_value=True):
        assert is_loot_media_roll_candidate(row) is False


def test_saved_ref_allowed_when_legacy_mode():
    from unittest.mock import MagicMock

    from app.models.media import Media

    row = MagicMock(spec=Media)
    row.id = 2
    row.telegram_message_id = 999
    row.file_id = "tg:abc"
    row.status = "approved"
    with patch("app.services.loot_media_deliverable.loot_local_bytes_only", return_value=False):
        assert is_loot_media_roll_candidate(row) is True
