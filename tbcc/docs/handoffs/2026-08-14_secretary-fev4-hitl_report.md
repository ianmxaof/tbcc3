# Reverse handoff — secretary-fev4-hitl

- Branch: `main`
- Head commit(s) this phase: `641dfe3` — feat(secretary): DB-backed Pilot drafts survive restart, redo keeps FE/coach suffix
- Status: **Phase 1 complete**

## Done

- **Drafts persisted to DB (closes G8).** New table `secretary_pending_drafts` (alembic `112_secretary_pending_drafts`, head `111_secretary_bot_instances`). The old in-memory `_pending_drafts` dict is gone — every draft read/write in `secretary_bot.py` (`/approve`, `/reject`, `/redo`, `/drafts`, `sec:ap`/`sec:rj`/`sec:rd` callbacks, `/fe_stats` count) now goes through `app/services/secretary_drafts.py`, keyed by `draft_id`. No in-memory cache layer — DB is the only source of truth, so a secretary container recreate no longer breaks `/approve`.
- **Full suffix stored on each draft.** `save_draft(...)` persists `extra_system_suffix` — the exact string passed to `complete_secretary_chat` for the first completion (FE context + sales coach + RAG + catalog + dashboard extra + the Pilot "this is a suggestion" note), not just the pre-suffix `llm_messages`.
- **Redo never drops FE/coach/RAG again (closes G5).** `build_redo_suffix(stored_suffix, style, custom)` concatenates the stored full suffix with the tone hint (or the custom instruction) — Casual/Pro/Short/custom regenerate now reuse the original context instead of a style-only rewrite. `update_draft_reply()` overwrites only the reply text, keeping `extra_system_suffix`/`llm_messages`/`created_at` untouched so a second redo still has the original context.
- **Pilot hydrates from Format Engine DB when memory is empty (closes G6).** `suggest_customer_lines(prev_lines, db_history)` prefers the live in-memory `BIZ_LINES_KEY` lines (fast path within one process lifetime) and falls back to `load_recent_messages_for_llm(user_id)` filtered to `role == "user"` after a restart, mirroring how the Auto path already hydrates. The just-persisted current turn is stripped from the DB fallback (same dedupe pattern the Auto path already used) so it isn't duplicated against "Latest message."
- **TTL:** rows older than 48h are pruned on every read/write (`_prune_expired`, `DRAFT_TTL_HOURS = 48`); `count_drafts()` used by `/fe_stats` is read-only (no delete/commit) so it doesn't fire a write inside a caller-owned session that's mid-read.

## Files touched

- `tbcc/backend/app/models/secretary_pending_draft.py` — new `SecretaryPendingDraft` model, one row per draft
- `tbcc/backend/alembic/versions/112_secretary_pending_drafts.py` — creates the table + 3 indexes (`draft_id` unique, `user_id`, `created_at`)
- `tbcc/backend/app/services/secretary_drafts.py` — new service: CRUD + TTL prune, plus the two pure helpers `build_redo_suffix()` and `suggest_customer_lines()` (kept out of `bots/secretary_bot.py` so they're importable without triggering the bot module's `load_dotenv(override=True)` at collection time)
- `tbcc/backend/bots/secretary_bot.py` — removed `_pending_drafts` dict; added thin `_save_draft`/`_load_draft`/`_update_draft_reply`/`_drop_draft`/`_list_pending_drafts` wrappers (open their own `SessionLocal()`, mirroring the existing `_customer_reply_mode` pattern); rewired `_deliver_draft_to_customer`, `cmd_approve`, `cmd_reject`, `cmd_redo`, `on_draft_callback`, `cmd_drafts`, `/fe_stats`; suggest-mode branch in `on_private_text` now builds `thread_lines` via `suggest_customer_lines()` and stores `extra_system_suffix=extra` on save
- `tbcc/backend/tests/conftest.py` — explicit `SecretaryPendingDraft` import (`# noqa: F401`) so `Base.metadata.create_all()` always registers the table, matching the existing pattern for the promo-affiliate models
- `tbcc/backend/tests/test_secretary_drafts.py` — new: round-trip across a second `sessionmaker` bound to the same engine, redo-suffix preservation (unit + a mocked-LLM integration test asserting the actual system message string), suggest-history memory-vs-DB fallback, TTL prune, delete/list/count
- `tbcc/docs/TEST_MAP.md` — added `test_secretary_drafts.py` to the "Format engine / secretary sales-rep" row

