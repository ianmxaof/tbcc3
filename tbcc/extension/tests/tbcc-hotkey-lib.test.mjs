/**
 * Hotkey format/match helpers.
 * Run: node extension/tests/tbcc-hotkey-lib.test.mjs
 */
import assert from "assert";
import { createRequire } from "module";
import { fileURLToPath } from "url";
import path from "path";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const lib = require(path.join(root, "tbcc-hotkey-lib.js")).TbccHotkeyLib;

const {
  normalizeHotkey,
  formatHotkey,
  eventMatchesHotkey,
  doubleTapEventMatches,
  createDoubleTapHandler,
  defaultQuickFixHotkey,
} = lib;

const def = defaultQuickFixHotkey();
assert.strictEqual(def.doubleTap, true);
assert.strictEqual(def.key, "Shift");

const hk = normalizeHotkey({ ctrl: true, shift: true, key: "e", code: "KeyE" });
assert.strictEqual(hk.key, "E");
assert.strictEqual(formatHotkey(hk, { mac: false }), "Ctrl+Shift+E");

const dbl = normalizeHotkey({ doubleTap: true, key: "Shift" });
assert.strictEqual(formatHotkey(dbl, { mac: false }), "Double Shift");
assert.strictEqual(formatHotkey(dbl, { mac: true }), "⇧⇧");

const fakeEvent = {
  key: "E",
  code: "KeyE",
  ctrlKey: true,
  shiftKey: true,
  altKey: false,
  metaKey: false,
};
assert.strictEqual(eventMatchesHotkey(fakeEvent, hk), true);
assert.strictEqual(eventMatchesHotkey({ ...fakeEvent, key: "F", code: "KeyF" }, hk), false);

const shiftDown = {
  key: "Shift",
  code: "ShiftRight",
  ctrlKey: false,
  shiftKey: true,
  altKey: false,
  metaKey: false,
  repeat: false,
};
assert.strictEqual(doubleTapEventMatches(shiftDown, dbl), true);
assert.strictEqual(doubleTapEventMatches({ ...shiftDown, ctrlKey: true }, dbl), false);

let fired = 0;
const handler = createDoubleTapHandler(() => dbl, () => {
  fired += 1;
}, 500);
handler(shiftDown);
assert.strictEqual(fired, 0);
handler(shiftDown);
assert.strictEqual(fired, 1);

console.log("tbcc-hotkey-lib: ok");
