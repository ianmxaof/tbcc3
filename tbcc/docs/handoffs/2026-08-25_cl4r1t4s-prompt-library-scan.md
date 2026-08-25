# Handoff — CL4R1T4S prompt-library scan (open, not closed)

**Date:** 2026-08-25
**Type:** Findings / primer — not a CC Relay directive, no ACK required
**Status:** Analysis only. Nothing implemented. Left open on purpose for other agents/perspectives.

## What this is

The operator asked Claude Code to entropy-scan a downloaded copy of the `elder-plinius/CL4R1T4S` repo — a public collection of leaked/published system prompts from frontier LLM products (Claude, GPT, Gemini, Grok, Devin, Cursor, ZCode, etc.) — for anything portable into TBCC's own `.claude/skills/` or `.claude/CLAUDE.md`. Three scan passes happened across this session, plus one from DeepSeek in a separate chat the operator ran in parallel. This doc collects all of it in one place rather than letting the findings live only in transcript scrollback.

**This handoff is deliberately open-ended.** It does not lock in a conclusion or a single recommended slice. It's a primer for whichever agent (Cursor, a fresh Claude Code session, DeepSeek, the operator) looks at this next — read the sources yourself before trusting any summary below, including this one.

## Source paths

| What | Path | Notes |
|------|------|-------|
| Local repo copy (real, downloaded) | `C:\Users\ianmp\Downloads\CL4R1T4S-main\CL4R1T4S-main\` | ~40 vendor folders (ANTHROPIC, OPENAI, DEVIN, ZAI/ZCode, CURSOR, GOOGLE, XAI, FACTORY, REPLIT, etc.), mostly `.md`/`.txt` system prompts |
| Origin (not fetched by any agent in this session — no browsing tool was used) | `https://github.com/elder-plinius/CL4R1T4S/tree/main` | Cite the local copy, not this link, when making claims — nobody here has confirmed the two are in sync |
| Operator's ChatGPT/Claude conversation about the repo | `C:\Users\ianmp\Documents\claritas.txt` | **Read this with a caveat**: its first analysis pass explicitly admits it never fetched the repo ("I don't have direct live access... I must rely on training data") and guessed at filenames/content. Several guesses were wrong once checked against the real repo. Treat everything before the operator's real download as speculation, not evidence. |
| DeepSeek's follow-up completion | Pasted into this Claude Code session's transcript (not a standalone file — ask the operator if they want it exported from the DeepSeek chat) | Fact-checked in this session against the real repo files — its specific quotes from `DROID.txt` and `DEVIN/Devin_2.0.md` / `Devin2_09-08-2025.md` came back **accurate**, near-verbatim. Unlike claritas.txt's first pass, this one appears grounded. |

## What each pass actually found

**Pass 1 (revenue → innovation lens, working from claritas.txt only, before the real repo was downloaded):** Flagged that claritas.txt's analysis was speculative and shouldn't be acted on. No real findings possible without the source.

**Pass 2 (innovation lens, real repo, light sampling):** One verified, concrete finding — `ZAI/ZCode/Skills.md` contains `web-gui-tester`, a real 4-phase black-box UI-testing methodology (scenario assessment → P0–P3 priority test plan → action/observation loop with mandatory before/after screenshot evidence → pass/fail report). TBCC's CLAUDE.md says to test UI changes in a browser before reporting done, but has no structure behind that instruction — `tbcc/dashboard/` (React) and `aof-forum/` (Next.js) are exactly its domain. Proposed but not built: a `tbcc-ui-test` skill (or a fold-in to the existing `run` skill) adapting this methodology, scoped to those two surfaces.

**Pass 3 (devops lens, pushed by operator for more depth):** Grepped the whole repo for devops/monetization engineering terms (retry, backoff, circuit breaker, idempotent, rate limit, dedupe, attribution, funnel, paywall, affiliate, UTM). Every hit was generic chatbot boilerplate, not real engineering content — confirmed by reading two specific files (`GPT-4o_Image_Gen_Postfill.txt`, `PERPLEXITY/Perplexity_Deep_Research.txt`) that turned out to be a 2-line UI quirk and a report-formatting spec, respectively. Conclusion at the time: this repo's genre is AI persona/behavior prompts, not a software-engineering-pattern library — devops/monetization axis came back essentially empty.

