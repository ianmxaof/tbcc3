"""Tests for Keep2Share integration helpers."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from app.services.keep2share_client import (
    check_url_alive,
    is_k2s_host,
    parse_k2s_file_id,
    public_file_url,
)
from app.services.k2s_lane_folders import infer_lane_from_text
from app.services.k2s_mirror_service import merge_k2s_source_note, parse_k2s_tokens


def test_is_k2s_host():
    assert is_k2s_host("https://k2s.cc/file/abc123def456")
    assert is_k2s_host("https://keep2share.cc/folder/abc123def456")
    assert not is_k2s_host("https://mega.nz/folder/abc")


def test_parse_k2s_file_id():
    assert parse_k2s_file_id("https://k2s.cc/file/a4b8776255578") == "a4b8776255578"
    assert parse_k2s_file_id("https://tezfiles.com/folder/0632a04bb0d21") == "0632a04bb0d21"


def test_public_file_url():
    assert public_file_url("abc") == "https://k2s.cc/file/abc"


def test_infer_lane_from_text():
    assert infer_lane_from_text("AOF Taboo drop", "taboo pack") == "taboo"
    assert infer_lane_from_text("voyeur cam pack") == "voyeur"
    assert infer_lane_from_text("AOF AI deepfake") == "ai"
    assert infer_lane_from_text("main group bulletin") == "main"
    assert infer_lane_from_text("loot room modifier") == "loot"


def test_merge_and_parse_k2s_tokens():
    note = merge_k2s_source_note(
        "pack_queue",
        k2s_file_id="abc123",
        k2s_url="https://k2s.cc/file/abc123",
        k2s_lane="taboo",
        k2s_mirror="done",
    )
    tokens = parse_k2s_tokens(note)
    assert tokens["k2s_file_id"] == "abc123"
    assert tokens["k2s_url"] == "https://k2s.cc/file/abc123"
    assert tokens["k2s_lane"] == "taboo"
    assert tokens["k2s_mirror"] == "done"


@patch("app.services.keep2share_client._post")
def test_check_url_alive(mock_post):
    mock_post.return_value = {
        "status": "success",
        "is_available": True,
        "is_folder": False,
        "id": "abc123def456",
    }
    ok, reason = check_url_alive("https://k2s.cc/file/abc123def456")
    assert ok is True
    assert reason is None


@patch("app.services.keep2share_client._post")
def test_check_url_dead(mock_post):
    mock_post.return_value = {
        "status": "success",
        "is_available": False,
        "is_folder": False,
    }
    ok, reason = check_url_alive("https://k2s.cc/file/deaddeaddeadde")
    assert ok is False


@patch("app.services.keep2share_client.check_url_alive")
def test_validate_k2s_in_pipeline(mock_check):
    from app.services.mega_link_pipeline import validate_file_host_has_content

    mock_check.return_value = (True, None)
    ok, reason = validate_file_host_has_content("https://k2s.cc/file/abc123def456")
    assert ok is True
    mock_check.assert_called_once()
