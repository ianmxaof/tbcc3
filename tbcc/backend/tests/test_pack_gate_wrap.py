"""Pack ingest gate order: Linkvertise → AdMaven → work.ink."""

from __future__ import annotations

from app.services.pack_gate_wrap import ingest_gate_provider_order, wrap_pack_gates_on_ingest


def test_ingest_order_defaults_lv_first(monkeypatch) -> None:
    monkeypatch.setenv("TBCC_LINKVERTISE_PUBLISHER_ID", "1367336")
    monkeypatch.setenv("TBCC_ADMAVEN_API_TOKEN", "adm-token")
    monkeypatch.setenv("TBCC_WORKINK_BASE_LINK", "https://work.ink/test/slug")
    monkeypatch.delenv("TBCC_LINK_GATE_PROVIDERS", raising=False)
    assert ingest_gate_provider_order()[0] == "linkvertise"
    assert "admaven" in ingest_gate_provider_order()
    assert "workink" in ingest_gate_provider_order()


def test_wrap_prefers_linkvertise(monkeypatch) -> None:
    monkeypatch.setenv("TBCC_LINKVERTISE_PUBLISHER_ID", "1367336")
    monkeypatch.setenv("TBCC_ADMAVEN_API_TOKEN", "adm-token")
    monkeypatch.setenv("TBCC_WORKINK_BASE_LINK", "https://work.ink/test/slug")
    monkeypatch.setenv("TBCC_LINK_GATE_PROVIDERS", "linkvertise,admaven,workink")
    monkeypatch.setenv("TBCC_LINKVERTISE_BASE_URL", "https://link-center.net")

    dest = "https://media.powercore.app/packs/flywheel/smoke.zip"
    result = wrap_pack_gates_on_ingest(dest)
    assert result.provider == "linkvertise"
    assert result.gate_lv_url and "/dynamic" in result.gate_lv_url
    assert result.primary_url == result.gate_lv_url
    assert result.gate_adm_url is None
    assert result.destination_url == dest


def test_wrap_falls_back_to_admaven(monkeypatch) -> None:
    monkeypatch.delenv("TBCC_LINKVERTISE_PUBLISHER_ID", raising=False)
    monkeypatch.setenv("TBCC_ADMAVEN_API_TOKEN", "adm-token")
    monkeypatch.setenv("TBCC_LINK_GATE_PROVIDERS", "linkvertise,admaven,workink")

    def _fake_wrap(target_url: str, *, provider=None, publisher_id=None, seed=None):
        if provider == "admaven":
            return "https://speedy-links.com/s?testFallback", "admaven"
        raise RuntimeError(f"no {provider}")

    monkeypatch.setattr("app.services.pack_gate_wrap.wrap_gate_url", _fake_wrap)
    result = wrap_pack_gates_on_ingest("https://example.com/a.zip")
    assert result.provider == "admaven"
    assert result.gate_adm_url == "https://speedy-links.com/s?testFallback"
