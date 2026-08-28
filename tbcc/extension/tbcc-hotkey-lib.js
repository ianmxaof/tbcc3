/**
 * Hotkey parse/format/match for extension UI recorders and content-script listeners.
 * Supports chord shortcuts (Ctrl+Shift+E) and double-tap keys (⇧⇧).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { TbccHotkeyLib: api };
  }
  root.TbccHotkeyLib = api;
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this, function () {
  const MODIFIER_ONLY = new Set([
    "Control",
    "Shift",
    "Alt",
    "Meta",
    "AltGraph",
    "OS",
  ]);
  const DEFAULT_DOUBLE_TAP_MS = 450;

  function isMacPlatform() {
    try {
      return /Mac|iPhone|iPad|iPod/i.test(navigator.platform || "") || navigator.userAgent.includes("Mac");
    } catch (_) {
      return false;
    }
  }

  function normalizeHotkey(raw) {
    if (!raw || typeof raw !== "object") return null;
    if (raw.doubleTap) {
      const key = String(raw.key || "Shift").trim();
      if (!key) return null;
      const hk = { doubleTap: true, key };
      const code = String(raw.code || "").trim();
      if (code) hk.code = code;
      return hk;
    }
    const key = String(raw.key || "").trim();
    if (!key) return null;
    const hk = {
      ctrl: !!raw.ctrl,
      shift: !!raw.shift,
      alt: !!raw.alt,
      meta: !!raw.meta,
      key: key.length === 1 ? key.toUpperCase() : key,
    };
    const code = String(raw.code || "").trim();
    if (code) hk.code = code;
    if (!hk.ctrl && !hk.shift && !hk.alt && !hk.meta) return null;
    return hk;
  }

  function defaultQuickFixHotkey() {
    return { doubleTap: true, key: "Shift" };
  }

  function keyLabel(hk) {
    if (!hk) return "";
    if (hk.code === "ShiftRight") return "Right Shift";
    if (hk.code === "ShiftLeft") return "Left Shift";
    if (hk.code === "ControlRight") return "Right Ctrl";
    if (hk.code === "ControlLeft") return "Left Ctrl";
    if (hk.code === "AltRight") return "Right Alt";
    if (hk.code === "AltLeft") return "Left Alt";
    if (hk.key === "Shift") return "Shift";
    if (hk.key === "Control") return "Ctrl";
    if (hk.key === "Alt") return "Alt";
    if (hk.key === "Meta") return isMacPlatform() ? "⌘" : "Win";
    return hk.key.length === 1 ? hk.key.toUpperCase() : hk.key;
  }

  function formatHotkey(h, opts) {
    const hk = normalizeHotkey(h);
    if (!hk) return "Not set";
    if (hk.doubleTap) {
      const mac = opts && opts.mac != null ? opts.mac : isMacPlatform();
      const label = keyLabel(hk);
      if (hk.key === "Shift" && !hk.code) return mac ? "⇧⇧" : "Double Shift";
      return "Double " + label;
    }
    const mac = opts && opts.mac != null ? opts.mac : isMacPlatform();
    const parts = [];
    if (hk.ctrl) parts.push(mac ? "⌃" : "Ctrl");
    if (hk.alt) parts.push(mac ? "⌥" : "Alt");
    if (hk.shift) parts.push(mac ? "⇧" : "Shift");
    if (hk.meta) parts.push(mac ? "⌘" : "Win");
    const displayKey = hk.key.length === 1 ? hk.key.toUpperCase() : hk.key;
    parts.push(displayKey);
    return mac ? parts.join("") : parts.join("+");
  }

  function eventMatchesHotkey(e, h) {
    const hk = normalizeHotkey(h);
    if (!hk || !e || hk.doubleTap) return false;
    if (MODIFIER_ONLY.has(e.key)) return false;
    if (e.ctrlKey !== hk.ctrl || e.shiftKey !== hk.shift || e.altKey !== hk.alt || e.metaKey !== hk.meta) {
      return false;
    }
    if (hk.code && e.code) return e.code === hk.code;
    return String(e.key || "").toLowerCase() === hk.key.toLowerCase();
  }

  function doubleTapEventMatches(e, hk) {
    if (!e || !hk || !hk.doubleTap) return false;
    if (e.repeat) return false;
    if (e.ctrlKey || e.altKey || e.metaKey) return false;
    if (hk.key === "Shift" && e.key !== "Shift") return false;
    if (hk.key === "Control" && e.key !== "Control") return false;
    if (hk.key === "Alt" && e.key !== "Alt") return false;
    if (hk.key === "Meta" && e.key !== "Meta") return false;
    if (hk.key !== "Shift" && hk.key !== "Control" && hk.key !== "Alt" && hk.key !== "Meta") {
      if (String(e.key || "").toLowerCase() !== hk.key.toLowerCase()) return false;
    }
    if (hk.code && e.code && e.code !== hk.code) return false;
    return true;
  }

  /**
   * Returns a keydown handler that fires on the second tap within windowMs.
   */
  function createDoubleTapHandler(getHotkey, onTrigger, windowMs) {
    const ms = Number.isFinite(windowMs) ? windowMs : DEFAULT_DOUBLE_TAP_MS;
    let lastTapAt = 0;
    let lastCode = "";
    return function onKeydown(e) {
      const hk = normalizeHotkey(getHotkey());
      if (!hk || !hk.doubleTap) return;
      if (!doubleTapEventMatches(e, hk)) return;
      const now = Date.now();
      const sameSide = !hk.code || e.code === lastCode;
      if (lastTapAt && now - lastTapAt <= ms && sameSide) {
        lastTapAt = 0;
        lastCode = "";
        onTrigger(e);
        return;
      }
      lastTapAt = now;
      lastCode = e.code || "";
    };
  }

  function hotkeyFromKeyboardEvent(e, recorderState) {
    if (!e) return null;
    if (e.key === "Escape") return { cancel: true };
    if (MODIFIER_ONLY.has(e.key) && !e.repeat) {
      const state = recorderState || { at: 0, code: "" };
      const now = Date.now();
      if (state.at && now - state.at <= DEFAULT_DOUBLE_TAP_MS && e.code === state.code) {
        return {
          hotkey: { doubleTap: true, key: e.key, code: e.code },
          resetRecorder: true,
        };
      }
      return {
        pendingDouble: true,
        recorderState: { at: now, code: e.code },
        label: keyLabel({ key: e.key, code: e.code }),
      };
    }
    if (!e.ctrlKey && !e.shiftKey && !e.altKey && !e.metaKey) {
      return { error: "modifier_required" };
    }
    const hk = normalizeHotkey({
      ctrl: e.ctrlKey,
      shift: e.shiftKey,
      alt: e.altKey,
      meta: e.metaKey,
      key: e.key,
      code: e.code,
    });
    return hk ? { hotkey: hk, resetRecorder: true } : { error: "invalid" };
  }

  return {
    MODIFIER_ONLY,
    DEFAULT_DOUBLE_TAP_MS,
    isMacPlatform,
    normalizeHotkey,
    defaultQuickFixHotkey,
    formatHotkey,
    eventMatchesHotkey,
    doubleTapEventMatches,
    createDoubleTapHandler,
    hotkeyFromKeyboardEvent,
  };
});
