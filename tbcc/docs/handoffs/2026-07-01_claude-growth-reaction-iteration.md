# 2026-07-01 — Growth reaction loop + backend CI (Claude Code iteration)

Source: Claude Code (Opus 4.8) · Branch: `claude/growth-reaction-openclaw-ci` ·
Structure adapted from [OPS_HANDOFF_PROTOCOL.md](../OPS_HANDOFF_PROTOCOL.md).

## 1. Context Summary

Iterated the growth reaction loop: TBCC ranks growth signals → OpenClaw reports
via Telegram cron → operator approves → system can **propose** (never
auto-execute) concrete scheduling/content actions. Added minimal backend CI so
the growth/ops surfaces get pytest coverage on every PR.

- **Scope:** `tbcc/backend/app/services/content_signals.py` (+ new
  `growth_reaction.py`), `tbcc/backend/app/api/analytics.py`,
  `tbcc/mcp-server/server.py`, growth OpenClaw skill + cron, new tests, GitHub
  Actions workflow.
- **Stack assumptions:** none required to build/test — all new tests run on
  in-memory SQLite (`tests/conftest.py`), Redis is faked. Live verification
  (MCP/curl) needs the lean stack + Redis up.
- **Non-destructive branch:** cut from current `crawler-multi-site` HEAD (which
  carried a large unrelated dirty tree). Only task files were staged per commit
  (`git add <path>`, never `-A`); the operator's other uncommitted work is
  untouched. **PR base branch is an open decision — see Recommendations.**

## 2. Findings (state going in)

| Priority | Code | Description | Evidence |
|----------|------|-------------|----------|
| P2 | `signal_type_drift` | Plan/SKILL.md referenced `caption_winner`/`channel_leader`, but the engine emits `caption_slot_winner`/`channel_view_leader`. Mapping on the wrong strings would silently never fire. | content_signals.py:245, :299 |
| P3 | `no_signal_coverage` | `content_signals.py` had zero tests despite driving OpenClaw reports. | `tests/` had no `test_content_signals*` |
| P3 | `ci_greenfield` | No `.github/workflows/` existed. | repo root |
| P2 | `suite_not_green` | 12 pre-existing test failures + 1 collection error, unrelated to this work (missing `pytest-asyncio`, stale `SimpleNamespace` mocks in companion/secretary/pool suites). A full-suite `-x` gate would be red on day one. | `pytest tests/ -q` → `12 failed, 254 passed, 1 error` |

## 3. What shipped

**Phase 1 — tests + CI**
- `tests/test_content_signals.py` (13 tests): peak-hour ranking on real SQLite
  rows, `_digest_hash` stability/change/ignoring non-signal fields,
  `format_signals_markdown` shape (with + without signals), `tick_growth_signals`
  digest_changed edge cases (first run / changed / unchanged / disabled).
- `.github/workflows/tbcc-backend-tests.yml`: Python 3.13, pip cache, path
  filter on `tbcc/backend/**` + `tbcc/mcp-server/**`. **Required gate** =
  growth + ops files (green, deterministic); **full suite = non-blocking** step
  until the pre-existing failures are triaged.

**Phase 2 — growth reaction proposals (observe-only)**
- `app/services/growth_reaction.py`: `propose_reactions(report)` maps the four
  actionable signals → `action_kind` + `action_params`:
  - `peak_post_hour` → `schedule_hour_bias`
  - `caption_slot_winner` → `caption_slot_reuse`
  - `channel_view_leader` → `increase_channel_frequency`
  - `conversion_hour` → `align_cta_window`
  - Proposal `id` = stable hash of signal **identity** (not volatile metrics), so
    a dismissal survives recompute. Redis-backed dismissal set — no new
    table/migration.
- API: `GET /analytics/signals/proposals`, `POST
  /analytics/signals/proposals/{id}/dismiss`; `proposed_actions[]` added to the
  `/analytics/signals/tick` response when `digest_changed=true`.
- MCP: `growth_signal_proposals(days=14)` tool.
- `tests/test_growth_reaction.py` (11 tests): mapping, stable-id invariance,
  dismiss-then-filtered, tick integration.

