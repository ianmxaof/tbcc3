"""A deposit that misses enrich (focus pause, Telethon failure, worker restart)
was never retried — run_auto_tag_enrich_for_media returns early and nothing
re-queues it, so the item sits with no lane decision and no quarantine card.
These cover the backstop sweep that re-drives those rows.
"""

from __future__ import annotations

import pytest

from app.services import enrich_backlog

STORAGE_SOURCE = "telegram:-1003812457581#topic:22569"


@pytest.fixture(autouse=True)
def _storage_hub_ident(monkeypatch):
    monkeypatch.setattr(
        "app.services.storage_deposit_auto_approve.is_storage_hub_source_label",
        lambda src: src == STORAGE_SOURCE,
    )


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *cols):
        # The decided-ids query feeds Media.id.in_(), which needs a real
        # expression list — a plain list of ids satisfies it.
        if len(cols) == 1:
            return []
        return _Query(self._rows)

    def close(self):
        pass


def test_sweep_returns_only_storage_hub_media():
    db = _Session([(3, STORAGE_SOURCE), (2, "telegram:scrape-channel"), (1, STORAGE_SOURCE)])

    assert enrich_backlog.find_unclassified_media(db, limit=10, max_age_hours=72) == [3, 1]


def test_sweep_honours_limit():
    rows = [(i, STORAGE_SOURCE) for i in range(10, 0, -1)]

    got = enrich_backlog.find_unclassified_media(_Session(rows), limit=3, max_age_hours=72)

    assert got == [10, 9, 8]


def test_sweep_skips_while_focus_pause_active(monkeypatch):
    monkeypatch.setattr("app.services.focus_profile.pause_auto_tag_work", lambda: True)
    stamped = {"n": 0}
    monkeypatch.setattr(
        enrich_backlog, "mark_last_success", lambda: stamped.__setitem__("n", stamped["n"] + 1)
    )

    # Re-driving during telegram_relief would just re-skip and burn Telethon.
    assert enrich_backlog.run_enrich_backlog_sweep() == {
        "ok": True,
        "skipped": "focus_pause_auto_tag",
    }
    assert stamped["n"] == 1


def test_sweep_disabled_by_env(monkeypatch):
    monkeypatch.setenv("TBCC_ENRICH_BACKLOG_SWEEP", "0")
    stamped = {"n": 0}
    monkeypatch.setattr(
        enrich_backlog, "mark_last_success", lambda: stamped.__setitem__("n", stamped["n"] + 1)
    )

    assert enrich_backlog.run_enrich_backlog_sweep() == {"ok": True, "skipped": "disabled"}
    assert stamped["n"] == 0


def test_sweep_enqueues_each_missed_media(monkeypatch):
    monkeypatch.setattr("app.services.focus_profile.pause_auto_tag_work", lambda: False)
    monkeypatch.setattr(
        enrich_backlog, "find_unclassified_media", lambda db, **k: [51, 52]
    )
    monkeypatch.setattr("app.database.session.SessionLocal", lambda: _Session([]))
    stamped = {"n": 0}
    monkeypatch.setattr(
        enrich_backlog, "mark_last_success", lambda: stamped.__setitem__("n", stamped["n"] + 1)
    )

    monkeypatch.setenv("TBCC_ENRICH_BACKLOG_STAGGER_S", "20")
    queued: list[tuple[list[int], int]] = []
    monkeypatch.setattr(
        "app.workers.media_auto_tag_worker.auto_tag_media_enrich",
        type(
            "T",
            (),
            {
                "apply_async": staticmethod(
                    lambda args, countdown: queued.append((args, countdown))
                )
            },
        )(),
    )

    out = enrich_backlog.run_enrich_backlog_sweep()

    # Staggered so a tick does not put N concurrent downloads on the Telethon
    # session, which is what tripped the lock-storm detector.
    assert queued == [([51], 0), ([52], 20)]
    assert out["queued"] == 2
    assert stamped["n"] == 1


def test_limit_is_clamped(monkeypatch):
    monkeypatch.setenv("TBCC_ENRICH_BACKLOG_LIMIT", "9999")
    assert enrich_backlog.backlog_limit() == 200

    monkeypatch.setenv("TBCC_ENRICH_BACKLOG_LIMIT", "not-a-number")
    assert enrich_backlog.backlog_limit() == 5