**DeepSeek's pass (same repo, different grep target — behavioral policy language instead of infra jargon):** Found real content this session's devops grep missed, because it searched for the right kind of thing. 15 candidate primitives, with source quotes. Fact-checked in this session against `DROID.txt` and the two Devin files — the quotes check out. Evaluated against what Claude Code actually is (not Cursor, which DeepSeek's framing assumed):

- **Already native to Claude Code, not a gap:** DROID's DIAGNOSTIC/IMPLEMENTATION mode gate (≈ `EnterPlanMode`/`ExitPlanMode`), the pre-edit mandatory-read rule (the `Edit` tool already refuses to run without a prior `Read` this session), `git add .` avoidance, no-comments-by-default, blocked/done signaling (≈ TBCC's own CC Relay ACK protocol).
- **Not applicable here:** package-manager-from-lockfile detection (TBCC backend is single-ecosystem Python), alert()-ban / Tailwind-vs-custom-CSS (real but low-stakes UI style items, nobody's hit this).
- **Genuinely missing, verified real, and TBCC-relevant:**
  - Test-first diagnosis discipline (`Devin_2.0.md:18`): "never modify the tests themselves... always first consider the root cause might be in the code you are testing." TBCC's completion gates run pytest but never say don't edit the failing test to make it pass.
  - N-strike escalation (`Devin_2.0.md:59`): "ask the user for help if CI does not pass after the third attempt." TBCC has a >8-files scope-halt gate but nothing analogous for a loop of failed fix-and-rerun cycles on the same test.

**Status of that recommendation: proposed, not adopted.** The operator moved to requesting this handoff + the `tbcc-integration-scan` improvement instead of picking a slice. Both candidate CLAUDE.md additions above are still just a suggestion sitting in this document.

## Side finding, also unresolved

The operator asked, mid-scan, about wrapping a cheaper/more consistent model (Kimi K2 named specifically) onto Sonnet or Cursor's Auto routing to cut cost. Answered narrowly in-session: Cursor's Auto is Cursor-side infra Claude Code can't attach to, and Claude Code's own model selection isn't a multi-vendor router today. Current Kimi K2 pricing/benchmarks were **not** looked up (no web tool used) — this is open if the operator wants a grounded answer instead of a training-data guess.

## What changed as a direct result of this scan

- `.claude/skills/tbcc-integration-scan/SKILL.md` — two additions, both earned by mistakes/lessons from this session, not speculative: (1) an "already-native" axis/tag, so a candidate that just re-describes something this environment already enforces gets flagged instead of scored as a fit; (2) a verify-before-trust step in the procedure — when candidates come from a secondhand summary or another model's completion rather than something fetched/read directly, spot-check its specific claims against the primary source first. Both were prompted directly by claritas.txt's fabricated first pass vs. DeepSeek's verified second pass sitting side by side in this same task.

## Open invitation

This doc is meant to be added to, not treated as final. If Cursor, a fresh Claude Code session, or another model picks this up:

- Re-verify the "already native" calls above against whatever Claude Code/Cursor version is current when you read this — tool contracts change.
- The devops/monetization axis came back empty on this session's search terms; that's evidence about *this session's grep choices*, not proof there's nothing there — DeepSeek already showed a different search angle surfaces real content.
- The `~40` vendor folders in the local repo were sampled, not exhaustively read (ANTHROPIC, OPENAI, GOOGLE, XAI, MULTION, MISTRAL, META and others were grepped but not deep-read file by file). There may be more here.
- Do not act on anything in `claritas.txt` without checking it against the local repo copy first — that's the one hard lesson this whole exercise produced.

## Not touched

Runtime code, bots, `.env`, `CURRENT_DIRECTIVE.md`, any new skill file. The two CLAUDE.md rule additions (test-first diagnosis, N-strike escalation) discussed above were **not** applied — they remain a proposal in this document only.
