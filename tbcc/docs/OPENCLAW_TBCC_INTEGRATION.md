# OpenClaw (github.com/openclaw/openclaw) + TBCC integration

Connect the real [OpenClaw](https://github.com/openclaw/openclaw) personal assistant to TBCC / AOF Network.

> **Naming (two different things):**
> - **OpenClaw** = [github.com/openclaw/openclaw](https://github.com/openclaw/openclaw) gateway on `:18789`, Telegram bot, MCP. Env: `TBCC_OPENCLAW_AUTO_START`, `TBCC_OPENCLAW_GATEWAY_PORT`.
> - **TBCC flywheel** = internal ops/growth event bus (HTTP tick, Celery-adjacent). Scripts: `run_tbcc_flywheel_tick.py`, `run-tbcc-flywheel-tick.ps1`. Env: `TBCC_FLYWHEEL_*`. Old `openclaw_*` / `TBCC_OPENCLAW_AUTO_TICK` names are deprecated aliases only.

## Architecture

```
OpenClaw Gateway (local daemon, ~18789)
  ├── Telegram: NEW BotFather bot (not @aof_secretary_bot)
  ├── Tools: bash, browser, cron, mcporter (TBCC MCP)
  └── mcporter → tbcc/mcp-server/server.py → http://127.0.0.1:8000

@aof_secretary_bot (TBCC)
  └── Flywheel Approve/Reject buttons (human gate)
```

## 1. Install OpenClaw

```powershell
npm install -g openclaw@latest
openclaw onboard --install-daemon
openclaw gateway status
```

Or use **Windows Hub** from [openclaw.ai](https://openclaw.ai).

## 2. Register TBCC MCP (mcporter)

OpenClaw **2026.1.x** does not ship `openclaw mcp`. Use the bundled **mcporter** skill + CLI instead.

From repo (adjust paths):

```powershell
cd tbcc\scripts
.\setup-openclaw-tbcc.ps1
```

Manual:

```powershell
npm install -g mcporter
$cfg = "$env:USERPROFILE\.openclaw\config\mcporter.json"
if (-not (Test-Path $cfg)) { '{"mcpServers":{}}' | Set-Content $cfg }

mcporter config add tbcc `
  --command py `
  --arg -3.13 `
  --arg "C:/Powercore-repo-main/telegram_bot2/tbcc/mcp-server/server.py" `
  --env "TBCC_API_URL=http://127.0.0.1:8000" `
  --persist $cfg

mcporter list tbcc --schema --config $cfg
mcporter call tbcc.tbcc_health --config $cfg
```

Copy config into the OpenClaw agent workspace (mcporter default path is `./config/mcporter.json` relative to workspace):

```powershell
Copy-Item -Force $cfg "$env:USERPROFILE\clawd\config\mcporter.json"
```

Verify in an agent turn (or CLI): `tbcc_health`, `tbcc_flywheel_tick`, `flywheel_approval_bundle`.

## 3. AOF operator skills

Installed to `~/.openclaw/workspace/skills/`:

| Skill | Purpose |
|-------|---------|
| `tbcc-aof-network` | Daily ops: health, flywheel, approvals |
| `tbcc-failure-modes` | Diagnose scheduler stall, CPU, MCP, notification storm |

Re-copy after updates:

```powershell
.\tbcc\scripts\setup-openclaw-tbcc.ps1 -SkipMcpAdd
```

Or:

```powershell
Copy-Item -Recurse -Force `
  "C:\Powercore-repo-main\telegram_bot2\tbcc\docs\openclaw-skill\*" `
  "$env:USERPROFILE\.openclaw\workspace\skills\"
```

## 3b. Ops workflow + handoffs

- **Workflow API:** `POST /ops/workflow/run` — YAML-driven `tbcc_ops_turn` (health → scheduling → flywheel → handoff)
- **Handoff format:** [OPS_HANDOFF_PROTOCOL.md](./OPS_HANDOFF_PROTOCOL.md)
- **Permissions:** [ops_tool_permissions.yaml](../backend/app/data/ops_tool_permissions.yaml) — OpenClaw cannot `flywheel_approve`
- **MCP:** `run_ops_workflow`, `flywheel_approval_bundle` (approve via Secretary only)

## 4. Telegram channel (separate bot)

1. BotFather → new bot (e.g. `AOF Operator Bot`).
2. Add token to OpenClaw config (not `tbcc/.env` secretary token):

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "botToken": "<OPENCLAW_BOT_TOKEN>",
      "dmPolicy": "pairing"
    }
  }
}
```

3. Pair your DM: `openclaw pairing approve telegram <code>`

**Never** reuse `@aof_secretary_bot` token — causes Telegram 409 conflicts.

Optional in `tbcc/.env` (documentation only):

```env
# TBCC_OPENCLAW_BOT_USERNAME=   # for cross-links in Secretary copy
```

## 5. Secretary ↔ OpenClaw approval flow

| Step | Who |
|------|-----|
| TBCC detects critical ops | Flywheel → Redis pending |
| Instant DM | **Secretary** → Approve / Reject buttons |
| OpenClaw cron/agent | Reads `flywheel_approval_bundle` via MCP |
| User decision | **Secretary** (preferred) or OpenClaw chat |
| Execute | `flywheel_approve` / Secretary callback → restart or Cursor triage |

OpenClaw should **notify** you about pending items; default policy is **do not auto-approve** unless you enable auto mode in the skill.

API:

- `GET /ops/flywheel/approval-bundle`
- `GET /ops/flywheel/pending`
- `POST /ops/flywheel/approve/{id}`
- `POST /ops/flywheel/reject/{id}`

MCP: `flywheel_approval_bundle`, `flywheel_approve`, `flywheel_reject`

## 6. Cron (replace Windows Task Scheduler tick)

Unregister internal TBCC task (OpenClaw owns the loop):

```powershell
tbcc\scripts\register-openclaw-scheduled-task.ps1 -Unregister
```

OpenClaw cron example (already configured if you ran setup):

```powershell
openclaw cron add --name tbcc-ops-check --every 20m --session isolated `
  --message "TBCC ops: mcporter tbcc_health, tbcc_flywheel_tick, flywheel_approval_bundle. One summary only; never auto-approve." `
  --deliver --channel telegram --to YOUR_TELEGRAM_USER_ID --best-effort-deliver
```

See OpenClaw docs: [Cron jobs](https://docs.openclaw.ai/).

### Two different “cron” systems (common confusion)

| System | What it runs | Stalls when |
|--------|----------------|-------------|
| **OpenClaw cron** (`openclaw cron list`) | Agent turns (health, flywheel notify) | Gateway not running; 0 jobs configured |
| **TBCC scheduler** (Celery Beat + workers) | Scheduled Telegram posts, relay polls, promos | Redis down; Beat/Celery-Post not running; focus profile pauses scheduling |

OpenClaw reporting “scheduler cron stalled” usually means **TBCC Beat/workers** — not OpenClaw cron. Fix: `.\start.ps1 -Full -WtTabs` (with Redis) and confirm `TBCC-Beat` + `TBCC-Celery-Post` tabs are up.

## 7. CPU / stack profile (Windows)

`-Full` launches many processes (API reload, dashboard, 2× Celery, Beat, 5+ bots, optional enrichment). On a busy PC this can peg CPU.

| Profile | Command | Scheduling | Load |
|---------|---------|------------|------|
| **API only** | `.\start.ps1 -NoReload` | No posts | Lowest |
| **Lean full** | `TBCC_STACK_PROFILE=lean` in `.env` + `.\start.ps1 -Full -WtTabs -NoReload` | Yes (Beat + workers) | Medium — skips MacroSearch, Album Composer, NSFW/Lustpress sidecars |
| **Full** | `.\start.ps1 -Full -WtTabs` | Yes | Highest |

For OpenClaw ops + Secretary only, API-only is enough. For live posting, use **lean full** unless you need every bot/sidecar.

**Notification storm:** with `TBCC_INBOX_OPS_ACTIONS=1` and flywheel enabled, a sick stack spams Secretary/inbox. After stopping the stack, reject stale pending: `py -3.13 tbcc/backend/scripts/flush_flywheel_pending.py --older-than-days 0 --all` (when API+Redis are back).

## 8. Gateway as Windows service (survives reboot)

Requires **Administrator** PowerShell:

```powershell
openclaw gateway install
openclaw gateway start
```

Without admin, run manually after boot: `openclaw gateway --port 18789`

## 9. TBCC internal flywheel (optional fallback)

If OpenClaw is offline, manual tick:

```powershell
tbcc\scripts\run-tbcc-flywheel-tick.ps1 --dry-run
tbcc\scripts\run-tbcc-flywheel-tick.ps1
```

API: `POST /analytics/tbcc-flywheel/tick` (alias: deprecated `/analytics/openclaw/tick`)

## Env reference

| Variable | Purpose |
|----------|---------|
| `TBCC_FLYWHEEL_ENABLED` | Ops router |
| `TBCC_FLYWHEEL_APPROVAL` | Secretary approve gate |
| `TBCC_FLYWHEEL_GROWTH_TICK` | Growth lane in unified tick |
| `TBCC_FLYWHEEL_AUTO_TICK` | In-backend auto tick (off by default) |
| `TBCC_CURSOR_TRIAGE_*` | Cursor SDK bridge |

Legacy aliases: `TBCC_OPENCLAW_GROWTH_TICK`, `TBCC_OPENCLAW_AUTO_TICK`

## Related

- [OPS_TRIAGE.md](./OPS_TRIAGE.md)
- [CURSOR_OPS_AUTOMATION.md](./CURSOR_OPS_AUTOMATION.md)
- TBCC MCP: [mcp-server/README.md](../mcp-server/README.md)
