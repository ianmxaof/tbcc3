/**
 * TBCC global "Copied!" tooltip toast + clipboard helper.
 * Load in extension pages (gallery, overlay) and mirror logic in dashboard TS.
 */
(function (root) {
  const COPIED_MSG = "Copied!";
  const DEFAULT_MS = 1600;

  function injectStyles() {
    if (typeof document === "undefined") return;
    if (document.getElementById("tbcc-copied-toast-styles")) return;
    const style = document.createElement("style");
    style.id = "tbcc-copied-toast-styles";
    style.textContent =
      ".tbcc-copied-toast-host{position:fixed;inset:0;z-index:2147483646;pointer-events:none}" +
      ".tbcc-copied-toast{position:fixed;padding:4px 10px;font:600 11px/1.35 system-ui,-apple-system,sans-serif;" +
      "color:#ecfdf5;background:rgba(16,185,129,.94);border:1px solid rgba(52,211,153,.55);border-radius:6px;" +
      "box-shadow:0 4px 14px rgba(0,0,0,.35);animation:tbcc-copied-pop .2s ease;pointer-events:none;white-space:nowrap}" +
      "@keyframes tbcc-copied-pop{from{opacity:0;transform:scale(.92) translateY(4px)}to{opacity:1;transform:scale(1) translateY(0)}}";
    (document.head || document.documentElement).appendChild(style);
  }

  function ensureHost() {
    injectStyles();
    let host = document.getElementById("tbcc-copied-toast-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "tbcc-copied-toast-host";
      host.className = "tbcc-copied-toast-host";
      host.setAttribute("aria-live", "polite");
      (document.body || document.documentElement).appendChild(host);
    }
    return host;
  }

  function copyViaExecCommand(text) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
      document.body.appendChild(ta);
      ta.select();
      ta.setSelectionRange(0, text.length);
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return !!ok;
    } catch (_) {
      return false;
    }
  }

  function showCopied(opts) {
    if (typeof document === "undefined") return;
    const host = ensureHost();
    const el = document.createElement("div");
    el.className = "tbcc-copied-toast";
    el.textContent = (opts && opts.message) || COPIED_MSG;
    host.appendChild(el);

    const anchor = opts && opts.anchor;
    if (anchor && typeof anchor.getBoundingClientRect === "function") {
      const r = anchor.getBoundingClientRect();
      const w = el.offsetWidth || 72;
      const left = Math.min(
        (window.innerWidth || 800) - w - 8,
        Math.max(8, r.left + r.width / 2 - w / 2)
      );
      const top = Math.max(8, r.top - 30);
      el.style.left = Math.round(left) + "px";
      el.style.top = Math.round(top) + "px";
    } else {
      el.style.right = "12px";
      el.style.bottom = "12px";
    }

    const ms = (opts && opts.durationMs) || DEFAULT_MS;
    window.setTimeout(function () {
      try {
        el.remove();
      } catch (_) {}
    }, ms);
  }

  async function copyText(text, opts) {
    const s = String(text == null ? "" : text);
    if (!s) return false;
    let ok = false;
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(s);
        ok = true;
      }
    } catch (_) {}
    if (!ok) ok = copyViaExecCommand(s);
    if (ok) showCopied({ anchor: opts && opts.anchor, message: opts && opts.message, durationMs: opts && opts.durationMs });
    return ok;
  }

  function bindDelegatedCopy(rootEl) {
    const root = rootEl || document;
    if (!root || root.__tbccCopyBound) return;
    root.__tbccCopyBound = true;
    root.addEventListener(
      "click",
      function (ev) {
        const t = ev.target;
        if (!t || !t.closest) return;
        const btn = t.closest("[data-tbcc-copy]");
        if (!btn || btn.disabled) return;
        const raw = btn.getAttribute("data-tbcc-copy");
        const fromId = btn.getAttribute("data-tbcc-copy-from");
        let text = raw != null ? raw : "";
        if (fromId) {
          const src = document.getElementById(fromId);
          if (src) text = src.textContent || src.innerText || "";
        }
        if (!String(text).trim()) return;
        ev.preventDefault();
        ev.stopPropagation();
        void copyText(text, { anchor: btn });
      },
      true
    );
  }

  const api = { COPIED_MSG, showCopied, copyText, copyViaExecCommand, bindDelegatedCopy };
  root.TbccClipboard = api;
  if (typeof document !== "undefined" && document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bindDelegatedCopy(document);
    });
  } else if (typeof document !== "undefined") {
    bindDelegatedCopy(document);
  }
})(typeof globalThis !== "undefined" ? globalThis : typeof window !== "undefined" ? window : self);
