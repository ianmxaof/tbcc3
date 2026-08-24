# Reverse handoff — semantic-deception-detector audit

- Branch: `lane-c/gatekeeper-lane-split`
- Head commit this phase: `49cbc55` docs(research): correct the Reddit-delay claim with real measured data
- Status: **needs Cursor review** — findings only, no code changed

## Context

Operator asked whether the `semantic-deception-detector` skill (a Cursor/Hermes-shared scanner for docs-vs-behavior mismatches, hidden Unicode, and prompt-injection bait — **not** a TBCC repo skill; lives at `~/.cursor/skills/semantic-deception-detector/`, shared per its own SKILL.md line 14: "Cursor and Hermes share the same scanner script") is solid enough to deploy anywhere. Operator's stated plan: keep it scoped to `tbcc/` alone until it's hardened, then widen to the full `telegram_bot2` monorepo. This report is the evidence for that call.

Also relevant: operator recently removed a folder from the Cursor workspace. When `tbcc/` was the only folder open, `scan.py`'s stated default ("current workspace root") resolved to `tbcc/`. The workspace root is now `telegram_bot2/` (parent of `tbcc/`), so an unqualified default-target run would now walk the wider monorepo (`aof-forum/`, etc.) instead of just `tbcc/` — worth knowing if anyone runs `/semantic-scan` without an explicit target going forward.

## What ran

```
python scripts/scan.py --self-test          # PASS, score 100 HIGH (self-test fixture, expected)
python scripts/scan.py --json -- "C:\Powercore-repo-main\telegram_bot2\tbcc"
```

Read-only. No `tbcc/` files touched, no scanner code changed. 398 files / 46,804 LOC scanned in 1.4s, exit code 1 (REVIEW/HIGH). `node_modules` and `.git` are excluded by the scanner itself (confirmed in source, lines 30/35), so the fast runtime and finding count aren't an artifact of vendored-code noise.

## Result: risk_score 100 / HIGH, 7 findings

| category | count | verdict |
|---|---|---|
| `side_effect_contradiction` | 3 | **false pairing** (see below) |
| `direct_contradiction` | 1 | **false pairing** (see below) |
| `hidden_unicode` | 2 | correct, benign |
| `undocumented_capability` | 1 | correct, real signal |

### The 3 legitimate findings

- Two `hidden_unicode` hits (`aof_network.py:155`, `aof_storage_hub_map.py:145`) are U+200D (zero-width joiner) inside literal compound emoji strings (e.g. `🧔‍♀️`), correctly bucketed as the low-weight non-agent-rule category rather than the TrapDoor-class `hidden_unicode_agent_rule` bucket. Working as designed.
- One `undocumented_capability` hit (`subprocess` import in `assets/emoji/fyp-aof-divider/_compose_fyp_aof.py:14`, no docs mention) is self-contained and real.

### The 4 false-pairing findings — root cause confirmed in source

`map_contradictions()` (`scan.py:410-459`) pairs the **first denial claim found anywhere in the whole scanned tree** with the **first matching capability found anywhere in the whole tree** — it is not scoped per file, per module, or even per package. Concretely reproduced:

- Finding: `direct_contradiction` at `backend/app/api/archive.py:74` ("docs deny network ('offline' at `backend/app/api/emoji_factory.py:1`)"), evidence `from urllib.parse import ...`.
- `archive.py` and `emoji_factory.py` have no relationship — one file's unrelated network import got matched against a completely different file's docstring.
- Same root cause produced the other two `side_effect_contradiction` findings (`archive.py:74` again, and `assets/emoji/fyp-aof-divider/_compose_fyp_aof.py:13-14`), all citing the same borrowed claim from `backend/app/api/analytics.py:1` ("no side effects").

