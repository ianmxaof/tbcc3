from __future__ import annotations

import os
import json
from types import SimpleNamespace

from app.data.aof_x_promo_defaults import AOF_X_PROMO_DEFAULTS
from app.models.caption_snippet import CaptionSnippet
from app.models.listening_relay_settings import ListeningRelaySettings
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_growth_hub import build_addlist_footer, build_links_hub_bulletin
from app.services.aof_network_promo_text import build_mega_pack_readme_text
from app.services.aof_public_copy_cutover import apply_public_copy_cutover
from app.services.local_media_watermark import ensure_local_watermark_defaults
from app.services.reddit_surface_caption import build_reddit_body


def test_links_hub_bulletin_uses_loot_public_entry(monkeypatch):
    monkeypatch.delenv("TBCC_AOF_PUBLIC_CTA_MODE", raising=False)
    text = build_links_hub_bulletin({}, db=None)

    assert "@aof_lootgod_bot" in text
    assert "Loot Room" in text
    assert "Main Group" not in text
    assert "aofmainhub" not in text


def test_addlist_footer_uses_loot_entry(monkeypatch):
    monkeypatch.delenv("TBCC_AOF_PUBLIC_CTA_MODE", raising=False)
    text = build_addlist_footer({})

    assert "loot bot" in text
    assert "loot room" in text
    assert "aofmainhub" not in text


def test_mega_readme_uses_loot_entry(monkeypatch):
    monkeypatch.delenv("TBCC_WORKINK_BASE_LINK", raising=False)
    text = build_mega_pack_readme_text()

    assert "Loot Bot (first contact)" in text
    assert "Loot Room Group (public commons)" in text
    assert "Main hub" not in text
    assert "Main group" not in text


def test_reddit_direct_policy_uses_loot_entry(monkeypatch):
    monkeypatch.delenv("TBCC_AOF_PUBLIC_CTA_MODE", raising=False)
    profile = SimpleNamespace(link_policy="direct_ok")

    body, comment_link = build_reddit_body(profile)

    assert "Loot entry: https://t.me/aof_lootgod_bot?start=loot_free" in body
    assert "aofmainhub" not in body
    assert comment_link is None


def test_watermark_default_uses_loot_bot(monkeypatch):
    monkeypatch.delenv("TBCC_WATERMARK_TEXT", raising=False)
    ensure_local_watermark_defaults()

    assert os.environ["TBCC_WATERMARK_TEXT"] == "t.me/aof_lootgod_bot"


def test_public_copy_cutover_updates_existing_snippets(db):
    title = AOF_X_PROMO_DEFAULTS[0]["title"]
    db.add(CaptionSnippet(title=title, body="Main hub\nhttps://t.me/+old"))
    db.commit()

    preview = apply_public_copy_cutover(db, execute=False)
    row = db.query(CaptionSnippet).filter(CaptionSnippet.title == title).one()
    assert preview["caption_snippets"]["would_update"] == 1
    assert row.body == "Main hub\nhttps://t.me/+old"

    executed = apply_public_copy_cutover(db, execute=True)
    row = db.query(CaptionSnippet).filter(CaptionSnippet.title == title).one()
    assert executed["caption_snippets"]["updated"] == 1
    assert "https://t.me/aof_lootgod_bot?start=loot_free" in row.body
    assert "Main hub" not in row.body


def test_public_copy_cutover_replaces_relay_blocks_and_queues(db):
    relay = ListeningRelaySettings(id=1)
    relay.message_copy_block_variations = json.dumps(
        [
            "Main hub just moved: https://t.me/+old",
            "custom operator block",
        ]
    )
    relay.set_buffer_x_queue([{"text": "main hub -> https://t.me/+old"}])
    db.add(relay)
    db.commit()

    report = apply_public_copy_cutover(db, execute=True)
    relay = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).one()
    blocks = json.loads(relay.message_copy_block_variations)
    queue = relay.get_buffer_x_queue()

    assert report["relay_copy_blocks"]["replaced_slots"] == 1
    assert blocks[-1] == "custom operator block"
    assert any("aof_lootgod_bot?start=loot_free" in block for block in blocks)
    assert queue
    assert all("main hub" not in item["text"].lower() for item in queue)


def test_public_copy_cutover_sweeps_scheduled_stored_copy(db):
    post = ScheduledTextPost(
        name="stale public copy",
        channel_id=1,
        content="Main Group: https://t.me/+old",
        content_variations=json.dumps(["MAIN COMMUNITY", "custom"]),
        buttons=json.dumps([[{"text": "Main hub", "url": "https://t.me/+old"}]]),
        surface_copy_json=json.dumps({"x": "main group"}),
        buffer_x_queue_json=json.dumps([{"text": "main hub queue"}]),
    )
    db.add(post)
    db.commit()

    report = apply_public_copy_cutover(db, execute=True)
    post = db.query(ScheduledTextPost).filter(ScheduledTextPost.name == "stale public copy").one()

    assert report["scheduled_public_copy"]["updated"] == 1
    assert "Loot Room" in post.content
    assert "PUBLIC ENTRY" in post.content_variations
    assert "Loot entry" in post.buttons
    assert "Loot Room" in post.surface_copy_json
    assert all("main hub" not in item["text"].lower() for item in post.get_buffer_x_queue())
