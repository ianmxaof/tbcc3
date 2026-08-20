/** Manager UI for download-routing rules (chrome.storage.local: tbccDownloadRoutes, tbccDownloadRoutingSettings). */
(function () {
  const STORAGE_ROUTES = "tbccDownloadRoutes";
  const STORAGE_SETTINGS = "tbccDownloadRoutingSettings";

  const MATCH_LABELS = {
    extension: "extension",
    domain: "domain",
    mimePrefix: "MIME prefix",
    urlRegex: "URL matches",
  };

  let routes = [];
  let settings = { enabled: true };
  let dragId = null;

  function uid() {
    return "r_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
  }

  function setStatus(text, isErr) {
    const el = document.getElementById("routeFormStatus");
    el.textContent = text || "";
    el.classList.toggle("err", !!isErr);
  }

  async function persist() {
    await chrome.storage.local.set({ [STORAGE_ROUTES]: routes });
    renderList();
  }

  function moveRoute(id, delta) {
    const idx = routes.findIndex((r) => r.id === id);
    if (idx < 0) return;
    const newIdx = idx + delta;
    if (newIdx < 0 || newIdx >= routes.length) return;
    const [item] = routes.splice(idx, 1);
    routes.splice(newIdx, 0, item);
    void persist();
  }

  function renderList() {
    const wrap = document.getElementById("routeList");
    const empty = document.getElementById("routeEmpty");
    wrap.innerHTML = "";
    if (!routes.length) {
      empty.style.display = "";
      return;
    }
    empty.style.display = "none";

    routes.forEach((r, i) => {
      const row = document.createElement("div");
      row.className = "route-row";
      row.draggable = true;
      row.dataset.id = r.id;

      row.addEventListener("dragstart", () => {
        dragId = r.id;
        row.classList.add("dragging");
      });
      row.addEventListener("dragend", () => {
        row.classList.remove("dragging");
        document.querySelectorAll(".route-row.drop-target").forEach((el) => el.classList.remove("drop-target"));
      });
      row.addEventListener("dragover", (e) => {
        e.preventDefault();
        row.classList.add("drop-target");
      });
      row.addEventListener("dragleave", () => row.classList.remove("drop-target"));
      row.addEventListener("drop", (e) => {
        e.preventDefault();
        row.classList.remove("drop-target");
        if (!dragId || dragId === r.id) return;
        const fromIdx = routes.findIndex((x) => x.id === dragId);
        const toIdx = routes.findIndex((x) => x.id === r.id);
        if (fromIdx < 0 || toIdx < 0) return;
        const [item] = routes.splice(fromIdx, 1);
        routes.splice(toIdx, 0, item);
        dragId = null;
        void persist();
      });

      const handle = document.createElement("div");
      handle.className = "route-handle";
      handle.textContent = "⋮⋮";
      handle.title = "Drag to reorder";
      row.appendChild(handle);

      const orderBtns = document.createElement("div");
      orderBtns.className = "route-order-btns";
      const upBtn = document.createElement("button");
      upBtn.type = "button";
      upBtn.textContent = "▲";
      upBtn.title = "Move up";
      upBtn.disabled = i === 0;
      upBtn.addEventListener("click", () => moveRoute(r.id, -1));
      const downBtn = document.createElement("button");
      downBtn.type = "button";
      downBtn.textContent = "▼";
      downBtn.title = "Move down";
      downBtn.disabled = i === routes.length - 1;
      downBtn.addEventListener("click", () => moveRoute(r.id, 1));
      orderBtns.appendChild(upBtn);
      orderBtns.appendChild(downBtn);
      row.appendChild(orderBtns);

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = r.enabled !== false;
      cb.title = "Enable/disable this rule";
      cb.addEventListener("change", () => {
        r.enabled = cb.checked;
        void persist();
      });
      row.appendChild(cb);

      const body = document.createElement("div");
      body.className = "route-body";
      const summary = document.createElement("div");
      summary.className = "route-summary";
      const label = r.label ? r.label + " — " : "";
      summary.innerHTML =
        label + (MATCH_LABELS[r.matchType] || r.matchType) + " <code>" + escapeHtml(r.matchValue || "") + "</code>";
      const folder = document.createElement("div");
      folder.className = "route-folder";
      folder.textContent = "→ Downloads/" + (r.folder || "(unset)") + "/…  ·  on conflict: " + (r.conflictAction || "uniquify");
      body.appendChild(summary);
      body.appendChild(folder);
      row.appendChild(body);

      const actions = document.createElement("div");
      actions.className = "route-actions";
      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.textContent = "Edit";
      editBtn.addEventListener("click", () => loadIntoForm(r));
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "danger";
      delBtn.textContent = "Delete";
      delBtn.addEventListener("click", () => {
        if (!confirm("Delete this rule?")) return;
        routes = routes.filter((x) => x.id !== r.id);
        void persist();
      });
      actions.appendChild(editBtn);
      actions.appendChild(delBtn);
      row.appendChild(actions);

      wrap.appendChild(row);
    });
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function loadIntoForm(r) {
    document.getElementById("routeEditId").value = r.id;
    document.getElementById("routeLabel").value = r.label || "";
    document.getElementById("routeMatchType").value = r.matchType || "extension";
    document.getElementById("routeMatchValue").value = r.matchValue || "";
    document.getElementById("routeFolder").value = r.folder || "";
    document.getElementById("routeConflictAction").value = r.conflictAction || "uniquify";
    document.getElementById("routeCancelEdit").style.display = "";
    setStatus("Editing rule — save to update, or cancel.");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function clearForm() {
    document.getElementById("routeEditId").value = "";
    document.getElementById("routeLabel").value = "";
    document.getElementById("routeMatchValue").value = "";
    document.getElementById("routeFolder").value = "";
    document.getElementById("routeConflictAction").value = "uniquify";
    document.getElementById("routeCancelEdit").style.display = "none";
    setStatus("");
  }

  document.getElementById("routeSaveEntry").addEventListener("click", async () => {
    const id = document.getElementById("routeEditId").value.trim();
    const label = document.getElementById("routeLabel").value.trim();
    const matchType = document.getElementById("routeMatchType").value;
    const matchValue = document.getElementById("routeMatchValue").value.trim();
    const folder = document.getElementById("routeFolder").value.trim();
    const conflictAction = document.getElementById("routeConflictAction").value;
    if (!matchValue) {
      setStatus("Match value is required.", true);
      return;
    }
    if (!folder) {
      setStatus("Destination subfolder is required.", true);
      return;
    }
    if (matchType === "urlRegex") {
      try {
        new RegExp(matchValue);
      } catch (e) {
        setStatus("Invalid regex: " + e.message, true);
        return;
      }
    }
    if (id) {
      const existing = routes.find((r) => r.id === id);
      if (existing) Object.assign(existing, { label, matchType, matchValue, folder, conflictAction });
    } else {
      routes.push({ id: uid(), label, matchType, matchValue, folder, conflictAction, enabled: true });
    }
    await persist();
    clearForm();
    setStatus("Saved.");
  });

  document.getElementById("routeCancelEdit").addEventListener("click", clearForm);

  document.getElementById("routingEnabled").addEventListener("change", async (e) => {
    settings.enabled = e.target.checked;
    await chrome.storage.local.set({ [STORAGE_SETTINGS]: settings });
  });

  async function boot() {
    const data = await chrome.storage.local.get([STORAGE_ROUTES, STORAGE_SETTINGS]);
    routes = Array.isArray(data[STORAGE_ROUTES]) ? data[STORAGE_ROUTES] : [];
    settings = Object.assign({ enabled: true }, data[STORAGE_SETTINGS] || {});
    document.getElementById("routingEnabled").checked = settings.enabled !== false;
    renderList();
  }

  boot();
})();
