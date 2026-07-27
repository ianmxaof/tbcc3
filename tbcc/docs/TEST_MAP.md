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
| **Loot** | `tests/test_loot_*.py`, `tests/test_lane_readiness_robocopy.py`, `tests/test_zip_flywheel.py`, `tests/test_pack_gate_wrap.py`, `tests/test_lane_drop_checkpoint.py`, `tests/test_prompt_gate_lookup.py`, `tests/test_prompt_gate_registry.py`, `tests/test_linkvertise_text_selectors.py`, `tests/test_aof_loot_goblin_promo.py`, `tests/test_prompt_gate_placement.py` | Pack pool, VIP pull, free/key roll, tier cards; lane economy; zip flywheel; LV ingest; prompt_gate registry + placement guards |
| **Companion** | `tests/test_companion_*.py` | Access, generation, stars |
| **AOF / VIP** | `tests/test_aof_*.py` | Checkout, captions, packs, hub→loot CTA |
| **Erome** | `tests/test_erome_*.py`, `tests/test_market_intel_probe.py`, `tests/test_market_intel_cycle.py`, `tests/test_erome_upload_governance.py`, `tests/test_erome_browse_intel.py`, `tests/test_cross_site_intel_report.py` | Upload, private staging governance, ingest, crawler, browse-intel (incl. ThisVid platform rows), cross-site revenue report helpers, Reddit probe, weekly cycle |
| **Scheduler** | `tests/test_post_scheduler.py`, `tests/test_scheduler_*.py` | |
| **Telegram** | `tests/test_telegram_*.py`, `tests/test_tbcc_telegram_admin.py` | |
| **Storage / Mega** | `tests/test_mega_*.py`, `tests/test_storage_*.py` | |
| **Link gate** | `tests/test_link_gate.py` | |
| **Format engine** | `tests/test_format_engine.py` | |
| **Growth** | `tests/test_growth_reaction.py`, `tests/test_content_signals.py` | |
| **Env secrets / capture** | `tests/test_tbcc_env_secret_store.py` | Clipboard/.env key suggest + write |
| **Zeus / secretary menu** | `tests/test_zeus_menu.py` | Phase 1 hub callbacks, stack HTML, deep-link keyboards |
| **Leave-message cleanup** | `tests/test_leave_message_cleanup.py` | Env flags + chat allowlist for Loot Room “X left” sweep |
| **Zeus HTTP (3a)** | `tests/test_zeus_v1.py` | Read-only `/zeus/v1/stack/status` alias of `/ops/stack-status` |
| **Zeus multi-app host** | `tests/test_zeus_multi_app.py` | Co-host lifecycle (mocked PTB); spike gated by `TBCC_ZEUS_COHOST_SPIKE` (secretary+macro_search) |
| **Remixer Cover** | `tests/test_remixer_cover.py` | `/cover` toggle + `copy_message` echo + send-to-channel |
| **Human gate pacing** | `tests/test_human_gate_pacing.py` | Robot ack opt-in, funnel RAG seed, DM outreach pool |
| **Scrape transport** | `tests/test_scrape_transport.py` | Cancel/skip/overview phases for Ingest transport |
| **Scrape tag map / views** | `tests/test_scrape_tag_pool_map.py`, `tests/test_aof_lane_tag_map.py` | Hashtag→canonical `big_tits` lanes + emoji/disk folder helpers |
| **Watch folder AOF lanes** | `tests/test_watch_folder_aof_lanes.py` | Sidecar tag→`🍒 AOF BIG TITS` / disk `AOF BIG TITS`; preprocess skip when `aof_preprocessed` |
| **Buffer X link order** | `tests/test_buffer_x_link_order.py` | Affiliate-first preview pin; optional cycle when `AFFILIATE_FIRST=0` |
| **Sale FOMO announce** | `tests/test_sale_public_announce.py` | Anonymous network + Buffer/X on fulfilled sales (no buyer PII) |
| **Gumroad Ping fulfill** | `tests/test_gumroad_ping.py`, `tests/test_aof_vip_membership.py` | EPO `tbcc_ref` → fulfill; VIP ladder ↔ ynnulc recurrences / price cents |
| **X promo / Gemini** | `tests/test_gemini_promo_prompt.py`, `tests/test_loot_tier_cards.py`, `tests/test_export_perchance_prompt_packs.py`, `tests/test_creative_orchestrator.py`, `tests/test_perchance_image_client.py`, `tests/test_aof_media_brand_naming.py`, `tests/test_r2_promo_upload.py` | Promo + loot builders; R2 `library/` + `sfw-x-promo/` key helpers; Perchance/watermark brand; API needs GEMINI_API_KEY |
| **LLM completions** | `tests/test_llm_completions_providers.py` | OpenRouter / Featherless / Venice / custom OpenAI-compatible runtime presets (`tbcc_uncensored_chat.py`) |
| **ThisVid** | `tests/test_thisvid_upload_provision.py` | Playwright upload MVP (local + URL mode) |
| **ThisVid ext infinite scroll** | `node --test tbcc/extension/tests/thisvid-infinite-scroll-stress.test.mjs` | n+1 HTML engine RAM caps (from repo root); shared `thisvid-infinite-scroll.js` |
| **Keep2share** | `tests/test_keep2share_client.py` | |
| **Import / mirror** | `tests/test_mirror_after_channel_import.py`, `tests/test_channel_import_timeout.py` | |
| **Rules / docs only** | skip tests | Lint or file verify instead |
| **Unknown area** | `pytest tests/ -x -q -k <keyword>` | Prefer adding a row here after |

Full suite (slow): `py -3.13 -m pytest tests/ -q`
