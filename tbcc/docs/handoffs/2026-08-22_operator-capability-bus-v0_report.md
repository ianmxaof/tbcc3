# Reverse handoff — operator-capability-bus-v0

- Branch: `lane-c/gatekeeper-lane-split`
- Head commit this phase: `49cbc55` docs(research): correct the Reddit-delay claim with real measured data
- Status: **Phase A + B complete, needs Cursor review**

## Done

### Phase A — registry + hub list/dispatch (I1, I2, I5)

- `%USERPROFILE%\.cursor\skills\operator-cli\registry.json` (new) — 4 skills: `semantic-scan` (`status: live`), `research`/`llm`/`slots` (`status: delegate`), each with `id`/`description`/`entry`/`corpora[]`.
- `operator_cli.py` rewritten to load the registry instead of hard-coding one command: `operator list` prints it; `research`/`llm`/`slots` forward their full remaining argv unchanged to `py -3.13 tbcc\backend\scripts\tbcc_cli.py <cmd> <rest>` (run with `cwd=tbcc\backend`, matching how the operator runs it by hand) — no reimplementation of any of the three engines, no argument parsing on the hub side beyond `argparse.REMAINDER`, so every flag those subcommands already accept works through the hub with zero extra wiring. `semantic-scan`'s existing live-dispatch behavior (path or URL, `--self-test`, etc.) is unchanged.

### Phase B — research feed-add (I3, I4, I7)

