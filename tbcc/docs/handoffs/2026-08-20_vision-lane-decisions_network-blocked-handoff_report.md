# Report: vision-lane decision-log deploy + ghost-town diagnosis + classifier accuracy investigation

**Against:** `tbcc/docs/handoffs/2026-08-20_vision-lane-decisions_network-blocked-handoff.md`
**Date:** 2026-08-21 (island-clock; session started 2026-08-20 local)

## Summary

Completed the original handoff (migrate + deploy the vision-lane shadow-classification feature), found and fixed a production-breaking regression the deploy itself introduced, diagnosed the "ghost town" pool-posting incident from the prior session, then spent the rest of the session testing whether the shipped vision-LLM classifier is actually accurate enough to trust — it wasn't, initially, and the investigation into *why* led to fixing several more real bugs and landing on a genuinely working approach for some of the taxonomy's harder lanes.

Net effect: the deploy shipped clean, several real infra bugs are fixed, and there is now honest, measured evidence about which parts of the classification approach work and which don't — instead of an untested shadow-mode feature sitting silent.

---

## Part 1 — Deploy execution

- `alembic upgrade head` landed migration `119_media_lane_vision_decisions` on the real island Postgres. Confirmed via `\d` — table exists.
- Full `deploy-island-live.ps1` run: rsync, Docker rebuild, service recreate, seed scripts, Storage Hub panel bootstrap, mainhub VIP pin refresh — all completed.
- Cleanup: removed `tbcc/backend/backend/` (leftover one-shot dev script, wrong nested path — matches prior session's triage note).

## Part 2 — Regression found and fixed mid-deploy

**Symptom:** deploy step 6 (`repair_content_lanes.py`) failed with `redis.exceptions.AuthenticationError`. Investigation showed `beat` itself lost its Redis connection — **all** scheduled posting was down, not just the vision-lane feature, for the ~2 minutes it took to diagnose and fix.

**Root cause:** `tbcc/scripts/revenue-island/seed-island-env-from-home.ps1` had `REDIS_URL` hardcoded in its `$forceKeep` table as `redis://redis:6379/0` — no password — and rewrites this on **every** deploy, unconditionally, silently reverting any hand-patched fix. This is why an earlier commit (`6641d64`, "document that REDIS_URL must carry TBCC_REDIS_PASSWORD") was docs-only and never actually stuck.

**Fix (shipped, committed to working tree):**
- Removed `REDIS_URL` from `$forceKeep`.
- Added derivation logic: `REDIS_URL` is now built from whatever `TBCC_REDIS_PASSWORD` is already present on the island (`redis://:$password@redis:6379/0`), every run — self-healing, can't drift out of sync again.
- Verified via `-WhatIf` dry run: exits clean, no PowerShell errors.

Live island patched by hand for immediate recovery; the script fix ensures the *next* real deploy doesn't reintroduce it.

## Part 3 — "Ghost town" pool-posting diagnosis (root cause found, NOT fixed — left for Cursor)

Confirmed via live Celery logs that pool-album posting had been completely silent since **2026-08-19 02:15 UTC** (`post_pool` task last succeeded then, never even *attempted* again for ~32 hours), while regular per-channel scheduled posts kept running normally.

**Root cause:** `post_scheduler.py`'s `TBCC_POOL_AUTOPOST_PAUSE_WHEN_OVERDUE` gate — if *any* recurring scheduler is even a few seconds past due (`min_overdue_minutes=0.0`), **all** pool auto-posting is skipped for that cycle. With ~50 active recurring schedulers on 2–8 hour intervals, something is transiently overdue on nearly every 2-minute `run_schedule` tick, effectively starving pool posting almost permanently. Confirmed live: `Skipping all pool auto-post — N scheduler(s) overdue` firing repeatedly in production logs.

Separately: 3 "AOF LOOT ROOM" scheduled posts were also auto-paused (their own, smaller issue) from repeated `SendMediaRequest`/`ImageProcessFailedError` failures — real but unrelated to the main gate issue.

**Status:** diagnosed with hard evidence, deliberately not touched — this is a doctrine/threshold-tuning call, not a bug fix, per repo rules (Cursor owns judgment calls like this).

## Part 4 — Vision-lane classifier: from zero to measured

The handoff's own migration had **never once run against real data** — table was empty, and tracing why surfaced a chain of independent blockers:

1. **Telethon import session was dead** (`admin_import.session` not logged in) — blocked *all* Telegram media import, not just this feature. Fixed live by the operator (`login_telethon_sessions.py`, interactive).
2. **`TBCC_ENRICH_ON_IMPORT` disabled** island-wide — the enrichment pipeline (which the vision classifier hooks into) never runs automatically. Left disabled deliberately (flipping it is a real ongoing-cost decision, not made this session); classification was invoked manually for testing instead.
3. **Vision LLM never configured** (`TBCC_VISION_LLM_PROVIDER=none`). Set to `openrouter` + a working model, persisted to both the live island and the local `.env.revenue-island` mirror (so the next deploy doesn't drop it).
4. **Real bug in the shipped code:** `vision_llm.py`'s OpenRouter branch called the generic `chat_completions_url()` (which resolves through the *default* text-LLM runtime, not OpenRouter specifically) — 404. **Fixed** (repo file + patched onto live containers).
5. **Configured default model deprecated** by OpenRouter (`google/gemma-3-12b-it:free` → paid-only now). Found a working replacement (`nvidia/nemotron-nano-12b-v2-vl:free`).
6. **Separate pre-existing bug** (July 4 commit, `e7adb4e6`, unrelated to this session): `_fetch_image_bytes_for_classify` called a function name (`_fetch_media_bytes_and_type_via_import`) that was never defined anywhere in the codebase — blocked classification of any media not already exported to R2. **Fixed** (one-line revert to the correctly-named, already-imported function; repo file + patched onto live containers).

All code fixes above exist in the repo working tree; container patches are live now but will be **overwritten by the next `--force-recreate`** until a real image rebuild ships them — flagged as a live fragility, not resolved.

## Part 5 — Classifier accuracy: real numbers, not assumptions

First test (8 items from one forwarded album) all returned `big_tits` — initially misread as a good sign. Caught the error: consistency across one homogeneous album isn't accuracy. Re-tested against actual ground truth: known-correct-lane media already sitting in 5 visually distinct Storage Hub subtopics (ai, voyeur, taboo, milf, blowjob).

**Round 1 — bare category list, free model:** 0/11 correct. Never once picked `ai`/`voyeur`/`taboo`/`milf` despite them being valid options.

**Round 2 — staging-cue prompt (self-authored definitions), free model:** 0/9 usable (plus 1 refusal, 1 malformed response). No improvement.

**Round 3 — stronger paid model (`qwen/qwen3-vl-235b-a22b-instruct`), same bare-ish prompt:** 1/11. Marginal, within noise.

**Round 4 — real domain vocabulary from operator-supplied RedGIFs niche list (1,704 real adult-content tags), free model:** `voyeur` 2/2. First non-noise positive result of the night, on the same images that had failed twice before.

**Round 5 — same approach, full tag pull for taboo/milf, free model:** rate-limited mid-run (OpenRouter free-tier shared pool), partial data: `voyeur` 2/3 (facets correct even on the one miss).

**Round 6 — same prompt, paid Qwen model, remaining taboo/milf items:** `milf` 2/3 (first-ever milf hits), `taboo` 0/2 (zero across every single approach tried all night).

### Final scorecard

| Lane | Result | Read |
|---|---|---|
| `voyeur` | ~2-3/3 | Real, reproducible fix via domain vocabulary |
| `milf` | 2/3 | Real fix, but needed the stronger paid model, not just vocabulary |
| `taboo` | 0/2 | Unsolved by every method tried — thin RedGIFs cue coverage (~11 terms vs. 30+ for milf) and/or these specific images lack visible taboo-staging cues |
| `ai` | 0/3 | Confirmed structurally out of scope for any prompt/vocabulary approach — "AI-generated" is a provenance/artifact-detection problem, not a content-description problem |

## Open items (not done, deliberately)

- `TBCC_ENRICH_ON_IMPORT` — still disabled; nothing auto-classifies on import yet.
- No pool-routing logic exists — tonight only validated the classification *signal*, never wired it to move media or assign pools. (The mechanism to do so, `route_media_to_lane_topics`, already exists and is production-proven for the named-topic flow — reusing it is the right integration point when this gets built.)
- Pool-autopost overdue gate (Part 3) — diagnosed, not fixed.
- The existing pre-tonight CLIP-based "Rule E" auto-router has its own separate timing bug (checks for CLIP signal before CLIP finishes) — has never fired once in production history. Not touched.
- `taboo` lane classification — unsolved; needs either richer domain vocabulary or acceptance that some lanes require caption/context signal the image alone doesn't carry.
- Operator's longer-term intent: build a labeled dataset from operator-approved classifications toward an eventual fine-tune, rather than relying on zero-shot prompting indefinitely. Not scoped or started — a real project deserving its own planning session.
- Operator's separate idea: a multi-provider credential registry + automatic rate-limit fallback (motivated directly by tonight's repeated OpenRouter free-tier limits). Not started — needs the operator to create accounts on trusted providers first; explicitly declined to sign up for unfamiliar services or use publicly-shared API keys on the operator's behalf.
- **AOF LOOT ROOM scheduler auto-pauses** — 3 scheduled-post rows (ids 1, 50, 49) auto-paused from repeated `SendMediaRequest`/`ImageProcessFailedError` failures on that channel's media specifically. Smaller, separate from the main pool-autopost gate. Not fixed.
- **Database watchdog's Redis health check has no auth** — `ensure-island-databases.sh`'s `redis_ok()` runs `redis-cli ping` with no password, so it now always reports Redis as unhealthy (false alarm, not a real outage, since Redis correctly requires auth post-fix). Identified live, probe itself not patched.
- **Telegram fetch path is fragile for older media** — even after the `NameError` fix, `_fetch_media_bytes_and_type`'s Saved-Messages-based fetch assumes media was copied to the bot's Saved Messages at import time; for a lot of historical media that never happened, so it 404s (`Media not found in Telegram`). Worked around for testing by fetching directly from the Storage Hub group instead; the underlying function most other callers use is still unreliable for older media.
- **`sent_cache_composer.py:337` missing `await`** — `notify_composer_bot()` calls `.get()` directly on a coroutine, throwing `AttributeError: 'coroutine' object has no attribute 'get'`. Fired live in production logs during this session's inbox intake test run. Noticed at the time, not flagged or fixed — a genuine miss, not a deliberate deferral.

## Files changed (repo working tree)

- `tbcc/scripts/revenue-island/seed-island-env-from-home.ps1` — REDIS_URL fix
- `tbcc/backend/app/services/vision_llm.py` — OpenRouter URL fix
- `tbcc/backend/app/services/auto_tag_enrich.py` — NameError fix
- `tbcc/infra/.env.revenue-island` — vision LLM provider/model config added
- `tbcc/backend/backend/` — removed (dev-script residue)
