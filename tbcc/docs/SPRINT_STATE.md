# Sprint State

**Last updated:** 2026-07-06

## Sprint goal

Fully automated agent workflow — zero slash commands; ship-log and session rituals run on situational triggers + scheduled tasks.

## In flight

| Item | Owner | Notes |
|------|-------|-------|
| Calm Ops Phase 5 (Erome hands-off) | Claude | Playwright flow recording + `TBCC_EROME_AUTO_UPLOAD` path; extension-assisted |
| Erome browse-intel v4.2 + market intel | agent | TM v4.2 (uploader/velocity), Reddit probe worker, upload hints, content_signals anomaly |
| X ↔ Erome flywheel (SFW promo pool + Buffer) | agent | `aof_x_promo_image_pool.json`, pool mirror wires Erome URL + promo image on X |

## Blocked on

- (none)

## CI / stack status (last known)

- `lean-stack-hardening`: Calm Ops phases 1/3/4/6 committed + pushed (liveness backfill, idle governor, celery ops lane, supervisor menu hints).
- Milestone build-in-public post **queued** on @wizardstick69 (~2026-07-05 via Buffer addToQueue).
- Windows task `TBCC-Ship-Log-Tick` registered (Mondays 09:00).
- Content X posts firing on schedule (native/relay — separate from ship-log).

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
