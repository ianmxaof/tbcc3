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


def test_default_video_poses_loaded_from_catalog():
    from app.services.undress_tool_client import DEFAULT_VIDEO_POSES

    assert len(DEFAULT_VIDEO_POSES) >= 100
    names = {p["name"] for p in DEFAULT_VIDEO_POSES}
    assert "Blowjob 360" in names
    assert "Cowgirl POV" in names


def test_check_video_submit_blocked_when_vendor_disallows(monkeypatch):
    import asyncio

    from app.services.undress_tool_client import UndressUserInfo, check_video_submit_allowed

    async def fake_get_me(**_kwargs):
        return UndressUserInfo(
            telegram_id=1,
            balance=707,
            can_create_photos=True,
            can_create_videos=False,
            raw={},
        )

    monkeypatch.setattr("app.services.undress_tool_client.configured", lambda: True)
    monkeypatch.setattr("app.services.undress_tool_client.get_me", fake_get_me)
    ok, msg = asyncio.run(check_video_submit_allowed())
    assert not ok
    assert "can_create_videos" in msg
    assert "707" in msg
