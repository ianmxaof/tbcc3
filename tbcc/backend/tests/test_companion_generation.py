"""Tests for companion generation helpers."""

from __future__ import annotations

from app.services.companion_generation import extract_result_urls
from app.services.companion_jobs import CompanionJob, get_job, new_job_id, pop_job, put_job


def test_extract_result_urls_nudify_shape():
    payload = {
        "jobId": "abc",
        "status": "completed",
        "output": {"imageUrl": ["https://cdn.example.com/out.jpg"]},
    }
    assert extract_result_urls(payload) == ["https://cdn.example.com/out.jpg"]


def test_extract_result_urls_undress_flat():
    payload = {"id_gen": "tg_1_2_abc", "status": "ok", "result_url": "https://cdn.example.com/u.jpg"}
    assert extract_result_urls(payload) == ["https://cdn.example.com/u.jpg"]


def test_companion_job_roundtrip_memory():
    jid = new_job_id(chat_id=100, user_id=200)
    put_job(
        CompanionJob(
            job_id=jid,
            chat_id=100,
            user_id=200,
            provider="undress",
            created_at=1.0,
            pending_pose="doggy",
            hold_delivery=True,
        )
    )
    loaded = get_job(jid)
    assert loaded is not None
    assert loaded.chat_id == 100
    assert loaded.pending_pose == "doggy"
    assert loaded.hold_delivery is True
    popped = pop_job(jid)
    assert popped is not None
    assert get_job(jid) is None
