# Sprint State

**Last updated:** 2026-07-13 (anonymous sale announce → network + Buffer/X)

## Sprint goal

Fully automated agent workflow — zero slash commands; ship-log and session rituals run on situational triggers + scheduled tasks.

## In flight

| Item | Owner | Notes |
|------|-------|-------|
| Sale FOMO announce | agent | **2026-07-13:** every fulfilled sale (loot key / pack / sub) → anonymous post to Telegram network + Buffer/X (`TBCC_SALE_ANNOUNCE_*`). Hooked from `notify_sale_fulfilled`; Celery `sale_announce_worker`. |
| Celery home backlog + import priority | agent | **2026-07-12:** resume + seed + watchdog dedupe/import priority. Tray Services copy rewrite + **Services triage chips** (health cache, Fix all / conflict rows, severity paint). **Scheduler stall fix:** enqueue lock TTL capped 15m; drain requeues on lock timeout; drain wait 180s; cleared 18→0 overdue. |
| Userscript monorepo + FetLife suite | agent | **v1.4 + ext 1.30:** Profile & stories tab — social-proof count pad + story types nested (no FAB). |
| Perchance Gemini-parity suite | agent | Prompt packs + suite; **headless** `run_perchance_headless.py` + `perchance_image_client` (verify→generate→disk/R2/loot). Gemini CLI fallback. |
| ThisVid upload MVP | agent | Playwright CLI + **extension ThisVid enhancer 1.31** (title filter + **Erome-parity infinite scroll** n+1). TM suite optional for PervertMonkey. |
| AOF watermark brand rename | agent | After Explorer watermark: `YYYYMMDD · TG@AOFMAINHUB · {content} · allmylinks.comaof69 · {tail}.ext` |
| Creative orchestrator | agent | `/creative/plan` + suite Orch executor + Analytics deploy button; Playwright batch textarea-only |
| Loot key → full `/roll` | agent | Operators **7787282561** + **8630278848** via `tbcc_operator_ids` (VIP/loot/companion/secretary/album). Avatars: `tbcc/assets/botfather/lootgod-avatar-v{1,2}-*.png` (640²). Prefer v2 for contrast. |
| Loot tier cards (Gemini) | agent | Tiers renamed Crumb→Godroll; ASCII `<pre>` dividers; `gemini_loot_card_prompt` + generate script — generate PNGs next; wire into key-roll reveal |
| AOF Main ban → Loot Room public CTA | agent | Cutover done (Main→Loot Group). **Blast fix 2026-07-12:** paused dup bot-cmd id=35; staggered loot liveness/X/cross/bot-cmd next fires 25–210m apart. Note: `t.me/aofmainhub` = affiliate/LV **bulletin board** (not banned Main group); public landing stays `@aof_lootgod_bot?start=loot_free`. |
| Calm Ops Phase 5 (Erome hands-off) | agent | Private staging + governance; **extension transport overlay** (live Pareto intel + Playwright record) |
| Erome browse-intel v4.2 + market intel | agent | TM/ext **v4.3** title keywords + browse-intel; **ext 1.32** grid Like/Repost on thumbnails (no album open). |
| X ↔ Erome flywheel (SFW promo pool + Buffer) | agent | **Gemini CLI** `generate_aof_promo_gemini.py`; R2 upload script; link-order cycle shipped; pool URLs still placeholder |
| XEnhancer download parity | agent | **ext 1.33.1:** MAIN-world GraphQL hook + download without SW `createObjectURL` (direct CDN / data-URL fallback). |
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
