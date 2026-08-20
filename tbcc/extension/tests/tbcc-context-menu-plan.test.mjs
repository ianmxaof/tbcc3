/**
 * Context-menu order/enable plan builder.
 * Run: node extension/tests/tbcc-context-menu-plan.test.mjs
 */
import assert from "assert";
import { createRequire } from "module";
import { fileURLToPath } from "url";
import path from "path";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const plan = require(path.join(root, "tbcc-context-menu-plan.js")).TbccContextMenuPlan;

const { buildMenuPlan, groupByFamily } = plan;
const { TBCC_STATIC_MENU_ITEMS } = require(path.join(root, "tbcc-context-menu-items.js"));

const items = [
  { id: "a", title: "A", contexts: ["image"], menuFamily: "media" },
  { id: "b", title: "B", contexts: ["image"], menuFamily: "media" },
  { id: "c", title: "C", contexts: ["action"], menuFamily: "action" },
];

// No config: default order, nothing stripped but menuFamily
const def = buildMenuPlan(items, {});
assert.deepStrictEqual(def.map((x) => x.id), ["a", "b", "c"]);
assert.strictEqual(def[0].menuFamily, undefined);
assert.strictEqual(def[0].title, "A");

// Custom order
const reordered = buildMenuPlan(items, { order: ["c", "a", "b"] });
assert.deepStrictEqual(reordered.map((x) => x.id), ["c", "a", "b"]);

// Disabled item removed
const withDisabled = buildMenuPlan(items, { disabled: { b: true } });
assert.deepStrictEqual(withDisabled.map((x) => x.id), ["a", "c"]);

// Order references an id that no longer exists in the static list -> ignored
const staleOrder = buildMenuPlan(items, { order: ["zzz", "b", "a"] });
assert.deepStrictEqual(staleOrder.map((x) => x.id), ["b", "a", "c"]);

// New item not present in a saved order -> appended in its default position
const partialOrder = buildMenuPlan(items, { order: ["b"] });
assert.deepStrictEqual(partialOrder.map((x) => x.id), ["b", "a", "c"]);

// Grouping
const groups = groupByFamily(items);
assert.deepStrictEqual(groups.media.map((x) => x.id), ["a", "b"]);
assert.deepStrictEqual(groups.action.map((x) => x.id), ["c"]);

// Guard against the real production list: unique ids, every item has a menuFamily + at least one context,
// and the plan builder round-trips it without dropping or duplicating anything.
const ids = TBCC_STATIC_MENU_ITEMS.map((it) => it.id);
assert.strictEqual(new Set(ids).size, ids.length, "TBCC_STATIC_MENU_ITEMS has a duplicate id");
for (const it of TBCC_STATIC_MENU_ITEMS) {
  assert.ok(it.menuFamily === "media" || it.menuFamily === "action", it.id + " missing/invalid menuFamily");
  assert.ok(Array.isArray(it.contexts) && it.contexts.length, it.id + " missing contexts");
}
const roundTrip = buildMenuPlan(TBCC_STATIC_MENU_ITEMS, {});
assert.deepStrictEqual(roundTrip.map((x) => x.id), ids);
assert.ok(roundTrip.every((x) => !("menuFamily" in x)), "menuFamily must be stripped for chrome.contextMenus.create");

console.log("tbcc-context-menu-plan: ok");
