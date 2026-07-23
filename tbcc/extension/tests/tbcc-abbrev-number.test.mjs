/**
 * Decimal-comma + K/M parse (Erome live intel inflate regression).
 * Run: node extension/tests/tbcc-abbrev-number.test.mjs
 */
import assert from "assert";
import { createRequire } from "module";
import { fileURLToPath } from "url";
import path from "path";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const { tbccParseAbbrevNumber, tbccFormatAbbrevNumber } = require(path.join(root, "tbcc-abbrev-number.js"));

assert.strictEqual(tbccParseAbbrevNumber("4,7M"), 4_700_000);
assert.strictEqual(tbccParseAbbrevNumber("4.7M"), 4_700_000);
assert.strictEqual(tbccParseAbbrevNumber("24,0M"), 24_000_000);
assert.strictEqual(tbccParseAbbrevNumber("1,2K"), 1200);
assert.strictEqual(tbccParseAbbrevNumber("1.2K"), 1200);
assert.strictEqual(tbccParseAbbrevNumber("98000"), 98000);
assert.strictEqual(tbccParseAbbrevNumber("98,000"), 98000);
assert.strictEqual(tbccParseAbbrevNumber("1.234.567"), 1_234_567);
assert.strictEqual(tbccParseAbbrevNumber("240 views"), 240);
assert.strictEqual(tbccParseAbbrevNumber("2.4M views"), 2_400_000);

// Regression: old bug stripped commas first → 47M
assert.notStrictEqual(tbccParseAbbrevNumber("4,7M"), 47_000_000);

assert.strictEqual(tbccFormatAbbrevNumber(4_700_000), "4.7M");
assert.strictEqual(tbccFormatAbbrevNumber(24_000_000), "24M");
assert.strictEqual(tbccFormatAbbrevNumber(1200), "1.2K");

console.log("tbcc-abbrev-number: ok");
