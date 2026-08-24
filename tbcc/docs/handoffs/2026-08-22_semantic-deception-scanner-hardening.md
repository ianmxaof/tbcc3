# Forward handoff — semantic-deception-detector Phase 1+2 hardening

- **Target:** Claude Code (Lane C)
- **Author:** Cursor (ACK of `2026-08-22_semantic-deception-detector-audit_report.md`)
- **Status:** ready to paste
- **Reverse report expected:** `tbcc/docs/handoffs/2026-08-22_semantic-deception-scanner-hardening_report.md`

## Context

Cursor reviewed the CC audit report and approved fixes for two confirmed bugs in the shared scanner at `%USERPROFILE%\.cursor\skills\semantic-deception-detector\scripts\scan.py`. Operator bundled Phase 1 (contradiction pairing + line offset + self-test) and Phase 2 (`omission_kinds` scoping) in one CC grind.

**Baseline (pre-fix):** `python scan.py --json -- tbcc` → 7 findings, risk_score 100 HIGH — 4 false contradictions, 3 real (2× hidden_unicode, 1× undocumented_capability).

**Post-fix target:** 3 findings, 0× direct_contradiction / side_effect_contradiction, risk_score < 70.

See paste block in chat / below for full directive.
