# TBCC growth signals (OpenClaw skill)

Use when monitoring content performance, spotting growth opportunities, and delivering findings to the operator via OpenClaw Telegram.

## Prerequisites

- TBCC API on `http://127.0.0.1:8000` (lean full stack: `TBCC_STACK_PROFILE=lean` + `start.ps1 -Full -WtTabs`)
- Redis + Celery Beat/workers for scheduled posts and view refresh
- TBCC MCP: `analytics_content_performance`, `tbcc_flywheel_tick`, `tbcc_health`

## Every growth turn

1. Call `tbcc_health` — if backend down, report P0 and stop.
2. Call `growth_signals_eligibility` (MCP) or `GET /analytics/signals/eligibility` — if `eligible=false`, send **one line** with `reason` and **stop** (no tick, no Telethon, no proposals).
3. Call `analytics_content_performance` with `run_tick=true` and `days=14`.
3. Deliver the **full markdown report** to the user on Telegram:
   - Start with a 2-sentence executive summary (top opportunity + suggested action).
   - Then paste ranked signals with recommendations unchanged.
4. If `digest_changed=false` and signals unchanged since last report, send a one-line "no new signals" instead of repeating the full digest.
5. If `digest_changed=true`, the tick response carries `proposed_actions[]` — list each proposal's `id` + `action_kind` under the report so the operator can approve one. Do **not** act on them; report only (see Reaction proposals below).

## Signal types (what to prioritize)

| Signal (exact type string) | Action bias |
|--------|-------------|
| `peak_post_hour` | Shift recurring posts toward that hour (local tz) |
| `caption_slot_winner` | Reuse or A/B that caption slot on high-view channels |
| `channel_view_leader` | Double down on top lane; inspect laggards |
| `conversion_hour` | Align VIP/loot promos to conversion peaks |
| `hub_web_traffic` | GA4 hub spikes → mirror winning topics |
| `industry_benchmark` | Category gaps vs benchmark → content fill |

## Reaction policy (critical)

| Action | Default |
|--------|---------|
| Report findings | Always deliver on cron or when user asks |
| Change schedules / create posts / deposits | Ask first |
| Auto-approve flywheel fixes | Never — use @aof_secretary_bot |
| Code edits | Branch + PR only |

## Reaction proposals (draft actions)

When the growth tick's digest changes, TBCC derives **draft reaction proposals**
from the top actionable signals. Each is observe-only: an `action_kind` +
`action_params` an operator could act on, with a stable `id`.

| From signal | `action_kind` | Params |
|-------------|---------------|--------|
| `peak_post_hour` | `schedule_hour_bias` | `target_hour_local`, `timezone` |
| `caption_slot_winner` | `caption_slot_reuse` | `scheduled_post_id`, `caption_slot_index` |
| `channel_view_leader` | `increase_channel_frequency` | `channel_id`, `channel_name` |
| `conversion_hour` | `align_cta_window` | `target_hour_local` |

- Read: MCP `growth_signal_proposals(days=14)` or `GET /analytics/signals/proposals`.
- The growth tick response includes `proposed_actions[]` when `digest_changed=true`.
- Dismiss (operator says "drop proposal X"): `POST /analytics/signals/proposals/{id}/dismiss`. Dismissals persist across recomputes (Redis set keyed by the stable id).

**Operator flow (never skip the OK):**
1. Report signals + list any pending proposals with their ids.
2. Operator reviews and says e.g. "approve proposal `a1b2c3`".
3. ONLY THEN call the follow-up draft API (`list_scheduled_posts` to inspect, then
   the relevant create/schedule tool). No proposal auto-executes — no live post,
   reschedule, or spend without explicit operator approval.

## MCP tools

- `analytics_content_performance(days=14, run_tick=true)` — primary growth report
- `growth_signal_proposals(days=14)` — pending draft reaction proposals (review + approve)
- `analytics_weekly_summary(days=7)` — subs + outbound volume context
- `tbcc_flywheel_tick(ops_limit=0)` — growth-only tick when ops lane not needed
- `list_scheduled_posts`, `list_channels`, `list_pools` — follow-up when user approves action

## Cron (OpenClaw)

Growth report every 30m (isolated session, deliver to Telegram):

> TBCC growth report: load skill tbcc-growth-signals. mcporter call tbcc.analytics_content_performance run_tick=true days=14. Deliver full markdown + 2-sentence summary. Never auto-post.

Ops + growth pulse every 20m (lighter):

> TBCC ops: tbcc_health, tbcc_flywheel_tick ops_limit=1, flywheel_approval_bundle. One summary. If growth digest changed, add one-line top signal. Never auto-approve.

Setup: `tbcc\scripts\setup-openclaw-growth-cron.ps1`

## Do not confuse

- **Growth signals** = analytics digest (this skill)
- **TBCC flywheel ops** = restart/Cursor triage approvals (Secretary bot)
- **You (OpenClaw)** = operator channel — separate BotFather bot from @aof_secretary_bot

Docs: `tbcc/docs/OPENCLAW_TBCC_INTEGRATION.md`
