# Sprint State

**Last updated:** 2026-07-12

## Sprint goal

Fully automated agent workflow — zero slash commands; ship-log and session rituals run on situational triggers + scheduled tasks.

## In flight

| Item | Owner | Notes |
|------|-------|-------|
| Userscript monorepo + FetLife suite v1 | agent | `tbcc/userscripts` scaffold + CI; dist `fetlife-suite.user.js` (masonry, story filter, mute, newest discussions) |
| Loot key → full `/roll` | agent | **Shipped 2026-07-12:** `is_loot_key_holder` + `POST /loot/key-roll/claim`; card reveal→divider→album; `loot_roll` affiliate footer. Drop PNGs in `app/data/loot_tier_cards/tier-N.png` (or `TBCC_LOOT_TIER_CARD_DIR`). Tag affiliates with placement `loot_roll`. |
| Loot tier cards (Gemini) | agent | Tiers renamed Crumb→Godroll; ASCII `<pre>` dividers; `gemini_loot_card_prompt` + generate script — generate PNGs next; wire into key-roll reveal |
| AOF Main ban → Loot Room public CTA | agent | Cutover done (Main→Loot Group). **Blast fix 2026-07-12:** paused dup bot-cmd id=35; staggered loot liveness/X/cross/bot-cmd next fires 25–210m apart. Note: `t.me/aofmainhub` = affiliate/LV **bulletin board** (not banned Main group); public landing stays `@aof_lootgod_bot?start=loot_free`. |
| Calm Ops Phase 5 (Erome hands-off) | agent | Private staging + governance; **extension transport overlay** (live Pareto intel + Playwright record) |
| Erome browse-intel v4.2 + market intel | agent | TM v4.2; Reddit probe; weekly cycle; intel-week staging sidecar |
| X ↔ Erome flywheel (SFW promo pool + Buffer) | agent | **Gemini CLI** `generate_aof_promo_gemini.py`; R2 upload script; link-order cycle shipped; pool URLs still placeholder |
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
- **Supervisor full panel** — benched (slow/unstable; needs pagination + global on/off before production use)

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
