/**
 * Text-expansion content script: type a stored trigger (e.g. "/p3") in any
 * text input, textarea, or contenteditable field to instantly expand it.
 * Registers through tbcc-module-gate.js so it can be toggled off per-install.
 */
(function () {
  const MODULE_ID = "snippetExpander";
  const STORAGE_SNIPPETS = "tbccSnippets";
  const STORAGE_SETTINGS = "tbccSnippetSettings";
  const ALLOWED_INPUT_TYPES = new Set(["text", "search", "url", "tel", "email"]);

  const lib = typeof TbccSnippetLib !== "undefined" ? TbccSnippetLib : null;
  if (!lib) return;

  let snippets = [];
  let usagePersistTimer = null;

  /** Bump useCount/lastUsedAt on the expanded entry and persist (debounced — a fast typist can trigger several expansions in a row). */
  function recordUsage(entry) {
    if (!entry || !entry.id) return;
    entry.useCount = (Number(entry.useCount) || 0) + 1;
    entry.lastUsedAt = Date.now();
    if (usagePersistTimer) clearTimeout(usagePersistTimer);
    usagePersistTimer = setTimeout(() => {
      usagePersistTimer = null;
      chrome.storage.local.set({ [STORAGE_SNIPPETS]: snippets });
    }, 400);
  }

  let settings = { enabled: true, disabledDomains: [] };
  let suppressed = false;
  let listening = false;

  function isEditableInput(el) {
    if (!el) return false;
    if (el.tagName === "TEXTAREA") return true;
    if (el.tagName === "INPUT") return ALLOWED_INPUT_TYPES.has((el.type || "text").toLowerCase());
    return false;
  }

  function isDomainDisabled() {
    const host = String((location && location.hostname) || "").toLowerCase();
    if (!host) return false;
    const list = Array.isArray(settings.disabledDomains) ? settings.disabledDomains : [];
    return list.some((d) => {
      const dom = String(d || "").trim().toLowerCase();
      return dom && (host === dom || host.endsWith("." + dom));
    });
  }

  function nativeValueSetter(el) {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    return desc && desc.set;
  }

  function replaceInInputLike(el, triggerLen, expansion) {
    const start = el.selectionStart;
    if (start == null || start < triggerLen) return false;
    const value = el.value || "";
    const before = value.slice(0, start);
    const after = value.slice(start);
    const prefix = before.slice(0, before.length - triggerLen);
    const cursorOffset = expansion.cursorOffset != null ? expansion.cursorOffset : expansion.text.length;
    const newValue = prefix + expansion.text + after;
    suppressed = true;
    try {
      const setter = nativeValueSetter(el);
      if (setter) setter.call(el, newValue);
      else el.value = newValue;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      const caret = prefix.length + cursorOffset;
      try {
        el.setSelectionRange(caret, caret);
      } catch (_) {}
    } finally {
      suppressed = false;
    }
    return true;
  }

  function textBeforeCaretInContentEditable(el) {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || !sel.isCollapsed) return null;
    const range = sel.getRangeAt(0);
    if (!el.contains(range.startContainer)) return null;
    if (range.startContainer.nodeType !== Node.TEXT_NODE) return null;
    return String(range.startContainer.textContent || "").slice(0, range.startOffset);
  }

  /** Best-effort: deletes the trigger and inserts expansion text; caret lands at the end (no {{cursor}} support here). */
  function replaceInContentEditable(el, triggerLen) {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return false;
    const range = sel.getRangeAt(0);
    const node = range.startContainer;
    const offset = range.startOffset;
    if (node.nodeType !== Node.TEXT_NODE || offset < triggerLen) return false;
    const delRange = document.createRange();
    delRange.setStart(node, offset - triggerLen);
    delRange.setEnd(node, offset);
    sel.removeAllRanges();
    sel.addRange(delRange);
    return true;
  }

  async function tryExpand(el) {
    if (suppressed || !settings.enabled || !el) return;
    if (isDomainDisabled()) return;
    if (!snippets.length) return;

    const editableInput = isEditableInput(el);
    const editableCE = !editableInput && el.isContentEditable;
    if (!editableInput && !editableCE) return;

    const textBefore = editableInput
      ? (el.value || "").slice(0, el.selectionStart == null ? (el.value || "").length : el.selectionStart)
      : textBeforeCaretInContentEditable(el);
    if (textBefore == null) return;

    const match = lib.findTriggerMatch(snippets, textBefore);
    if (!match) return;
    const triggerLen = String(match.trigger).length;

    let clipboardText = "";
    if (lib.needsClipboard(match.body)) {
      try {
        clipboardText = await navigator.clipboard.readText();
      } catch (_) {}
    }
    const expansion = lib.expandTokens(match.body, { clipboardText });

    let expanded = false;
    if (editableInput) {
      expanded = replaceInInputLike(el, triggerLen, expansion);
    } else {
      suppressed = true;
      try {
        if (replaceInContentEditable(el, triggerLen)) {
          document.execCommand("insertText", false, expansion.text);
          expanded = true;
        }
      } finally {
        suppressed = false;
      }
    }
    if (expanded) recordUsage(match);
  }

  function onInput(e) {
    void tryExpand(e.target);
  }

  function start() {
    if (listening) return;
    listening = true;
    document.addEventListener("input", onInput, true);
  }

  function stop() {
    if (!listening) return;
    listening = false;
    document.removeEventListener("input", onInput, true);
  }

  function applySettings(data) {
    if (Array.isArray(data[STORAGE_SNIPPETS])) snippets = data[STORAGE_SNIPPETS];
    if (data[STORAGE_SETTINGS] && typeof data[STORAGE_SETTINGS] === "object") {
      settings = Object.assign({ enabled: true, disabledDomains: [] }, data[STORAGE_SETTINGS]);
    }
  }

  function boot() {
    chrome.storage.local.get([STORAGE_SNIPPETS, STORAGE_SETTINGS], (data) => {
      applySettings(data || {});
      start();
    });
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local") return;
      if (changes[STORAGE_SNIPPETS]) snippets = Array.isArray(changes[STORAGE_SNIPPETS].newValue) ? changes[STORAGE_SNIPPETS].newValue : [];
      if (changes[STORAGE_SETTINGS]) {
        settings = Object.assign({ enabled: true, disabledDomains: [] }, changes[STORAGE_SETTINGS].newValue || {});
      }
    });
  }

  if (typeof tbccWaitForModule === "function") {
    tbccWaitForModule(MODULE_ID, boot);
    if (typeof tbccBindModuleDisableListener === "function") {
      tbccBindModuleDisableListener(MODULE_ID, stop);
    }
  } else {
    boot();
  }
})();
