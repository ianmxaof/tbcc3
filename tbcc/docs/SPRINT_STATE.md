# Sprint State

**Last updated:** 2026-07-14 (Zeus `/zeus/v1` read facade; FYP–AOF divider staged)

## Sprint goal

Fully automated agent workflow — zero slash commands; ship-log and session rituals run on situational triggers + scheduled tasks.

## In flight

| Item | Owner | Notes |
|------|-------|-------|
| FYP–AOF Link Hub divider | agent | **2026-07-13:** champagne LED mosaic staged under `tbcc/assets/emoji/fyp-aof-divider/` (14×100² tiles + 7 unique pack). Remixer upload pending — see `PACK_README.md`. |
| Zeus CI/CD prep | agent | **2026-07-14:** 3a facade live + committed; **co-host spike** (`zeus_multi_app` + `zeus_cohost_spike`, gated) — not tray-wired. Next: Phase 2 tray merge of one token after operator smoke. |
| Sale FOMO announce | agent | **2026-07-13:** every fulfilled sale (loot key / pack / sub) → anonymous post to Telegram network + Buffer/X (`TBCC_SALE_ANNOUNCE_*`). Hooked from `notify_sale_fulfilled`; Celery `sale_announce_worker`. |
| Celery home backlog + import priority | agent | **2026-07-14:** Supervisor Phase 2.5: bar sparks, THROTTLE strip, DWM dark title bar, Flt filter crash fix. Relaunch tray to load. |
| Userscript monorepo + FetLife suite | agent | **v1.7 + ext 1.39:** FLConsole 4 privacy presets (editable JSON); place→kinksters input (no hardcoded SJ); cross-tab overlay. |
| Perchance Gemini-parity suite | agent | Prompt packs + suite; **headless** `run_perchance_headless.py` + `perchance_image_client` (verify→generate→disk/R2/loot). Gemini CLI fallback. |
| ThisVid upload MVP | agent | Playwright CLI + **ext 1.37.7**: expanded panel title bar drag (same vertical reposition as chevron); infinite scroll caps; download FAB. |
| AOF watermark brand rename | agent | Burn-in + defaults: **`telegram.me/aofmainhub`** (t.me→telegram.me normalizer for .env/DB; zip `telegram.me_aofmainhub`). Gate retarget: `docs/GATE_LINK_AUDIT.md`. |
| Creative orchestrator | agent | `/creative/plan` + suite Orch executor + Analytics deploy button; Playwright batch textarea-only |
| Loot key → full `/roll` | agent | Operators **7787282561** + **8630278848** via `tbcc_operator_ids` (VIP/loot/companion/secretary/album). Avatars: `tbcc/assets/botfather/lootgod-avatar-v{1,2}-*.png` (640²). Prefer v2 for contrast. |
| Loot tier cards (Gemini) | agent | Tiers renamed Crumb→Godroll; ASCII `<pre>` dividers; `gemini_loot_card_prompt` + generate script — generate PNGs next; wire into key-roll reveal |
| AOF Main ban → Loot Room public CTA | agent | Public loot CTA locked to **https://telegram.me/aof_lootgod_bot** only (no `?start=`). Room invite separate: `+97f4Crv3G1RkMGU5`. LV loot gate must target live room. |
| Calm Ops Phase 5 (Erome hands-off) | agent | Private staging + governance; **extension transport overlay** (live Pareto intel + Playwright record) |
| Erome browse-intel v4.2 + market intel | agent | TM/ext **v4.3**; **ext 1.36** FAB **Videos** tab (paginated copy / → ThisVid) + ↑↓ under FAB; fixed insertBefore crash. |
| Promo affiliate rotation | agent | Seed includes **PornMaker AI** `https://pornmaker.ai?ref=DExnc3FJ` (x_buffer / telegram_footer / links_hub_ai / loot_roll). |
| X ↔ Erome flywheel (SFW promo pool + Buffer) | agent | **Gemini CLI** `generate_aof_promo_gemini.py`; R2 upload script; link-order cycle shipped; pool URLs still placeholder |
| XEnhancer download parity | agent | **ext 1.36.1:** ZIP archive named `TBCC Bundle · {xHandle} · TG@AOFMAINHUB · allmylinks.comaof69.zip` (5-digit fallback). |
| Remote scrape offload (GCP + GHCR) | agent | Scripts + GHCR workflow + capture-secret fix; go-live: create VM + enable-home-offload |
| Scrape transport (Ingest) | agent | JD-ish table: row select → master ▶/⏸/■/skip; columns + progress %; hide/show cols |
| Scrape channel metrics (TGStat-lite) | agent | viewers/members on transport row; hashtag→pool map; hyperlinked t.me; migration 092 |
| X affiliate-first cards | agent | `TBCC_BUFFER_X_AFFILIATE_FIRST=1` default — no bare t.me telegram-globe previews |
| Username search overlay + history UX | agent | FAB modal on SC/CB/OF/IG/X; **gallery nav tab chips**; macrosearch Setup (approve host + template) → Search/Sources |

## Blocked on

- (none)

## CI / stack status (last known)

- `lean-stack-hardening`: Calm Ops phases 1/3/4/6 committed + pushed (liveness backfill, idle governor, celery ops lane, supervisor menu hints).
- Milestone build-in-public post **queued** on @wizardstick69 (~2026-07-05 via Buffer addToQueue).
- Windows task `TBCC-Ship-Log-Tick` registered (Mondays 09:00).
- Content X posts firing on schedule (native/relay — separate from ship-log).
- **Cloud agent primers:** `tbcc/docs/handoffs/CLOUD_AGENT_PRIMERS.md` (universal contract + V1–V14 paste prompts).
- Home stack 11/11 enabled up (2026-07-11); remote scrape VM on Tailscale; `start.ps1` ASCII-sanitized for WinPS 5.1.

## Do not touch

- Secrets, `.env` commits
- Duplicate Telegram bot spawns outside tray (see `tbcc-dev-ops.mdc`)
- **Supervisor panel deep rewrite** — leave foundation grind to Lane C handoff; Cursor only for targeted UX; no live bot Start from agents

## Definition of done (automation sprint)

- [x] `workflow-automation.mdc` — zero-command situational triggers
- [x] `.cursor/hooks.json` — sprint state at session start
- [x] `run_ship_log_tick.py` + weekly Windows task
- [x] Milestone post queued (outcome language, no scheduler IP)
- [ ] Set `TBCC_SHIP_LOG_AUTO_MODE=queue` in `.env` for future milestones auto-queue

## Definition of done (automation sprint)

- [x] `workflow-automation.mdc` — zero-command situational triggers
- [x] `.cursor/hooks.json` — sprint state at session start
- [x] `run_ship_log_tick.py` + weekly Windows task
- [x] Milestone post queued (outcome language, no scheduler IP)
- [ ] Set `TBCC_SHIP_LOG_AUTO_MODE=queue` in `.env` for future milestones auto-queue

## Deferred (do not ladder without "why now")

See `tbcc/docs/TBCC_IMPROVEMENT_NOTES.md` — content distribution schedule, X.com scraper, album poster bot.
