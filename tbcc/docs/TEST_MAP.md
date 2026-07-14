# TBCC Test Map

Feature area → pytest path for completion gates. Run from repo root unless noted.

```powershell
cd tbcc/backend
py -3.13 -m pytest <path> -x -q
```

| Area | Path / pattern | Notes |
|------|----------------|-------|
| **Ops / stack** | `tests/test_tbcc_stack_control.py` | Tray adapter, stack CLI |
| **Ops alerts** | `tests/test_ops_alert_smoke.py`, `test_ops_restart_grace.py`, `test_ops_workflow_runner.py` | |
| **Loot** | `tests/test_loot_*.py` | Pack pool, VIP pull, free/key roll, tier cards / Gemini prompts |
| **Companion** | `tests/test_companion_*.py` | Access, generation, stars |
| **AOF / VIP** | `tests/test_aof_*.py` | Checkout, captions, packs, hub→loot CTA |
| **Erome** | `tests/test_erome_*.py`, `tests/test_market_intel_probe.py`, `tests/test_market_intel_cycle.py`, `tests/test_erome_upload_governance.py`, `tests/test_erome_browse_intel.py` | Upload, private staging governance, ingest, crawler, browse-intel (incl. ThisVid platform rows), Reddit probe, weekly cycle |
| **Scheduler** | `tests/test_post_scheduler.py`, `tests/test_scheduler_*.py` | |
| **Telegram** | `tests/test_telegram_*.py`, `tests/test_tbcc_telegram_admin.py` | |
| **Storage / Mega** | `tests/test_mega_*.py`, `tests/test_storage_*.py` | |
| **Link gate** | `tests/test_link_gate.py` | |
| **Format engine** | `tests/test_format_engine.py` | |
| **Growth** | `tests/test_growth_reaction.py`, `tests/test_content_signals.py` | |
| **Env secrets / capture** | `tests/test_tbcc_env_secret_store.py` | Clipboard/.env key suggest + write |
| **Zeus / secretary menu** | `tests/test_zeus_menu.py` | Phase 1 hub callbacks, stack HTML, deep-link keyboards |
| **Zeus HTTP (3a)** | `tests/test_zeus_v1.py` | Read-only `/zeus/v1/stack/status` alias of `/ops/stack-status` |
| **Zeus multi-app host** | `tests/test_zeus_multi_app.py` | Co-host lifecycle (mocked PTB); spike gated by `TBCC_ZEUS_COHOST_SPIKE` |
| **Scrape transport** | `tests/test_scrape_transport.py` | Cancel/skip/overview phases for Ingest transport |
| **Scrape tag map / views** | `tests/test_scrape_tag_pool_map.py` | Hashtag→pool suggestions + view sample helpers |
| **Buffer X link order** | `tests/test_buffer_x_link_order.py` | Affiliate-first preview pin; optional cycle when `AFFILIATE_FIRST=0` |
| **Sale FOMO announce** | `tests/test_sale_public_announce.py` | Anonymous network + Buffer/X on fulfilled sales (no buyer PII) |
| **X promo / Gemini** | `tests/test_gemini_promo_prompt.py`, `tests/test_loot_tier_cards.py`, `tests/test_export_perchance_prompt_packs.py`, `tests/test_creative_orchestrator.py`, `tests/test_perchance_image_client.py`, `tests/test_aof_media_brand_naming.py` | Promo + loot builders; Perchance pack export + headless client; watermark brand rename; creative orchestrator; API needs GEMINI_API_KEY |
| **ThisVid** | `tests/test_thisvid_upload_provision.py` | Playwright upload MVP (local + URL mode) |
| **Keep2share** | `tests/test_keep2share_client.py` | |
| **Import / mirror** | `tests/test_mirror_after_channel_import.py`, `tests/test_channel_import_timeout.py` | |
| **Rules / docs only** | skip tests | Lint or file verify instead |
| **Unknown area** | `pytest tests/ -x -q -k <keyword>` | Prefer adding a row here after |

Full suite (slow): `py -3.13 -m pytest tests/ -q`
