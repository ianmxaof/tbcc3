/**
 * Turns the static chrome.contextMenus descriptor list + a user config
 * (custom order + per-item disable) into the final create()-ready plan.
 * chrome.contextMenus has no index/position property — menu order is purely
 * the order create() was called in — so "reordering" means reordering this list.
 */
(function (root) {
  /**
   * @param {Array<{id:string, menuFamily?:string, [k:string]:any}>} items static descriptors
   * @param {{ order?: string[], disabled?: Record<string, boolean> }} config
   * @returns props ready for chrome.contextMenus.create (menuFamily stripped), in final order, disabled ones removed
   */
  function buildMenuPlan(items, config) {
    const list = Array.isArray(items) ? items : [];
    const cfg = config && typeof config === "object" ? config : {};
    const disabled = cfg.disabled && typeof cfg.disabled === "object" ? cfg.disabled : {};
    const order = Array.isArray(cfg.order) ? cfg.order : [];

    const byId = new Map();
    for (const it of list) {
      if (it && it.id) byId.set(it.id, it);
    }

    const seen = new Set();
    const ordered = [];
    for (const id of order) {
      if (byId.has(id) && !seen.has(id)) {
        ordered.push(byId.get(id));
        seen.add(id);
      }
    }
    // Items with no saved position (new items shipped after the user's last edit) keep their default order, appended.
    for (const it of list) {
      if (!seen.has(it.id)) {
        ordered.push(it);
        seen.add(it.id);
      }
    }

    return ordered
      .filter((it) => disabled[it.id] !== true)
      .map((it) => {
        const props = Object.assign({}, it);
        delete props.menuFamily;
        return props;
      });
  }

  /** Group static descriptors by menuFamily for editor UI (e.g. "media" vs "action"). */
  function groupByFamily(items) {
    const groups = {};
    for (const it of Array.isArray(items) ? items : []) {
      const fam = (it && it.menuFamily) || "media";
      if (!groups[fam]) groups[fam] = [];
      groups[fam].push(it);
    }
    return groups;
  }

  const api = { buildMenuPlan, groupByFamily };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { TbccContextMenuPlan: api };
  } else {
    root.TbccContextMenuPlan = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
