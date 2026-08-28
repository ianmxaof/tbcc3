/**
 * Local Quick Fix caps/typo cleanup.
 * Run: node extension/tests/tbcc-text-quickfix-lib.test.mjs
 */
import assert from "assert";
import { createRequire } from "module";
import { fileURLToPath } from "url";
import path from "path";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const lib = require(path.join(root, "tbcc-text-quickfix-lib.js")).TbccTextQuickfix;

const { localQuickFix, stripLlmReply } = lib;

assert.strictEqual(localQuickFix("THIS IS A tEST"), "This Is A Test");
assert.strictEqual(localQuickFix("  teh   recieve   "), "The receive");
assert.strictEqual(localQuickFix("HELLO WORLD"), "Hello World");
assert.strictEqual(localQuickFix("line one\n\n\nline two"), "Line one\n\nLine two");

assert.strictEqual(stripLlmReply("Here's the corrected text: Hello world."), "Hello world.");
assert.strictEqual(stripLlmReply('"Fixed line"'), "Fixed line");

console.log("tbcc-text-quickfix-lib: ok");
