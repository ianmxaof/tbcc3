# Forward handoff — operator capability bus v0 (registry + feed-add)

- **Target:** Claude Code (Lane C)
- **Author:** Cursor (entropy-scan pick 1, 2026-08-22)
- **Status:** ready to paste
- **Reverse report expected:** `tbcc/docs/handoffs/2026-08-22_operator-capability-bus-v0_report.md`

## Context

Operator capability bus: shared CLI registry + transferable local context (not Context7).
Slice 1 = registry schema, register four skills, implement `research feed-add`.

Existing TBCC primitives (do not reinvent):
- Research: `research_scanner.py` + `tbcc_cli.py research scan` — no feed-add yet
- LLM rotator: `tbcc_cli.py llm ask|next|status|keys`
- API Pocket (mechanical arm): `tbcc_cli.py slots add|list|show|call|remove|suggest`
- Semantic-scan: `~/.cursor/skills/semantic-deception-detector` via `operator_cli.py`

See paste block in chat for full directive.
