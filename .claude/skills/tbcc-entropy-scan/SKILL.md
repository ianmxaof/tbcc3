---
name: tbcc-entropy-scan
description: Capped leftover-yield scan (revenue vertices by default) before locking a product/funnel/devops plan — surfaces up to 5 missed angles, then stops for a pick. Invoke as /tbcc-entropy-scan or /tbcc-entropy-scan innovation|devops.
---

# TBCC Entropy Scan

Surface leftover yield **before** locking a plan or writing code — then stop and wait for a pick. Do not turn every bugfix into a re-architecture. This is a Plan-only scan: no file edits, no implementation, until the operator picks a slice or says "literal only".

Adapted from `.cursor/rules/tbcc-entropy-scan.mdc` / `~/.cursor/skills/tbcc-entropy-scan/SKILL.md` (GSP v2.2), with the Cursor-specific model-routing/Desktop-Auto/Cloud-lane mechanics dropped — Claude Code has no equivalent lanes — and generalized with a lens so the same procedure covers more than revenue work.

## Lens (from the `/tbcc-entropy-scan` argument)

Default lens is **revenue** when no argument is given. Other lenses: `innovation`, `devops`. The lens only changes the vertex taxonomy below — the four-section output contract and the stop-and-wait rule are identical across all three.

## When to invoke

- Trigger phrases: `/tbcc-entropy-scan`, "entropy scan", "scour vertices", "max yield this request", "conversion vertices" (naturally the revenue lens)
- Situational, by lens:
  - **revenue**: the ask is product / funnel / pricing / SKU / paywall / CTA / copy / retention / "how should we" — without a file-level spec yet
  - **innovation**: "what's underexploited here", "what could this unlock", a recent build that might have leftover leverage nobody's using yet
  - **devops**: "what's fragile/manual here", preflight before a bigger refactor, a repeated pain point that hasn't been named as a ticket
- **Skip** (do not expand — just do the literal ask): named file-level bugfix; docs/lint/pytest only; `.env` / secrets / bot-spawn mechanics; island deploy mechanics; operator said "just the bug" or "literal only"

## Vertex taxonomy by lens

- **revenue** (default): CTA, paywall/SKU, attribution (`source_ref`), friction-to-cash, retention / latency-to-money
- **innovation**: unexploited primitives already sitting in the codebase, capability gaps versus what's now possible, integration surfaces nobody's wired up yet, leverage left on the table by a recent build
- **devops**: toil (a step done by hand repeatedly), fragility (single points of failure, untested paths, silent failure modes), observability gaps, reversibility of recent changes

## Behavioral rules

- Reason by: literal ask → ≤5 vertices (each tagged `missed` | `covered` | `blocked`) → one recommended slice **or** an explicit no-ascend
- Avoid: fake FOMO or dark-pattern "extraction" (revenue lens); rewriting anything `tbcc/docs/SPRINT_STATE.md` marks "do not touch"; unbounded "leave no vertex unaddressed" implementation; architecture tourism
- Prioritize: the operator's stated done-condition; the current `tbcc/docs/SPRINT_STATE.md` goal; reversible slices over irreversible ones

## Output contract

Required, all four, dense — short bullets, no essay:

1. **Literal ask** — one sentence
2. **Vertices** — max 5 bullets, each tagged `missed` | `covered` | `blocked`
3. **Ascend?** — `yes` + one slice with a testable done-condition, **or** `no` + why the literal ask is already the yield
4. **Fence** — in scope / out of scope; what will explicitly not be re-engineered this pass

Failure contract: if `SPRINT_STATE.md`'s do-not-touch list or a live-ops constraint blocks a vertex, tag it `blocked` and stop expanding it — do not implement around the block. Report what was scanned and what was skipped.

## Procedure

1. Read `tbcc/docs/SPRINT_STATE.md` for the current goal and any do-not-touch list. If a skip condition matches, say so in one line and just do the literal ask instead of running the scan.
2. Resolve the lens from the argument (default: revenue).
3. Emit the four Output Contract sections for that lens.
4. Stop. Do not write or edit any files until the operator picks a slice or says "literal only".
