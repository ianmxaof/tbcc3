---
name: tbcc-continue-thread
description: >
  This skill should be used when the user asks to "/tbcc-continue-thread",
  "/continue-thread", "next directive", "what should CC do next", "pick up deferred",
  or after a reverse-report ACK when Claude Code is standing by for the next directive.
  Resurfaces deferred/out-of-scope from the latest handoff report — does not invent a
  greenfield plan. Do not use for unrelated new verticals or named "just the bug" fixes.
---

# TBCC Continue Thread

Close the gap between “slice shipped / standing by” and “what do I paste (or grind) next.”

Read the latest reverse report’s fence / out-of-scope / open questions and put **deferred work first**. Prefer report-authored deferred over new ideas.

Adapted from `~/.cursor/skills/tbcc-continue-thread/SKILL.md` (GSP v2.4). Cursor Desktop Auto / Frontier lane lines are dropped — Claude Code has no equivalent. Chains: `tbcc/docs/protocol-chains.json`. Lenses: `tbcc/docs/entropy-lenses.json`.

## When to invoke

- Triggers: `/tbcc-continue-thread`, `/continue-thread`, “next directive”, “what should CC do next”, “pick up deferred”, “continue the CC thread”
- Situational: after Cursor `/cc-report` ACK; this session ends a phase with “standing by for the next directive”
- **Skip:** no `tbcc/docs/handoffs/*_report.md`; operator wants an unrelated vertical; “just the bug” on a named file

## Dual role (Lane C)

| Role | When | Behavior |
|------|------|----------|
| **Author** | Package the next slice for a fresh CC session or Cursor paste | Emit Recommend + paste path; stop; do not implement |
| **Consumer** | This session continues the deferred work | Execute the recommended slice within Fence; after phase write `*_report.md` then **STOP** for Cursor ACK |

## Procedure

1. Locate the report (operator path or newest matching `tbcc/docs/handoffs/*_report.md`).
2. Confirm prior slice done-condition (yes/no + one evidence line from the report).
3. List ≤5 **Deferred** bullets from fence / out-of-scope / open questions.
4. **Recommend** one next slice + testable done-condition + optional lens (`media-intel`, `devops`, …).
5. **Paste path:** hand to `/tbcc-directive-generator` if cold-start needed; or grind here if Consumer; or `/tbcc-entropy-scan <lens>` if several deferred compete.
6. Stop for operator pick unless Consumer role was explicit.

## Output contract

1. **Prior slice** — done? + evidence  
2. **Deferred** — ≤5  
3. **Recommend** — one slice + done-condition + lens  
4. **Paste path** — `/tbcc-directive-generator` | `/tbcc-entropy-scan <lens>` | grind here  

## Exit

- Composes → `tbcc-directive-generator` | `tbcc-entropy-scan` | implement (Consumer)
- Do not auto-run the next grind without a pick (Author) or explicit Consumer intent
- Reverse stop-gate after each phase still applies when grinding
