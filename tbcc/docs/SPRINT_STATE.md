# Sprint State

**Last updated:** 2026-07-31 (spicy conversion shipped + operator smoke pass)

## Sprint goal

Fully automated agent workflow — zero slash commands; ship-log and session rituals run on situational triggers + scheduled tasks.

**Control-plane / revenue addendum:** Home = light optional workstation (true lean); money = dedicated ~$5–15/mo Linux island; scrape stays on GCP micro. See `docs/REVENUE_ISLAND.md`.

## In flight

| Item | Owner | Notes |
|------|-------|-------|
| Module A revenue stack | agent + operator | **2026-07-31 — spicy conversion live.** Diagnosis: `photos_sold=0` was traffic starvation (spicy beacon 0 clicks vs ~75 affiliate). Shipped: `TBCC_BUFFER_X_SPICY_BIAS_EVERY=3`, `{spicy}` armory, post-delivery Stars invoice, `/buy` command, ledger error logging. **Operator smoke 2026-07-31:** gate → trial photo → Stars invoice at 25⭐ — pass. **Watch until ~2026-08-07:** `python scripts/island_ops_snapshot.py` on island → `spicy_beacon.hit_count`, `spicy_funnel_14d`, `companion_margin_30d.photos_sold`. Kill: still 0 spicy clicks after 7d → tighten bias to 2 or cut undress affiliate from x_buffer. **COGS:** set `TBCC_COMPANION_UNDRESS_USD_PER_CREDIT` = plan $ ÷ credits from undress invoice (608 credits on island at deploy). Then enable daily pull after attribution week. Docs: `handoffs/2026-07-27_module-a-stack-architect.md`, `handoffs/SPICYBOT_PARITY_SCORECARD.md`. |
| Loot album delivery + import starvation | agent | **2026-07-28 — deployed.** Root cause: Celery import workers hold a long-lived SQLite handle on `admin_import.session`, so paid roll albums starved on "database is locked". Loot reads now run on `admin_album.session` (`_loot_telegram_io`, env `TBCC_LOOT_DELIVERY_SESSION`); batch downloads keep partial results and only quarantine Telegram-confirmed-missing refs (infra failures no longer reject live media — 27 wrongly rejected rows restored). Smoke: album of 5 delivered. Second bug: 783 channel imports failed since 07-21 with `RuntimeError: Cannot run the event loop while another loop is running` (re-entrant `_run_on_worker_loop`) — now deferred + re-queued with backoff instead of failing the job. Saved-msg deprecate left only **124** local `approved` island-wide; **second survivor refill** (`refill_lanes_from_survivors.py --apply --unpause`): **+481** rows → **605** `approved` (most lanes at depth 60; MILF 37, TABOO 12); probed 1320 refs, zero auto-paused schedulers. **Open:** loop re-entrancy unfixed (retry only); recovered stock is recycled — fresh local imports + working storage deposits still needed for loot durability (`TBCC_LOOT_LOCAL_BYTES_ONLY=1`). **Watch:** ABG #9 auto-unpaused (was IP-conflict pause — re-pause via tray if Telethon fights again); #50 drop-ticker, #54/#122 manual BOP, #111 restricted may still need operator attention if not auto-pause flags. |
| Pool album duplicate tiles | agent | **2026-07-24:** `media_album_dedupe` on scheduler + `post_pool_albums`; audit `scripts/audit_pool_album_duplicates.py`. Deploy island + run audit on ASS/ABG pools. |
| Listening relay + loot goblin | agent | **2026-07-26:** Phases 1–4 on island; alembic **102**; natural goblin spawn verified (drop 4, relay_log_id=2); production tuning restored (chance 0.20, cooldown 120). Key-roll album delivery fixed via `admin_import.session` (`local-20260725-2030`). Phase 5 Bot API relay = plan in `docs/handoffs/2026-07-26_relay-bot-api-phase5-plan.md`. |
| True lean home cold-start | agent | **2026-07-15:** Lean = API + celery + beat + payment + loot; album_composer no longer mandatory; dashboard/secretary/post lanes default Off. Post-cutover: `TBCC_REVENUE_ISLAND_ACTIVE=1` + `mark-home-bots-off.ps1` keeps home payment/loot Off. |
| Tray trust (Phase B honesty) | operator | Meltdown/`THROTTLE`/`STALE` already in panel — **smoke**, not greenfield. Doc sync done. Lane C only if smoke proves foundation bugs. |
| Revenue island (dedicated VPS) | operator + agent | **2026-07-20:** Named tunnel `api.powercore.app`; Gumroad Ping 200; VIP ladder plans 10–14; checkout schedulers migrated off dead `start=c6` → plan 10 + `cm10` menu. `/uploads` volume on island for bundle zips. Buffer keys sync via `seed-island-env-from-home.ps1`. Home bots stay Off. |
| Loot Lane Economy | agent | **2026-07-27:** Module A+B handoffs shipped; **VIP floor $18** in code; `bonus_album_draws` applied to album size. **Operator:** Gumroad `ynnulc` prices + island reseed + `price:1800`…`30000` PRODUCT_MAP + deploy. Lane Pass still shelved (0/11 ready). |
| Mega → R2 vault | agent | **PAUSED 2026-07-16:** Export killed on island. Hold until media-purpose + Cloudflare profit case decided (ThisVid upload experiments inconclusive). Partial R2 prefix may exist — not the vault. |
| Sale FOMO announce | agent | **2026-07-16:** Hub `main` = **Loot Room** (`-1003927742839`, invite `+97f4…`). Clear `TBCC_SALE_ANNOUNCE_SKIP_KEYS`. Island FOMO targets `network,buffer`. Bake `aof_network.py` into GHCR. |
| Save AOF + watch lanes | agent | **2026-07-15:** Plan shipped — `aof_lane_tag_map` + watch preprocess/route; Ext Save AOF (watermark-bytes → inbox + `.tbcc-meta.json`); overlay Download = Save AOF by default. Folders: emoji `🍒 AOF BIG TITS` or `TBCC_WATCH_AOF_FOLDER_STYLE=disk` → `AOF NETWORK/AOF BIG TITS`. |
| R2 watermark upload menus | agent | **2026-07-15:** Ext **1.40.5** — context **Watermark → R2 aof-media (library)** + **R2 SFW X promo** (`library/` / `sfw-x-promo/` via `POST /import/watermark-upload-r2`). Set `TBCC_R2_BUCKET=aof-media`. |
| Motherless enhancer | agent | **2026-07-19:** Ext **1.40.30** — Intel tab: grid auto-scan + Pareto/Live + auto-push at max. Prior: thumb ♥ 📣 🖼 👥. |
| Loot Room leave sweep | agent | **2026-07-19:** Shared `leave_message_cleanup` on secretary + **loot-bot** (island money path) + album composer. Needs bot admin in Loot Room; `TBCC_CLEAN_LEAVE_MESSAGES=1` (default). Restart loot/secretary after pull. |
| FYP–AOF Link Hub divider | agent | **Live:** `fyp_aof_divider_v2_by_7787282561` — Saved Messages preview #110075; add via https://t.me/addemoji/fyp_aof_divider_v2_by_7787282561. Paste: F Y P · · A O F. |
| Zeus CI/CD prep | operator | **2026-07-22 smoke:** Alembic **095+** live (`click_links` tables; head **096**). Click beacon green — `POST /zeus/v1/click-links`, `GET /r/{slug}` → 302 + hit row (`?id=` works). Island `TBCC_CLICK_BEACON_PUBLIC_BASE=https://api.powercore.app`. Home `.env` has `TBCC_ZEUS_COHOST_SPIKE=1`; tray secretary+macro_search **Off** — enable secretary only when testing co-host (tokens in Dashboard). Remixer `/cover` smoke: start album_composer, forward photo in DM. |
| Celery home backlog + import priority | agent | **2026-07-14:** Supervisor: champagne diamond CPU/RAM meters (heat + flutter sparkle). Relaunch tray to load. |
| Userscript monorepo + FetLife suite | agent | **v1.8.0:** Clear place/ASL + no place→ASL sync; kinksters Resume bookmark; build writes `extension/fetlife-suite.bundle.js`. Survey: `docs/FETLIFE_MOD_SURVEY.md`. |
| Perchance Gemini-parity suite | agent | **extension-only** `perchance-suite.bundle.js` (no TM). **0.3 / ext 1.40.9:** Loot God Card Lab (border+primer+Δ subject), lean page, jobs. Reload TBCC after `userscripts` npm build. |
| ThisVid upload MVP | agent | **ext 1.40.30:** Erome Videos → R2 library watermark → `my_video_upload` From-a-URL auto-paste. |
| Erome browse-intel v4.2 + market intel | agent | **2026-07-19:** Shared `tbcc-browse-intel-common` — auto-push at max (keep 20%) on ER/TV/ML; TV+ML Pareto/Live captures; ML grid auto-scan. |
| AOF watermark brand rename | agent | Burn-in + defaults: **`telegram.me/aofmainhub`** (t.me→telegram.me normalizer for .env/DB; zip `telegram.me_aofmainhub`). Gate retarget: `docs/GATE_LINK_AUDIT.md`. |
| Creative orchestrator | agent | `/creative/plan` + suite Orch executor + Analytics deploy button; Playwright batch textarea-only |
| Loot key → full `/roll` | agent | **2026-07-16:** Shared-library eligibility — all named TBCC pools banded **1–10** (22 enabled on island); `_pools_for_tier` uses every loot_enabled row. Temp until true 1:1 tier pools. Bake docker-cp into GHCR. |
| Loot tier cards (Gemini/Perchance) | agent | **2026-07-22:** Animated reveal path shipped — `loot_reveal_video.py`, 5 background loops, `TBCC_LOOT_REVEAL_VIDEO=1` + Celery offload flag. Island deploy in flight (ffmpeg in Dockerfile). Item 5 (Mini App) → Frontier. |
| AOF Main ban → Loot Room public CTA | agent | Public loot CTA locked to **https://telegram.me/aof_lootgod_bot** only (no `?start=`). Room invite separate: `+97f4Crv3G1RkMGU5`. LV loot gate must target live room. |
| Calm Ops Phase 5 (Erome hands-off) | agent | Private staging + governance; **extension transport overlay** (live Pareto intel + Playwright record) |
| Promo affiliate rotation | agent | Seed includes **PornMaker AI** `https://pornmaker.ai?ref=DExnc3FJ` (x_buffer / telegram_footer / links_hub_ai / loot_roll). |
| Stars bait outreach (DM + channel pace) | agent | **2026-07-22:** Island `local-20260722-0610`; alembic **097** head; funnel RAG +9; scheduler **#148** (15 bait variations). DM pace: `ENABLED=1` batch=2 / 60min; pool=19 users. Smoke: `?start=bait_loot`. |
| Stars bait outreach (DM + channel pace) | agent | **2026-07-22:** Island `local-20260722-0610`; alembic **097** head; funnel RAG +9 patterns; scheduler **#148** (15 bait variations). DM pace: `ENABLED=1` batch=2 / 60min; pool=19 users. Smoke: `?start=bait_loot` on payment bot. |
| X ↔ Erome flywheel (SFW promo pool + Buffer) | agent | **2026-07-22:** `TBCC_POOL_BUFFER_MIRROR=0` on island (no false Erome claims). Honest opener + `#erome` only when URL present; armory reseeded (16 items w/ hashtags). Re-enable mirror when Erome upload reliable. |
| AI curated packs relist | agent | **2026-07-20:** `seed_ai_curated_packs.py` — legacy AI zips → $3 / 250⭐ / crypto bundles with 3-image promo albums in `/packs` catalog. |
| XEnhancer download parity | agent | **ext 1.40.7:** per-post DL → AOF name under `Downloads/tbcc/inbox` + sidecar (`defer_preprocess`); watch organizer watermarks. ZIP archive still `TBCC Bundle · …`. |
| Remote scrape offload (GCP + GHCR) | agent | Scripts + GHCR workflow + capture-secret fix; go-live: create VM + enable-home-offload |
| Scrape transport (Ingest) | agent | JD-ish table: row select → master ▶/⏸/■/skip; columns + progress %; hide/show cols |
| Site intel frontier prompts | agent | **2026-07-16:** Answered + wired — ext **1.40.8**: Motherless RSS→intel Push; ThisVid uploader+dur bands; Erome dur tags; FetLife thin opt-in Intel; backend multi-platform tag scores. Doc: `SITE_INTEL_FRONTIER_PROMPTS.md`. Tunnel for `:8000`. |
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
- **No agent Start** of payment/loot (home or island) — operator cutover only
- **Supervisor panel deep rewrite** — meltdown already shipped; Lane C only if operator smoke proves foundation bugs; Cursor = targeted UX only

## Definition of done (automation sprint)

- [x] `workflow-automation.mdc` — zero-command situational triggers
- [x] `.cursor/hooks.json` — sprint state at session start
- [x] `run_ship_log_tick.py` + weekly Windows task
- [x] Milestone post queued (outcome language, no scheduler IP)
- [ ] Set `TBCC_SHIP_LOG_AUTO_MODE=queue` in operator `.env` (never commit secrets)

## Definition of done (revenue island ladder)

- [x] Phase A true lean home + post-cutover Off docs/helpers
- [x] Phase B meltdown honesty (docs) — operator smoke pending
- [x] Phase C island compose + queue audit (`celery,subscription,telegram`) + `REVENUE_ISLAND.md`
- [~] Phase D operator cutover (island bots live; Gumroad+crypto+Stars checkout; scheduler copy fixed; home payment/loot Off; tray relaunch + Tailscale still open)
- [x] Phase E sprint-state patch

## Deferred (do not ladder without "why now")

See `tbcc/docs/TBCC_IMPROVEMENT_NOTES.md` — content distribution schedule, X.com scraper, album poster bot.
