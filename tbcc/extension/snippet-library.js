/** Manager UI for the snippet/prompt library (chrome.storage.local: tbccSnippets, tbccSnippetSettings). */
(function () {
  const STORAGE_SNIPPETS = "tbccSnippets";
  const STORAGE_SETTINGS = "tbccSnippetSettings";

  let snippets = [];
  let settings = { enabled: true, disabledDomains: [] };

  function uid() {
    return "s_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
  }

  function setStatus(text, isErr) {
    const el = document.getElementById("snipFormStatus");
    el.textContent = text || "";
    el.classList.toggle("err", !!isErr);
  }

  function renderList() {
    const wrap = document.getElementById("snipList");
    const empty = document.getElementById("snipEmpty");
    wrap.innerHTML = "";
    if (!snippets.length) {
      empty.style.display = "";
      return;
    }
    empty.style.display = "none";
    snippets
      .slice()
      .sort((a, b) => String(a.trigger || "").localeCompare(String(b.trigger || "")))
      .forEach((s) => {
        const row = document.createElement("div");
        row.className = "snip-row";

        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = s.enabled !== false;
        cb.title = "Enable/disable this snippet";
        cb.addEventListener("change", () => {
          s.enabled = cb.checked;
          void save();
        });
        row.appendChild(cb);

        const trig = document.createElement("code");
        trig.className = "snip-trigger";
        trig.textContent = s.trigger;
        row.appendChild(trig);

        const body = document.createElement("div");
        body.className = "snip-body";
        const label = document.createElement("div");
        label.className = "snip-label";
        label.textContent = s.label || "(untitled)";
        const preview = document.createElement("div");
        preview.className = "snip-preview";
        preview.textContent = String(s.body || "").replace(/\s+/g, " ").slice(0, 140);
        body.appendChild(label);
        body.appendChild(preview);
        row.appendChild(body);

        const actions = document.createElement("div");
        actions.className = "snip-actions";
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", () => loadIntoForm(s));
        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "danger";
        delBtn.textContent = "Delete";
        delBtn.addEventListener("click", () => {
          if (!confirm("Delete snippet " + s.trigger + "?")) return;
          snippets = snippets.filter((x) => x.id !== s.id);
          void save();
        });
        actions.appendChild(editBtn);
        actions.appendChild(delBtn);
        row.appendChild(actions);

        wrap.appendChild(row);
      });
  }

  function loadIntoForm(s) {
    document.getElementById("snipEditId").value = s.id;
    document.getElementById("snipTrigger").value = s.trigger || "";
    document.getElementById("snipLabel").value = s.label || "";
    document.getElementById("snipBody").value = s.body || "";
    document.getElementById("snipCancelEdit").style.display = "";
    setStatus("Editing " + s.trigger + " — save to update, or cancel.");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function clearForm() {
    document.getElementById("snipEditId").value = "";
    document.getElementById("snipTrigger").value = "";
    document.getElementById("snipLabel").value = "";
    document.getElementById("snipBody").value = "";
    document.getElementById("snipCancelEdit").style.display = "none";
    setStatus("");
  }

  async function save() {
    await chrome.storage.local.set({ [STORAGE_SNIPPETS]: snippets });
    renderList();
  }

  document.getElementById("snipSaveEntry").addEventListener("click", async () => {
    const id = document.getElementById("snipEditId").value.trim();
    const trigger = document.getElementById("snipTrigger").value.trim();
    const label = document.getElementById("snipLabel").value.trim();
    const body = document.getElementById("snipBody").value;
    if (!trigger) {
      setStatus("Trigger is required.", true);
      return;
    }
    const dupe = snippets.find((s) => s.trigger === trigger && s.id !== id);
    if (dupe) {
      setStatus("Another snippet already uses trigger " + trigger + ".", true);
      return;
    }
    if (id) {
      const existing = snippets.find((s) => s.id === id);
      if (existing) {
        existing.trigger = trigger;
        existing.label = label;
        existing.body = body;
        existing.updatedAt = Date.now();
      }
    } else {
      snippets.push({
        id: uid(),
        trigger,
        label,
        body,
        enabled: true,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      });
    }
    await save();
    clearForm();
    setStatus("Saved.");
  });

  document.getElementById("snipCancelEdit").addEventListener("click", clearForm);

  document.getElementById("snipSaveSettings").addEventListener("click", async () => {
    settings.enabled = document.getElementById("snipEnabled").checked;
    settings.disabledDomains = document
      .getElementById("snipDisabledDomains")
      .value.split("\n")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    await chrome.storage.local.set({ [STORAGE_SETTINGS]: settings });
  });

  async function boot() {
    const data = await chrome.storage.local.get([STORAGE_SNIPPETS, STORAGE_SETTINGS]);
    snippets = Array.isArray(data[STORAGE_SNIPPETS]) ? data[STORAGE_SNIPPETS] : [];
    settings = Object.assign({ enabled: true, disabledDomains: [] }, data[STORAGE_SETTINGS] || {});
    document.getElementById("snipEnabled").checked = settings.enabled !== false;
    document.getElementById("snipDisabledDomains").value = (settings.disabledDomains || []).join("\n");
    renderList();
  }

  boot();
})();