**Second, compounding bug — the cited line number is also wrong.** `harvest_claims()` (`scan.py:241-256`) computes `line = text[:m.start()].count("\n") + 1` against whatever text it's handed. For claims sourced from a docstring, callers pass just the extracted docstring string (`doc`, `d` — `scan_python()` around lines 358-367), not the full file. So the reported line number is the match's offset *inside the docstring*, not its position in the file. Verified directly: the finding cites `'offline'` at `emoji_factory.py:1`, but grepping that file shows no "offline" anywhere near line 1 — the module docstring (line 1) is a single unrelated line ("Emoji pack factory — prerequisites check + manifest upload (local paths)."). The actual match is on line 301, inside a *function* docstring ("Run a queued job inline when Celery worker is offline (dev / recovery)."). Because that docstring is a single line, the offset-within-docstring math resolves to line 1, which then gets reported as the file's line 1 — silently wrong.

Net effect: this directly breaks the skill's own stated contract in its Output Contract section ("Demand evidence: path + line + snippet for every alarm. No vibe scores.") — the path is right, but the line is fabricated by an offset bug, and the pairing itself crosses file boundaries the tool has no business crossing. On a 398-file repo with zero actual cross-file contradictions, this alone was enough to max the score at HIGH/100.

## Recommendation

Not ready to deploy as a trusted signal (auto-flagging, gating, or anything unreviewed) yet. It's ready as a human-reviewed leads generator only, and only with the `hidden_unicode`/`undocumented_capability` categories — the two contradiction categories should be treated as unreliable until fixed.

Two fixes, both isolated to `scan.py`, before this gets any wider run than `tbcc/`:

1. **Scope `map_contradictions` per file.** Group `claims` and `caps` by `path` (or at minimum don't let a denial in file A get paired with a capability in file B) before running the `pairs` loop at `scan.py:437-459`.
2. **Fix docstring line attribution.** `harvest_claims` needs the docstring's starting line (e.g. `node.lineno`, or the AST body's first `Expr` line) added to its internal offset, not just the offset within the extracted substring — for both the module-docstring call site (`scan.py:360`) and the per-def call site (~`scan.py:367`).

This wasn't fixed in this pass — the skill lives outside `tbcc/` (no repo file to touch), and per Lane C doctrine "Cursor owns judgment (pricing, doctrine); Lane C implements locked plans only," a fix to shared Cursor/Hermes scanning logic seemed like the kind of call that should get your sign-off before code changes, especially since Hermes runs this unattended via cron-adjacent skills.

## Files touched

None. Read-only investigation (`scan.py` inspected via `Read`/`Grep`; one live scan run against `tbcc/`, output written to a scratch temp file, not committed anywhere).

## Verification run

```
python scripts/scan.py --self-test
→ self-test: PASS {"score": 100, "level": "HIGH", "cats": [...]}

python scripts/scan.py --json -- "C:\Powercore-repo-main\telegram_bot2\tbcc"
→ risk_score 100, risk_level HIGH, files_scanned 398, loc_scanned 46804, 7 findings
```

## Risks / open questions

- Is `map_contradictions`'s whole-tree pairing intentional (a cheap first-pass "does *anything* in this tree contradict *anything* else" smoke test) rather than a bug? If so the Output Contract wording ("Demand evidence... No vibe scores") oversells the precision and should be softened instead of the matcher being rescoped.
- Same open question for the sibling `omission_kinds` block (`scan.py:461+`, not fully audited this pass) — worth a follow-up read once the two confirmed bugs are addressed, in case it shares the same whole-tree assumption.
- Workspace-root default (see Context) — confirm before anyone runs `/semantic-scan` unqualified against `telegram_bot2` that the operator wants monorepo-wide scope, not `tbcc/`-only.

## Do not

- Do not widen this scanner's default target beyond `tbcc/` until the two fixes above land and are re-verified against this same 7-finding baseline.
- Do not treat current `direct_contradiction` / `side_effect_contradiction` output as actionable without manually checking the cited file/line first — they're currently unreliable in a way that reads as confident.
- Do not push/deploy anything — this phase made no repo changes.
