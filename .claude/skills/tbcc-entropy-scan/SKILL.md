---
name: tbcc-entropy-scan
description: >-
  Capped leftover-yield scan with lens rolodex (revenue default; devops, marketing,
  media-intel, …). Invoke as /tbcc-entropy-scan or /tbcc-entropy-scan marketing|devops|…
---

# TBCC Entropy Scan

Surface leftover yield **before** locking a plan — then stop and wait for a pick. Do not turn every bug fix into a re-architecture. Plan-only: no file edits until the operator picks a slice or says "literal only".

Adapted from Cursor `tbcc-entropy-scan` (GSP v2.4). Lenses: `tbcc/docs/entropy-lenses.json`. Chains: `tbcc/docs/protocol-chains.json`.

## Lens

Resolve from `/tbcc-entropy-scan <lens>` or infer via JSON `infer_rules`. Default `revenue` only for funnel/money asks — do not force monetization axes on marketing/devops/vision threads.

## When to invoke

- Triggers: `/tbcc-entropy-scan`, `/entropy-scan`, "entropy scan", "scour vertices", "max yield this request"
- Skip: named bug fix; docs/lint/pytest; `.env` / bot-spawn; island deploy mechanics; "just the bug" / "literal only"

## Vertex taxonomy

Load axes from `entropy-lenses.json` for the resolved lens (revenue, devops, innovation, marketing, media-intel, agent-workflow, observability).

## Output contract

Same four sections: Literal (+ Lens) → Vertices ≤5 → Ascend? → Fence. Stop for pick.

## Exit

Pick → implement / directive / preflight per `protocol-chains.json`. Do not auto-run.
