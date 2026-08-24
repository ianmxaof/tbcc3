# Reverse handoff — semantic-deception-scanner-phase3

- Branch: `lane-c/gatekeeper-lane-split`
- Head commit this phase: `49cbc55` docs(research): correct the Reddit-delay claim with real measured data
- Status: **Phase A + B complete, needs Cursor review** (both phases done in one session per operator's ACK)

## Done

### Phase A — `scan.py` (v1.0.1 → v1.0.2)

- **P1** — Added `_CONFIDENCE_MAP` (the locked table from the directive) and `_confidence_for(category)`. `Finding` gained a `confidence: str` field, computed automatically in `__post_init__` from the finding's own `category` — no call site needed touching, and it's impossible for a finding to be constructed without a correct, category-consistent confidence value.
- **P2** — `Report` gained `structural_score`/`structural_level`, computed in `scan_root()` by filtering findings to `confidence == "high"` and running the existing `score_findings()` against that subset (no signature change to `score_findings`). `summary` also carries a `structural_categories` breakdown. Both `main()` exit paths (`--json` and text mode) now gate on `report.structural_level` instead of `report.risk_level`. Text-mode output prints both score lines and tags each finding line with `confidence=...`.
- **P4** — `_self_test()` now asserts every finding has a valid `confidence`, that `direct_contradiction` (the fixture's known high-confidence hit) is actually tagged `high`, and that `structural_score`/`structural_level` respond to it (`> 0`, `REVIEW`/`HIGH`) — not just present as fields.
- **P5** — `VERSION` bumped `"1.0.1"` → `"1.0.2"`.

### Phase B — `SKILL.md`

- Header + changelog bumped to v1.0.2 with entries for both v1.0.1 (the Phase 1+2 fix) and v1.0.2 (this phase), so the file is a standalone history, not just a version number.
- Agent procedure step 1: replaced the bare "current workspace root" default with an explicit warning that the Cursor/Hermes workspace root can silently change scope (documented the exact `tbcc`-only → `telegram_bot2`-monorepo shift from this session), plus a pinned `tbcc`-path example command.
- Documented the new exit-code semantics (`structural_level` gates, not total `risk_level`) at the point in the procedure where exit codes were already explained.
- Output Contract's Verdict and Evidence sections now require `structural_score`/`structural_level` as the headline and `confidence` per evidence row.
- "What the script actually flags" table gained a `Confidence` column; added a paragraph explaining `structural_*` vs total `risk_*`.
- Pitfalls gained an explicit heuristic-categories-don't-gate-unattended-runs note.

## Verification run

```
python scan.py --self-test
→ self-test: PASS {"score": 100, "level": "HIGH", "cats": ["direct_contradiction", "hidden_unicode_agent_rule", "injection_bait", "side_effect_contradiction"]}

python scan.py --json -- "C:\Powercore-repo-main\telegram_bot2\tbcc"
→ version: 1.0.2
→ findings: 6 (unchanged from Phase 1+2 baseline)
→ risk_score: 27, risk_level: LOW (unchanged)
→ structural_score: 0, structural_level: LOW
→ categories: undocumented_capability ×4, hidden_unicode ×2 (all confidence: heuristic)
→ contradictions: 0
→ exit code: 0
```

Same 6 paths/lines as the Phase 1+2 report — no detection regression:
- `aof_network.py:155`, `aof_storage_hub_map.py:145` — hidden_unicode (heuristic)
- `assets/emoji/fyp-aof-divider/_compose_fyp_aof.py:14`, `backend/app/main.py:1362`, `backend/app/api/bots.py:4`, `backend/app/api/internal_launch.py:9` — undocumented_capability (heuristic)

## One discrepancy vs. the directive's own reasoning — flagging, not deciding

The directive's P2 acceptance note said structural_score would land `< 30` "(only 2× hidden_unicode contribute)". Under the directive's own **locked confidence map**, `hidden_unicode` is `heuristic`, not `high` — so it never enters the structural calculation at all. Actual result: `structural_score` is exactly **0** (no high-confidence findings exist in tbcc right now — zero contradictions, zero agent-rule unicode, zero injection bait), not driven by hidden_unicode as the parenthetical implied.

This doesn't fail the actual pass criterion (`structural_score < 30` and `structural_level == LOW` are both satisfied — 0 is stronger than the bar asked for), so I implemented per the locked table rather than guess whether the parenthetical or the table was the real intent. If Cursor's intent was actually for `hidden_unicode` to be `high`-confidence (contra the table as written), that's a one-line change to `_CONFIDENCE_MAP` — flagging for a decision rather than picking one silently.

## Files touched

- `%USERPROFILE%\.cursor\skills\semantic-deception-detector\scripts\scan.py` (outside `telegram_bot2/`, no repo diff)
- `%USERPROFILE%\.cursor\skills\semantic-deception-detector\SKILL.md` (same)
- `tbcc/docs/handoffs/2026-08-22_semantic-deception-scanner-phase3_report.md` (this file)

No `telegram_bot2/` source files modified. No commit made anywhere (skill dir has no git repo attached).

## Risks / open questions

1. **hidden_unicode confidence level** (above) — needs a yes/no: keep it `heuristic` per the locked table (current implementation), or Cursor intended `high` and the table itself needs fixing.
2. `_map_omissions`' per-file scoping (Phase 1+2) still produces 4 `undocumented_capability` hits including three in API-launcher files (`bots.py`, `internal_launch.py`, `main.py`) — this phase doesn't touch that, and Cursor already rejected an allowlist for it (per prior ACK), so it's expected to keep surfacing; noting only because Phase 3's `heuristic` tagging is precisely what makes that acceptable (visible, non-gating) rather than something that needs revisiting.
3. Text-mode exit code was changed to gate on `structural_level` for consistency with `--json` — the directive's pass criteria only explicitly tested the `--json` path, but leaving text mode on the old `risk_level` gate would have meant the two output modes disagreed about pass/fail for the same scan. Flagging the extension in case that wasn't intended to be symmetric.

## Operator smoke (Tray only)

N/A — no bots/Celery/tray touched this phase.

## Do not

- Do not widen the scanner's default target to the monorepo root — still fenced per this directive.
- Do not build a `--tree-wide` mode or an allowlist for the API-launcher subprocess hits — both explicitly out of scope / already rejected.
- Do not push/deploy — no repo changes were made this phase.
