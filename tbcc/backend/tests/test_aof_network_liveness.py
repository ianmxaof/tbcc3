"""Phase 1: public drop-signal gating + internal thin-pool backfill selection."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import aof_growth_hub as gh
from app.services import aof_network_liveness as nl


def _fake_db_with_rows(rows):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = rows
    return db


# --- drop-signal gating ---------------------------------------------------------------------

def test_disable_public_drop_signals_pauses_rows():
    row = SimpleNamespace(
        name=f"{nl.DROP_SIGNAL_PREFIX} — X",
        id=1,
        posting_auto_paused_at=None,
        posting_auto_pause_reason=None,
        send_failure_streak=0,
    )
    db = _fake_db_with_rows([row])
    with patch.object(nl, "liveness_drop_signals_public_enabled", return_value=False):
        out = nl._upsert_drop_signals(db, {}, {"thin_min": 60}, execute=True)
    assert out[0]["status"] == "disabled"
    assert row.posting_auto_paused_at is not None
    assert row.posting_auto_pause_reason == nl.DROP_SIGNAL_DISABLE_REASON


def test_disable_is_idempotent_and_preserves_real_pause_reason():
    row = SimpleNamespace(
        name=f"{nl.DROP_SIGNAL_PREFIX} — Y",
        id=2,
        posting_auto_paused_at="already",
        posting_auto_pause_reason="send failed: flood",
    )
    db = _fake_db_with_rows([row])
    out = nl._disable_public_drop_signals(db, execute=True)
    assert out[0]["status"] == "already_disabled"
    assert row.posting_auto_pause_reason == "send failed: flood"  # not clobbered


def test_reactivate_clears_only_our_sentinel_pauses():
    ours = SimpleNamespace(
        name=f"{nl.DROP_SIGNAL_PREFIX} — A",
        posting_auto_paused_at="ts",
        posting_auto_pause_reason=nl.DROP_SIGNAL_DISABLE_REASON,
        send_failure_streak=3,
    )
    theirs = SimpleNamespace(
        name=f"{nl.DROP_SIGNAL_PREFIX} — B",
        posting_auto_paused_at="ts",
        posting_auto_pause_reason="send failed: flood",
        send_failure_streak=5,
    )
    db = _fake_db_with_rows([ours, theirs])
    nl._reactivate_public_drop_signals(db)
    assert ours.posting_auto_paused_at is None and ours.send_failure_streak == 0
    assert theirs.posting_auto_paused_at == "ts"  # real send-failure pause untouched


# --- thin-pool backfill selection -----------------------------------------------------------

def _backfill(depths, *, execute):
    with patch.object(gh, "CONTENT_LANE_NETWORK_KEYS", frozenset(depths)), patch.object(
        gh, "_pool_content_depth", side_effect=lambda db, pid: depths[pid]
    ), patch(
        "app.services.export_flywheel_service.pool_id_for_network_key",
        side_effect=lambda db, k: k,
    ), patch.object(
        gh, "queue_storage_hub_deposits", return_value={"ok": True, "matched_count": 1}
    ) as q:
        out = gh.backfill_thin_pools_from_storage_hub(MagicMock(), execute=execute)
    return out, q


def test_backfill_queues_only_below_median_lanes():
    # median([2,10,10,20]) = 10 -> only "a" (2) is below.
    out, q = _backfill({"a": 2, "b": 10, "c": 10, "d": 20}, execute=True)
    assert out["median"] == 10
    assert out["thin_lanes"] == ["a"]
    q.assert_called_once()
    assert q.call_args.kwargs["topic_keys"] == ["a"]
    assert q.call_args.kwargs["include_topic_mirror"] is False


def test_backfill_dry_run_does_not_queue():
    out, q = _backfill({"a": 1, "b": 5}, execute=False)
    assert out["would_queue"] == ["a"]
    q.assert_not_called()


def test_backfill_no_thin_when_all_equal():
    out, q = _backfill({"a": 5, "b": 5, "c": 5}, execute=True)
    assert out["thin_lanes"] == []
    assert out["reason"] == "no_thin_lanes"
    q.assert_not_called()
