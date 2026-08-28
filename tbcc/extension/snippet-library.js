/** Manager UI for the snippet/prompt library (chrome.storage.local: tbccSnippets, tbccSnippetSettings). */
(function () {
  const STORAGE_SNIPPETS = "tbccSnippets";
  const STORAGE_SETTINGS = "tbccSnippetSettings";

  const PROMPT_PAGE_SIZE = 10;

  let snippets = [];
  let settings = { enabled: true, disabledDomains: [] };
  let searchQuery = "";
  const hkLib = globalThis.TbccHotkeyLib;
  const recallLib = globalThis.TbccRecallLib;
  let recordingHotkey = false;
  let hotkeyCapture = null;
  let hotkeyRecorderState = { at: 0, code: "" };

  let promptSearchQuery = "";
  let promptUseCaseFilter = "";
  let promptPage = 0;

  function isPromptKind(s) {
    return s && s.kind === "prompt";
  }
  function isSnippetKind(s) {
    return !isPromptKind(s);
  }

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
    const scoped = snippets.filter(isSnippetKind);
    if (!scoped.length) {
      empty.style.display = "";
      empty.textContent = "No snippets yet — add one above.";
      return;
    }
    empty.style.display = "none";
    const ordered = recallLib ? recallLib.rankByQuery(searchQuery, scoped) : scoped.slice();
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
    renderPromptList();
  }

  // ---- Prompts tab (facet-scoped, paginated view over the same snippet store) ----

  function switchTab(name) {
    const isPrompts = name === "prompts";
    document.getElementById("tabPanelSnippets").hidden = isPrompts;
    document.getElementById("tabPanelPrompts").hidden = !isPrompts;
    document.getElementById("tabBtnSnippets").classList.toggle("active", !isPrompts);
    document.getElementById("tabBtnPrompts").classList.toggle("active", isPrompts);
    document.getElementById("tabBtnSnippets").setAttribute("aria-selected", String(!isPrompts));
    document.getElementById("tabBtnPrompts").setAttribute("aria-selected", String(isPrompts));
  }

  function populateFacetSelect(selectEl, values, labels) {
    if (!selectEl || !recallLib) return;
    for (const v of values) {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = labels[v] || v;
      selectEl.appendChild(opt);
    }
  }

  function renderPromptFacetChips() {
    const wrap = document.getElementById("promptFacetChips");
    if (!wrap || !recallLib) return;
    wrap.innerHTML = "";
    const allChip = document.createElement("button");
    allChip.type = "button";
    allChip.className = "facet-chip" + (promptUseCaseFilter ? "" : " active");
    allChip.textContent = "All";
    allChip.addEventListener("click", () => {
      promptUseCaseFilter = "";
      promptPage = 0;
      renderPromptList();
    });
    wrap.appendChild(allChip);
    for (const uc of recallLib.USE_CASES) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "facet-chip" + (promptUseCaseFilter === uc ? " active" : "");
      chip.textContent = recallLib.USE_CASE_LABELS[uc] || uc;
      chip.addEventListener("click", () => {
        promptUseCaseFilter = promptUseCaseFilter === uc ? "" : uc;
        promptPage = 0;
        renderPromptList();
      });
      wrap.appendChild(chip);
    }
  }

  function renderPromptList() {
    const wrap = document.getElementById("promptList");
    const empty = document.getElementById("promptEmpty");
    const pager = document.getElementById("promptPager");
    if (!wrap) return;
    wrap.innerHTML = "";
    renderPromptFacetChips();

    let scoped = snippets.filter(isPromptKind);
    if (promptUseCaseFilter) scoped = scoped.filter((s) => s.useCase === promptUseCaseFilter);
    const ordered = recallLib ? recallLib.rankByQuery(promptSearchQuery, scoped) : scoped.slice();

    if (!ordered.length) {
      empty.style.display = "";
      empty.textContent = snippets.some(isPromptKind)
        ? "No prompts match the current search/filter."
        : "No prompts yet — add one above.";
      pager.innerHTML = "";
      return;
    }
    empty.style.display = "none";

    const pageCount = Math.max(1, Math.ceil(ordered.length / PROMPT_PAGE_SIZE));
    promptPage = Math.min(promptPage, pageCount - 1);
    const start = promptPage * PROMPT_PAGE_SIZE;
    const pageItems = ordered.slice(start, start + PROMPT_PAGE_SIZE);

    pageItems.forEach((s) => {
      const row = document.createElement("div");
      row.className = "snip-row";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = s.enabled !== false;
      cb.title = "Enable/disable this prompt";
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
      body.setAttribute("aria-label", "Prompt body preview for " + (s.trigger || "prompt"));
      const label = document.createElement("div");
      label.className = "snip-label";
      label.textContent = s.label || "(untitled)";
      const tags = document.createElement("div");
      [s.useCase, s.role, s.outputType].filter(Boolean).forEach((v) => {
        const labelMap = recallLib ? Object.assign({}, recallLib.USE_CASE_LABELS, recallLib.ROLE_LABELS, recallLib.OUTPUT_TYPE_LABELS) : {};
        const tag = document.createElement("span");
        tag.className = "facet-tag";
        tag.textContent = labelMap[v] || v;
        tags.appendChild(tag);
      });
      const preview = document.createElement("div");
      preview.className = "snip-preview";
      preview.textContent = snippetBodyText(s).replace(/\s+/g, " ").slice(0, 140);
      body.appendChild(label);
      body.appendChild(tags);
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
      editBtn.addEventListener("click", () => loadIntoPromptForm(s));
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "danger";
      delBtn.textContent = "Delete";
      delBtn.addEventListener("click", () => {
        if (!confirm("Delete prompt " + s.trigger + "?")) return;
        snippets = snippets.filter((x) => x.id !== s.id);
        void save();
      });
      actions.appendChild(editBtn);
      actions.appendChild(delBtn);
      row.appendChild(actions);

      wrap.appendChild(row);
    });

    pager.innerHTML = "";
    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "tbcc-btn-secondary";
    prevBtn.textContent = "Prev";
    prevBtn.disabled = promptPage <= 0;
    prevBtn.addEventListener("click", () => {
      promptPage = Math.max(0, promptPage - 1);
      renderPromptList();
    });
    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "tbcc-btn-secondary";
    nextBtn.textContent = "Next";
    nextBtn.disabled = promptPage >= pageCount - 1;
    nextBtn.addEventListener("click", () => {
      promptPage = Math.min(pageCount - 1, promptPage + 1);
      renderPromptList();
    });
    const label = document.createElement("span");
    label.textContent = "Page " + (promptPage + 1) + " of " + pageCount + " (" + ordered.length + " prompt" + (ordered.length === 1 ? "" : "s") + ")";
    pager.appendChild(prevBtn);
    pager.appendChild(label);
    pager.appendChild(nextBtn);
  }

  function setPromptStatus(text, isErr) {
    const el = document.getElementById("promptFormStatus");
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("err", !!isErr);
  }

  function loadIntoPromptForm(s) {
    switchTab("prompts");
    document.getElementById("promptEditId").value = s.id;
    document.getElementById("promptTrigger").value = s.trigger || "";
    document.getElementById("promptLabel").value = s.label || "";
    document.getElementById("promptBody").value = s.body || "";
    document.getElementById("promptUseCase").value = s.useCase || "";
    document.getElementById("promptRole").value = s.role || "";
    document.getElementById("promptOutputType").value = s.outputType || "";
    document.getElementById("promptVerbosity").value = s.verbosity || "";
    document.getElementById("promptCancelEdit").style.display = "";
    setPromptStatus("Editing " + s.trigger + " — save to update, or cancel.");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function clearPromptForm() {
    document.getElementById("promptEditId").value = "";
    document.getElementById("promptTrigger").value = "";
    document.getElementById("promptLabel").value = "";
    document.getElementById("promptBody").value = "";
    document.getElementById("promptUseCase").value = "";
    document.getElementById("promptRole").value = "";
    document.getElementById("promptOutputType").value = "";
    document.getElementById("promptVerbosity").value = "";
    document.getElementById("promptCancelEdit").style.display = "none";
    setPromptStatus("");
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
        kind: "snippet",
        trigger,
        label,
        body,
        enabled: true,
        useCount: 0,
        lastUsedAt: null,
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

  document.getElementById("tabBtnSnippets").addEventListener("click", () => switchTab("snippets"));
  document.getElementById("tabBtnPrompts").addEventListener("click", () => switchTab("prompts"));

  document.getElementById("promptSearch").addEventListener("input", (e) => {
    promptSearchQuery = e.target.value || "";
    promptPage = 0;
    renderPromptList();
  });

  document.getElementById("promptAutoClassify").addEventListener("click", () => {
    if (!recallLib) return;
    const body = document.getElementById("promptBody").value;
    if (!body.trim()) {
      setPromptStatus("Write a body first, then auto-classify.", true);
      return;
    }
    const guess = recallLib.classify(body);
    if (guess.useCase) document.getElementById("promptUseCase").value = guess.useCase;
    if (guess.role) document.getElementById("promptRole").value = guess.role;
    if (guess.outputType) document.getElementById("promptOutputType").value = guess.outputType;
    setPromptStatus("Guessed facets at " + guess.confidence + " confidence — review before saving.");
  });

  document.getElementById("promptCancelEdit").addEventListener("click", clearPromptForm);

  document.getElementById("promptSaveEntry").addEventListener("click", async () => {
    const id = document.getElementById("promptEditId").value.trim();
    const trigger = document.getElementById("promptTrigger").value.trim();
    const label = document.getElementById("promptLabel").value.trim();
    const body = document.getElementById("promptBody").value;
    const useCase = document.getElementById("promptUseCase").value || null;
    const role = document.getElementById("promptRole").value || null;
    const outputType = document.getElementById("promptOutputType").value || null;
    const verbosity = document.getElementById("promptVerbosity").value || null;
    if (!trigger) {
      setPromptStatus("Trigger is required.", true);
      return;
    }
    const dupe = snippets.find((s) => s.trigger === trigger && s.id !== id);
    if (dupe) {
      setPromptStatus("Another snippet/prompt already uses trigger " + trigger + ".", true);
      return;
    }
    if (id) {
      const existing = snippets.find((s) => s.id === id);
      if (existing) {
        existing.trigger = trigger;
        existing.label = label;
        existing.body = body;
        existing.useCase = useCase;
        existing.role = role;
        existing.outputType = outputType;
        existing.verbosity = verbosity;
        existing.updatedAt = Date.now();
      }
    } else {
      snippets.push({
        id: uid(),
        kind: "prompt",
        trigger,
        label,
        body,
        useCase,
        role,
        outputType,
        verbosity,
        enabled: true,
        useCount: 0,
        lastUsedAt: null,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      });
    }
    await save();
    clearPromptForm();
    setPromptStatus("Saved.");
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
    if (recallLib) {
      populateFacetSelect(document.getElementById("promptUseCase"), recallLib.USE_CASES, recallLib.USE_CASE_LABELS);
      populateFacetSelect(document.getElementById("promptRole"), recallLib.ROLES, recallLib.ROLE_LABELS);
      populateFacetSelect(document.getElementById("promptOutputType"), recallLib.OUTPUT_TYPES, recallLib.OUTPUT_TYPE_LABELS);
    }
    renderList();
    renderPromptList();
  }

  boot();
})();
