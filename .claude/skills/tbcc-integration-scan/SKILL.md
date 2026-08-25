---
name: tbcc-integration-scan
description: Capped scan of candidate external tools/repos/models/prompt-libraries against the current pipeline before adopting one — checks secondhand claims against the primary source, flags already-native duplicates, surfaces fit per candidate across up to 6 axes, then stops for a pick. Invoke as /tbcc-integration-scan with one or more URLs, names, or a pasted analysis.
---

# TBCC Integration Scan

Surface adoption fit for external tools/libraries/models **before** wiring one in — then stop and wait for a pick. This is a Plan-only scan: no file edits, no dependency installs, no Dockerfiles, until the operator picks a candidate or says "literal only".

Sibling to `tbcc-entropy-scan` (leftover yield *inside* the codebase) — this scan looks *outward* at candidates the operator pastes or names, and answers "does this slot in cleanly, or does it fight the doctrine/architecture."

## When to invoke

- Trigger phrases: `/tbcc-integration-scan`, "does this work for our pipeline", "any of these easy wins", "integration scan", a paste of one or more GitHub/HF/PyPI links followed by "would this help / fit / be worth adding"
- Situational: the operator drops candidate tools without a file-level spec yet — before any adoption decision, not after
- **Skip** (do not expand — just answer directly): a single named library already decided on with a clear "add X" instruction; a version bump; anything already covered by `tbcc-entropy-scan`'s `innovation` lens mid-scan

## Evaluation axes (score each candidate against these)

- **Already-native check** — does the candidate duplicate a mechanism this environment already enforces (a tool contract, a base instruction, an existing skill/CLAUDE.md rule)? If so, tag it `already-native` and stop scoring further axes for that one — citing the existing mechanism (path or behavior) is the whole answer. Don't let a candidate score `fits` just because it's well-written if it's re-describing something already running.
- **Architecture fit** — does it slot into an existing extension point (sidecar/signal behind an env-var gate, a Celery task, a Beat tick) or does adopting it require inventing a new integration shape? Cite the existing pattern it would mirror (e.g. `clip_categorize_app.py`'s sidecar shape) or note there isn't one.
- **Doctrine fit** — does it respect the locked red lines (e.g. `MEDIA_GATEKEEPER.md`'s "vision LLM/CLIP sidecars are signals, never the judge for age/zoo/illegal content")? Anything that would need a doctrine change is `blocked`, not `missed`.
- **Effort vs. what's already required** — is it a served API/model you point at, or a GUI/desktop/CLI tool you'd have to re-wrap (same lift as building the integration from scratch, just borrowing weights/logic)?
- **Data / privacy** — self-hosted (data never leaves infra) vs. calls an external API (new data-egress surface, new cost line, new ToS to check)?
- **Maintenance risk** — license, last-commit recency, single-maintainer bus factor — only flag when it changes the recommendation, don't pad with generic OSS caveats.

Drop an axis from the table if it's not differentiating for the candidates in hand (e.g. all candidates are self-hosted — skip the data/privacy row rather than writing "n/a" five times).

## Behavioral rules

- Reason by: literal ask → per-candidate axis table → one recommended slice **or** an explicit no-ascend
- Avoid: recommending a rewrite of a working signal path to swap in a shinier model; treating "it's on GitHub" as evidence of fit; silently expanding scope to "let's also evaluate the whole vision pipeline" when the ask was three links; scoring candidates off a secondhand summary (another model's writeup, a pasted analysis) without checking its specific claims against the primary source first — a fluent synthesis is not evidence it's accurate, and an ungrounded one can look identical to a grounded one until checked
- Prioritize: candidates that plug into an *existing* extension point over ones that require a new one; self-hosted over external-API when the pipeline is already self-hosted-first; the operator's stated done-condition

## Output contract

Required, all four, dense — short bullets, no essay:

1. **Literal ask** — one sentence naming what was pasted/asked
2. **Candidates** — per candidate: one line, tagged `fits` | `partial-fit` | `no-fit` | `already-native` | `blocked`, plus the one-clause reason (cite the axis that decided it)
3. **Recommend?** — `yes` + one slice with a testable done-condition (what stood up, what it's measured against), **or** `no` + why none clear the bar this pass
4. **Fence** — in scope / out of scope; which candidates are explicitly not being adopted or spiked this pass

Failure contract: if a candidate would require a doctrine change (e.g. letting a model judge age/zoo content) or breaks an operator-policy red line (e.g. requires a second live Telethon connection), tag it `blocked` and stop expanding it — do not design around the block. Report what was scanned and what was skipped.

## Procedure

1. Identify the candidates from the paste (URLs, repo names, or described tools).
2. Skim what each one actually is (README/description) — don't assume from the name. If the source is a secondhand summary or another model's completion rather than something fetched/read directly, spot-check its specific factual claims (quotes, file names, described mechanisms) against the primary source before trusting it — treat an unverified paste the same as an unverified name.
3. Score each against the axes that differentiate for this set (drop non-differentiating axes), applying the already-native check first.
4. Emit the four Output Contract sections.
5. Stop. Do not install, clone, Dockerize, or wire anything in until the operator picks a candidate or says "literal only".
