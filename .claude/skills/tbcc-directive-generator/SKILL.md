---
name: tbcc-directive-generator
description: >
  This skill should be used when the user asks to "generate a directive", "handoff prompt for",
  "/tbcc-directive-generator", "/directive", "prompt for {model/agent}", or pastes a messy issue
  dump for another LLM / fresh Claude Code session. Also use when receiving an unstructured
  work dump that lacks Goal/Scope/Verification — normalize into a cold-start directive before
  grinding, or when packaging a reverse handoff stop-gate. Do not use for a named file-level
  bugfix with "just fix it" and no handoff intent.
---

# TBCC Directive Generator

Turn `{target agent} + raw issues` into a **cold-start paste block** a receiving agent can execute with zero prior chat. Emit only — do not implement the issues unless the operator explicitly says to execute after the emit (or the TARGET of this session is self and they said “execute here”).

Adapted from `~/.cursor/skills/directive-generator/SKILL.md` and `tbcc/docs/DIRECTIVE_GENERATOR_GPT_PASTE.md` (v1.2 condensed paste). Cursor Desktop Auto / Frontier lane lines are dropped — Claude Code has no equivalent. Paste twin is short for browser Custom Instructions; this skill holds the full dual-role (author/consumer) procedure. Keep versions in sync when bumping.

## When to invoke

- Trigger phrases: `/tbcc-directive-generator`, `/directive`, “generate a directive”, “handoff prompt for”, “prompt for Claude Code|Cursor|ChatGPT|Cloud”
- Situational:
  - Operator pastes an unstructured issue list and names (or clearly implies) a receiving agent
  - Operator asks to package work for a **fresh** Claude Code session (network-blocked continuity, phase handoff)
  - Incoming work dump lacks Goal / Scope / Verification — normalize first, then grind
- **Skip:** scoped handoff already has Goal + paths + verify + reverse path; named “just fix it” bug with no handoff intent

## Dual role (Lane C)

| Role | When | Behavior |
|------|------|----------|
| **Author** | Generate / package for another agent or session | Emit fenced directive; stop; do not implement |
| **Consumer** | This session is the TARGET of a paste/handoff | Execute Goal within Fence; honor Working agreement; after each phase write `tbcc/docs/handoffs/YYYY-MM-DD_<topic>_report.md` then **STOP** for Cursor ACK |

## Procedure (author)

1. Parse TARGET + ISSUES (+ optional repo/branch/sprint/do-not-touch). Ask once if TARGET or ISSUES missing. Do not invent issues.
2. **Literal** — one sentence intention.
3. **Normalize** → ≤8 issue cards: id, symptom, evidence (path|log|repro|`unknown`), severity P0/P1/P2, depends_on, acceptance.
4. **Target profile** — mode (Plan|Ask|Agent|grind), tools, judgment_ceiling (MAY / MUST NOT). Context is always ZERO prior chat for the receiver.
5. **Ascend / Fence** — ≤5 vertices on the issue set (`missed`|`covered`|`blocked`); one slice + done-condition **or** literal pack; explicit out-of-scope.
6. **Emit** — single fenced block (see Output contract). Stop.

Load full procedure text from `tbcc/docs/DIRECTIVE_GENERATOR_GPT_PASTE.md` when wording must match the browser twin exactly.

## Output contract (author)

1. **Preface** (outside fence) — Literal; Ascend yes/no + one line; TARGET named
2. **Emit** (one fence) — required sections:
   - Goal (testable)
   - Scope (in + **Out of scope**)
   - Prior state (`none — greenfield` **or** continuity: verified / do-not-re-litigate / not-deployed)
   - Issue cards (≤8)
   - Constraints & gotchas (judgment ceiling + live-ops / secrets bans)
   - Verification (≥1 exact command or observable check)
   - Working agreement (commit/push/branch; reverse report + STOP for ACK if multiphase/grind)
   - Phases (only if >1; each ends verify + reverse when grind)
   - Target profile (short: mode + must-not-decide)
3. **Paste line** — `Paste into <TARGET>.` If TARGET is Claude Code: note reverse path under `tbcc/docs/handoffs/`.
4. **Reverse path** — name `YYYY-MM-DD_<topic>_report.md` when TBCC grind

Done means: emit survives a cold start (no chat-only refs; verify present; fence present).  
Failure: unbounded scope → one scoping question; P0 with evidence `unknown` → Phase 0 = locate or stop (do not fake paths).

## Consumer rules (when this session executes a directive)

- Prefer the pasted Goal / Scope / Prior state over chat memory.
- Do **not** re-open Prior state “do not re-litigate” items unless evidence shows regression.
- Do **not** decide pricing, leak doctrine, brand, or live bot starts — Cursor owns judgment; see root `.claude/CLAUDE.md`.
- After each phase: write reverse report, then stop. Do not start Phase N+1 until Cursor ACK.
- Never commit `.env`, `*.session*`, `.tbcc-run/`, `.tmp/`.

## Forbidden (author)

- Chat-only references (“as we discussed”)
- Emit without Verification
- Doctrine / pricing / leak policy assigned to a mechanical grind TARGET
- Implementing the issues in the author turn
- Mixing orthogonal P0s into Goal without a separate card + Fence

## Related

- Browser paste twin: `tbcc/docs/DIRECTIVE_GENERATOR_GPT_PASTE.md`
- Cursor skill: `~/.cursor/skills/directive-generator/SKILL.md`
- Dry-run examples: `~/.cursor/skills/directive-generator/examples.md`
- Sibling scan: `.claude/skills/tbcc-entropy-scan/SKILL.md` (yield before plan; this skill packs execution)
- Reverse reports: `tbcc/docs/handoffs/*_report.md` + Cursor `/cc-report`
