# TBCC GSP Protocols

Protocols conform to **Global Protocol Standard v2.0** (`.cursor/rules/global-protocol-standard.mdc` in your local Cursor config). Personal skill copies live under `~/.cursor/skills/`; this file is the repo-backed index.

## Registered protocols

| Protocol | Triggers | Skill |
|----------|----------|-------|
| **TBCC Ship Log** | `/ship-log`, `TBCC ship log`, `draft my build-in-public tweet` | `~/.cursor/skills/tbcc-ship-log/SKILL.md` |
| **TBCC Milestone Ship** | `/milestone-ship`, `TBCC milestone ship`, `ship milestone to GitHub` | `~/.cursor/skills/tbcc-milestone-ship/SKILL.md` |

## Tooling

| Script | Purpose |
|--------|---------|
| `backend/scripts/ship_log_sources.py` | Git + improvement-notes context |
| `backend/scripts/ship_log_buffer.py` | Buffer Idea or X queue |
| `backend/scripts/milestone_ship.py` | Status, push, full milestone pipeline |
| `backend/scripts/buffer_channels.py` | List Buffer org/channel ids |

## Milestone ship flow

1. `py -3.13 scripts/milestone_ship.py --status`
2. Stage files (`git add tbcc/` …), exclude secrets per `tbcc/.gitignore`
3. `py -3.13 scripts/milestone_ship.py --execute -m "…" --post-variant 1`

Buffer: [developers.buffer.com](https://developers.buffer.com/guides/getting-started.html)
