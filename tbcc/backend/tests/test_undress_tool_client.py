"""Tests for undress API error formatting."""

from __future__ import annotations

from app.services.undress_tool_client import _format_http_error


def test_format_validation_detail():
    body = {
        "detail": [
            {"loc": ["body", "breast_size"], "msg": "Input should be 'small', 'normal' or 'big'", "type": "enum"}
        ]
    }
    msg = _format_http_error(422, body)
    assert "breast_size" in msg
    assert "big" in msg


def test_default_photo_poses_nonempty():
    from app.services.undress_tool_client import DEFAULT_PHOTO_POSES

    assert "Wet girl" in DEFAULT_PHOTO_POSES
    assert len(DEFAULT_PHOTO_POSES) >= 10
