"""Tests for companion webhook payload parsing."""

from __future__ import annotations

import asyncio
import base64

from app.api.webhooks_companion import _decode_payload_image, _extract_job_key


def test_extract_job_key_accepts_id_field():
    payload = {"id": "tg_7787282561_7787282561_d875ee1fdad1", "photo": "abc"}
    assert _extract_job_key(payload) == "tg_7787282561_7787282561_d875ee1fdad1"


def test_extract_job_key_prefers_id_gen():
    payload = {"id_gen": "tg_1_2_aaa", "id": "other"}
    assert _extract_job_key(payload) == "tg_1_2_aaa"


def test_decode_payload_image_from_base64_photo():
    raw = base64.b64encode(b"\xff\xd8" + b"x" * 200).decode()
    out = _decode_payload_image({"photo": raw}, None)
    assert out is not None
    assert len(out) > 100


def test_handle_json_undress_webhook_delivers(monkeypatch):
    from app.api import webhooks_companion as wh
    from app.services.companion_jobs import CompanionJob, get_job, pop_job, put_job

    jid = "tg_100_200_testjson"
    put_job(CompanionJob(job_id=jid, chat_id=100, user_id=200, provider="undress", created_at=1.0))
    sent: list[dict] = []

    async def fake_send(**kwargs):
        sent.append(kwargs)
        return True

    monkeypatch.setattr(wh, "send_result_photo_bytes", fake_send)
    monkeypatch.setattr(wh, "send_companion_menu_after_delivery", fake_send)

    upsell_calls: list[dict] = []

    async def fake_upsell(**kwargs):
        upsell_calls.append(kwargs)
        return True

    monkeypatch.setattr(
        "app.services.companion_stars.maybe_offer_stars_after_delivery",
        fake_upsell,
    )
    img = base64.b64encode(b"\xff\xd8" + b"y" * 300).decode()

    async def _run():
        return await wh._handle_payload("undress", {"id": jid, "photo": img})

    result = asyncio.run(_run())
    assert result.get("delivered") == "photo_bytes"
    assert sent and sent[0]["chat_id"] == 100
    assert upsell_calls and upsell_calls[0]["user_id"] == 200
    assert pop_job(jid) is None
    assert get_job(jid) is None