## Verification run

From `tbcc/backend`:

```
py -3.13 -m pytest tests/test_format_engine.py tests/test_secretary_reply_mode.py tests/test_secretary_sales_coach.py tests/test_secretary_new_lead.py tests/test_secretary_drafts.py -x -q --tb=short
```

**30 passed**, 41 warnings (all pre-existing `datetime.utcnow()` deprecation warnings from `format_engine.py`/SQLAlchemy — not introduced this phase).

Baseline (before touching anything): the same command minus `test_secretary_drafts.py` was run first and passed 15/15, confirming a clean starting point.

## Risks / open questions

- **Suggest-history DB fallback is thin.** `load_recent_messages_for_llm` returns the last `TBCC_FORMAT_ENGINE_LLM_HISTORY` rows (default 8) **across both roles**, so after filtering to `role == "user"` a thread with several already-approved drafts can yield only 1–2 lines, not full parity with a long customer thread. This satisfies the letter of the task ("hydrate ... user turns") but is not a complete conversation reconstruction — worth knowing before assuming Pilot drafts have full context after a long-running thread survives a restart.
- **`sec:rj` callback answer ordering:** `query.answer()` is called unconditionally before the drop in `on_draft_callback` (pre-existing structure), so a "Dropped" toast always fires even if the draft had already expired/been dropped elsewhere — same UX as before this phase, not changed.
- **Pre-existing, unrelated:** `tests/test_zeus_multi_app.py::test_cohost_spike_requires_env_flag` (and the tests after it in that file) hang indefinitely in this environment. Confirmed via `git stash` that this reproduces identically on the pre-phase code — not caused by this change. Not part of the requested verification command; flagging so it isn't mistaken for a regression from this phase.
- **No in-memory cache.** Every draft action now does a DB round-trip (SQLite locally, presumably Postgres on the island). Given draft volume (single admin, HITL, low QPS) this should be a non-issue, but it's a deliberate simplicity choice per the phase brief ("in-memory cache OK if DB is canonical") — flagging in case Cursor wants a cache layer added later for a busier install.
- **`pytest.mark.asyncio` unavailable in this environment** (confirmed pre-existing via `test_companion_access.py` failing the same way) — the mocked-LLM redo test in `test_secretary_drafts.py` uses `asyncio.run()` directly instead of the marker, consistent with how `test_zeus_multi_app.py` already drives async code in this repo.

## Operator smoke (Tray / island only — do not run yourself)

1. Toggle a live Business or direct-DM customer to **Pilot**, send a test message, confirm a draft card lands in the admin DM as before.
2. Recreate the secretary container (or restart the tray service) with that draft still pending, then run `/drafts` — the draft should still be listed, and **✓ Send** should still deliver it (proves G8 fixed).
3. On a fresh draft, tap **↻ Casual** — the redraft should still steer toward the payment bot / mention the sales-coach angle from the original draft, not read like a generic FAQ rewrite (proves G5 fixed — compare against a pre-phase build if unsure).
4. Send two customer messages in the same Pilot thread, restart the secretary process between them, then check the second draft's admin card — the earlier customer message should be reflected in tone/continuity even though it happened in a prior process lifetime (proves G6 fixed).
5. `/fe_stats` — "Pending business drafts" count should match `/drafts` output.

## Do not

- push
- start bots
- touch `.env`
- begin Phase 2 (3-candidate triage, psychology corpus, Zelle/Stars offer split, clone fleet) until Cursor ACK
