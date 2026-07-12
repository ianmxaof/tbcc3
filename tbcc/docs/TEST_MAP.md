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
| **Erome** | `tests/test_erome_*.py`, `tests/test_market_intel_probe.py`, `tests/test_market_intel_cycle.py`, `tests/test_erome_upload_governance.py` | Upload, private staging governance, ingest, crawler, browse-intel, Reddit probe, weekly cycle |
| **Scheduler** | `tests/test_post_scheduler.py`, `tests/test_scheduler_*.py` | |
| **Telegram** | `tests/test_telegram_*.py`, `tests/test_tbcc_telegram_admin.py` | |
| **Storage / Mega** | `tests/test_mega_*.py`, `tests/test_storage_*.py` | |
| **Link gate** | `tests/test_link_gate.py` | |
| **Format engine** | `tests/test_format_engine.py` | |
| **Growth** | `tests/test_growth_reaction.py`, `tests/test_content_signals.py` | |
| **Env secrets / capture** | `tests/test_tbcc_env_secret_store.py` | Clipboard/.env key suggest + write |
| **Zeus / secretary menu** | `tests/test_zeus_menu.py` | Phase 1 hub callbacks, stack HTML, deep-link keyboards |
| **Scrape transport** | `tests/test_scrape_transport.py` | Cancel/skip/overview phases for Ingest transport |
| **Scrape tag map / views** | `tests/test_scrape_tag_pool_map.py` | Hashtag→pool suggestions + view sample helpers |
| **Buffer X link order** | `tests/test_buffer_x_link_order.py` | Affiliate-first preview pin; optional cycle when `AFFILIATE_FIRST=0` |
| **X promo / Gemini** | `tests/test_gemini_promo_prompt.py`, `tests/test_loot_tier_cards.py` | Promo + loot card prompt builders; API needs GEMINI_API_KEY |
| **Keep2share** | `tests/test_keep2share_client.py` | |
| **Import / mirror** | `tests/test_mirror_after_channel_import.py`, `tests/test_channel_import_timeout.py` | |
| **Rules / docs only** | skip tests | Lint or file verify instead |
| **Unknown area** | `pytest tests/ -x -q -k <keyword>` | Prefer adding a row here after |

Full suite (slow): `py -3.13 -m pytest tests/ -q`
