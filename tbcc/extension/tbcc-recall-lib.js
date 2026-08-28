/**
 * Intent-first recall ranking + usage-based promotion for the snippet/prompt library.
 * Heuristic only (no embeddings/LLM) — adapted from prompt-library's recall.ts ranking
 * weights and classification.ts pattern matching, scaled down for a trigger/label/body record.
 * Pure module (no chrome.* / DOM deps) so it is unit-testable like tbcc-snippet-lib.js.
 */
(function (root) {
  const USE_CASES = ["coding", "debugging", "writing", "analysis", "learning", "planning", "creative", "media", "meta"];
  const ROLES = ["engineer", "teacher", "editor", "analyst", "designer", "reviewer", "consultant", "critic"];
  const OUTPUT_TYPES = ["checklist", "essay", "json", "plan", "code", "stepwise", "freeform", "image", "video"];

  const USE_CASE_LABELS = {
    coding: "Coding", debugging: "Debugging", writing: "Writing", analysis: "Analysis",
    learning: "Learning", planning: "Planning", creative: "Creative", media: "Media", meta: "Meta",
  };
  const ROLE_LABELS = {
    engineer: "Engineer", teacher: "Teacher", editor: "Editor", analyst: "Analyst",
    designer: "Designer", reviewer: "Reviewer", consultant: "Consultant", critic: "Critic",
  };
  const OUTPUT_TYPE_LABELS = {
    checklist: "Checklist", essay: "Essay", json: "JSON", plan: "Plan", code: "Code",
    stepwise: "Stepwise", freeform: "Freeform", image: "Image", video: "Video",
  };

  const USE_CASE_KEYWORDS = {
    coding: ["code", "function", "implement", "refactor", "component", "api", "script", "class", "typescript", "javascript", "python"],
    debugging: ["bug", "error", "fix", "crash", "stack trace", "exception", "broken", "fails", "debug", "traceback"],
    writing: ["write", "draft", "article", "blog", "copy", "essay", "paragraph", "caption", "email"],
    analysis: ["analyze", "compare", "evaluate", "assess", "review", "audit", "breakdown", "pros and cons"],
    learning: ["explain", "teach", "learn", "understand", "eli5", "tutorial", "how does"],
    planning: ["plan", "roadmap", "strategy", "steps", "outline", "schedule", "milestones"],
    creative: ["story", "poem", "creative", "brainstorm", "idea", "concept", "imagine"],
    media: ["image", "video", "photo", "thumbnail", "caption", "prompt for", "generate an image"],
    meta: ["prompt", "instruction", "system prompt", "ruleset", "agent", "directive"],
  };
  const ROLE_KEYWORDS = {
    engineer: ["engineer", "developer", "coder", "programmer"],
    teacher: ["teacher", "tutor", "instructor", "mentor"],
    editor: ["editor", "proofreader", "copyeditor"],
    analyst: ["analyst", "researcher", "data scientist"],
    designer: ["designer", "ux", "ui designer"],
    reviewer: ["reviewer", "critic", "grader"],
    consultant: ["consultant", "advisor", "strategist"],
    critic: ["critic", "skeptic", "devil's advocate"],
  };
  const OUTPUT_TYPE_KEYWORDS = {
    checklist: ["checklist", "todo list", "bullet list of steps"],
    essay: ["essay", "article", "prose"],
    json: ["json", "structured data", "schema"],
    plan: ["plan", "roadmap", "outline"],
    code: ["code", "function", "script", "snippet of code"],
    stepwise: ["step by step", "step-by-step", "numbered steps"],
    freeform: ["freeform", "open ended", "however you"],
    image: ["image", "picture", "photo", "thumbnail"],
    video: ["video", "clip", "reel"],
  };

  const STOPWORDS = new Set([
    "the", "a", "an", "for", "to", "of", "in", "on", "and", "or", "with", "is", "are",
    "this", "that", "me", "my", "your", "you", "it", "be", "as", "at", "by", "from",
  ]);

  function tokenize(text) {
    return String(text || "")
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter((t) => t.length > 1 && !STOPWORDS.has(t));
  }

  function bestKeywordMatch(lowerText, keywordMap) {
    let best = null;
    let bestHits = 0;
    for (const key of Object.keys(keywordMap)) {
      const hits = keywordMap[key].reduce((n, kw) => (lowerText.includes(kw) ? n + 1 : n), 0);
      if (hits > bestHits) {
        bestHits = hits;
        best = key;
      }
    }
    return { key: best, hits: bestHits };
  }

  /**
   * Heuristic auto-classification for facet suggestions on save.
   * @param {string} text
   * @returns {{useCase:string|null, role:string|null, outputType:string|null, confidence:"low"|"med"|"high"}}
   */
  function classify(text) {
    const lower = String(text || "").toLowerCase();
    const uc = bestKeywordMatch(lower, USE_CASE_KEYWORDS);
    const role = bestKeywordMatch(lower, ROLE_KEYWORDS);
    const outputType = bestKeywordMatch(lower, OUTPUT_TYPE_KEYWORDS);
    const totalHits = uc.hits + role.hits + outputType.hits;
    const confidence = totalHits >= 4 ? "high" : totalHits >= 2 ? "med" : "low";
    return { useCase: uc.key, role: role.key, outputType: outputType.key, confidence };
  }

  const WEIGHT_USE_CASE = 100;
  const WEIGHT_OUTPUT_TYPE = 50;
  const WEIGHT_ROLE = 30;
  const WEIGHT_RAW_SUBSTRING = 20;
  const WEIGHT_KEYWORD = 5;
  const WEIGHT_USAGE = 2;

  const USAGE_RECENCY_WINDOW_DAYS = 30;
  const PROMOTION_RECENCY_BONUS_DAYS = 20;
  const MS_PER_DAY = 86400000;

  /** Usage weight with linear recency decay — recent, repeated use scores highest. */
  function usageScore(entry, now) {
    const t = now || Date.now();
    const useCount = Number(entry && entry.useCount) || 0;
    if (!useCount) return 0;
    const lastUsedAt = entry && entry.lastUsedAt;
    if (!lastUsedAt) return useCount;
    const days = Math.max(0, (t - lastUsedAt) / MS_PER_DAY);
    const recency = Math.max(0, 1 - days / USAGE_RECENCY_WINDOW_DAYS);
    return useCount * (0.5 + 0.5 * recency);
  }

  /** Default (no-query) sort key: usage-weighted with a decaying recency bonus. */
  function promotionScore(entry, now) {
    const t = now || Date.now();
    const useCount = Number(entry && entry.useCount) || 0;
    const lastUsedAt = entry && entry.lastUsedAt;
    const recencyBonus = lastUsedAt ? Math.max(0, PROMOTION_RECENCY_BONUS_DAYS - (t - lastUsedAt) / MS_PER_DAY) : 0;
    return useCount * 10 + recencyBonus;
  }

  function scoreEntry(queryTokens, queryClassification, entry, now) {
    let score = 0;
    if (queryClassification.useCase && entry.useCase && entry.useCase === queryClassification.useCase) score += WEIGHT_USE_CASE;
    if (queryClassification.outputType && entry.outputType && entry.outputType === queryClassification.outputType) score += WEIGHT_OUTPUT_TYPE;
    if (queryClassification.role && entry.role && entry.role === queryClassification.role) score += WEIGHT_ROLE;

    const trigger = String(entry.trigger || "").toLowerCase();
    const label = String(entry.label || "").toLowerCase();
    const rawQuery = queryTokens.rawLower;
    if (rawQuery && (trigger.includes(rawQuery) || label.includes(rawQuery))) score += WEIGHT_RAW_SUBSTRING;

    const hay = tokenize([entry.trigger, entry.label, entry.body].join(" "));
    const overlap = queryTokens.tokens.filter((t) => hay.includes(t)).length;
    score += overlap * WEIGHT_KEYWORD;

    score += usageScore(entry, now) * WEIGHT_USAGE;
    return score;
  }

  /**
   * Rank entries against a free-text query using intent-first multi-factor scoring.
   * Empty query falls back to usage-based promotion order (most-used, most-recent first).
   * @param {string} query
   * @param {Array<object>} entries
   * @param {{ now?: number }} [opts]
   * @returns {Array<object>} entries, ranked (input array is not mutated)
   */
  function rankByQuery(query, entries, opts) {
    const list = Array.isArray(entries) ? entries.slice() : [];
    const now = (opts && opts.now) || Date.now();
    const q = String(query || "").trim();

    if (!q) {
      return list.sort((a, b) => {
        const diff = promotionScore(b, now) - promotionScore(a, now);
        if (diff) return diff;
        return String(a.trigger || a.label || "").localeCompare(String(b.trigger || b.label || ""));
      });
    }

    const queryTokens = { tokens: tokenize(q), rawLower: q.toLowerCase() };
    const queryClassification = classify(q);

    return list
      .map((entry) => ({ entry, score: scoreEntry(queryTokens, queryClassification, entry, now) }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score || String(a.entry.trigger || "").localeCompare(String(b.entry.trigger || "")))
      .map((x) => x.entry);
  }

  const api = {
    USE_CASES,
    ROLES,
    OUTPUT_TYPES,
    USE_CASE_LABELS,
    ROLE_LABELS,
    OUTPUT_TYPE_LABELS,
    classify,
    usageScore,
    promotionScore,
    rankByQuery,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { TbccRecallLib: api };
  } else {
    root.TbccRecallLib = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
