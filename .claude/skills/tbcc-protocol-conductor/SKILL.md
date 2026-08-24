---
name: tbcc-protocol-conductor
description: >
  This skill should be used when the user asks "/tbcc-conductor", "/conductor",
  "what command next", "which protocol next", "standing by for next directive",
  or "hand off to the next agent". Thin compose-edge matcher over
  tbcc/docs/protocol-chains.json — recommends the next slash/skill hop; does not
  swallow leaf skills. Menu only unless the operator picks a hop.
---

# TBCC Protocol Conductor

Thin overseer (browse-intel pattern): leaf skills stay leafs. Match `tbcc/docs/protocol-chains.json` edges via **situational-match** (same idea as Cursor `workflow-automation.mdc` + registry triggers — no extra NLP). Cap recommendations at **3**.

Adapted from `~/.cursor/skills/tbcc-protocol-conductor/SKILL.md` (GSP v2.4).

## When to invoke

- Triggers: `/tbcc-conductor`, `/conductor`, “what command next”, “which protocol next”, “standing by for next directive”
- Situational: ambiguous next hop after a phase report; operator asks which TBCC protocol to run
- **Skip:** operator already named the next protocol; pure trivia; `.env` / bot-spawn

## Procedure

1. Read `tbcc/docs/protocol-chains.json` (and optionally `entropy-lenses.json` for topic→lens edges).
2. Match `when_hints` against what just finished + thread topic.
3. Prefer high `ladder_bias` edges that clearly hit. Topic edges with `from: "*"` count (e.g. payment notification → `/tbcc-entropy-scan marketing`).
4. Emit Output Contract. Stop for pick — do not auto-run the hop.

## Output contract

1. **Just finished** — one line  
2. **Next hops** — ≤3: alias · why matched · lens if any  
3. **Recommend** — single best (or “none obvious”)  
4. **Fence** — will not auto-run unless they pick  

## Exit

- Pick → load that skill fully (`tbcc-continue-thread`, `tbcc-entropy-scan`, `tbcc-directive-generator`, …)
- Prefer CC-facing aliases (`/tbcc-*`) when recommending inside Claude Code
