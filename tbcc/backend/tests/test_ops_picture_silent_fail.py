"""Ops picture surfaces class-2 silent-fail probes as blockers."""

from __future__ import annotations

from app.services.ops_picture_report import derive_blockers


def test_derive_blockers_emits_silent_fail_never_seen():
    report = {
        "silent_fail": {
            "verdict": "never_seen",
            "probes": [
                {
                    "id": "enrich_backlog",
                    "verdict": "never_seen",
                    "stop_evidence": "tbcc:enrich_backlog:last_success=0",
                },
                {"id": "intake_all_lanes", "verdict": "ok"},
            ],
        }
    }
    blockers = derive_blockers(report)
    hits = [b for b in blockers if b["id"] == "silent_fail_enrich_backlog"]
    assert len(hits) == 1
    assert hits[0]["severity"] == "high"
    assert "never_seen" in hits[0]["what"]


def test_derive_blockers_skips_idle_and_ok():
    report = {
        "silent_fail": {
            "probes": [
                {"id": "storage_hub_r2_export", "verdict": "idle"},
                {"id": "intake_all_lanes", "verdict": "ok"},
            ]
        }
    }
    blockers = derive_blockers(report)
    assert not any(str(b.get("id", "")).startswith("silent_fail_") for b in blockers)
