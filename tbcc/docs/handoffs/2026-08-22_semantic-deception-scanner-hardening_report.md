# Reverse handoff — semantic-deception-scanner-hardening

- Branch: `lane-c/gatekeeper-lane-split`
- Head commit this phase: `49cbc55` docs(research): correct the Reddit-delay claim with real measured data
- Status: **Phase 1 + 2 complete, needs Cursor review** (both phases done in one session per operator's ACK)

## Done

Fixed both confirmed bugs in `%USERPROFILE%\.cursor\skills\semantic-deception-detector\scripts\scan.py` (outside `telegram_bot2/`, not tracked in this repo):

- **S1** — `map_contradictions` now groups claims and capabilities by `path` and only pairs a denial with an observation when both live in the **same file**. Extracted the JS-kind-bucketing logic into a shared `_bucket_caps()` helper reused by both the contradiction pass and the omission pass.
- **S2** — `harvest_claims` takes a `base_line: int = 1` param and computes `line = base_line + <offset within extracted text>` instead of always counting from the start of the extracted docstring substring. `scan_python` now passes the real AST line for both call sites: `tree.body[0].lineno` for the module docstring, `node.lineno` for function/class docstrings.
- **S3** — `_self_test()` gained a negative cross-file fixture (`offline_claim.py` + `other.py`, mirroring the real false positive this fixes) and an assertion that every `direct_contradiction`/`side_effect_contradiction` finding's `path` is `helper.py` — i.e. no cross-file leakage. The pre-existing positive case (`helper.py`'s own docstring self-contradicts its own `urllib` import) still fires, confirming same-file detection wasn't broken by the rescoping.
- **S4** — `_map_omissions` (split out of `map_contradictions`) now checks whether a capability's own file mentions the relevant keyword, not whether *any* file in the tree does.
- **S5** — `VERSION` bumped `"1.0.0"` → `"1.0.1"`.

## Verification run

```
python scan.py --self-test
→ self-test: PASS {"score": 100, "level": "HIGH", "cats": ["direct_contradiction", "hidden_unicode_agent_rule", "injection_bait", "side_effect_contradiction"]}

python scan.py --json -- "C:\Powercore-repo-main\telegram_bot2\tbcc"
→ files_scanned 398, loc_scanned 46804
→ risk_score 27, risk_level LOW   (was 100 / HIGH)
→ 6 findings   (was 7)
→ categories: hidden_unicode (2), undocumented_capability (4)   (was side_effect_contradiction 3, direct_contradiction 1, hidden_unicode 2, undocumented_capability 1)
→ contradictions: 0   (was 4)
```

Real hits from the original audit preserved exactly (same path, same line):
- `aof_network.py:155` — ZWJ in emoji literal
- `aof_storage_hub_map.py:145` — ZWJ in emoji literal
- `assets/emoji/fyp-aof-divider/_compose_fyp_aof.py:14` — undocumented subprocess

## Deviation from the directive's numeric pass criteria — flagging for your call

The directive's acceptance criteria expected **3** findings post-fix (`hidden_unicode` ×2, `undocumented_capability` ×1, contradictions zero). Actual result is **6** findings: contradictions did go to zero as specified, but `undocumented_capability` came in at **4**, not 1 — three new files surfaced:

- `backend/app/api/bots.py:4` — `import subprocess`, no module docstring at all
- `backend/app/api/internal_launch.py:9` — `import subprocess`, module docstring exists but never says subprocess/shell/popen/spawn
- `backend/app/main.py:1362` — local `import subprocess` inside a function, no docstring mention

I checked all three directly — they're real, not a scanner bug. Root cause: under the **old** tree-wide `mentioned` check (pre-S4), these three files were being silently suppressed because *some other unrelated file in the tree* happened to contain a denial-pattern word like "subprocess" or "spawn" — the same class of cross-file bleed that S1 fixed for contradictions. S4's explicit goal was to scope that check per-file instead, so surfacing these three is the fix working as specified, not a regression. The directive's "3 findings" number looks like it was estimated before accounting for what per-file omission scoping would actually change.

Score (27) is well under the <70 threshold and all three originally-verified real findings are intact, so I judged this as "spec correctly implemented, stale estimate" rather than a blocking failure — but I did not adjust the fix to force the count back to 3, since doing so would mean re-introducing some form of tree-wide suppression, which is the exact defect class this phase exists to remove. Flagging rather than deciding: if the operator wants these three specific files silenced (e.g. because subprocess-for-launching-a-daemon is an accepted, intentional pattern in this codebase and not something worth a per-file `undocumented_capability` nag), that's a scoring-policy call, not a bug fix, and stays with Cursor.

## Files touched

- `%USERPROFILE%\.cursor\skills\semantic-deception-detector\scripts\scan.py` (outside `telegram_bot2/`, no repo diff)
- `tbcc/docs/handoffs/2026-08-22_semantic-deception-scanner-hardening_report.md` (this file)

No `telegram_bot2/` source files modified. No commit made anywhere (skill dir has no git repo attached).

## Risks / open questions

1. **The 3-vs-6 finding count deviation above** — needs your sign-off: accept per-file omission scoping's real output, or add a scoping/allowlist policy for known-intentional subprocess usage (would be a Phase 3/scoring-policy change, out of this task's scope).
2. Per the original audit, `omission_kinds`' sibling logic wasn't independently re-audited beyond what S4 already touched — no further issues found while implementing, but a dedicated read wasn't a separate pass.
3. Workspace-root default target question from the audit report is still open and untouched by this phase (SKILL.md default-target policy is explicitly out of scope here).

## Operator smoke (Tray only)

N/A — no bots/Celery/tray touched this phase.

## Do not

- Do not start Phase 3 (scoring split / `confidence` field) or `--tree-wide` opt-in mode — both explicitly out of scope.
- Do not widen the scanner's default target to the monorepo root yet.
- Do not edit SKILL.md — Cursor owns that patch post-ACK per the directive.
- Do not push/deploy — no repo changes were made this phase.
