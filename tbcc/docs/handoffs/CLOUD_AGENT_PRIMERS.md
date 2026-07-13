# TBCC Cloud Agent Primers

**Purpose:** Paste-ready prompts so a Cursor Cloud Agent can own one vertical without prior chat history.

**How to use**

1. Copy **Universal contract** (once).
2. Append **one vertical primer** below.
3. Add a single concrete task line at the end (`Task: …`).
4. Cloud agent = branch + PR + tests. Do **not** operate the live Windows tray or Telegram sessions.

**Repo root:** `telegram_bot2` (TBCC lives under `tbcc/`).  
**Warm start:** always read `tbcc/docs/SPRINT_STATE.md` and this file’s universal rules first.  
**Last synced:** 2026-07-11

---

## Universal contract (paste first)

```text
You are a Cursor Cloud Agent working on TBCC (Telegram Bot Command Center) in repo telegram_bot2 / tbcc/.

## Product
TBCC runs a 24/7 adult-content revenue flywheel: scrape/ingest → pools → Telegram schedule → Buffer/X mirrors → loot/promo bots. Home Windows PC runs API, bots, Beat, Postgres, Redis (tray supervisor). Optional GCP VM consumes Celery `scrape` over Tailscale + GHCR image.

## Non-negotiables
1. NEVER commit secrets, `.env`, session files (`*.session*`), tokens, or Credential Manager dumps.
2. NEVER spawn Telegram bots or Celery workers that talk to live Telegram. No `POST /bots/runtime/*/start`. Process ownership is Windows tray / `tbcc-stack-cli.ps1` on the operator machine only.
3. NEVER run parallel heavy scrapes against the same Telethon session (SQLite lock / 409 risk).
4. Prefer small PRs. Touch only files needed for THIS vertical.
5. Before edits: read `tbcc/docs/SPRINT_STATE.md` (Do not touch + In flight). Read mapped tests in `tbcc/docs/TEST_MAP.md`.
6. After logic changes: run the mapped pytest (or note why skipped). Keep ASCII-only in PowerShell scripts (no em-dashes/smart quotes — WinPS 5.1 misparses UTF-8 without BOM).
7. Do not unbench the Supervisor full panel unless the task explicitly says so (needs pagination + global on/off first).
8. Output: summary of changes, tests run, residual risks, suggested next slice for this vertical.

## Environment assumptions
- You have a cloned git repo and can install Python deps / run pytest.
- You do NOT have the operator’s live `.env`, Telegram sessions, or tray.
- Use mocks/fixtures; do not require live Buffer/Telegram/GCP to merge.
```

---

## Vertical index

| ID | Vertical | Best for cloud? |
|----|----------|-----------------|
| V1 | Agent workflow / automation sprint | Yes |
| V2 | Userscript monorepo + FetLife suite | Yes |
| V3 | Loot tier cards (Gemini) | Yes (assets/scripts) |
| V4 | AOF Main ban → Loot Room CTA | Yes |
| V5 | Calm Ops Phase 5 — Erome hands-off | Partial (code); live Playwright on operator |
| V6 | Erome browse-intel + market intel | Yes |
| V7 | X ↔ Erome flywheel (SFW promo + Buffer) | Yes |
| V8 | Remote scrape offload (GCP + GHCR) | Yes (scripts/docs/CI) |
| V9 | Scrape transport (Ingest UI/API) | Yes |
| V10 | Scrape channel metrics (TGStat-lite) | Yes |
| V11 | X affiliate-first cards | Yes |
| V12 | Username search overlay + gallery UX | Yes |
| V13 | Zeus / Secretary menu | Yes |
| V14 | Lean stack / ops reliability | Careful — no live process control |

---

## V1 — Agent workflow / automation sprint

```text
VERTICAL: Agent workflow automation (sprint goal)
MISSION: Zero slash-command rituals; situational triggers + scheduled tasks own ship-log / session close / preflight.

READ FIRST:
- tbcc/docs/SPRINT_STATE.md
- tbcc/docs/TBCC_PROTOCOLS.md
- .cursor/rules/workflow-automation.mdc
- .cursor/hooks.json

KEY PATHS:
- tbcc/backend/scripts/ship_log_*.py, milestone_ship.py, run_ship_log_tick.py
- tbcc/scripts/register-ship-log-scheduled-task.ps1
- tbcc/docs/automations/*.json

CURRENT STATE:
- workflow-automation.mdc, hooks, weekly Windows ship-log task: done.
- Still open: set TBCC_SHIP_LOG_AUTO_MODE=queue in operator .env (operator-only; document, do not commit .env).

DONE WHEN:
- Docs/scripts make auto-queue mode clear; no secret commits; tests for any script logic you touch.

Task: <one concrete slice>
```

---

## V2 — Userscript monorepo + FetLife suite

```text
VERTICAL: Userscript monorepo + FetLife suite v1
MISSION: Maintain tbcc/userscripts as a buildable monorepo; ship dist/fetlife-suite.user.js with masonry, story filter, mute, newest discussions (and related features) without breaking Tampermonkey headers.

READ FIRST:
- tbcc/userscripts/README.md
- tbcc/userscripts/packages/fetlife-suite/manifest.json
- tbcc/docs/erome-enhancer/TAMPERMONKEY_SECURITY.md (security patterns)

KEY PATHS:
- tbcc/userscripts/packages/fetlife-suite/**
- tbcc/userscripts/packages/shared/**
- tbcc/userscripts/scripts/build.mjs, lint-headers.mjs
- tbcc/userscripts/dist/fetlife-suite.user.js

CURRENT STATE:
- Scaffold + CI + dist suite with core features shipped.
- Next: harden tests, polish UX, keep build deterministic.

DONE WHEN:
- npm test / build green; header lint clean; dist regenerated if sources change.

Task: <one concrete slice>
```

---

## V3 — Loot tier cards (Gemini)

```text
VERTICAL: Loot tier cards (Gemini)
MISSION: Generate and wire loot-tier presentation cards (Crumb→Godroll rename already done) via Gemini prompts/scripts; ASCII <pre> dividers; produce PNGs for bot/UX use.

READ FIRST:
- tbcc/backend/app/services/gemini_loot_card_prompt.py
- tbcc/backend/app/services/loot_tier_catalog.py
- tbcc/backend/app/services/loot_roll_presentation.py
- tbcc/backend/scripts/generate_aof_loot_card_gemini.py
- tbcc/docs/samples/gemini_loot_card_layout_lock.txt
- tests: tbcc/backend/tests/test_loot_tier_cards.py

KEY PATHS:
- services above + bots/loot_bot.py (presentation only if needed)
- app/data/aof_loot_card_presets.json

CURRENT STATE:
- Prompt + generate script + tier rename done.
- Next: generate PNG assets; wire URLs/paths safely without hardcoding secrets.

DONE WHEN:
- pytest test_loot_tier_cards passes; generation script documented; no API keys in repo.

Task: <one concrete slice>
```

---

## V4 — AOF Main ban → Loot Room public CTA

```text
VERTICAL: AOF Main ban → Loot Room public CTA
MISSION: While AOF Main is banned, all public hub/referral/Buffer CTAs point to @aof_lootgod_bot?start=loot_free. VIP fulfillment stays unchanged. Daily promo is Buffer-only (no Main channel posts).

READ FIRST:
- tbcc/docs/AOF_QUICK_COPY_HUB.md
- tbcc/docs/loot-room-pinned-instructions.md
- tbcc/backend/app/services/aof_growth_hub.py
- tbcc/backend/app/services/aof_social_links.py
- tbcc/backend/app/services/loot_daily_promo.py
- tests: test_aof_hub_loot_cta.py, test_loot_daily_promo.py

CURRENT STATE:
- Defaults largely wired to loot bot deep link.
- Audit remaining copy surfaces for bare Main invites; keep VIP paths intact.

DONE WHEN:
- Grep-clean public CTAs; unit tests cover hub/referral/Buffer defaults; no accidental Main channel send in daily promo.

Task: <one concrete slice>
```

---

## V5 — Calm Ops Phase 5 (Erome hands-off)

```text
VERTICAL: Calm Ops Phase 5 — Erome hands-off
MISSION: Extension-assisted / Playwright path toward TBCC_EROME_AUTO_UPLOAD with private staging + governance. Transport overlay shows live Pareto intel + record hooks.

READ FIRST:
- tbcc/docs/EROME_TOS.md (compliance constraints)
- tbcc/docs/erome-enhancer/README.md
- extension: erome-enhancer.js, gallery/transport overlay pieces
- backend: erome upload governance tests (test_erome_upload_governance.py)

CONSTRAINTS:
- Respect Erome ToS / rate limits; prefer staging flags over silent prod uploads.
- Cloud agent: implement code + tests. Do not drive a live logged-in browser session against prod Erome unless task says so (operator does that).

CURRENT STATE:
- Private staging + governance + transport overlay in progress.
- Next: tighten Playwright record path and auto-upload flag safety.

DONE WHEN:
- Flags default safe-off; tests for governance gates; docs updated.

Task: <one concrete slice>
```

---

## V6 — Erome browse-intel + market intel

```text
VERTICAL: Erome browse-intel v4.2 + market intel
MISSION: Keep TM browse-intel (uploader/velocity) and weekly market-intel cycle (Reddit probe, beat schedule, API) accurate and testable.

READ FIRST:
- tbcc/docs/erome-enhancer/MARKET_INTEL_ARCHITECTURE.md
- tbcc/backend/app/services/market_intel_cycle.py
- tbcc/backend/app/services/market_intel_cycle_executor.py
- tbcc/backend/app/workers/market_intel_worker.py
- tests: test_market_intel_cycle.py, test_market_intel_probe.py, test_erome_*.py

CURRENT STATE:
- Weekly cycle Mon 09:05 beat + /analytics/market-intel/cycle exist.
- Next: harden cycle reliability, staging sidecar, clearer analytics payload.

DONE WHEN:
- Mapped pytest green; no live network required for unit tests.

Task: <one concrete slice>
```

---

## V7 — X ↔ Erome flywheel (SFW promo pool + Buffer)

```text
VERTICAL: X ↔ Erome flywheel (SFW promo + Buffer)
MISSION: Generate SFW promo creatives (Gemini), upload (R2), attach to X/Buffer with correct link order; pool URLs must become real (not placeholders).

READ FIRST:
- tbcc/backend/scripts/generate_aof_promo_gemini.py
- tbcc/backend/scripts/upload_x_promo_pool.py
- tbcc/backend/app/services/gemini_promo_generate.py, gemini_promo_prompt.py
- tbcc/backend/app/services/r2_promo_upload.py
- tbcc/backend/app/services/buffer_x_link_order.py
- tbcc/backend/app/services/pool_surface_mirror.py
- docs/samples/gemini_aof_promo_*.txt
- tests: test_gemini_promo_prompt.py, test_r2_promo_upload.py, test_buffer_x_link_order.py

CURRENT STATE:
- Gemini CLI + R2 script + link-order cycle shipped; pool URLs still placeholder.
- Next: real pool URL wiring + safe defaults for affiliate-first previews.

DONE WHEN:
- Tests green; placeholders removed or clearly flagged; no secrets in tree.

Task: <one concrete slice>
```

---

## V8 — Remote scrape offload (GCP + GHCR)

```text
VERTICAL: Remote scrape offload (GCP + GHCR)
MISSION: Home Celery excludes `scrape`; GCP VM pulls ghcr.io worker image and consumes scrape over Tailscale to home Redis/Postgres.

READ FIRST:
- tbcc/docs/REMOTE_WORKER.md
- tbcc/scripts/remote-worker/*
- tbcc/infra/docker-compose.remote-worker.ghcr.yml
- tbcc/infra/docker-compose.tailscale-bind.yml
- .github/workflows/tbcc-remote-worker-ghcr.yml

CURRENT STATE (operator, 2026-07-11):
- VM reachable; home queues TBCC_CELERY_HOME_QUEUES=celery,subscription,telegram.
- launch-remote-worker.ps1 fixed for WinPS; start.ps1 ASCII-sanitized (em-dash parse bug).
- Tailscale bind publishes 100.x:5432/6379 alongside localhost.
- Remaining: CRLF/`set -o pipefail` issue in pull-remote-worker.sh on VM; polish GHCR path; docs accuracy.

CONSTRAINTS:
- Do not put GHCR tokens or Tailscale auth keys in git.
- Prefer fixing scripts/compose/CI; operator runs gcloud/tray.

DONE WHEN:
- Scripts parse on Windows PowerShell 5.1; bash scripts are LF; health script documented.

Task: <one concrete slice>
```

---

## V9 — Scrape transport (Ingest)

```text
VERTICAL: Scrape transport (Ingest UI)
MISSION: JD-ish transport table: row select → master play/pause/stop/skip; columns + progress %; hide/show columns.

READ FIRST:
- dashboard transport / Sources / ScrapeRunBanner / ScrapeTransportBar
- tbcc/dashboard/src/utils/scrapeTransportStatus.ts
- tbcc/backend/app/services/scrape_run_service.py
- tbcc/backend/app/api/jobs.py (relevant endpoints)
- tests: test_scrape_transport.py, scrapeTransportStatus.test.ts

CURRENT STATE:
- Core transport UX in flight.
- Next: polish control correctness, progress %, column prefs persistence.

DONE WHEN:
- Unit tests + dashboard tests for status mapping; no tray/process changes.

Task: <one concrete slice>
```

---

## V10 — Scrape channel metrics (TGStat-lite)

```text
VERTICAL: Scrape channel metrics (TGStat-lite)
MISSION: Show viewers/members on transport rows; hashtag→pool map; hyperlinked t.me; keep migration 092 path coherent.

READ FIRST:
- tbcc/backend/alembic/versions/092_scrape_channel_metrics.py
- tbcc/backend/app/models/scrape_channel_profile.py
- tbcc/backend/app/services/scrape_channel_intel.py
- tbcc/backend/app/services/scrape_tag_pool_map.py
- tests: test_scrape_tag_pool_map.py

CONSTRAINTS:
- If schema changes: add/adjust alembic revision; do not claim deploy-ready without migration note.

DONE WHEN:
- Model/API/dashboard alignment; pytest green; migration noted in PR.

Task: <one concrete slice>
```

---

## V11 — X affiliate-first cards

```text
VERTICAL: X affiliate-first Buffer cards
MISSION: Keep TBCC_BUFFER_X_AFFILIATE_FIRST=1 default so X previews pin affiliate links first — no bare t.me “telegram globe” previews when avoidable.

READ FIRST:
- tbcc/backend/app/services/buffer_x_link_order.py
- tbcc/backend/app/services/buffer_x_caption.py
- tbcc/backend/app/services/buffer_native_queue_refill.py
- tests: test_buffer_x_link_order.py
- .env.example flag docs

CURRENT STATE:
- Default affiliate-first shipped.
- Next: edge cases (multi-link, cycle when AFFILIATE_FIRST=0), caption consistency.

DONE WHEN:
- pytest covers order rules; .env.example documents flag.

Task: <one concrete slice>
```

---

## V12 — Username search overlay + gallery UX

```text
VERTICAL: Username search overlay + gallery history UX
MISSION: FAB modal search on SC/CB/OF/IG/X; gallery nav tab chips; macrosearch Setup (approve host + template) → Search/Sources.

READ FIRST:
- tbcc/extension/* (gallery.js/html, overlay, model-search, x-profile-*)
- tbcc/extension/manifest.json
- related options HTML

CONSTRAINTS:
- Extension changes need clear reload notes; avoid breaking gallery send pipeline.
- No secrets in extension code.

DONE WHEN:
- Features work in isolation; minimal manifest permission creep; smoke notes for operator reload.

Task: <one concrete slice>
```

---

## V13 — Zeus / Secretary menu

```text
VERTICAL: Zeus menu Phase 1 (Secretary hub)
MISSION: Secretary bot hub: Network | Inbox | Ops | More + /stack status rendering from tray-backed stack status.

READ FIRST:
- tbcc/docs/ZEUS_MENU.md
- tbcc/backend/bots/zeus_menu.py
- tbcc/backend/bots/secretary_bot.py (hub wiring)

CONSTRAINTS:
- /stack must not start/stop processes; display-only from GET /ops/stack-status semantics.
- No duplicate bot runtime.

DONE WHEN:
- Menu callbacks stable; HTML/Telegram formatting safe; unit-testable pure render helpers preferred.

Task: <one concrete slice>
```

---

## V14 — Lean stack / ops reliability (cloud-safe slices only)

```text
VERTICAL: Lean stack & ops reliability
MISSION: Improve scripts/docs/health logic so the operator’s 24/7 flywheel stays lean. Cloud agent may fix code paths; must NOT control live processes.

READ FIRST:
- .cursor/rules/tbcc-dev-ops.mdc
- tbcc/docs/OPS_TRIAGE.md
- tbcc/docs/REMOTE_WORKER.md
- tbcc/scripts/tbcc-service-control.ps1 (read patterns; careful edits)
- tbcc/backend/app/services/system_health.py
- tests: test_service_user_enabled.py, test_celery_routes.py

ALLOWED:
- Health checks, toggle defaults, PowerShell ASCII fixes, compose overlays, docs, unit tests.

FORBIDDEN:
- Instructing production start/stop; committing .env; enabling Supervisor full panel without explicit unbench task.

Task: <one concrete slice>
```

---

## Deferred verticals (only with explicit “why now”)

Do not start cloud agents on these unless the operator overrides:

- Content distribution schedule (strategy)
- X.com scraper bot (ToS / rate limits)
- Album poster bot
- Supervisor full panel unbench (pagination + global on/off first)
- Full desktop ops cockpit rewrite

See `tbcc/docs/TBCC_IMPROVEMENT_NOTES.md`.

---

## Example full prompt

```text
<paste Universal contract>

VERTICAL: X affiliate-first Buffer cards
… (V11 body) …

Task: Add a regression test for three-link captions where affiliate must stay first when TBCC_BUFFER_X_AFFILIATE_FIRST=1, and document the flag in .env.example if missing. Open a focused PR.
```
