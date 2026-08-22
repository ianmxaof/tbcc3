"""Topic-qualified source_channel ("telegram:{chat}#topic:{thread}") must still
resolve to the Storage Hub for lazy-fetch downloads. Index-only channel/topic
deposits (_index_channel_message) store this compound form; before this fix,
_is_storage_hub_source did a bare equality check and never matched it, so
vision classify's lazy Telethon fetch fell through to Saved Messages and 404'd
for every index-only-imported item (2026-08-22 regression, found while
verifying the AOF INBOX auto-classify pipeline)."""

from __future__ import annotations

import pytest

from app.api.media import _extract_storage_hub_chat_ident, _is_storage_hub_source
from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT


@pytest.mark.parametrize(
    "raw,expected",
    [
        (STORAGE_HUB_IDENT, STORAGE_HUB_IDENT),
        (f"telegram:{STORAGE_HUB_IDENT}", STORAGE_HUB_IDENT),
        (f"telegram:{STORAGE_HUB_IDENT}#topic:22569", STORAGE_HUB_IDENT),
        (f"{STORAGE_HUB_IDENT}#topic:22569", STORAGE_HUB_IDENT),
        ("", ""),
        (None, ""),
    ],
)
def test_extract_storage_hub_chat_ident(raw, expected):
    assert _extract_storage_hub_chat_ident(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        STORAGE_HUB_IDENT,
        f"telegram:{STORAGE_HUB_IDENT}",
        f"telegram:{STORAGE_HUB_IDENT}#topic:22569",
        f"telegram:{STORAGE_HUB_IDENT}#topic:3058",
    ],
)
def test_is_storage_hub_source_matches_topic_qualified_forms(raw):
    assert _is_storage_hub_source(raw) is True


@pytest.mark.parametrize(
    "raw",
    [None, "", "https://t.me/somechannel", "12345", "telegram:12345#topic:1"],
)
def test_is_storage_hub_source_rejects_non_hub_sources(raw):
    assert _is_storage_hub_source(raw) is False
