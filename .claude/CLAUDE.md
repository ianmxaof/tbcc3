# TBCC / AOF — Claude Code project memory

Monorepo root: `telegram_bot2/` (`tbcc/`, `aof-forum/`).

## Operator policy (non-negotiable)

- **Cloud-only runtime:** revenue island (`https://api.powercore.app`) is canonical. Do **not** start local tray, Postgres, Redis, Celery, or Telegram bots on the operator PC.
- **Never** `tbcc-stack-cli.ps1 -Action Start` (any service) or spawn `python -m bots.*` locally — causes Telegram **409 Conflict** with island/tray.
- **Status truth:** `curl https://api.powercore.app/health` or island `GET /ops/stack-status` — not guessed from terminals.
- **Deploy:** `tbcc/scripts/revenue-island/deploy-island-live.ps1` (rsync working tree to VPS; not `git pull` on island).
- **One Telethon admin session** at a time for heavy scrapes.
- **Never hot-patch without restart:** do not `docker cp` into a running island container and walk away — Python will keep the old code until restart. Use `tbcc/scripts/revenue-island/hot-patch-island.ps1` (always restarts) or full `deploy-island-live.ps1`.
- **Telethon scripts:** open admin.session only via `run_telegram_io` / Celery telegram queue (`TBCC_REQUIRE_TELETHON_SESSION_LOCK=1` default). Login script sets the override.

## Lane C (your role here)

Mechanical grinds: multi-file commits, pytest, island deploy, handoff reports.

- Forward handoffs: `tbcc/docs/handoffs/YYYY-MM-DD_*.md`
- Reverse reports: `tbcc/docs/handoffs/YYYY-MM-DD_*_report.md` — **stop after each phase** for Cursor ACK via `/cc-report`
- Commit **one slice at a time**; push when handoff says so; never commit `.env`, `*.session*`, `.tbcc-run/`, `.tmp/`, generated promo art

### Directive Generator (regular handoff packing)

When packaging work for another LLM / a **fresh** Claude Code session, or when the operator pastes a messy issue dump (“generate a directive”, “handoff prompt for”, `/directive`, `/tbcc-directive-generator`):

1. Load and follow **`.claude/skills/tbcc-directive-generator/SKILL.md`** (project skill — auto-discovered from repo root).
2. Emit a cold-start fence (Goal / Scope / Prior state / issue cards / Constraints / Verification / Working agreement / Phases) — do **not** implement in the author turn unless they say execute here.
3. Browser twin (same procedure): `tbcc/docs/DIRECTIVE_GENERATOR_GPT_PASTE.md`.

When **this** session is the TARGET of a pasted directive/handoff: honor Fence + Prior state; write the reverse `_report.md` after each phase; stop for Cursor ACK. Do not invent Goal/Scope from chat vibes if the paste already defined them.

### Project skills (`.claude/skills/`)

| Skill | Invoke when |
|-------|-------------|
| `tbcc-entropy-scan` | leftover yield / conversion vertices before locking a plan (`/tbcc-entropy-scan`) |
| `tbcc-directive-generator` | raw issues → paste-ready directive for another agent/session (`/tbcc-directive-generator`, `/directive`) |

Skills need valid `name` + third-person `description` frontmatter to trigger. Start Claude Code from **repo root** (`telegram_bot2/`) so these load.

## Completion gates

Before declaring substantive code work done, check every applicable row and report pass / skip-with-reason / fail in the summary:

| Gate | When | Action |
|------|------|--------|
| **Tests** | Logic in `tbcc/backend/` touched | Run mapped pytest from `tbcc/docs/TEST_MAP.md`; if no map entry, `pytest tbcc/backend/tests/ -x -q --tb=short -k <keyword>` or note "no test; suggest one" |
| **Migration** | Models/schema touched | Note the alembic revision needed; don't call it deploy-ready without one |
| **Stack** | Bots, Celery, beat, runtime APIs touched | No duplicate bot spawn — see Operator policy above |
| **Extension version** | Any edit under `tbcc/extension/` (shipped JS/HTML/CSS/manifest) | Bump `manifest.json` `"version"` patch; state old → new in the summary |
| **Git** | Files changed | Summarize `git status` — modified, uncommitted, unstaged |
| **Scope** | >8 files modified | Halt and confirm scope with the user before continuing, rather than sprawling further |

Skip a gate only with an explicit reason (docs-only, rules-only, user said skip).

## Next-steps ladder

End substantive completions (implementation, debugging, planning, review, ops triage — not pure Q&A) with a **Next steps** list: up to 5 candidate follow-ups, ordered low-effort/impact → high-impact, in the best interest of the project. Each row:

- **What:** the route in one clause
- **Unblocks:** self | other-work | deploy | revenue-ops
- **Reversibility:** trivial-revert | migration | prod-data
- **Evidence:** exact command/endpoint to prove it landed

At least one option should tie back to `tbcc/docs/SPRINT_STATE.md`'s current goal (closes it vs. orthogonal — label which). Don't pad the ladder — 2 options beats 5 padded ones. Menu only: do not start any of them until the user picks.

**Skip when:** pure Q&A/trivia, or the user already gave the next instruction outright — don't re-offer a menu they've already bypassed.

Adapted from `.cursor/rules/bottom-line-next-steps.mdc` — dropped its "Lane" line (Cursor's Desktop Auto / Frontier / Cloud Agent spend routing has no Claude Code equivalent).

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
| `tbcc/docs/DIRECTIVE_GENERATOR_GPT_PASTE.md` | Cold-start handoff meta-prompt (browser + skill twin) |
| `.claude/skills/` | Project skills (entropy-scan, directive-generator) |

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