- `app/services/research_scanner.py`: `_SOURCES_PATH` constant replaced with `_sources_path()` (mirrors the existing `_db_path()` env-override pattern) — respects `TBCC_RESEARCH_SCANNER_SOURCES` for tests, defaults to the real file otherwise. Added `list_sources()` (raw dicts, file order) and `add_source()` (validates required fields + `lane ∈ {dev,growth,content}`, rejects duplicate id or duplicate url with `ValueError`, appends via targeted text insertion rather than a full `json.dumps` re-serialize — keeps the file's hand-curated single-line-per-source formatting and lane groupings intact instead of reformatting all 21 existing entries into a multi-line diff for a one-line addition).
- `tbcc_cli.py`: `research feed-add --id --url --label --lane [--json]` and `research feed-list [--json]`, following the existing `slots add`/`slots list` call/print convention (`ValueError` → stderr + exit 1).
- `operator research feed-add|feed-list|scan` all forward through the same Phase A delegate path — verified feed-list round-trip through the hub, not just direct `tbcc_cli.py`.
- Tests: `tests/test_research_scanner.py` gained 6 new tests (`_sources_file` fixture using `TBCC_RESEARCH_SCANNER_SOURCES` + a seeded tmp JSON, not the production file) — list reads seed, add appends + round-trips through `load_sources()`, duplicate id rejected, duplicate url rejected, invalid lane rejected, each missing-field case rejected. All pre-existing tests (including the production-file-reading `test_load_sources_reads_real_config` asserting `len == 21`) untouched and still pass.
- Docs (I6): expanded `operator-cli/SKILL.md` (v0.1 → v0.2 — Layout, Subcommands, "Do not rebuild", and a dedicated "local transferable context, not Context7" section) and added `tbcc/docs/OPERATOR_CAPABILITY_BUS.md` (new, ~1 page) so a TBCC-side session knows the hub exists without already knowing the `%USERPROFILE%\.cursor\skills\` path.

## Verification run

```
python operator_cli.py list
→ prints all 4 registered skills with entry + corpora

python operator_cli.py semantic-scan --self-test
→ self-test: PASS {"score": 100, "level": "HIGH", ...}   (unchanged from Phase 3)

py -3.13 -m pytest tests/test_research_scanner.py -x -q --tb=short
→ 29 passed   (23 pre-existing + 6 new)

py -3.13 scripts\tbcc_cli.py research feed-add --id bus-v0-test-hn --url "https://hnrss.org/frontpage" --label "HN frontpage (bus-v0 test)" --lane growth
→ bus-v0-test-hn: added (growth) https://hnrss.org/frontpage   (exit 0)

py -3.13 scripts\tbcc_cli.py research feed-list --json
→ 22 sources, new entry present, all 21 originals byte-identical

py -3.13 scripts\tbcc_cli.py research feed-add --id bus-v0-test-hn --url "https://hnrss.org/frontpage" --label "dup" --lane growth
→ source id already registered: bus-v0-test-hn   (exit 1, as required)

python operator_cli.py research feed-list --json
→ same 22 sources via the hub delegate path

python operator_cli.py llm status
→ sticky provider + 13-provider table printed, exit 0

python operator_cli.py slots list --json
→ []   (exit 0 — no slots registered on this machine yet, expected)
```

**Cleanup:** per the working agreement, removed `bus-v0-test-hn` from the production `research_scanner_sources.json` after verification (`git checkout --` on that one file — confirmed via `git diff` beforehand that the only change was the single appended line, comma-corrected, nothing else touched). Re-ran the pytest suite after reverting: still 29 passed, including `test_load_sources_reads_real_config`'s `len == 21` assertion.

## Files touched

Outside `telegram_bot2/` (no repo diff, skill dir has no git):
- `%USERPROFILE%\.cursor\skills\operator-cli\operator_cli.py` (rewritten)
- `%USERPROFILE%\.cursor\skills\operator-cli\registry.json` (new)
- `%USERPROFILE%\.cursor\skills\operator-cli\SKILL.md` (v0.1 → v0.2)

Inside `telegram_bot2/` (this phase's diff only — working tree currently has substantial unrelated changes from other concurrent sessions, not touched or reviewed here):
- `tbcc/backend/app/services/research_scanner.py`
- `tbcc/backend/scripts/tbcc_cli.py`
- `tbcc/backend/tests/test_research_scanner.py`
- `tbcc/docs/OPERATOR_CAPABILITY_BUS.md` (new)
- `tbcc/docs/handoffs/2026-08-22_operator-capability-bus-v0_report.md` (this file)

No commit made — working tree only, per the working agreement.

## Risks / open questions

1. **`py -3.13` on PATH assumption.** `_delegate_to_tbcc_cli` shells out to `["py", "-3.13", ...]` rather than `sys.executable`, matching how the operator runs `tbcc_cli.py` by hand (and this repo's own `CLAUDE.md` verification defaults). This only works if the `py` launcher is on PATH for whatever process invokes `operator_cli.py` — verified working in this session's shell; flagging in case Hermes/Cursor invoke it from a context where `py` isn't resolvable (a plain venv `python` on PATH without the launcher, for instance).
2. **`add_source`'s text-splice write** (vs. a full `json.dumps` re-serialize) is a deliberate diff-minimizing choice, not something the directive specified either way — flagging the design call for visibility rather than silently picking it. It round-trips correctly (verified: `json.loads` on the result, plus `load_sources()`/`list_sources()` both read it back correctly) and produces a clean single-line diff, but it is more fragile than a generic serializer if the file's structure (a `"sources": [...]` array with a trailing `]`) ever changes shape by hand.
3. No allowlist or rate-limit added on `feed-add` itself — anyone with local CLI access can add arbitrary RSS URLs to the scanner's source list. Existing `research scan` fault-isolation (one bad/slow source never blocks the rest) already contains the blast radius; flagging only because it's a new write path that didn't exist before this phase.

## Operator smoke (Tray only)

N/A — no bots/Celery/tray touched this phase; `research feed-add`/`feed-list` are local file operations, `llm`/`slots` delegates only read/report existing local state.

## Do not

- Do not build the multi-agent work queue / full bus orchestration — explicitly out of scope for v0.
- Do not touch vision_llm / Storage Hub / island deploy, or add a Context7 integration.
- Do not change research match prompts, lane doctrine, or LLM ranking.
- Do not push/deploy — no repo changes were committed this phase.
