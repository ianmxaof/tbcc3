/** Drag/arrow reorder + enable-disable editor for TBCC's native chrome.contextMenus entries. */
(function () {
  const STORAGE_CONFIG = "tbccContextMenuConfig";

  const items = typeof TBCC_STATIC_MENU_ITEMS !== "undefined" ? TBCC_STATIC_MENU_ITEMS : [];
  const plan = typeof TbccContextMenuPlan !== "undefined" ? TbccContextMenuPlan : null;
  const groups = plan ? plan.groupByFamily(items) : { media: items, action: [] };

  let disabled = {};
  // Per-family working order (array of ids), independent of the saved flat order.
  let familyOrder = {
    media: (groups.media || []).map((it) => it.id),
    action: (groups.action || []).map((it) => it.id),
  };
  let dragId = null;

  function byId(id) {
    return items.find((it) => it.id === id);
  }

  function setStatus(text) {
    document.getElementById("cmeStatus").textContent = text || "";
  }

  async function persist() {
    const order = [...familyOrder.media, ...familyOrder.action];
    await chrome.storage.local.set({ [STORAGE_CONFIG]: { order, disabled } });
    setStatus("Saved — menu updated.");
  }

  function moveItem(family, id, delta) {
    const arr = familyOrder[family];
    const idx = arr.indexOf(id);
    if (idx < 0) return;
    const newIdx = idx + delta;
    if (newIdx < 0 || newIdx >= arr.length) return;
    arr.splice(idx, 1);
    arr.splice(newIdx, 0, id);
    renderFamily(family);
    void persist();
  }

  function contextsLabel(it) {
    return (it.contexts || []).join(", ") + (it.documentUrlPatterns ? " · site-restricted" : "");
  }

  function renderFamily(family) {
    const wrap = document.getElementById(family === "media" ? "mediaList" : "actionList");
    wrap.innerHTML = "";
    const ids = familyOrder[family];
    ids.forEach((id, i) => {
      const it = byId(id);
      if (!it) return;
      const row = document.createElement("div");
      row.className = "menu-row";
      row.draggable = true;
      row.dataset.id = id;

      row.addEventListener("dragstart", () => {
        dragId = id;
        row.classList.add("dragging");
      });
      row.addEventListener("dragend", () => {
        row.classList.remove("dragging");
        wrap.querySelectorAll(".menu-row.drop-target").forEach((el) => el.classList.remove("drop-target"));
      });
      row.addEventListener("dragover", (e) => {
        e.preventDefault();
        row.classList.add("drop-target");
      });
      row.addEventListener("dragleave", () => row.classList.remove("drop-target"));
      row.addEventListener("drop", (e) => {
        e.preventDefault();
        row.classList.remove("drop-target");
        if (!dragId || dragId === id) return;
        const arr = familyOrder[family];
        const fromIdx = arr.indexOf(dragId);
        const toIdx = arr.indexOf(id);
        if (fromIdx < 0 || toIdx < 0) return;
        arr.splice(fromIdx, 1);
        arr.splice(toIdx, 0, dragId);
        dragId = null;
        renderFamily(family);
        void persist();
      });

      const handle = document.createElement("div");
      handle.className = "menu-handle";
      handle.textContent = "⋮⋮";
      handle.title = "Drag to reorder";
      row.appendChild(handle);

      const orderBtns = document.createElement("div");
      orderBtns.className = "menu-order-btns";
      const upBtn = document.createElement("button");
      upBtn.type = "button";
      upBtn.textContent = "▲";
      upBtn.disabled = i === 0;
      upBtn.addEventListener("click", () => moveItem(family, id, -1));
      const downBtn = document.createElement("button");
      downBtn.type = "button";
      downBtn.textContent = "▼";
      downBtn.disabled = i === ids.length - 1;
      downBtn.addEventListener("click", () => moveItem(family, id, 1));
      orderBtns.appendChild(upBtn);
      orderBtns.appendChild(downBtn);
      row.appendChild(orderBtns);

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = disabled[id] !== true;
      cb.title = "Show/hide this menu item";
      cb.addEventListener("change", () => {
        disabled[id] = !cb.checked;
        title.classList.toggle("disabled-item", !cb.checked);
        void persist();
      });
      row.appendChild(cb);

      const body = document.createElement("div");
      const title = document.createElement("div");
      title.className = "menu-title" + (disabled[id] === true ? " disabled-item" : "");
      title.textContent = it.title;
      const ctx = document.createElement("div");
      ctx.className = "menu-contexts";
      ctx.textContent = contextsLabel(it);
      body.appendChild(title);
      body.appendChild(ctx);
      row.appendChild(body);

      wrap.appendChild(row);
    });
  }

  document.getElementById("cmeResetDefault").addEventListener("click", async () => {
    disabled = {};
    familyOrder = {
      media: (groups.media || []).map((it) => it.id),
      action: (groups.action || []).map((it) => it.id),
    };
    renderFamily("media");
    renderFamily("action");
    await chrome.storage.local.set({ [STORAGE_CONFIG]: { order: [], disabled: {} } });
    setStatus("Reset to default order.");
  });

  async function boot() {
    const data = await chrome.storage.local.get([STORAGE_CONFIG]);
    const cfg = data[STORAGE_CONFIG] || {};
    disabled = cfg.disabled && typeof cfg.disabled === "object" ? cfg.disabled : {};
    const savedOrder = Array.isArray(cfg.order) ? cfg.order : [];
    if (savedOrder.length) {
      for (const family of ["media", "action"]) {
        const idsInFamily = new Set(familyOrder[family]);
        const fromSaved = savedOrder.filter((id) => idsInFamily.has(id));
        const remaining = familyOrder[family].filter((id) => !fromSaved.includes(id));
        familyOrder[family] = [...fromSaved, ...remaining];
      }
    }
    renderFamily("media");
    renderFamily("action");
  }

  boot();
})();
