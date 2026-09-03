"""Unit tests for money_path_health (no live network)."""

from __future__ import annotations

from pathlib import Path

from app.services import money_path_health as mph


def test_verdict_rank_worst():
    assert mph.worst_verdict(["ok", "idle"]) == "ok"
    assert mph.worst_verdict(["ok", "stale", "idle"]) == "stale"
    assert mph.worst_verdict(["never_seen", "ok"]) == "never_seen"
    assert mph.worst_verdict([]) == "blocked"


def test_probe_money_path_all_ok(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TBCC_VAULT_NOTES_PATH", str(tmp_path))
    monkeypatch.setenv("TBCC_GUMROAD_PRODUCT_URL", "https://gumroad.example/l/vip")
    monkeypatch.setenv("TBCC_MONEY_PATH_BEACON_SLUG", "wk31-lv-loot")

    def fake_fetch(
        url: str, *, timeout: float = 15.0, follow_redirects: bool = True
    ) -> mph.HttpFetchResult:
        if "api.powercore.app/health" in url:
            return mph.HttpFetchResult(
                status_code=200,
                body='{"status":"ok","crypto_auto_checkout":true,"external_payment_orders_impl":"uuid-epo-v2"}',
                error=None,
            )
        if "telegram.me" in url:
            return mph.HttpFetchResult(status_code=200, body="ok", error=None)
        if "gumroad.example" in url:
            return mph.HttpFetchResult(status_code=200, body="ok", error=None)
        if "/r/wk31-lv-loot" in url:
            return mph.HttpFetchResult(
                status_code=302,
                body="",
                error=None,
                final_url="https://telegram.me/aof_lootgod_bot?start=src_lv_loot_wk31",
            )
        return mph.HttpFetchResult(status_code=0, body="", error=f"unexpected {url}")

    monkeypatch.setattr(mph, "fetch_url_ex", fake_fetch)

    out = mph.probe_money_path(write_vault=True)
    assert out["id"] == "money_path"
    assert out["verdict"] == "ok"
    assert out["stop_kind"] == "http"
    surfaces = {s["id"]: s for s in out["surfaces"]}
    assert surfaces["island_api_health"]["verdict"] == "ok"
    assert surfaces["loot_public_cta"]["verdict"] == "ok"
    assert surfaces["gumroad_default"]["verdict"] == "ok"
    assert surfaces["click_beacon:wk31-lv-loot"]["verdict"] == "ok"

    vault = tmp_path / "3-Resources" / "Revenue" / "money-path-health.md"
    assert vault.is_file()
    text = vault.read_text(encoding="utf-8")
    assert "type: money-path-health" in text
    assert "island_api_health" in text
    assert "suggested: true" in text


def test_probe_money_path_gumroad_idle_when_unset(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TBCC_VAULT_NOTES_PATH", str(tmp_path))
    monkeypatch.delenv("TBCC_GUMROAD_PRODUCT_URL", raising=False)
    monkeypatch.delenv("TBCC_DONATION_URL", raising=False)
    monkeypatch.setenv("TBCC_MONEY_PATH_BEACON_SLUG", "0")

    def fake_fetch(
        url: str, *, timeout: float = 15.0, follow_redirects: bool = True
    ) -> mph.HttpFetchResult:
        if "api.powercore.app/health" in url:
            return mph.HttpFetchResult(
                status_code=200,
                body='{"status":"ok","crypto_auto_checkout":true}',
                error=None,
            )
        if "telegram.me" in url:
            return mph.HttpFetchResult(status_code=200, body="ok", error=None)
        return mph.HttpFetchResult(status_code=0, body="", error=f"unexpected {url}")

    monkeypatch.setattr(mph, "fetch_url_ex", fake_fetch)

    out = mph.probe_money_path(write_vault=False)
    surfaces = {s["id"]: s for s in out["surfaces"]}
    assert surfaces["gumroad_default"]["verdict"] == "idle"
    beacon_rows = [s for s in out["surfaces"] if str(s.get("id", "")).startswith("click_beacon")]
    assert len(beacon_rows) == 1
    assert beacon_rows[0]["verdict"] == "idle"
    assert out["verdict"] == "ok"
    assert not (tmp_path / "3-Resources" / "Revenue" / "money-path-health.md").exists()


def test_beacon_defaults_to_wk31_loot(monkeypatch):
    monkeypatch.delenv("TBCC_MONEY_PATH_BEACON_SLUG", raising=False)
    monkeypatch.delenv("TBCC_MONEY_PATH_BEACON_SLUGS", raising=False)
    monkeypatch.delenv("TBCC_MONEY_PATH_BEACON_WEEK", raising=False)
    slugs = mph._beacon_slugs()
    assert "wk31-lv-loot" in slugs
    assert "wk31-lv-lootgod" in slugs
    assert len(slugs) >= 3
    monkeypatch.setenv("TBCC_MONEY_PATH_BEACON_SLUG", "0")
    assert mph._beacon_slugs() == []


def test_beacon_slugs_from_csv_env(monkeypatch):
    monkeypatch.setenv("TBCC_MONEY_PATH_BEACON_SLUGS", "wk31-lv-loot, wk31-lv-packs")
    assert mph._beacon_slugs() == ["wk31-lv-loot", "wk31-lv-packs"]


def test_click_only_beacons_do_not_expect_start_payload():
    """mainhub/addlist redirect straight to a channel/addlist link with no bot deep-link —
    GATE_LINK_AUDIT.md 'click_only' gate class. A missing ?start= there is not stale."""
    assert mph._beacon_expects_start_payload("wk31-lv-mainhub") is False
    assert mph._beacon_expects_start_payload("wk31-lv-addlist") is False
    assert mph._beacon_expects_start_payload("wk31-lv-loot") is True
    assert mph._beacon_expects_start_payload("wk31-lv-lootgod") is True
    assert mph._beacon_expects_start_payload("plain-slug") is False


def test_mainhub_redirect_without_start_stays_ok(monkeypatch, tmp_path: Path):
    """click_only mainhub beacon: 3xx redirect with no ?start= must not be flagged stale."""
    monkeypatch.setenv("TBCC_VAULT_NOTES_PATH", str(tmp_path))
    monkeypatch.setenv("TBCC_GUMROAD_PRODUCT_URL", "https://gumroad.example/l/vip")
    monkeypatch.setenv("TBCC_MONEY_PATH_BEACON_SLUGS", "wk31-lv-mainhub")
    monkeypatch.delenv("TBCC_MONEY_PATH_BEACON_SLUG", raising=False)

    def fake_fetch(
        url: str, *, timeout: float = 15.0, follow_redirects: bool = True
    ) -> mph.HttpFetchResult:
        if "api.powercore.app/health" in url:
            return mph.HttpFetchResult(
                status_code=200,
                body='{"status":"ok","crypto_auto_checkout":true}',
                error=None,
            )
        if "telegram.me" in url or "gumroad.example" in url:
            return mph.HttpFetchResult(status_code=200, body="ok", error=None)
        if "/r/wk31-lv-mainhub" in url:
            return mph.HttpFetchResult(
                status_code=302,
                body="",
                error=None,
                final_url="https://telegram.me/aofmainhub",
            )
        return mph.HttpFetchResult(status_code=0, body="", error=f"unexpected {url}")

    monkeypatch.setattr(mph, "fetch_url_ex", fake_fetch)
    out = mph.probe_money_path(write_vault=False)
    surfaces = {s["id"]: s for s in out["surfaces"]}
    assert surfaces["click_beacon:wk31-lv-mainhub"]["verdict"] == "ok"


def test_probe_money_path_multi_beacon(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TBCC_VAULT_NOTES_PATH", str(tmp_path))
    monkeypatch.setenv("TBCC_GUMROAD_PRODUCT_URL", "https://gumroad.example/l/vip")
    monkeypatch.setenv("TBCC_MONEY_PATH_BEACON_SLUGS", "wk31-lv-loot,wk31-lv-mainhub")
    monkeypatch.delenv("TBCC_MONEY_PATH_BEACON_SLUG", raising=False)

    def fake_fetch(
        url: str, *, timeout: float = 15.0, follow_redirects: bool = True
    ) -> mph.HttpFetchResult:
        if "api.powercore.app/health" in url:
            return mph.HttpFetchResult(
                status_code=200,
                body='{"status":"ok","crypto_auto_checkout":true}',
                error=None,
            )
        if "telegram.me" in url or "gumroad.example" in url:
            return mph.HttpFetchResult(status_code=200, body="ok", error=None)
        if "/r/wk31-lv-loot" in url:
            return mph.HttpFetchResult(status_code=302, body="", error=None)
        if "/r/wk31-lv-mainhub" in url:
            return mph.HttpFetchResult(status_code=404, body="missing", error=None)
        return mph.HttpFetchResult(status_code=0, body="", error=f"unexpected {url}")

    monkeypatch.setattr(mph, "fetch_url_ex", fake_fetch)
    out = mph.probe_money_path(write_vault=False)
    surfaces = {s["id"]: s for s in out["surfaces"]}
    assert surfaces["click_beacon:wk31-lv-loot"]["verdict"] == "ok"
    assert surfaces["click_beacon:wk31-lv-mainhub"]["verdict"] == "stale"
    assert out["verdict"] == "stale"

    monkeypatch.setenv("TBCC_VAULT_NOTES_PATH", str(tmp_path))
    monkeypatch.delenv("TBCC_GUMROAD_PRODUCT_URL", raising=False)
    monkeypatch.delenv("TBCC_DONATION_URL", raising=False)
    monkeypatch.setenv("TBCC_MONEY_PATH_BEACON_SLUG", "0")

    def fake_fetch(
        url: str, *, timeout: float = 15.0, follow_redirects: bool = True
    ) -> mph.HttpFetchResult:
        if "api.powercore.app/health" in url:
            return mph.HttpFetchResult(
                status_code=200,
                body='{"status":"degraded"}',
                error=None,
            )
        if "telegram.me" in url:
            return mph.HttpFetchResult(status_code=404, body="missing", error=None)
        return mph.HttpFetchResult(status_code=0, body="", error=f"unexpected {url}")

    monkeypatch.setattr(mph, "fetch_url_ex", fake_fetch)

    out = mph.probe_money_path(write_vault=True)
    assert out["verdict"] == "stale"
    assert any("health" in h.lower() or "cta" in h.lower() for h in out.get("friction_hypotheses") or [])
    text = (tmp_path / "3-Resources" / "Revenue" / "money-path-health.md").read_text(
        encoding="utf-8"
    )
    assert "## Friction hypotheses" in text


def test_format_vault_markdown_redacts_nothing_useful():
    payload = {
        "verdict": "ok",
        "generated_at": "2026-09-03T10:00:00Z",
        "surfaces": [
            {
                "id": "island_api_health",
                "verdict": "ok",
                "url": "https://api.powercore.app/health",
                "stop_evidence": 'status=ok crypto_auto_checkout=true',
            }
        ],
        "friction_hypotheses": ["Island health looks fine — no friction from this sweep."],
    }
    md = mph.format_money_path_health_markdown(payload)
    assert "money-path-health" in md
    assert "island_api_health" in md
    assert "api.powercore.app/health" in md
