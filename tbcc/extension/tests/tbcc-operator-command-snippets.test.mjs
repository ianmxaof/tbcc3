/**
 * Run: node extension/tests/tbcc-operator-command-snippets.test.mjs
 */
import assert from "node:assert/strict";
import path from "node:path";
import { createRequire } from "node:module";
import vm from "node:vm";

const root = path.resolve(import.meta.dirname, "..");
const require = createRequire(import.meta.url);

function loadCatalog() {
  const src = require("fs").readFileSync(path.join(root, "tbcc-operator-command-snippets.js"), "utf8");
  const sandbox = { globalThis: {} };
  vm.runInNewContext(src, sandbox, { filename: "tbcc-operator-command-snippets.js" });
  return sandbox.globalThis.TbccOperatorCommandSnippets;
}

const lib = loadCatalog();
assert.ok(lib && Array.isArray(lib.CATALOG), "CATALOG exported");
assert.ok(lib.CATALOG.length >= 20, "expected full pocket kit catalog");

const triggers = new Set();
for (const row of lib.CATALOG) {
  assert.ok(row.catalogId, "catalogId required");
  assert.ok(row.trigger.startsWith("/"), row.trigger);
  assert.ok(row.body.trim().length > 20, row.trigger);
  assert.ok(!triggers.has(row.trigger), "duplicate trigger " + row.trigger);
  triggers.add(row.trigger);
}

const merged = lib.mergeCatalog([], null);
assert.equal(merged.snippets.length, lib.CATALOG.length);
assert.ok(merged.snippets.some((s) => s.trigger === "/preflight"));
assert.ok(merged.snippets.some((s) => s.trigger === "/entropy-scan"));
assert.ok(!merged.snippets.some((s) => s.trigger === "/opr-ask"));

const preflight = lib.CATALOG.find((c) => c.trigger === "/preflight");
const again = lib.mergeCatalog(merged.snippets, [preflight.catalogId]);
assert.equal(again.snippets.length, lib.CATALOG.length);

console.log("tbcc-operator-command-snippets: ok (" + lib.CATALOG.length + " commands)");
