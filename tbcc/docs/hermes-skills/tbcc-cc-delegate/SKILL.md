---
name: tbcc-cc-delegate
description: "TBCC overlay on bundled claude-code — Lane C grind only after operator ACK; print mode; reverse report; never bots/.env/cron."
version: 1.0.0
platforms: [windows, macos, linux]
metadata:
  hermes:
    tags: [Claude, Claude-Code, TBCC, Lane-C, overlay]
    related_skills: [claude-code, operator-daily-digest]
---

# TBCC Claude Code Delegate

Load bundled **`claude-code`** (do not reinstall). Then obey **this overlay**. Hermes is the dispatcher; Claude Code (CC) is Lane C grind off the Cursor bill.

## When to Use

Operator explicitly ACK'd a grind (chat: "delegate to CC", "run that GRIND item", or a numbered digest candidate). Never from `operator-daily-digest` cron.

## Prerequisites

```
claude --version          # need v2.x+
claude auth status --text
```

If unauthenticated, stop and tell the operator to run `claude` once (Pro OAuth). Do not set `ANTHROPIC_API_KEY` from TBCC `.env`.

## Hard gates (never)

- `.env`, `*.session*`, `.tbcc-run/`, credentials, `google_token.json`
- `POST /bots/runtime/*/start`, tray Start, `python -m bots.payment_bot` / loot / secretary
- Island deploy unless the operator said so in **this** turn
- `git push` unless the operator said so
- Spawn CC from cron / daily digest
- `--dangerously-skip-permissions`
- tmux / PTY on Windows — **print mode only**
- Pricing, leak doctrine, watermark policy, architecture judgment (those stay Cursor / Frontier)

## When it is OK

Low-judgment mechanical work: tests, codemods, boilerplate, filling `tbcc/docs/handoffs/*_report.md`. Bounded file list. Exact pytest command.

## How to run (Windows)

Print mode only. `workdir` = repo root `C:\Powercore-repo-main\telegram_bot2` unless operator named another **non-secret** path.

```
claude -p "<HANDOFF BLOCK>" --model sonnet --max-turns 15 --allowedTools "Read,Edit,Bash,Glob,Grep" --output-format json
```

Timeout: 10–20 minutes. Do not background and forget.

## Handoff block (required in the `-p` prompt)

Self-contained. CC has zero Hermes chat memory.

1. **Goal** — testable done
2. **Scope** — repo root, in-scope paths, **out of scope**
3. **Constraints** — no `.env`, no bot Start, no push, no island unless stated
4. **Verification** — exact command (e.g. `pytest tbcc/backend/tests/test_foo.py -x -q`)
5. **Working agreement** — uncommitted unless operator asked to commit; **after the phase** write:

`tbcc/docs/handoffs/YYYY-MM-DD_<topic>_report.md`

Structure:

```
# Reverse handoff — <topic>
- Branch:
- Head commit(s) this phase (hash + subject):
- Status: Phase N complete | blocked | needs Cursor review

## Done
## Files touched
## Verification run
## Risks / open questions
## Operator smoke (Tray only)
## Do not
- push / start bots / touch .env / Phase N+1 until Cursor ACK
```

Then **STOP**. Do not start phase 2.

## After CC exits

Summarize for the operator: report path, pytest pass/fail, files touched. Do **not** ACK the next phase yourself. Cursor reviews via `claude-code-report`.

If CC fails (auth, max-turns, budget): report the JSON `subtype` / stderr and stop.

## Smoke (safe)

Throwaway dir only: `%LOCALAPPDATA%\hermes\smoke\` — never `tbcc/` money paths.
