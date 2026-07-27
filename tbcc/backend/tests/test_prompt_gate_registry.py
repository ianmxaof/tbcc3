"""prompt_gate registry — drift queue, supersede, and import."""

from __future__ import annotations

from unittest.mock import patch

from app.database.session import SessionLocal, engine
from app.models.base import Base
from app.models.prompt_gate import (
    PROMPT_GATE_STATUS_FAILED,
    PROMPT_GATE_STATUS_PENDING,
    PROMPT_GATE_STATUS_PROVISIONED,
    PROMPT_GATE_STATUS_SUPERSEDED,
    PROMPT_GATE_STATUS_TAKEDOWN,
    PromptGate,
)
from app.services.prompt_gate_lookup import active_prompt_gate_row, hash_prompt_body
from app.services.prompt_gate_registry import (
    apply_provision_success,
    import_catalog_items,
    list_provision_queue,
    mark_provision_failed,
    probe_and_requeue_takedowns,
    upsert_catalog_row,
)


def _ensure_table() -> None:
    PromptGate.__table__.drop(engine, checkfirst=True)
    Base.metadata.create_all(engine, tables=[PromptGate.__table__])


def test_upsert_unchanged_when_hash_matches() -> None:
    _ensure_table()
    db = SessionLocal()
    try:
        body = "SFW border prompt v1"
        row = PromptGate(
            key="border_v1",
            prompt_body=body,
            body_hash=hash_prompt_body(body),
            lv_url="https://link-target.net/1367336/abc",
            status=PROMPT_GATE_STATUS_PROVISIONED,
        )
        db.add(row)
        db.commit()

        kept, action = upsert_catalog_row(db, "border_v1", body)
        assert action == "unchanged"
        assert kept.id == row.id
        assert db.query(PromptGate).count() == 1
    finally:
        db.close()


def test_upsert_body_drift_queues_new_pending_row() -> None:
    _ensure_table()
    db = SessionLocal()
    try:
        old_body = "SFW border prompt v1"
        row = PromptGate(
            key="border_v1",
            prompt_body=old_body,
            body_hash=hash_prompt_body(old_body),
            lv_url="https://link-target.net/1367336/old",
            status=PROMPT_GATE_STATUS_PROVISIONED,
        )
        db.add(row)
        db.commit()

        new_body = "SFW border prompt v2 — revised chrome"
        new_row, action = upsert_catalog_row(db, "border_v1", new_body)
        assert action == "queued_drift"
        assert new_row.status == PROMPT_GATE_STATUS_PENDING
        assert new_row.body_hash == hash_prompt_body(new_body)
        assert active_prompt_gate_row(db, "border_v1").id == row.id
    finally:
        db.close()


def test_apply_provision_success_supersedes_prior() -> None:
    _ensure_table()
    db = SessionLocal()
    try:
        body = "SFW prompt"
        old = PromptGate(
            key="k1",
            prompt_body=body,
            body_hash=hash_prompt_body(body),
            lv_url="https://link-target.net/1367336/old",
            status=PROMPT_GATE_STATUS_PROVISIONED,
        )
        new = PromptGate(
            key="k1",
            prompt_body=body + " v2",
            body_hash=hash_prompt_body(body + " v2"),
            status=PROMPT_GATE_STATUS_PENDING,
        )
        db.add_all([old, new])
        db.commit()

        apply_provision_success(db, new, "https://link-target.net/1367336/new", probe={"flags": ["LV_SHELL"]})
        db.refresh(old)
        db.refresh(new)

        assert new.status == PROMPT_GATE_STATUS_PROVISIONED
        assert old.status == PROMPT_GATE_STATUS_SUPERSEDED
        assert old.superseded_by_id == new.id
        assert active_prompt_gate_row(db, "k1").lv_url.endswith("/new")
    finally:
        db.close()


def test_list_provision_queue_includes_failed_by_default() -> None:
    _ensure_table()
    db = SessionLocal()
    try:
        db.add(
            PromptGate(
                key="pending_k",
                prompt_body="body a",
                body_hash=hash_prompt_body("body a"),
                status=PROMPT_GATE_STATUS_PENDING,
            )
        )
        db.add(
            PromptGate(
                key="failed_k",
                prompt_body="body b",
                body_hash=hash_prompt_body("body b"),
                status=PROMPT_GATE_STATUS_FAILED,
            )
        )
        db.commit()

        queue = list_provision_queue(db)
        assert len(queue) == 2
        assert {item.row.key for item in queue} == {"pending_k", "failed_k"}
    finally:
        db.close()


def test_import_catalog_items() -> None:
    _ensure_table()
    db = SessionLocal()
    try:
        counts = import_catalog_items(
            db,
            [
                {"key": "a", "prompt_body": "alpha"},
                {"key": "b", "prompt_body": "beta", "tier": "T3"},
            ],
        )
        assert counts["queued_new"] == 2
        assert db.query(PromptGate).count() == 2
    finally:
        db.close()


def test_probe_and_requeue_takedowns() -> None:
    _ensure_table()
    db = SessionLocal()
    try:
        body = "SFW prompt"
        row = PromptGate(
            key="takedown_k",
            prompt_body=body,
            body_hash=hash_prompt_body(body),
            lv_url="https://link-target.net/1367336/dead",
            status=PROMPT_GATE_STATUS_PROVISIONED,
        )
        db.add(row)
        db.commit()

        with patch(
            "app.services.linkvertise_dashboard_provision.probe_lv_gate",
            return_value={"flags": ["TAKEDOWN"], "ok": False},
        ):
            queued = probe_and_requeue_takedowns(db)

        db.refresh(row)
        assert row.status == PROMPT_GATE_STATUS_TAKEDOWN
        assert len(queued) == 1
        assert queued[0].row.status == PROMPT_GATE_STATUS_PENDING
        assert queued[0].reason == "takedown_requeue"
    finally:
        db.close()


def test_mark_provision_failed() -> None:
    _ensure_table()
    db = SessionLocal()
    try:
        row = PromptGate(
            key="fail_k",
            prompt_body="x",
            body_hash=hash_prompt_body("x"),
            status=PROMPT_GATE_STATUS_PENDING,
        )
        db.add(row)
        db.commit()
        mark_provision_failed(db, row, reason="guidelines")
        db.refresh(row)
        assert row.status == PROMPT_GATE_STATUS_FAILED
    finally:
        db.close()
