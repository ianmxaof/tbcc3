/**
 * Recall ranking + usage-based promotion.
 * Run: node extension/tests/tbcc-recall-lib.test.mjs
 */
import assert from "assert";
import { createRequire } from "module";
import { fileURLToPath } from "url";
import path from "path";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const lib = require(path.join(root, "tbcc-recall-lib.js")).TbccRecallLib;

const { classify, usageScore, promotionScore, rankByQuery } = lib;

// Classification: heuristic facet detection
const c1 = classify("Debug this stack trace and fix the crash in the function");
assert.strictEqual(c1.useCase, "debugging");

const c2 = classify("Write a checklist for reviewing a pull request step by step");
assert.strictEqual(c2.outputType, "checklist");

// Usage scoring: more uses + more recent = higher score
const now = Date.now();
const fresh = { useCount: 5, lastUsedAt: now - 1 * 86400000 };
const stale = { useCount: 5, lastUsedAt: now - 29 * 86400000 };
const unused = { useCount: 0, lastUsedAt: null };
assert.ok(usageScore(fresh, now) > usageScore(stale, now));
assert.strictEqual(usageScore(unused, now), 0);

// Promotion score: recency bonus decays, usage count dominates
assert.ok(promotionScore({ useCount: 3, lastUsedAt: now }, now) > promotionScore({ useCount: 0, lastUsedAt: null }, now));

// rankByQuery: empty query falls back to usage-based order
const entries = [
  { id: "a", trigger: "/a", label: "Rare", body: "x", useCount: 0, lastUsedAt: null },
  { id: "b", trigger: "/b", label: "Popular", body: "y", useCount: 10, lastUsedAt: now },
];
const defaultOrder = rankByQuery("", entries, { now });
assert.strictEqual(defaultOrder[0].id, "b");

// rankByQuery: query surfaces facet + keyword matches, excludes unrelated entries
const facetEntries = [
  { id: "code1", trigger: "/code1", label: "Refactor helper", body: "Refactor this function into smaller pieces", useCase: "coding", useCount: 0 },
  { id: "write1", trigger: "/write1", label: "Blog draft", body: "Write a blog post about onboarding", useCase: "writing", useCount: 0 },
];
const ranked = rankByQuery("refactor this function", facetEntries, { now });
assert.strictEqual(ranked[0].id, "code1");
assert.ok(!ranked.some((e) => e.id === "write1"));

// rankByQuery: raw substring on trigger/label matches even without keyword overlap
const substringEntries = [{ id: "p3", trigger: "/p3", label: "Outline generator", body: "irrelevant body text", useCount: 0 }];
const bySubstring = rankByQuery("/p3", substringEntries, { now });
assert.strictEqual(bySubstring.length, 1);
assert.strictEqual(bySubstring[0].id, "p3");

console.log("tbcc-recall-lib: ok");
