# TBCC / AOF — Claude Code project memory

Monorepo root: `telegram_bot2/` (`tbcc/`, `aof-forum/`).

## Operator policy (non-negotiable)

- **Cloud-only runtime:** revenue island (`https://api.powercore.app`) is canonical. Do **not** start local tray, Postgres, Redis, Celery, or Telegram bots on the operator PC.
- **Never** `tbcc-stack-cli.ps1 -Action Start` (any service) or spawn `python -m bots.*` locally — causes Telegram **409 Conflict** with island/tray.
- **Status truth:** `curl https://api.powercore.app/health` or island `GET /ops/stack-status` — not guessed from terminals.
- **Deploy:** `tbcc/scripts/revenue-island/deploy-island-live.ps1` (rsync working tree to VPS; not `git pull` on island).
- **One Telethon admin session** at a time for heavy scrapes.

## Lane C (your role here)

Mechanical grinds: multi-file commits, pytest, island deploy, handoff reports.

- Forward handoffs: `tbcc/docs/handoffs/YYYY-MM-DD_*.md`
- Reverse reports: `tbcc/docs/handoffs/YYYY-MM-DD_*_report.md` — **stop after each phase** for Cursor ACK via `/cc-report`
- Commit **one slice at a time**; push when handoff says so; never commit `.env`, `*.session*`, `.tbcc-run/`, `.tmp/`, generated promo art

## Repo map

| Path | Purpose |
|------|---------|
| `tbcc/backend/` | FastAPI, bots, Celery workers, pytest |
| `tbcc/extension/` | Chrome importer (bump `manifest.json` patch on ship) |
| `tbcc/dashboard/` | React ops UI |
| `tbcc/infra/docker-compose.revenue-island.yml` | Island compose |
| `aof-forum/` | Next.js forum / hub P9–P10 |
| `tbcc/docs/TEST_MAP.md` | pytest paths for completion gates |
| `tbcc/docs/SPRINT_STATE.md` | Read before substantive edits |

## Verification defaults

```bash
cd tbcc/backend
py -3.13 -m pytest <path-from-TEST_MAP> -x -q --tb=short
```

Island smoke after deploy:

```bash
curl -sS https://api.powercore.app/health
curl -sS https://api.powercore.app/tags/ | head -c 200
```

## TBCC product rules (short)

- **Loot promo art:** clean generation; overlay frames in code; host on R2; CTA `@aof_lootgod_bot?start=loot_free`
- **Revenue island:** `TBCC_REVENUE_ISLAND_ACTIVE=1` gates beat schedules (scrape off, R2 export on)
- **Extension QA:** island API first; `loadTagCatalog` warn with healthy `/tags/` = noise
- **Cursor owns judgment** (pricing, doctrine); Lane C implements locked plans only

## Settings layers

| File | Scope |
|------|--------|
| `.claude/settings.json` | Team defaults (git) |
| `.claude/settings.local.json` | Your machine: bypass mode, extra allows (gitignored) |
| `tbcc/.claude/` | Legacy — prefer starting CC from **repo root** |

Start sessions from `telegram_bot2/` so root `.claude/` applies.
