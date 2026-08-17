# Sprint State

**Last updated:** 2026-08-17 ~12:55 PT — Cerebras/NVIDIA secretary LLM fallback hops

## Sprint goal

Fully automated agent workflow — zero slash commands; ship-log and session rituals run on situational triggers + scheduled tasks.

**Control-plane / revenue addendum:** Home = light optional workstation (true lean); money = dedicated ~$5–15/mo Linux island; scrape stays on GCP micro. Always-on UI: compose `--profile ui` (dashboard + AOF Forum) — see `docs/ISLAND_UI_SURFACES.md`.

## In flight

| Item | Owner | Notes |
|------|-------|-------|
| Module A revenue stack | agent + operator | **2026-08-13 sitrep:** plans 24–26 active (5/15/50 @ 110/300/900⭐) — **0 pack subscriptions yet**; analytics `companion_photos_sold=0` (30d). Paywall + pack CTAs live on island companion/payment. **Operator:** firehose A/B still open; scoreboard empty until first charge. |
| Secretary sales-rep Phase 1 | agent | **2026-08-17:** Cerebras + NVIDIA NIM wired as secretary LLM fallback hops (home `.env` keys; island keys + deploy still needed). Prior: FE G3 ethical charter local/uncommitted; G9 coach; G11 Business turns; G4 LLM emotion. |
| Loot album delivery + import starvation | agent | **2026-08-13 sitrep:** dry-run thin lanes ass/big_tits/goon/full_length (would_restore 118) → **`--apply-refill --unpause` executed on island**. Still need fresh imports + Storage Hub deposits long-term. |
| Pool album duplicate tiles | agent | **2026-08-01 shipped:** sent-cache composer dedupe + per-item cache msg ids + hub fetch (`media_message_resolve`). Island `local-20260801-1911-fix`; `TBCC_SENT_CACHE_ALBUM_SIZE=3`; audit demoted **323** dup rows (voyeur 304, ASS 19). Watch next Loot Room albums for unique tiles. |
| Remixer `/rebundle` any-admin | agent | **2026-08-05:** `/rebundle` + `/rebundle go` (partial + delete sources). Commit `ce5b684`. Island `local-20260805-2117` deployed (album_composer + workers). Operator smoke: `/rebundle` in any admin group or hub **✅ Rebundle (+partial)**. |
| Listening relay + loot goblin | agent | **2026-07-26:** Phases 1–4 on island; alembic **102**; natural goblin spawn verified (drop 4, relay_log_id=2); production tuning restored (chance 0.20, cooldown 120). Key-roll album delivery fixed via `admin_import.session` (`local-20260725-2030`). Phase 5 Bot API relay = plan in `docs/handoffs/2026-07-26_relay-bot-api-phase5-plan.md`. |
| True lean home cold-start | agent | **2026-07-15:** Lean = API + celery + beat + payment + loot; album_composer no longer mandatory; dashboard/secretary/post lanes default Off. Post-cutover: `TBCC_REVENUE_ISLAND_ACTIVE=1` + `mark-home-bots-off.ps1` keeps home payment/loot Off. |
| Tray trust (Phase B honesty) | operator | Meltdown/`THROTTLE`/`STALE` already in panel — **smoke**, not greenfield. Doc sync done. Lane C only if smoke proves foundation bugs. |
| Revenue island (dedicated VPS) | operator + agent | **2026-08-13:** PR #9 (hub/dirty-tree) + PR #10 (phase2 cloud) on `main` `cc66a79`; deploy tag `local-20260813-0833`; all money containers Up. Cloud-only doctrine: no local tray bots. Prior: named tunnel `api.powercore.app`; Gumroad Ping 200; VIP ladder; home bots Off. |
| Loot Lane Economy | agent | **2026-07-27:** Module A+B handoffs shipped; **VIP floor $18** in code; `bonus_album_draws` applied to album size. **2026-08-03:** **VIP Intro Month** $10 / ~834⭐ — first main-section sub only; standard ladder unchanged. Reseed + island deploy. **Operator:** Gumroad add $10 intro tier (`price:1000` in PRODUCT_MAP). Lane Pass still shelved (0/11 ready). |
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
| Promo affiliate rotation | agent | **2026-08-14:** New **AI affiliate (aftrk3)** `priority_tier=5` on x_buffer / telegram_footer / links_hub_ai / loot_roll; hub rotation synced. Cloud Farm + Spicy still tier 0. Secretary `/sponsors` live. |
| Stars bait outreach (DM + channel pace) | agent | **2026-07-22:** Island `local-20260722-0610`; alembic **097** head; funnel RAG +9; scheduler **#148** (15 bait variations). DM pace: `ENABLED=1` batch=2 / 60min; pool=19 users. Smoke: `?start=bait_loot`. |
| Lifecycle DM (renewal + loot + companion re-engage) | agent | **2026-08-02:** daily beat — sub pre/post expiry, loot 7/14d, companion flirt 3/7/14d (`missed_you` deep link). `TBCC_LIFECYCLE_DM_ENABLED=1`. |
| X ↔ Erome flywheel (SFW promo pool + Buffer) | agent | **2026-08-13:** flavor banks healthy (unique_hooks 95–152, PACKS 101); 48h outbound ~354. Buffer MCP rate-limited mid-sitrep — re-sample openers later. Prior: 500 copy templates + island alembic/seed. |
| AI curated packs relist | agent | **2026-07-20:** `seed_ai_curated_packs.py` — legacy AI zips → $3 / 250⭐ / crypto bundles with 3-image promo albums in `/packs` catalog. |
| XEnhancer download parity | agent | **ext 1.40.7:** per-post DL → AOF name under `Downloads/tbcc/inbox` + sidecar (`defer_preprocess`); watch organizer watermarks. ZIP archive still `TBCC Bundle · …`. |
| Remote scrape offload (GCP + GHCR) | agent | Scripts + GHCR workflow + capture-secret fix; go-live: create VM + enable-home-offload |
| Scrape transport (Ingest) | agent | JD-ish table: row select → master ▶/⏸/■/skip; columns + progress %; hide/show cols |
| Site intel frontier prompts | agent | **2026-07-16:** Answered + wired — ext **1.40.8**: Motherless RSS→intel Push; ThisVid uploader+dur bands; Erome dur tags; FetLife thin opt-in Intel; backend multi-platform tag scores. Doc: `SITE_INTEL_FRONTIER_PROMPTS.md`. Tunnel for `:8000`. |
| Scrape channel metrics (TGStat-lite) | agent | viewers/members on transport row; hashtag→pool map; hyperlinked t.me; migration 092 |
| X affiliate-first cards | agent | **2026-08-15:** loot-first X cards (`TBCC_BUFFER_X_LOOT_FIRST=1` default) — `loot_free` beats spicy/affiliate preview. Flywheel captions inject `telegram.me/aof_lootgod_bot?start=loot_free`. Affiliates stay in caption, not the card. |
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

**Week 2–4 hold (AOF three-track, 2026-08-15):** Named Vault un-list, Inner Circle copy, LV cookie files / dead-slug watchdog, topic pins, channel-story boosts — not until Week 1 scoreboard (LV paste + crate tease + flood-safe story oneshot).
