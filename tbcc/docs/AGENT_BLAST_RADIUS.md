# Agent blast radius & trust fence (v1.0)

**Purpose:** Stop the Grok-Bot failure mode inside TBCC — *named specialists that look isolated while sharing one identity underneath*.

**Anti-pattern (external):** Five Grok bots on one cloud PC / one browser session / one login graph. Delete a bot; connected-app access stays. If money or exchanges sit behind that login, “five hires” is marketing — blast radius is one.

**TBCC answer:** Borrow OpenBot’s *contract* (decide-before-execute, record-after, role-scoped tools) without adopting OpenBot as a second orchestration runtime. Enforce via `/crew` + `/silent-fail` + this map.

## Shared vs isolated surfaces

| Surface | Shared? | Notes |
|---------|---------|--------|
| Island `infra/.env.revenue-island` / compose secrets | **Shared** | Payment, loot, R2, bot tokens — one machine identity for money path |
| Telethon `admin.session` | **Shared (hard)** | One host only (`REVENUE_ISLAND.md`). Home + island both open → 409 / AuthKeyDuplicated |
| Poster session (`admin_poster`) | Semi-isolated | Auto-copy from admin; still same Telegram account graph |
| Cursor / Claude Code agent sessions | **Shared tool graph** | Same MCP OAuth (Buffer, Kit, Cloudflare), same workspace files, same shell unless fenced |
| OpenClaw gateway `:18789` | **Shared** if enabled | Bash/browser/MCP via one gateway — treat like a single privileged coworker |
| Operator CLI / API Pocket slots | **Shared** | `operator slots call` can hit any registered base URL with stored keys |
| Celery queues / Beat | Process isolation | Workers are separate processes; **credentials** still come from the same env |
| CC Relay artifacts (`handoffs/*`, `CURRENT_DIRECTIVE.md`) | Isolated *workflow* | Files are the handoff bus — good. Do not confuse with credential isolation |
| `/silent-fail` probes | Read-only checks | Prove work fired; do **not** revoke access |

## Rules (operator ACK)

1. **Role ≠ identity.** A maker prompt does not create a security boundary. Assume every Agent-mode session can reach whatever credentials the host already holds.
2. **No money / Telegram mutate / R2 write without an external stop.** After a crew or multiphase grind: `/silent-fail` (or equivalent HTTP/DB/Redis/pytest evidence). “Agent says done” is forbidden as sole proof.
3. **Coordinator is checker-only when possible.** Parent synthesizes and refuses; makers explore/propose. Parent must not Start bots or invent restart policy.
4. **Never wire Grok-style five bots on one login for money.** Quant/trading desks on shared browser profiles are out of scope for TBCC.
5. **Revoke ≠ delete skill.** Removing a bot/skill/session does not rotate tokens. Treat MCP disconnect, `.env` key rotate, and Telethon session move as separate ops.
6. **OpenBot is a design reference, not the runtime (default).** See integration-scan result before any Docker/Bun adopt. Prefer file gateway (handoffs) + Cursor Task + `/silent-fail` (always-on rule + skill).

## How `/crew` must behave

- Load this doc before spawning makers.
- Cap makers (≤3 explore/propose + 1 coordinator).
- Shared workspace = `tbcc/docs/handoffs/` or an explicit scratch path — not a second secret store.
- Every crew ends with a `/silent-fail` stop list matching the blast radius.
- Compose: `/crew` → `/silent-fail` → (optional) `/preflight` or `/directive` if fixes need a grind.
- **`codebase-audit`:** readonly report only; reconnect ranked above delete; every unused/connect claim needs `rg`/path evidence; no auto-delete; Do-not-touch and paused tracks are `idle` not bloat.

## Related

- `/silent-fail` — `~/.cursor/skills/tbcc-silent-fail/SKILL.md`
- `/crew` — `~/.cursor/skills/tbcc-agent-crew/SKILL.md`
- Island Telethon hard rule — `tbcc/docs/REVENUE_ISLAND.md`
- OpenClaw — `tbcc/docs/OPENCLAW_TBCC_INTEGRATION.md`
- Capability bus (not a work queue) — `tbcc/docs/OPERATOR_CAPABILITY_BUS.md`
