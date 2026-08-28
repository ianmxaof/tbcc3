/** Manager UI for the snippet/prompt library (chrome.storage.local: tbccSnippets, tbccSnippetSettings). */
(function () {
  const STORAGE_SNIPPETS = "tbccSnippets";
  const STORAGE_SETTINGS = "tbccSnippetSettings";

  let snippets = [];
  let settings = { enabled: true, disabledDomains: [] };
  let searchQuery = "";
  const hkLib = globalThis.TbccHotkeyLib;
  const recallLib = globalThis.TbccRecallLib;
  let recordingHotkey = false;
  let hotkeyCapture = null;
  let hotkeyRecorderState = { at: 0, code: "" };

  function setSettingsStatus(text, isErr) {
    const el = document.getElementById("snipSettingsStatus");
    if (!el) return;
    el.textContent = text || "";
    el.style.color = isErr ? "var(--tbcc-error, #f38ba8)" : "var(--tbcc-text-muted)";
  }

  function resolvedQuickFixHotkey() {
    if (!hkLib) return null;
    return hkLib.normalizeHotkey(settings.quickFixHotkey) || hkLib.defaultQuickFixHotkey();
  }

  function renderQuickFixHotkeyButton() {
    const btn = document.getElementById("snipQuickFixHotkeyBtn");
    if (!btn || !hkLib) return;
    if (recordingHotkey) {
      btn.textContent = "Press keys… (Esc cancels)";
      btn.classList.add("recording");
      return;
    }
    btn.classList.remove("recording");
    btn.textContent = hkLib.formatHotkey(resolvedQuickFixHotkey());
  }

  async function persistSettings() {
    await chrome.storage.local.set({ [STORAGE_SETTINGS]: settings });
  }

  async function saveQuickFixHotkey(hotkey) {
    settings.quickFixHotkey = hotkey;
    await persistSettings();
    renderQuickFixHotkeyButton();
    setSettingsStatus("Quick Fix hotkey saved.");
  }

  function stopHotkeyRecording() {
    recordingHotkey = false;
    hotkeyRecorderState = { at: 0, code: "" };
    if (hotkeyCapture) {
      window.removeEventListener("keydown", hotkeyCapture, true);
      hotkeyCapture = null;
    }
    renderQuickFixHotkeyButton();
  }

  function startHotkeyRecording() {
    if (!hkLib) return;
    recordingHotkey = true;
    renderQuickFixHotkeyButton();
    setSettingsStatus("Recording… press your shortcut.");
    hotkeyCapture = (e) => {
      e.preventDefault();
      e.stopPropagation();
      const parsed = hkLib.hotkeyFromKeyboardEvent(e, hotkeyRecorderState);
      if (!parsed) return;
      if (parsed.cancel) {
        stopHotkeyRecording();
        setSettingsStatus("Recording cancelled.");
        return;
      }
      if (parsed.pendingDouble) {
        hotkeyRecorderState = parsed.recorderState || { at: 0, code: "" };
        setSettingsStatus("Tap " + (parsed.label || "key") + " again for double-tap…");
        return;
      }
      if (parsed.error === "modifier_required") {
        setSettingsStatus("Chord: include a modifier, or double-tap Shift (⇧⇧).", true);
        return;
      }
      if (parsed.hotkey) {
        stopHotkeyRecording();
        void saveQuickFixHotkey(parsed.hotkey);
      }
    };
    window.addEventListener("keydown", hotkeyCapture, true);
  }

  function uid() {
    return "s_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
  }

  function setStatus(text, isErr) {
    const el = document.getElementById("snipFormStatus");
    el.textContent = text || "";
    el.classList.toggle("err", !!isErr);
  }

  function snippetBodyText(s) {
    const text = String((s && s.body) || "").trim();
    return text || "(empty body)";
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
    const ordered = recallLib ? recallLib.rankByQuery(searchQuery, snippets) : snippets.slice();
    if (!ordered.length && searchQuery.trim()) {
      empty.style.display = "";
      empty.textContent = "No snippets match \"" + searchQuery.trim() + "\".";
      return;
    }
    empty.textContent = "No snippets yet — add one above.";
    ordered.forEach((s) => {
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
        if (s.useCount) {
          trig.title = "Used " + s.useCount + (s.useCount === 1 ? " time" : " times");
          trig.textContent += " ×" + s.useCount;
        }
        row.appendChild(trig);

        const body = document.createElement("div");
        body.className = "snip-body";
        body.tabIndex = 0;
        body.setAttribute("aria-label", "Snippet body preview for " + (s.trigger || "snippet"));
        const label = document.createElement("div");
        label.className = "snip-label";
        label.textContent = s.label || "(untitled)";
        const preview = document.createElement("div");
        preview.className = "snip-preview";
        preview.textContent = snippetBodyText(s).replace(/\s+/g, " ").slice(0, 140);
        body.appendChild(label);
        body.appendChild(preview);
        row.appendChild(body);

        const tip = document.createElement("div");
        tip.className = "snip-row-tooltip";
        tip.textContent = snippetBodyText(s);
        row.appendChild(tip);

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

  document.getElementById("snipSearch").addEventListener("input", (e) => {
    searchQuery = e.target.value || "";
    renderList();
  });

  document.getElementById("snipSaveSettings").addEventListener("click", async () => {
    settings.enabled = document.getElementById("snipEnabled").checked;
    settings.disabledDomains = document
      .getElementById("snipDisabledDomains")
      .value.split("\n")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    await persistSettings();
    setSettingsStatus("Settings saved.");
  });

  document.getElementById("snipQuickFixHotkeyBtn").addEventListener("click", () => {
    if (recordingHotkey) stopHotkeyRecording();
    else startHotkeyRecording();
  });

  document.getElementById("snipQuickFixHotkeyReset").addEventListener("click", () => {
    if (!hkLib) return;
    stopHotkeyRecording();
    void saveQuickFixHotkey(hkLib.defaultQuickFixHotkey());
  });

  async function boot() {
    if (globalThis.TbccOperatorCommandSnippets && globalThis.TbccOperatorCommandSnippets.ensureSeeded) {
      await globalThis.TbccOperatorCommandSnippets.ensureSeeded();
    }
    const data = await chrome.storage.local.get([STORAGE_SNIPPETS, STORAGE_SETTINGS]);
    snippets = Array.isArray(data[STORAGE_SNIPPETS]) ? data[STORAGE_SNIPPETS] : [];
    settings = Object.assign({ enabled: true, disabledDomains: [] }, data[STORAGE_SETTINGS] || {});
    if (hkLib && !hkLib.normalizeHotkey(settings.quickFixHotkey)) {
      settings.quickFixHotkey = hkLib.defaultQuickFixHotkey();
      await persistSettings();
    }
    document.getElementById("snipEnabled").checked = settings.enabled !== false;
    document.getElementById("snipDisabledDomains").value = (settings.disabledDomains || []).join("\n");
    renderQuickFixHotkeyButton();
    renderList();
  }

  boot();
})();
