/**
 * Raycast-style Quick Fix for snippet library users: select messy text (or focus a field),
 * press the recorded Quick Fix hotkey, and replace in place with corrected spelling/caps/grammar.
 * Active when snippet expansion is enabled (tbccSnippetSettings.enabled).
 */
(function () {
  const MODULE_ID = "snippetExpander";
  const STORAGE_SETTINGS = "tbccSnippetSettings";
  const ALLOWED_INPUT_TYPES = new Set(["text", "search", "url", "tel", "email"]);
  const lib = typeof TbccTextQuickfix !== "undefined" ? TbccTextQuickfix : null;
  const hkLib = typeof TbccHotkeyLib !== "undefined" ? TbccHotkeyLib : null;

  let settings = { enabled: true, disabledDomains: [] };
  let listening = false;
  let keyListening = false;

  function resolvedQuickFixHotkey() {
    if (!hkLib) return null;
    return hkLib.normalizeHotkey(settings.quickFixHotkey) || hkLib.defaultQuickFixHotkey();
  }

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

  function replaceRangeInInput(el, start, end, newText) {
    const value = el.value || "";
    const newValue = value.slice(0, start) + newText + value.slice(end);
    const setter = nativeValueSetter(el);
    if (setter) setter.call(el, newValue);
    else el.value = newValue;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    const caret = start + newText.length;
    try {
      el.setSelectionRange(caret, caret);
    } catch (_) {}
  }

  function activeEditable() {
    const el = document.activeElement;
    if (!el) return null;
    if (isEditableInput(el)) return el;
    if (el.isContentEditable) return el;
    return null;
  }

  function selectionFromInput(el) {
    const start = el.selectionStart;
    const end = el.selectionEnd;
    if (start == null || end == null) return null;
    const value = el.value || "";
    const hasSelection = start !== end;
    return {
      text: hasSelection ? value.slice(start, end) : value,
      start: hasSelection ? start : 0,
      end: hasSelection ? end : value.length,
      hadSelection: hasSelection,
    };
  }

  function selectionFromContentEditable(el) {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return null;
    const range = sel.getRangeAt(0);
    if (!el.contains(range.startContainer) || !el.contains(range.endContainer)) return null;
    const hadSelection = !sel.isCollapsed;
    const text = hadSelection ? sel.toString() : String(el.innerText || el.textContent || "");
    if (!text) return null;
    return { text, hadSelection, range: hadSelection ? range.cloneRange() : null, el };
  }

  function replaceInContentEditable(ctx, newText) {
    const sel = window.getSelection();
    if (!sel) return false;
    if (ctx.hadSelection && ctx.range) {
      sel.removeAllRanges();
      sel.addRange(ctx.range);
    } else {
      const el = ctx.el;
      const range = document.createRange();
      range.selectNodeContents(el);
      sel.removeAllRanges();
      sel.addRange(range);
    }
    document.execCommand("insertText", false, newText);
    return true;
  }

  function showToast(message, anchor) {
    if (typeof tbccShowCopiedToast === "function") {
      tbccShowCopiedToast({ message, anchor, durationMs: 1400 });
    }
  }

  async function requestFix(text) {
    try {
      const res = await chrome.runtime.sendMessage({ action: "tbcc-text-quickfix", text });
      if (res && res.ok && res.text) return res;
    } catch (_) {}
    if (lib && lib.localQuickFix) {
      return { ok: true, text: lib.localQuickFix(text), via: "local" };
    }
    return { ok: false, error: "quickfix unavailable" };
  }

  async function runQuickFix() {
    if (settings.enabled === false) return { ok: false, error: "disabled" };
    if (isDomainDisabled()) return { ok: false, error: "domain_disabled" };

    const el = activeEditable();
    if (!el) return { ok: false, error: "no_field" };

    const ctx = isEditableInput(el) ? selectionFromInput(el) : selectionFromContentEditable(el);
    if (!ctx || !String(ctx.text || "").trim()) return { ok: false, error: "no_text" };

    const original = ctx.text;
    const result = await requestFix(original);
    if (!result.ok || !result.text || result.text === original) {
      return { ok: false, error: result.error || "unchanged", via: result.via };
    }

    if (isEditableInput(el)) {
      replaceRangeInInput(el, ctx.start, ctx.end, result.text);
    } else if (replaceInContentEditable(ctx, result.text)) {
      el.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      return { ok: false, error: "replace_failed" };
    }

    showToast(result.via === "llm" ? "Fixed" : "Fixed (local)", el);
    return { ok: true, via: result.via || "unknown" };
  }

  function triggerQuickFix(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    void runQuickFix();
  }

  let onDoubleTapKeydown = null;

  function onKeydown(e) {
    if (settings.enabled === false || isDomainDisabled()) return;
    const hotkey = resolvedQuickFixHotkey();
    if (!hotkey || !hkLib) return;
    if (hotkey.doubleTap && onDoubleTapKeydown) {
      onDoubleTapKeydown(e);
      return;
    }
    if (!hkLib.eventMatchesHotkey(e, hotkey)) return;
    triggerQuickFix(e);
  }

  function onMessage(msg, _sender, sendResponse) {
    if (msg && msg.action === "tbcc-quick-fix-run") {
      void runQuickFix().then(sendResponse);
      return true;
    }
    return false;
  }

  function start() {
    if (listening) return;
    listening = true;
    chrome.runtime.onMessage.addListener(onMessage);
    if (!keyListening) {
      keyListening = true;
      if (hkLib && hkLib.createDoubleTapHandler) {
        onDoubleTapKeydown = hkLib.createDoubleTapHandler(resolvedQuickFixHotkey, triggerQuickFix);
      }
      document.addEventListener("keydown", onKeydown, true);
    }
  }

  function stop() {
    if (listening) {
      listening = false;
      chrome.runtime.onMessage.removeListener(onMessage);
    }
    if (keyListening) {
      keyListening = false;
      onDoubleTapKeydown = null;
      document.removeEventListener("keydown", onKeydown, true);
    }
  }

  function applySettings(data) {
    if (data[STORAGE_SETTINGS] && typeof data[STORAGE_SETTINGS] === "object") {
      settings = Object.assign({ enabled: true, disabledDomains: [] }, data[STORAGE_SETTINGS]);
    }
  }

  function boot() {
    chrome.storage.local.get([STORAGE_SETTINGS], (data) => {
      applySettings(data || {});
      start();
    });
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local" || !changes[STORAGE_SETTINGS]) return;
      settings = Object.assign({ enabled: true, disabledDomains: [] }, changes[STORAGE_SETTINGS].newValue || {});
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
