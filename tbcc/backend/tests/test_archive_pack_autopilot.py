"""Archive → AOF packs autopilot."""

from app.services.archive_pack_autopilot import archive_auto_pack_queue_enabled
from app.services.loot_pack_pool import is_pack_candidate_url


def test_archive_auto_pack_queue_enabled_default_on():
    assert archive_auto_pack_queue_enabled() is True


def test_is_pack_candidate_mega():
    assert is_pack_candidate_url("https://mega.nz/folder/abc#key") is True


def test_is_pack_candidate_erome_not_pack():
    assert is_pack_candidate_url("https://www.erome.com/a/abc") is False
