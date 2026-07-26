/**
 * Shared TBCC suite rail helpers — jump ↑↓ + keyword Include/Exclude.
 * Content scripts load this before site enhancers. Exposes window.TBCCSuiteRail.
 *
 * Jump UX (canonical — Erome transport):
 *  - Panel open → ↑↓ in .tbcc-foot
 *  - Panel collapsed → ↑↓ stack under the vertical chevron tab
 *
 * Keyword UX (canonical — Erome page bar + ThisVid match semantics):
 *  - Include = all tokens must match (AND)
 *  - Exclude = any token hides (OR)
 *  - Space/comma separated; case-insensitive
 */
(function (root) {
  "use strict";

  const STYLE_ID = "tbcc-suite-rail-css";

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent = `
.tbcc-suite-jump-stack{
  position:fixed;z-index:2147482999;right:0;display:none;flex-direction:column;gap:4px;pointer-events:none;
}
.tbcc-suite-jump-stack button{
  pointer-events:auto;width:28px;height:28px;border-radius:6px 0 0 6px;border:1px solid #444;border-right:0;
  background:#1a1a1a;color:#bcd;font-size:12px;font-weight:700;cursor:pointer;
}
.tbcc-suite-jump-stack button:hover{filter:brightness(1.15);color:#fff}
.tbcc-suite-kw-bar{
  position:sticky;top:0;z-index:2147482000;display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;
  padding:10px 12px;margin:0;background:rgba(18,18,18,.94);border-bottom:1px solid #333;
  font:12px/1.35 system-ui,Segoe UI,sans-serif;color:#ccc;backdrop-filter:blur(6px);
}
.tbcc-suite-kw-bar label{display:flex;flex-direction:column;gap:4px;flex:1;min-width:140px;color:#aaa}
.tbcc-suite-kw-bar input{
  background:#1b1b1b;border:1px solid #444;border-radius:6px;color:#eee;padding:6px 8px;font:inherit;
}
.tbcc-suite-kw-bar .tbcc-suite-kw-hint{width:100%;color:#777;font-size:11px}
.tbcc-suite-kw-bar button{
  background:#333;color:#eee;border:1px solid #555;border-radius:6px;padding:6px 12px;cursor:pointer;font:inherit;
  height:32px;align-self:flex-end;
}
.tbcc-suite-kw-bar button:hover{filter:brightness(1.1)}
.tbcc-suite-kw-filtered{display:none !important}
.tbcc-suite-foot-jumps{display:flex;gap:6px;align-items:center}
.tbcc-suite-foot-jumps button{
  background:#333;color:#ddd;border:1px solid #555;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px;
}
`;
    document.documentElement.appendChild(s);
  }

  function parseKeywords(raw) {
    return String(raw || "")
      .toLowerCase()
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  /** Include = AND all; exclude = OR any. Empty include = pass. */
  function matchesKeywords(haystack, includeRaw, excludeRaw) {
    const text = String(haystack || "").toLowerCase();
    const exclude = parseKeywords(excludeRaw);
    if (exclude.some((k) => text.includes(k))) return false;
    const include = parseKeywords(includeRaw);
    if (!include.length) return true;
    return include.every((k) => text.includes(k));
  }

  function scrollTop() {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function scrollBottom() {
    const y = Math.max(
      document.documentElement.scrollHeight,
      document.body ? document.body.scrollHeight : 0
    );
    window.scrollTo({ top: y, behavior: "smooth" });
  }

  /**
   * @param {object} opts
   * @param {string} opts.stackId unique element id
   * @param {HTMLElement|null} opts.overlayEl
   * @param {boolean} opts.visible overlay mounted/enabled
   * @param {boolean} opts.collapsed panel collapsed to chevron
   */
  function syncJumpStack(opts) {
    ensureStyles();
    const stackId = opts.stackId;
    if (!stackId) return;
    let stack = document.getElementById(stackId);
    if (!stack) {
      stack = document.createElement("div");
      stack.id = stackId;
      stack.className = "tbcc-suite-jump-stack";
      stack.innerHTML = `
        <button type="button" data-jump="top" title="Back to top">↑</button>
        <button type="button" data-jump="bottom" title="Back to bottom">↓</button>
      `;
      document.documentElement.appendChild(stack);
      stack.querySelector('[data-jump="top"]')?.addEventListener("click", scrollTop);
      stack.querySelector('[data-jump="bottom"]')?.addEventListener("click", scrollBottom);
    }
    const show = !!(opts.visible && opts.collapsed);
    stack.style.display = show ? "flex" : "none";
    const root = opts.overlayEl;
    if (root) {
      const top = parseInt(root.style.top || "120", 10) || 120;
      stack.style.top = `${top + 120}px`;
    }
  }

  /** Wire ↑↓ buttons already in .tbcc-foot (data-jump top|bottom). */
  function bindFootJumps(root) {
    if (!root || root.dataset.tbccFootJumpsBound) return;
    root.dataset.tbccFootJumpsBound = "1";
    root.querySelectorAll("[data-jump]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (btn.getAttribute("data-jump") === "bottom") scrollBottom();
        else scrollTop();
      });
    });
  }

  /**
   * Insert jump controls into an existing .tbcc-foot without removing Prev/Next.
   * Layout: [↑] [Prev] ind [Next] [↓]
   */
  function ensureFootJumpButtons(foot) {
    if (!foot || foot.querySelector("[data-jump]")) return;
    const up = document.createElement("button");
    up.type = "button";
    up.setAttribute("data-jump", "top");
    up.title = "Back to top";
    up.textContent = "↑";
    const down = document.createElement("button");
    down.type = "button";
    down.setAttribute("data-jump", "bottom");
    down.title = "Back to bottom";
    down.textContent = "↓";
    foot.insertBefore(up, foot.firstChild);
    foot.appendChild(down);
  }

  /**
   * Sticky page keyword bar (Erome-style).
   * @param {object} opts
   * @param {string} opts.barId
   * @param {string} opts.hint
   * @param {() => string} opts.getInclude
   * @param {() => string} opts.getExclude
   * @param {(inc: string, exc: string) => void} opts.onChange
   * @param {() => boolean} [opts.shouldMount]
   */
  function mountKeywordBar(opts) {
    ensureStyles();
    const barId = opts.barId;
    if (!barId || document.getElementById(barId)) return null;
    if (typeof opts.shouldMount === "function" && !opts.shouldMount()) return null;

    const bar = document.createElement("div");
    bar.id = barId;
    bar.className = "tbcc-suite-kw-bar";
    bar.innerHTML = `
      <label>Include (all must match)<input type="text" data-kw="inc" placeholder="e.g. milf blonde" autocomplete="off"></label>
      <label>Exclude (hide if any)<input type="text" data-kw="exc" placeholder="e.g. gay" autocomplete="off"></label>
      <button type="button" data-kw="clear">Clear</button>
      <div class="tbcc-suite-kw-hint">${opts.hint || "Refines titles on this grid (space/comma separated)."}</div>
    `;
    document.body.appendChild(bar);

    const inc = bar.querySelector('[data-kw="inc"]');
    const exc = bar.querySelector('[data-kw="exc"]');
    inc.value = opts.getInclude?.() || "";
    exc.value = opts.getExclude?.() || "";

    let t = null;
    const applyLive = () => {
      opts.onChange?.(String(inc.value || "").trim(), String(exc.value || "").trim());
    };
    const onInput = () => {
      clearTimeout(t);
      t = setTimeout(applyLive, 250);
    };
    inc.addEventListener("input", onInput);
    exc.addEventListener("input", onInput);
    bar.querySelector('[data-kw="clear"]')?.addEventListener("click", () => {
      inc.value = "";
      exc.value = "";
      applyLive();
    });
    return bar;
  }

  /** Overlay Filters-tab HTML matching the page bar. */
  function keywordFieldsHtml(prefix) {
    const p = prefix || "kw";
    return `
      <label>Include (all must match)
        <input type="text" data-${p}-inc placeholder="e.g. milf blonde" autocomplete="off" />
      </label>
      <label>Exclude (hide if any)
        <input type="text" data-${p}-exc placeholder="e.g. gay" autocomplete="off" />
      </label>
      <button type="button" class="secondary" data-${p}-clear>Clear keywords</button>
      <p class="hint" style="margin-top:8px">Space/comma separated. Include = all must match; exclude = hide if any.</p>
    `;
  }

  root.TBCCSuiteRail = {
    ensureStyles,
    parseKeywords,
    matchesKeywords,
    scrollTop,
    scrollBottom,
    syncJumpStack,
    bindFootJumps,
    ensureFootJumpButtons,
    mountKeywordBar,
    keywordFieldsHtml,
  };
})(typeof window !== "undefined" ? window : globalThis);
