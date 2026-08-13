"""Sent-cache preview cap controls."""

from app.services import sent_cache_control as scc


def test_preview_max_defaults_to_one(monkeypatch):
    monkeypatch.delenv("TBCC_SENT_CACHE_PREVIEW_MAX_ALBUMS", raising=False)
    monkeypatch.setattr(scc, "_redis", lambda: (_ for _ in ()).throw(RuntimeError("no redis")))
    assert scc.preview_max_loot_albums_per_run() == 1


def test_preview_max_redis_override(monkeypatch):
    store: dict[str, str] = {}

    class _FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, val):
            store[key] = val

    monkeypatch.setattr(scc, "_redis", lambda: _FakeRedis())
    monkeypatch.delenv("TBCC_SENT_CACHE_PREVIEW_MAX_ALBUMS", raising=False)
    assert scc.set_preview_max_loot_albums_per_run(2) == 2
    assert scc.preview_max_loot_albums_per_run() == 2
