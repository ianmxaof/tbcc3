/**
 * Operator GPT Pocket Kit — built-in slash-trigger prompts for tbccSnippets.
 * Source: tbcc/docs/OPERATOR_GPT_POCKET_KIT.md
 * Seeded into chrome.storage.local on extension install/update (see background.js).
 */
(function (root) {
  const STORAGE_SNIPPETS = "tbccSnippets";
  /** Retired catalog ids removed on the next seed pass (operator chose to drop them). */
  const RETIRED_CATALOG_IDS = new Set(["opr-ask"]);

  /** @type {Array<{catalogId:string,trigger:string,label:string,body:string}>} */
  const CATALOG = [
    {
      catalogId: "followup",
      trigger: "/followup",
      label: "Chat follow-up (uses clipboard + cursor)",
      body: "Continuing our thread:\n\n{{clipboard}}\n\n{{cursor}}",
    },
    {
      catalogId: "directive",
      trigger: "/directive",
      label: "Cold-start handoff for another GPT/agent",
      body: [
        "You are a cold-start agent with ZERO prior context. Everything you need is below.",
        "",
        "GOAL:",
        "<outcome, not method>",
        "",
        "SCOPE:",
        "In: <…>",
        "Out of scope: <…>",
        "",
        "PRIOR STATE:",
        "<none — greenfield OR verified facts with sources; mark unknown if unverified>",
        "",
        "ISSUE CARDS (≤8, in order):",
        "I1. Symptom: …",
        "    Evidence: <path/log/repro or unknown>",
        "    Severity: P0|P1|P2",
        "    Depends on: none|I#",
        "    Acceptance: <testable>",
        "",
        "CONSTRAINTS:",
        "- Judgment: MAY <…> / MUST NOT <pricing/doctrine by default>",
        "- Do not invent file paths or claim tools ran",
        "",
        "VERIFICATION:",
        "<something checkable without tools, OR exact command the human will run and paste back>",
        "",
        "WORKING AGREEMENT:",
        "Reply: Done / What you concluded / Verification / Open questions / What you could not do.",
        "Do not claim edits, commands, or tests. Stop after one full reply.",
      ].join("\n"),
    },
    {
      catalogId: "entropy-scan",
      trigger: "/entropy-scan",
      label: "≤5 leftover-yield vertices before building",
      body: [
        "Run an ENTROPY SCAN (Plan-only, no code).",
        "",
        "Lens: <revenue|devops|marketing|innovation|… or infer>",
        "Literal ask: {{cursor}}",
        "",
        "Output exactly:",
        "1) Literal ask (+ Lens)",
        "2) Vertices (≤5): each missed|covered|blocked + one clause why",
        "3) Ascend?: yes + ONE slice + done-condition OR no + why stay literal",
        "4) Fence: in / out",
        "",
        "Rules: no fake FOMO; no rewriting locked doctrine; stop for my pick. Do not implement.",
      ].join("\n"),
    },
    {
      catalogId: "integration-scan",
      trigger: "/tbcc-integration-scan",
      label: "External tool/repo fit before adopt",
      body: [
        "Run an INTEGRATION SCAN (Plan-only). Candidates:",
        "<URLs / names / pasted analysis>",
        "",
        "Score each on differentiating axes only:",
        "- already-native (cite existing mechanism → stop scoring that candidate)",
        "- architecture fit (existing extension point?)",
        "- doctrine fit (blocked if needs red-line change)",
        "- effort vs rebuild",
        "- data/privacy egress",
        "- maintenance risk (only if it changes the call)",
        "",
        "Output:",
        "1) Literal ask",
        "2) Candidates: fits|partial-fit|no-fit|already-native|blocked + one-clause reason",
        "3) Ascend?: one recommended slice OR no-ascend",
        "4) Fence",
        "",
        "Verify secondhand claims against primary sources before trusting them. No installs/edits.",
      ].join("\n"),
    },
    {
      catalogId: "silent-fail",
      trigger: "/silent-fail",
      label: "Class-2 never ran / stale (external stops)",
      body: [
        "Run a SILENT-FAIL PASS (class-2 work-never-ran). Readonly; no restarts.",
        "",
        "For each watch I care about (or infer from this change set):",
        "- enablement true? expected cadence?",
        "- probe with EXTERNAL stop only: http | api_field | redis | db | file_mtime | pytest | log_ts",
        "- verdict: ok | stale | never_seen | idle | blocked",
        "",
        "Rules:",
        "- Agent self-attestation is invalid",
        "- intentional-idle (*_ENABLED=0, governed_idle) = idle, not zombie",
        "- Cap ≤5 always-on / ≤8 conditional",
        "Output a table: watch | enablement | cadence | stop evidence (verbatim) | verdict",
        "Then stop. Do not auto-fix.",
      ].join("\n"),
    },
    {
      catalogId: "zombie-pass",
      trigger: "/zombie-pass",
      label: "Alias — same as /silent-fail",
      body: [
        "Run a SILENT-FAIL PASS (class-2 work-never-ran). Readonly; no restarts.",
        "",
        "For each watch I care about (or infer from this change set):",
        "- enablement true? expected cadence?",
        "- probe with EXTERNAL stop only: http | api_field | redis | db | file_mtime | pytest | log_ts",
        "- verdict: ok | stale | never_seen | idle | blocked",
        "",
        "Rules:",
        "- Agent self-attestation is invalid",
        "- intentional-idle (*_ENABLED=0, governed_idle) = idle, not zombie",
        "- Cap ≤5 always-on / ≤8 conditional",
        "Output a table: watch | enablement | cadence | stop evidence (verbatim) | verdict",
        "Then stop. Do not auto-fix.",
      ].join("\n"),
    },
    {
      catalogId: "crew",
      trigger: "/crew",
      label: "Maker/checker swarm → silent-fail",
      body: [
        "Spin a MAKER/CHECKER CREW. Preset: investigate|preflight-review|ops-brief",
        "",
        "Graph spec (investigate/preflight-review — paste from tbcc/docs/CREW_GRAPH_SPEC.md):",
        "GOAL / PARALLEL WORK (≤3) / EDGE DATA per arrow / REDUCER / VERIFICATION (checker falsifies) /",
        "FAILURE POLICY / BUDGET / HUMAN GATE",
        "",
        "Rules:",
        "- ≤3 makers + 1 coordinator checker",
        "- Role isolation in prompts/tools (not “five bots one login”)",
        "- Makers readonly unless I unlock write",
        "- No Start bots / .env",
        "- Coordinator must state what exact data crosses each maker→checker edge",
        "- Coordinator synthesizes contradictions and refuses “looks fixed”",
        "- End with a SILENT-FAIL stop list (external probes), then stop for my pick",
        "",
        "Output: graph spec → role results → coordinator verdict → silent-fail watches → open questions",
      ].join("\n"),
    },
    {
      catalogId: "cc-run",
      trigger: "/cc-run",
      label: "Claude Code — execute latest directive",
      body: [
        "You are TARGET for an existing forward directive (do not re-author a new handoff).",
        "",
        "1) Read tbcc/docs/handoffs/CURRENT_DIRECTIVE.md, else newest non-*_report.md handoff",
        "2) Implement ACTIVE PHASE ONLY",
        "3) Write matching *_report.md: Done / Changed / Verification / Deferred / Open questions",
        "4) STOP. Do not ask push-vs-Cursor as the main question. Do not expand fence.",
      ].join("\n"),
    },
    {
      catalogId: "cc-report",
      trigger: "/cc-report",
      label: "Cursor — review CC reverse report",
      body: [
        "Review this Claude Code reverse report (pasted below).",
        "Confirm: done-condition met? verification credible? fence respected?",
        "Output: ACK | NACK + gaps | Deferred to pick up next | Recommended next protocol (/continue-thread|/directive|/silent-fail|/preflight)",
        "Do not start implementing unless I say so.",
        "",
        "REPORT:",
        "<paste *_report.md>",
      ].join("\n"),
    },
    {
      catalogId: "continue-thread",
      trigger: "/continue-thread",
      label: "After ACK — next slice from deferred",
      body: [
        "CONTINUE THREAD after ACK.",
        "From the reverse report: list deferred / out-of-scope / open questions first.",
        "Recommend ONE next slice with a testable done-condition.",
        "Prefer report-authored deferred over new ideas. Do not reopen fenced “do not touch.”",
        "Then stop for my pick (next = /directive or implement here).",
      ].join("\n"),
    },
    {
      catalogId: "conductor",
      trigger: "/conductor",
      label: "What protocol next? (menu only)",
      body: [
        "You are PROTOCOL CONDUCTOR (menu only). From this situation:",
        "<what just finished / what’s ambiguous>",
        "",
        "Recommend ≤3 next protocols with one-line why each.",
        "Prefer chain edges: crew→silent-fail; entropy→preflight|directive|integration-scan; silent-fail→preflight|directive; signal-scout→ship-log.",
        "Do NOT auto-run the next protocol. Wait for my pick.",
      ].join("\n"),
    },
    {
      catalogId: "signal-scout",
      trigger: "/signal-scout",
      label: "Dev diary + paste fanout draft",
      body: [
        "SIGNAL SCOUT draft (no secrets).",
        "",
        "Opportunity: <why diary-worthy or none>",
        "Diary: ≤260 char teaser + optional longer body (prompt-craft voice; operator is primary reader)",
        "Bump: SFW CTA to hub/loot_free OR skipped",
        "Leak fence: never .env, keys, chat ids, undeployed pricing, ToS-violating NSFW on clearnet pastes",
        "Fanout plan: which hosts / Buffer? draft-only unless I say execute",
        "",
        "Output those 5 sections. Do not post unless I say execute/publish.",
      ].join("\n"),
    },
    {
      catalogId: "semantic-scan",
      trigger: "/semantic-scan",
      label: "Docs-vs-code / hidden Unicode triage",
      body: [
        "SEMANTIC DECEPTION triage (evidence only; no intent/guilt claims).",
        "",
        "Target: {{cursor}}",
        "Flag: docs-vs-behavior mismatches; hidden Unicode in agent rules; prompt-injection bait in comments/rules.",
        "Per finding: category, evidence quote, confidence high|heuristic.",
        "Do not generate jailbreaks or execute untrusted code. Summarize structural_level from high-confidence only.",
      ].join("\n"),
    },
    {
      catalogId: "ops-picture",
      trigger: "/ops-picture",
      label: "Money + ops health snapshot",
      body: [
        "OPS PICTURE (observe-only). Window: 30d money / 7d posts unless I say otherwise.",
        "Sources prefer live API/analytics if I paste them; else reason from pasted metrics/logs.",
        "",
        "Output:",
        "1) Pulse (money + runtime truth; include vision LLM spend if present)",
        "2) Blockers ranked ST money → LT money → Ops risk → Noise (≤8 themes)",
        "3) Funnel/scheduling one-liners",
        "4) Recommended next probe or fix (one pick) — no Start bots, no .env edits",
        "",
        "PASTE DATA:",
        "<health / analytics / logs>",
      ].join("\n"),
    },
    {
      catalogId: "analytics-direction",
      trigger: "/analytics-direction",
      label: "Data-driven Top 5 where to invest",
      body: [
        "ANALYTICS DIRECTION (observe-only). Rank where to invest next.",
        "Law: ST revenue > LT compounding > OPS risk.",
        "Output Top 5 directions with: horizon ST|LT|OPS, evidence metric, effort, mcp_followup/action, contradiction notes.",
        "Do not reorder by narrative fluff. No auto-execute growth proposals.",
        "",
        "PASTE SNAPSHOT / METRICS:",
        "<…>",
      ].join("\n"),
    },
    {
      catalogId: "daily-brief",
      trigger: "/daily-brief",
      label: "Cold-start priorities",
      body: [
        "DAILY BRIEF. No code.",
        "1) Pulse (1–3 sentences)",
        "2) Untied (≤8 material loops)",
        "3) Top 5 highest $ impact first (ST→LT→OPS→velocity); each: horizon, effort, lane Why+How, evidence",
        "4) Skip / defer with why",
        "Stop for my pick. Do not implement yet.",
        "CONTEXT:",
        "<sprint / notes / handoffs paste>",
      ].join("\n"),
    },
    {
      catalogId: "sitrep",
      trigger: "/sitrep",
      label: "Mid-op bearing",
      body: [
        "SITREP (mid-op, no code). Caps: Just shipped ≤8; Wire/close ≤5; Vectors = 5.",
        "1) Just shipped (glossed, ~36h)",
        "2) Collision board (untested seams / bake debt)",
        "3) Wire/close (CI/CD fuses)",
        "4) Vectors ranked ST money → LT → Ops → velocity",
        "Stop for my pick.",
        "CONTEXT:",
        "<git log / sprint / agent notes>",
      ].join("\n"),
    },
    {
      catalogId: "preflight",
      trigger: "/preflight",
      label: "Plan gate before ≥3-file work",
      body: [
        "PREFLIGHT (Plan mode). Task: {{cursor}}",
        "Map: files in/out, callers, tests, migrations, Do-not-touch hits, risks, verification commands.",
        "Output approvable plan. Do not edit until I say go/implement/proceed.",
      ].join("\n"),
    },
    {
      catalogId: "session-close",
      trigger: "/session-close",
      label: "Wrap session — deferrals + next hop",
      body: [
        "TBCC SESSION CLOSE. No new implementation unless I say so.",
        "Summarize: what shipped this session, what's still open, collision/bake debt, recommended next protocol.",
        "Update mental model of sprint state if context was pasted. Stop for my pick.",
      ].join("\n"),
    },
    {
      catalogId: "sprint-start",
      trigger: "/sprint-start",
      label: "Initialize / reset sprint state",
      body: [
        "TBCC SPRINT START. Plan-only until I confirm.",
        "Propose sprint name, goal, in/out fence, and initial Top 5 slices from context pasted below.",
        "Do not implement until I say go.",
        "CONTEXT:",
        "<notes / handoffs>",
      ].join("\n"),
    },
    {
      catalogId: "ship-log",
      trigger: "/ship-log",
      label: "Draft build-in-public ship log (X/Buffer)",
      body: [
        "TBCC SHIP LOG draft. Observe-only until I say publish.",
        "From pasted git/session context: draft ≤280 char engineer progress post(s) with concrete wins.",
        "No secrets. No fake metrics. Stop for my pick on variant.",
        "CONTEXT:",
        "<git log / session notes>",
      ].join("\n"),
    },
    {
      catalogId: "milestone-ship",
      trigger: "/milestone-ship",
      label: "Milestone commit + push + optional Buffer",
      body: [
        "TBCC MILESTONE SHIP checklist (plan-only until I say execute).",
        "Confirm: tests/gates, commit message, push scope, optional Buffer post variant.",
        "Do not push or post unless I explicitly say execute.",
        "MILESTONE:",
        "{{cursor}}",
      ].join("\n"),
    },
    {
      catalogId: "handoff-cc",
      trigger: "/handoff-cc",
      label: "Package work for Claude Code (Lane C)",
      body: [
        "Package a forward directive for Claude Code (Lane C grind).",
        "Output: GOAL, SCOPE in/out, ACTIVE PHASE ONLY, files likely touched, verification commands, fence.",
        "Write as a paste-ready handoff — do not implement here unless I say Cursor lane.",
        "TASK:",
        "{{cursor}}",
      ].join("\n"),
    },
  ];

  function uid() {
    return "s_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
  }

  function triggersInstalled(existing, catalogId) {
    const entry = CATALOG.find((c) => c.catalogId === catalogId);
    if (!entry) return false;
    return (Array.isArray(existing) ? existing : []).some(
      (s) => s.trigger === entry.trigger && s.catalogId === entry.catalogId
    );
  }

  /**
   * Merge catalog entries into snippet list (by trigger — updates body if trigger exists).
   * @param {Array<object>} existing
   * @param {string[]|null} catalogIds null = all
   */
  function mergeCatalog(existing, catalogIds) {
    const withoutRetired = (Array.isArray(existing) ? existing : []).filter(
      (s) => !s.catalogId || !RETIRED_CATALOG_IDS.has(s.catalogId)
    );
    const list = withoutRetired.slice();
    const byTrigger = new Map(list.map((s) => [s.trigger, s]));
    const want = catalogIds
      ? CATALOG.filter((c) => catalogIds.includes(c.catalogId))
      : CATALOG.slice();
    const installed = [];
    for (const entry of want) {
      const prev = byTrigger.get(entry.trigger);
      const row = {
        id: (prev && prev.id) || uid(),
        trigger: entry.trigger,
        label: entry.label,
        body: entry.body,
        enabled: prev && prev.enabled === false ? false : true,
        catalogId: entry.catalogId,
        updatedAt: Date.now(),
        createdAt: (prev && prev.createdAt) || Date.now(),
      };
      byTrigger.set(entry.trigger, row);
      installed.push(entry.catalogId);
    }
    return { snippets: Array.from(byTrigger.values()), installed };
  }

  async function ensureSeeded(storage) {
    const store = storage || chrome.storage.local;
    const data = await store.get(STORAGE_SNIPPETS);
    const raw = Array.isArray(data[STORAGE_SNIPPETS]) ? data[STORAGE_SNIPPETS] : [];
    const existing = raw.filter((s) => !s.catalogId || !RETIRED_CATALOG_IDS.has(s.catalogId));
    const have = new Set(existing.map((s) => s.catalogId).filter(Boolean));
    const missingIds = CATALOG.filter((c) => !have.has(c.catalogId)).map((c) => c.catalogId);
    if (!missingIds.length) {
      if (existing.length !== raw.length) await store.set({ [STORAGE_SNIPPETS]: existing });
      return { added: 0 };
    }
    const merged = mergeCatalog(existing, missingIds);
    await store.set({ [STORAGE_SNIPPETS]: merged.snippets });
    return { added: missingIds.length };
  }

  root.TbccOperatorCommandSnippets = {
    STORAGE_SNIPPETS,
    CATALOG,
    mergeCatalog,
    triggersInstalled,
    ensureSeeded,
  };
})(typeof globalThis !== "undefined" ? globalThis : self);
