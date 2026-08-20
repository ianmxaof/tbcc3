/**
 * Snippet trigger matching + dynamic token expansion.
 * Run: node extension/tests/tbcc-snippet-lib.test.mjs
 */
import assert from "assert";
import { createRequire } from "module";
import { fileURLToPath } from "url";
import path from "path";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const lib = require(path.join(root, "tbcc-snippet-lib.js")).TbccSnippetLib;

const { findTriggerMatch, expandTokens, needsClipboard, formatDate } = lib;

// Exact trailing trigger match
const snippets = [
  { trigger: "/p3", body: "prompt three", enabled: true },
  { trigger: "/p", body: "prompt short", enabled: true },
  { trigger: "/off", body: "should not match", enabled: false },
];
assert.strictEqual(findTriggerMatch(snippets, "hello /p3").trigger, "/p3");
// Longest match wins when multiple triggers are suffixes of each other
assert.strictEqual(findTriggerMatch(snippets, "type /p").trigger, "/p");
assert.strictEqual(findTriggerMatch(snippets, "typing /p3").trigger, "/p3");
assert.strictEqual(findTriggerMatch(snippets, "no match here"), null);
assert.strictEqual(findTriggerMatch(snippets, "disabled /off"), null);
assert.strictEqual(findTriggerMatch(snippets, ""), null);

// Date/time formatting
const d = new Date(2026, 7, 19, 9, 5, 3); // 2026-08-19 09:05:03 local
assert.strictEqual(formatDate(d, "YYYY-MM-DD"), "2026-08-19");
assert.strictEqual(formatDate(d, "HH:mm"), "09:05");
assert.strictEqual(formatDate(d, "YYYY-MM-DD HH:mm:ss"), "2026-08-19 09:05:03");

// Token expansion
const r1 = expandTokens("Today is {{date}} at {{time}}", { now: d });
assert.strictEqual(r1.text, "Today is 2026-08-19 at 09:05");
assert.strictEqual(r1.cursorOffset, null);

const r2 = expandTokens("Signed,\n{{clipboard}}", { clipboardText: "Ian" });
assert.strictEqual(r2.text, "Signed,\nIan");

const r3 = expandTokens("Hello {{cursor}} world", {});
assert.strictEqual(r3.text, "Hello  world");
assert.strictEqual(r3.cursorOffset, 6);

assert.strictEqual(needsClipboard("no tokens here"), false);
assert.strictEqual(needsClipboard("paste: {{clipboard}}"), true);

console.log("tbcc-snippet-lib: ok");
