"""Phase 2 secretary clone registry helpers."""

from app.services.secretary_bot_instances import (
    list_active_instances,
    mask_bot_token,
    tokens_for_host,
    upsert_instance,
)


def test_mask_bot_token():
    assert mask_bot_token("") == ""
    assert "…" in mask_bot_token("123456:ABCDEFghijklmnop")


def test_upsert_and_tokens_for_host(db, monkeypatch):
    monkeypatch.setenv("TBCC_SECRETARY_BOT_TOKEN", "111:PRIMARYTOKENVALUE")
    monkeypatch.delenv("SECRETARY_BOT_TOKEN", raising=False)
    row = upsert_instance(
        db,
        bot_token="222:CLONETOKENVALUE99",
        bot_username="aof_sales_clone",
        label="clone-a",
    )
    assert row.id
    assert len(list_active_instances(db)) == 1
    toks = tokens_for_host(db)
    assert len(toks) == 2
    assert toks[0]["is_primary"] is True
    assert toks[1]["bot_username"] == "aof_sales_clone"
