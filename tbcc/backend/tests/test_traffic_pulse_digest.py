"""Traffic Pulse digest suppress + recurring issue fingerprint."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.admin_inbox import (
    REDIS_KEY_RECURRING_ISSUES,
    bump_recurring_issue,
    format_recurring_issues_html,
    list_recurring_issues,
)
from app.services.secretary_report_copy import pulse_digest_fingerprint, pulse_issue_id
from app.services.traffic_pulse import (
    REDIS_DIGEST_COUNTS,
    REDIS_DIGEST_LAST_FINGERPRINT,
    REDIS_DIGEST_SUPPRESS_STREAK,
    clear_digest_buffer,
    send_traffic_pulse_digest,
)


@pytest.fixture(autouse=True)
def _clear_digest():
    clear_digest_buffer()
    yield
    clear_digest_buffer()


def test_pulse_issue_id_ignores_post_count():
    low = {"post_ok": 1, "start": 0, "beacon": 0}
    high = {"post_ok": 9, "start": 0, "beacon": 0}
    assert pulse_issue_id(low) == "cta_no_bot_start"
    assert pulse_issue_id(high) == "cta_no_bot_start"
    assert pulse_digest_fingerprint(low, []) == pulse_digest_fingerprint(high, [])


def test_bump_recurring_issue_increments(monkeypatch):
    store: dict[str, str] = {}

    class FakeRedis:
        def hget(self, key, field):
            return store.get(f"{key}:{field}")

        def hset(self, key, field, value):
            store[f"{key}:{field}"] = value

        def hgetall(self, key):
            prefix = f"{key}:"
            return {k[len(prefix) :]: v for k, v in store.items() if k.startswith(prefix)}

        def hdel(self, key, field):
            store.pop(f"{key}:{field}", None)

    monkeypatch.setattr("app.services.admin_inbox._redis_client", lambda: FakeRedis())
    first = bump_recurring_issue("cta_no_bot_start", title="read", action="fix cta")
    second = bump_recurring_issue("cta_no_bot_start", title="read", action="fix cta")
    assert first["count"] == 1
    assert second["count"] == 2
    listed = list_recurring_issues()
    assert listed[0]["issue_id"] == "cta_no_bot_start"
    html = format_recurring_issues_html(listed)
    assert "×2" in html
    assert "Posts ship" in html


def test_digest_suppresses_repeat_fingerprint(monkeypatch):
    monkeypatch.setenv("TBCC_TRAFFIC_PULSE_DIGEST_SUPPRESS_AFTER", "1")

    state = {
        REDIS_DIGEST_COUNTS: {"post_ok": "1"},
        REDIS_DIGEST_LAST_FINGERPRINT: "",
        REDIS_DIGEST_SUPPRESS_STREAK: "0",
    }

    class FakeRedis:
        def hgetall(self, key):
            if key == REDIS_DIGEST_COUNTS:
                return dict(state.get(REDIS_DIGEST_COUNTS, {}))
            if key.endswith(":refs"):
                return {}
            return {}

        def hget(self, key, field):
            if key == REDIS_KEY_RECURRING_ISSUES:
                return state.get(f"recur:{field}")
            return state.get(key)

        def hset(self, key, field=None, value=None, mapping=None):
            if mapping:
                for k, v in mapping.items():
                    state[f"{key}:{k}"] = v
            elif field is not None:
                if key == REDIS_KEY_RECURRING_ISSUES:
                    state[f"recur:{field}"] = value
                else:
                    state[f"{key}:{field}"] = value

        def hdel(self, key, field):
            state.pop(f"{key}:{field}", None)
            state.pop(f"recur:{field}", None)

        def get(self, key):
            return state.get(key)

        def set(self, key, value):
            state[key] = value

        def incr(self, key):
            state[key] = str(int(state.get(key) or 0) + 1)
            return int(state[key])

        def delete(self, *keys):
            for k in keys:
                state.pop(k, None)

    fake = FakeRedis()
    monkeypatch.setattr("app.services.traffic_pulse._redis", lambda: fake)
    monkeypatch.setattr("app.services.admin_inbox._redis_client", lambda: fake)

    sent: list[str] = []

    def _capture(text, **_kw):
        sent.append(text)

    monkeypatch.setattr("app.services.admin_inbox._telegram_send_html", _capture)
    monkeypatch.setattr("app.services.admin_inbox.bump_recurring_issue", lambda *a, **k: {"count": 1})

    first = send_traffic_pulse_digest()
    state[REDIS_DIGEST_COUNTS] = {"post_ok": "3"}
    second = send_traffic_pulse_digest()

    assert first.get("sent") is True
    assert second.get("skipped") is True
    assert second.get("reason") == "unchanged_fingerprint"
    assert len(sent) == 1