**Phase 3 — OpenClaw + docs**
- `tbcc-growth-signals/SKILL.md`: corrected signal-type strings; added Reaction
  proposals section + strict operator-approval flow; added `growth_signal_proposals`
  to MCP list.
- `setup-openclaw-growth-cron.ps1`: growth cron message now calls
  `growth_signal_proposals` on `digest_changed` and reiterates "no acting on a
  proposal without my OK" (ASCII only — no em-dashes).
- This handoff.

**No auto-execution anywhere:** proposals carry suggested follow-up params only;
no post, reschedule, or spend happens without explicit operator approval, mirroring
the ops-flywheel notify-only policy.

## 4. Recommendations

- **PR base branch (operator decision):** this branch sits on top of
  `crawler-multi-site`, which has diverged from `main`. A PR to `main` would diff
  in all of that divergence. Options: (a) PR to `main` after `crawler-multi-site`
  merges; (b) PR `→ crawler-multi-site`; (c) cherry-pick the three task commits
  onto a fresh branch off `main`. Recommend (b) or (c) to keep the PR reviewable.
  Effort: 5–15 min. **Do not push to `main` directly.**
- **Triage the 12 pre-existing failures**, then promote the full-suite CI step
  from non-blocking to required. Quick win: add `pytest-asyncio` to a dev-requirements
  file — clears the companion/gate-health async errors. Effort: ~1h.
- Live-verify once the lean stack is up (see Implementation Steps).

## 5. Implementation Steps (verify)

```bash
# Unit tests (no stack needed)
cd tbcc/backend && py -3.13 -m pytest tests/test_content_signals.py tests/test_growth_reaction.py -v

# CI gate set (exactly what the workflow runs as the required gate)
py -3.13 -m pytest -q tests/test_content_signals.py tests/test_growth_reaction.py \
  tests/test_ops_workflow_runner.py tests/test_ops_tool_permissions.py

# Live (lean stack + Redis up)
curl -s http://127.0.0.1:8000/analytics/signals/proposals | jq .
mcporter call tbcc.growth_signal_proposals days=14 --config %USERPROFILE%\.openclaw\config\mcporter.json
```

## 6. Files changed / created

| Path | Type | Note |
|------|------|------|
| `.github/workflows/tbcc-backend-tests.yml` | new | backend CI (gate + non-blocking full suite) |
| `tbcc/backend/tests/test_content_signals.py` | new | 13 signal-engine tests |
| `tbcc/backend/tests/test_growth_reaction.py` | new | 11 proposal tests |
| `tbcc/backend/app/services/growth_reaction.py` | new | proposal engine (Redis-backed) |
| `tbcc/backend/app/services/content_signals.py` | mod | `proposed_actions[]` on tick when changed |
| `tbcc/backend/app/api/analytics.py` | mod | proposals GET + dismiss routes |
| `tbcc/mcp-server/server.py` | mod | `growth_signal_proposals` MCP tool |
| `tbcc/docs/openclaw-skill/tbcc-growth-signals/SKILL.md` | mod | proposals + corrected signal names |
| `tbcc/scripts/setup-openclaw-growth-cron.ps1` | mod | cron surfaces proposals on digest change |

## 7. Suggested next iterations

| Priority | Item | Notes |
|----------|------|-------|
| P1 | View refresh without lock storms | Dedicated refresh session / off-peak batch; keeps `TBCC_VIEW_REFRESH_BEAT_ENABLED=0` safe. See [[tbcc-telegram-io-serialized]]. |
| P1 | Wire GA4 credentials | `ga4_hub` signals currently `configured: false`. |
| P2 | Dashboard proposals UI | List/dismiss/approve in `SchedulerGrowthHub.tsx`. |
| P2 | Celery beat task for growth tick | Alternative to OpenClaw-only polling. |
| P2 | Promote full-suite CI to required | After the 12 pre-existing failures are fixed. |
| P3 | Auto-draft Buffer/X captions from `caption_slot_winner` | LLM lane, still ask-first. |

## 8. Dependencies

- TBCC API :8000, Redis :6379, OpenClaw gateway :18789
- MCP: mcporter + `tbcc` server
- Skills used: `tbcc-growth-signals`
