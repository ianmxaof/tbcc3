/**
 * Erome transport overlay — right-edge chevron tab (like ML/TV/FL).
 * Live browse-intel + album Videos + Playwright. Shares localStorage with erome-enhancer.js.
 */
(function () {
  "use strict";

  const INTEL_KEY = "eromeBrowseIntelRows";
  const INTEL_META_KEY = "eromeBrowseIntelMeta";
  const OVERLAY_ID = "tbcc-erome-transport-overlay";
  const ROOT_ID = OVERLAY_ID; // body lookups still use tbccEtBody
  const OVERLAY_TOP_KEY = "tbcc_erome_overlay_top_v1";
  const OVERLAY_UI_KEY = "tbcc_erome_overlay_ui_v1";
  const JUMP_ID = "tbcc-erome-jump-stack";
  const THISVID_PENDING_KEY = "tbccThisVidPendingUpload";
  const THISVID_UPLOAD_URL = "https://thisvid.com/my_video_upload/";
  const VIDEOS_PAGE_SIZE = 1;

  let overlayCollapsed = true;
  let overlayWidthMode = "slim";
  let lastIntelBadgeCount = 0;

  function updateIntelHeaderBadge(opts) {
    const o = opts || {};
    const el = document.querySelector(`#${OVERLAY_ID} [data-er-intel-count]`);
    const btn = document.querySelector(`#${OVERLAY_ID} .tbcc-intel-badge`);
    if (!el) return;
    const count = loadRows().length;
    const recording = loadMeta().recordIntel !== false;
    el.textContent = String(count);
    if (btn) {
      btn.classList.toggle("off", !recording);
      btn.title = recording
        ? `Browse intel: ${count} rows · click for Live intel / Enhancer settings`
        : "Recording off — click for settings";
    }
    if (o.pulse && count > lastIntelBadgeCount) {
      el.style.transition = "color 0.2s ease, transform 0.2s ease";
      el.style.color = "#fff";
      el.style.transform = "scale(1.25)";
      setTimeout(() => {
        el.style.color = "";
        el.style.transform = "";
      }, 400);
    }
    lastIntelBadgeCount = count;
  }

  function openIntelSettingsPanel() {
    setOverlayCollapsed(false);
    showTab("intel");
    // Same config modal as the site-nav Enhancer total.
    try {
      const btn = document.getElementById("enhancerBtn");
      if (btn) btn.click();
    } catch (_) {}
  }

  function loadMeta() {
    try {
      return Object.assign(
        {
          recordIntel: true,
          showTransportOverlay: true,
          showIntelLivePanel: true,
          tbccApiUrl: "http://127.0.0.1:8000/analytics/erome-browse-intel",
          maxIntelRows: 5000,
        },
        JSON.parse(localStorage.getItem(INTEL_META_KEY) || "{}")
      );
    } catch (_) {
      return { showTransportOverlay: true, showIntelLivePanel: true };
    }
  }

  function saveMeta(meta) {
    localStorage.setItem(INTEL_META_KEY, JSON.stringify(meta));
  }

  function clampOverlayTop(px) {
    const max = Math.max(8, window.innerHeight - 140);
    return Math.min(max, Math.max(8, Math.round(Number(px) || 72)));
  }

  function loadOverlayTop() {
    try {
      return clampOverlayTop(JSON.parse(localStorage.getItem(OVERLAY_TOP_KEY) || "120"));
    } catch (_) {
      return 120;
    }
  }

  function saveOverlayTop(px) {
    try {
      localStorage.setItem(OVERLAY_TOP_KEY, JSON.stringify(clampOverlayTop(px)));
    } catch (_) {}
  }

  function loadOverlayUi() {
    try {
      const ui = JSON.parse(localStorage.getItem(OVERLAY_UI_KEY) || "{}");
      return {
        collapsed: ui.collapsed !== false,
        widthMode: ui.widthMode === "wide" || ui.widthMode === "normal" ? ui.widthMode : "slim",
      };
    } catch (_) {
      return { collapsed: true, widthMode: "slim" };
    }
  }

  function persistOverlayUi() {
    try {
      localStorage.setItem(
        OVERLAY_UI_KEY,
        JSON.stringify({ collapsed: !!overlayCollapsed, widthMode: overlayWidthMode })
      );
    } catch (_) {}
  }

  function bindVerticalDrag(root, handle, opts = {}) {
    if (!root || !handle) return;
    let dragging = false;
    let startY = 0;
    let startTop = 0;
    const ignore = opts.ignoreSelector || "";
    handle.addEventListener("pointerdown", (e) => {
      if (e.button != null && e.button !== 0) return;
      if (ignore && e.target && e.target.closest && e.target.closest(ignore)) return;
      dragging = true;
      startY = e.clientY;
      startTop = parseInt(root.style.top || "120", 10) || loadOverlayTop();
      handle.setPointerCapture?.(e.pointerId);
      e.preventDefault();
    });
    handle.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const next = clampOverlayTop(startTop + (e.clientY - startY));
      root.style.top = `${next}px`;
      syncJumpStack(root, root.style.display !== "none");
      if (Math.abs(e.clientY - startY) > 4) handle.dataset.suppressClick = "1";
    });
    const end = (e) => {
      if (!dragging) return;
      dragging = false;
      saveOverlayTop(parseInt(root.style.top || "120", 10) || 120);
      syncJumpStack(root, root.style.display !== "none");
      setTimeout(() => {
        delete handle.dataset.suppressClick;
      }, 0);
      try {
        handle.releasePointerCapture?.(e.pointerId);
      } catch (_) {}
    };
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  }

  function loadRows() {
    try {
      return JSON.parse(localStorage.getItem(INTEL_KEY) || "[]");
    } catch (_) {
      return [];
    }
  }

  function median(vals) {
    if (!vals.length) return 0;
    const a = vals.slice().sort((x, y) => x - y);
    return a[Math.floor(a.length / 2)] || 0;
  }

  function fmtNum(n) {
    if (typeof globalThis.tbccFormatAbbrevNumber === "function") {
      return globalThis.tbccFormatAbbrevNumber(n);
    }
    const v = Number(n);
    if (!Number.isFinite(v)) return "?";
    if (v >= 1e6) return `${(v / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
    if (v >= 1e3) return `${(v / 1e3).toFixed(1).replace(/\.0$/, "")}K`;
    return String(Math.round(v));
  }

  /** Pareto-style ranking: tags by median views/day (fallback median views). */
  function paretoTagRanks(rows) {
    const buckets = {};
    rows.forEach((r) => {
      (r.tags || []).forEach((t) => {
        if (!buckets[t]) buckets[t] = { vpd: [], views: [], n: 0 };
        buckets[t].n += 1;
        if (r.views_per_day_proxy) buckets[t].vpd.push(Number(r.views_per_day_proxy));
        if (r.views) buckets[t].views.push(Number(r.views));
      });
    });
    const ranked = Object.entries(buckets)
      .map(([tag, b]) => {
        const score = b.vpd.length ? median(b.vpd) : median(b.views);
        return { tag, score, n: b.n, metric: b.vpd.length ? "vpd" : "views" };
      })
      .sort((a, b) => b.score - a.score);
    const cut = Math.max(1, Math.ceil(ranked.length * 0.2));
    return { ranked, paretoCut: cut, pareto: ranked.slice(0, cut) };
  }

  function ensureStyles() {
    if (document.getElementById("tbcc-erome-transport-css")) return;
    const s = document.createElement("style");
    s.id = "tbcc-erome-transport-css";
    s.textContent = `
#${OVERLAY_ID}{
  position:fixed;right:0;z-index:2147483000;font:12px/1.35 system-ui,sans-serif;
  color:#e8e8e8;display:flex;align-items:stretch;pointer-events:none;
}
#${OVERLAY_ID} .tbcc-chevron,#${OVERLAY_ID} .tbcc-panel{pointer-events:auto}
#${OVERLAY_ID} .tbcc-chevron{
  writing-mode:vertical-rl;text-orientation:mixed;
  background:#1a1a1a;border:1px solid #444;border-right:0;color:#7ec8e3;
  padding:10px 6px;cursor:grab;border-radius:8px 0 0 8px;
  min-height:110px;font-size:11px;font-weight:700;letter-spacing:.06em;
  touch-action:none;user-select:none;
}
#${OVERLAY_ID} .tbcc-chevron:active{cursor:grabbing}
#${OVERLAY_ID} .tbcc-panel{
  display:flex;width:var(--tbcc-er-panel-w,260px);max-width:calc(100vw - 36px);
  max-height:min(72vh,560px);background:#141414;border:1px solid #3a3a3a;border-right:0;
  border-radius:10px 0 0 10px;box-shadow:-6px 0 24px rgba(0,0,0,.45);
  flex-direction:column;overflow:hidden;
}
#${OVERLAY_ID}.collapsed .tbcc-panel{display:none}
#${OVERLAY_ID}.slim{--tbcc-er-panel-w:220px}
#${OVERLAY_ID}.wide{--tbcc-er-panel-w:320px}
#${OVERLAY_ID} .tbcc-head{
  display:flex;justify-content:space-between;align-items:center;gap:6px;
  padding:8px 10px;background:#0d0d0d;border-bottom:1px solid #333;cursor:grab;
  touch-action:none;user-select:none;
}
#${OVERLAY_ID} .tbcc-head strong{flex:1;pointer-events:none;color:#7ec8e3;min-width:0}
#${OVERLAY_ID} .tbcc-head .tbcc-intel-badge{
  cursor:pointer;touch-action:auto;user-select:none;flex-shrink:0;
  display:inline-flex;align-items:center;gap:4px;
  background:#1a2830;color:#7ec8e3;border:1px solid #3a5560;border-radius:6px;
  padding:3px 8px;font-size:12px;font-weight:700;
}
#${OVERLAY_ID} .tbcc-head .tbcc-intel-badge:hover{filter:brightness(1.12);border-color:#7ec8e3}
#${OVERLAY_ID} .tbcc-head .tbcc-intel-badge.off{opacity:.45}
#${OVERLAY_ID} .tbcc-head button{
  cursor:pointer;touch-action:auto;user-select:auto;
  background:#333;color:#eee;border:1px solid #555;border-radius:6px;padding:4px 8px;font-size:11px;
}
#${OVERLAY_ID} .tabs{display:flex;gap:4px;padding:6px 8px;border-bottom:1px solid #2a2a2a;overflow-x:auto}
#${OVERLAY_ID} .tab{
  flex:0 0 auto;background:#222;color:#ccc;border:1px solid #3a3a3a;border-radius:6px;
  padding:5px 8px;cursor:pointer;font-size:11px;font-weight:600;
}
#${OVERLAY_ID} .tab.active{background:#243039;border-color:#7ec8e3;color:#fff}
#${OVERLAY_ID} .body{padding:10px;overflow:auto;flex:1}
#${OVERLAY_ID} .tbcc-foot{
  display:flex;justify-content:space-between;align-items:center;gap:6px;
  padding:6px 10px;border-top:1px solid #2a2a2a;background:#0d0d0d;
}
#${OVERLAY_ID} .tbcc-foot button{
  background:#333;color:#ddd;border:1px solid #555;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px;
}
#${OVERLAY_ID} .btn{display:inline-flex;align-items:center;gap:6px;padding:8px 12px;border-radius:8px;border:1px solid #456;
background:#2a4a5a;color:#dff;cursor:pointer;font-weight:600;font-size:12px;width:100%;justify-content:center;margin:4px 0}
#${OVERLAY_ID} .btn:hover{filter:brightness(1.1)}
#${OVERLAY_ID} .btn.primary{background:#eb6395;border-color:#eb6395;color:#fff}
#${OVERLAY_ID} .btn.row{width:auto;flex:1;margin:0}
#${OVERLAY_ID} .muted{color:#888;font-size:11px;margin:6px 0 10px}
#${OVERLAY_ID} .stat{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px}
#${OVERLAY_ID} .chip{background:#243039;border-radius:6px;padding:4px 8px;font-size:11px;color:#bcd}
#${OVERLAY_ID} .pareto-row{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px}
#${OVERLAY_ID} .pareto-row .bar{height:6px;border-radius:3px;background:#7ec8e3;min-width:2px}
#${OVERLAY_ID} .pareto-row.top{color:#fff;font-weight:700}
#${OVERLAY_ID} .pareto-row.top .bar{background:#eb6395}
#${OVERLAY_ID} .feed{margin-top:8px;border-top:1px solid #333;padding-top:8px;max-height:160px;overflow:auto}
#${OVERLAY_ID} .feed-item{font-size:11px;color:#aaa;padding:3px 0;border-bottom:1px solid #2a2a2a}
#${OVERLAY_ID} .feed-item strong{color:#ddd}
#${OVERLAY_ID} .status{font-size:11px;color:#9c9;margin-top:6px;min-height:1.2em}
#${OVERLAY_ID} .status.err{color:#f88}
#${OVERLAY_ID} .vid-pager{display:flex;align-items:center;gap:8px;margin:8px 0;justify-content:space-between}
#${OVERLAY_ID} .vid-pager button{flex:0 0 auto;width:auto;padding:6px 10px;margin:0}
#${OVERLAY_ID} .vid-url-field{width:100%;box-sizing:border-box;background:#12161a;border:1px solid #456;color:#dff;
border-radius:8px;padding:8px 10px;font:12px/1.35 ui-monospace,Consolas,monospace;resize:vertical;min-height:64px}
#${OVERLAY_ID} .vid-actions{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
#${OVERLAY_ID} .vid-alt{margin-top:10px;border-top:1px solid #333;padding-top:8px}
#${OVERLAY_ID} .vid-alt .chip{display:inline-block;margin:2px 4px 2px 0;cursor:pointer;max-width:100%;overflow:hidden;text-overflow:ellipsis}
#${JUMP_ID}{position:fixed;z-index:2147482999;right:0;display:none;flex-direction:column;gap:4px;pointer-events:none}
#${JUMP_ID} button{pointer-events:auto;width:28px;height:28px;border-radius:6px 0 0 6px;border:1px solid #444;border-right:0;
background:#1a1a1a;color:#bcd;font-size:12px;font-weight:700;cursor:pointer}
#${JUMP_ID} button:hover{filter:brightness(1.15);color:#fff}
`;
    document.documentElement.appendChild(s);
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function collectVideosFromDom() {
    const list = [];
    document.querySelectorAll("video").forEach((videoEl) => {
      const sources = Array.from(videoEl.querySelectorAll("source")).filter((s) => s && s.src);
      let entries = sources.map((s) => ({
        src: s.src,
        label: String(s.getAttribute("label") || s.getAttribute("data-quality") || "").trim(),
      }));
      if (!entries.length && videoEl.src && !/^blob:/i.test(videoEl.src)) {
        entries = [{ src: videoEl.src, label: "" }];
      }
      if (!entries.length) return;
      const hd = entries.find((e) => /hd|1080|720/i.test(e.label));
      const mp4 = entries.find((e) => /\.mp4(\?|#|$)/i.test(e.src));
      const best = (hd || mp4 || entries[0]).src;
      list.push({
        index: list.length + 1,
        url: best,
        sources: entries.map((e) => e.src).filter(Boolean),
      });
    });
    return list;
  }

  function getAlbumVideos() {
    const published = window.__tbccEromeAlbumVideos;
    if (Array.isArray(published) && published.length) return published;
    return collectVideosFromDom();
  }

  function albumTitleHint() {
    const h =
      document.querySelector("h1")?.textContent ||
      document.querySelector(".album-title")?.textContent ||
      document.title ||
      "";
    return String(h).replace(/\s+/g, " ").trim().slice(0, 120);
  }

  function isExtensionContextAlive() {
    try {
      return !!(typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.id);
    } catch (_) {
      return false;
    }
  }

  function sendToThisVid(srcUrl) {
    // Stale content script after TBCC reload — R2 bridge needs a fresh tab.
    if (!isExtensionContextAlive()) {
      try {
        void navigator.clipboard.writeText(String(srcUrl || ""));
      } catch (_) {}
      return { ok: false, error: "TBCC was reloaded — refresh this tab, then retry → ThisVid (URL copied)" };
    }
    if (typeof window.__tbccEromeSendToThisVid === "function") {
      window.__tbccEromeSendToThisVid(srcUrl);
      return { ok: true };
    }
    const payload = {
      url: srcUrl,
      title: albumTitleHint(),
      albumUrl: location.href.split("#")[0],
      ts: Date.now(),
    };
    const openUpload = () => window.open(THISVID_UPLOAD_URL, "_blank");
    try {
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        chrome.storage.local.set({ [THISVID_PENDING_KEY]: payload }, openUpload);
        return { ok: true };
      }
    } catch (_) {}
    try {
      localStorage.setItem(THISVID_PENDING_KEY, JSON.stringify(payload));
    } catch (_) {}
    openUpload();
    return { ok: true };
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      return false;
    }
  }

  async function fetchBackendDiscoveries() {
    try {
      const meta = loadMeta();
      const hint = String(meta.tbccApiUrl || "").trim();
      if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.fetchIntelSummary === "function") {
        const data = await globalThis.tbccBrowseIntel.fetchIntelSummary(hint, 30);
        if (!data) return null;
        return data.discoveries || data;
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  async function renderIntelBody(el) {
    const rows = loadRows();
    const { ranked, paretoCut, pareto } = paretoTagRanks(rows);
    const maxScore = ranked[0]?.score || 1;
    const recent = rows.slice(-12).reverse();
    const disc = await fetchBackendDiscoveries();
    const action = disc && Array.isArray(disc.suite_actions) ? disc.suite_actions[0] : null;
    const discoveryHtml = action
      ? `<div class="stat" style="margin-bottom:8px;border:1px solid #eb6395;padding:8px;border-radius:6px">
          <span class="chip" style="background:#eb6395;color:#fff">discovery</span>
          <span>${escapeHtml(action.label || "")}</span>
          <span class="muted">${escapeHtml(String(disc.preferred_format_bucket || ""))} · ${escapeHtml(String(disc.preferred_metric || ""))}</span>
        </div>`
      : "";
    const topHtml = ranked
      .slice(0, 15)
      .map((r, i) => {
        const pct = Math.round((r.score / maxScore) * 100);
        const isPareto = i < paretoCut;
        return `<div class="pareto-row${isPareto ? " top" : ""}">
          <span style="width:18px;color:#666">${i + 1}</span>
          <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(r.tag)}</span>
          <div class="bar" style="width:${Math.max(8, pct * 0.9)}px"></div>
          <span style="width:64px;text-align:right;font-variant-numeric:tabular-nums">${fmtNum(r.score)}${r.metric === "vpd" ? "/d" : ""}</span>
        </div>`;
      })
      .join("");
    const feedHtml = recent
      .map(
        (r) =>
          `<div class="feed-item"><strong>${escapeHtml((r.title || r.album_id || "").slice(0, 40))}</strong>
          · ${r.views != null ? fmtNum(r.views) : "?"} views · ${(r.tags || []).slice(0, 3).map(escapeHtml).join(", ")}</div>`
      )
      .join("");
    el.innerHTML = `
      ${discoveryHtml}
      <div class="stat">
        <span class="chip">rows ${rows.length}</span>
        <span class="chip">tags ${ranked.length}</span>
        <span class="chip">Pareto top ${pareto.length}/${ranked.length || 0}</span>
      </div>
      <div class="muted">Pareto (≈ top 20% by median views/day). Format discovery comes from TBCC ledger (push intel). After ext upgrade: Clear intel + re-scan if old rows show inflated M views.</div>
      ${topHtml || '<div class="muted">No intel yet — enable likes + Record browse intel, then scroll explore/search.</div>'}
      <div class="feed"><div class="muted" style="margin:0 0 4px">Live captures</div>${feedHtml || '<div class="muted">Waiting for albums…</div>'}</div>
    `;
  }

  function renderRecordBody(el) {
    el.innerHTML = `
      <p class="muted">Starts Playwright Codegen in a separate Brave window (not this tab). Backend must be running with your internal API key set in extension options.</p>
      <button type="button" class="btn primary" id="tbccPwRecordBtn">● Start Playwright record</button>
      <button type="button" class="btn" id="tbccPwRecordEromeBtn">Record on erome.com (auth)</button>
      <div class="status" id="tbccPwStatus"></div>
      <p class="muted">After Stop, workflow lands in <code>tbcc/backend/playwright-recordings/</code>.</p>
    `;
    const status = el.querySelector("#tbccPwStatus");
    async function start(url, name) {
      status.className = "status";
      status.textContent = "Starting…";
      try {
        const resp = await chrome.runtime.sendMessage({
          action: "tbcc-playwright-record",
          url,
          name,
        });
        if (resp && resp.ok) {
          status.textContent = resp.detail || "Codegen launched — check the Playwright panel.";
        } else {
          status.className = "status err";
          status.textContent = (resp && resp.error) || "Launch failed";
        }
      } catch (e) {
        status.className = "status err";
        status.textContent = String(e.message || e);
      }
    }
    el.querySelector("#tbccPwRecordBtn")?.addEventListener("click", () => start(location.href, "erome-live"));
    el.querySelector("#tbccPwRecordEromeBtn")?.addEventListener("click", () =>
      start("https://www.erome.com/", "erome-session")
    );
  }

  let videosPage = 0;

  function renderVideosBody(el) {
    const videos = getAlbumVideos();
    const total = videos.length;
    if (!location.pathname.startsWith("/a/")) {
      el.innerHTML =
        '<div class="muted">Open an album page (<code>/a/…</code>) to list direct video CDN URLs for copy / ThisVid upload.</div>';
      return;
    }
    if (!total) {
      el.innerHTML =
        '<div class="muted">No <code>&lt;video&gt;</code> sources yet — wait for the player to load, then reopen this tab.</div>' +
        '<button type="button" class="btn" id="tbccVidRefresh">Refresh</button>';
      el.querySelector("#tbccVidRefresh")?.addEventListener("click", () => renderVideosBody(el));
      return;
    }
    if (videosPage >= total) videosPage = total - 1;
    if (videosPage < 0) videosPage = 0;
    const item = videos[videosPage];
    const alts = (item.sources || []).filter((u) => u && u !== item.url);
    el.innerHTML = `
      <div class="stat">
        <span class="chip">${total} video${total === 1 ? "" : "s"}</span>
        <span class="chip">${videosPage + 1} / ${total}</span>
      </div>
      <div class="vid-pager">
        <button type="button" class="btn row" id="tbccVidPrev" ${videosPage <= 0 ? "disabled" : ""}>← Prev</button>
        <span class="muted" style="margin:0">Clip ${item.index || videosPage + 1}</span>
        <button type="button" class="btn row" id="tbccVidNext" ${videosPage >= total - 1 ? "disabled" : ""}>Next →</button>
      </div>
      <label class="muted" style="display:block;margin:0 0 4px">Direct URL (select / copy)</label>
      <textarea class="vid-url-field" id="tbccVidUrlField" readonly rows="3">${escapeHtml(item.url)}</textarea>
      <div class="vid-actions">
        <button type="button" class="btn primary row" id="tbccVidCopy">Copy URL</button>
        <button type="button" class="btn row" id="tbccVidThisVid">→ ThisVid</button>
      </div>
      <button type="button" class="btn" id="tbccVidCopyAll">Copy all URLs (${total})</button>
      ${
        alts.length
          ? `<div class="vid-alt"><div class="muted" style="margin:0 0 4px">Other qualities</div>${alts
              .map(
                (u, i) =>
                  `<span class="chip tbcc-vid-alt" data-i="${i}" title="${escapeHtml(u)}">${escapeHtml(
                    u.length > 48 ? u.slice(0, 45) + "…" : u
                  )}</span>`
              )
              .join("")}</div>`
          : ""
      }
      <div class="status" id="tbccVidStatus"></div>
    `;
    const status = el.querySelector("#tbccVidStatus");
    const field = el.querySelector("#tbccVidUrlField");
    field?.addEventListener("focus", () => field.select());
    field?.addEventListener("click", () => field.select());
    el.querySelector("#tbccVidPrev")?.addEventListener("click", () => {
      videosPage = Math.max(0, videosPage - 1);
      renderVideosBody(el);
    });
    el.querySelector("#tbccVidNext")?.addEventListener("click", () => {
      videosPage = Math.min(total - 1, videosPage + 1);
      renderVideosBody(el);
    });
    el.querySelector("#tbccVidCopy")?.addEventListener("click", async () => {
      const ok = await copyText(item.url);
      status.className = ok ? "status" : "status err";
      status.textContent = ok ? "Copied to clipboard" : "Copy failed — select the field and Ctrl+C";
      field?.select();
    });
    el.querySelector("#tbccVidThisVid")?.addEventListener("click", () => {
      const r = sendToThisVid(item.url);
      if (r && r.ok === false) {
        status.className = "status err";
        status.textContent = r.error || "Bridge failed — refresh this tab";
        return;
      }
      status.className = "status";
      status.textContent = "Hosting to R2 / opening ThisVid…";
    });
    el.querySelector("#tbccVidCopyAll")?.addEventListener("click", async () => {
      const blob = videos.map((v) => v.url).join("\n");
      const ok = await copyText(blob);
      status.className = ok ? "status" : "status err";
      status.textContent = ok ? `Copied ${total} URL(s)` : "Copy all failed";
    });
    el.querySelectorAll(".tbcc-vid-alt").forEach((chip) => {
      chip.addEventListener("click", async () => {
        const u = alts[Number(chip.getAttribute("data-i"))];
        if (!u) return;
        if (field) field.value = u;
        const ok = await copyText(u);
        status.className = ok ? "status" : "status err";
        status.textContent = ok ? "Copied alternate quality" : "Copy failed";
      });
    });
  }

  function refreshJumpRail() {
    const Rail = window.TBCCSuiteRail;
    const root = document.getElementById(OVERLAY_ID);
    if (!Rail || !root) return;
    Rail.syncJumpStack({
      stackId: JUMP_ID,
      overlayEl: root,
      visible: root.style.display !== "none",
      collapsed: overlayCollapsed,
    });
  }

  function syncJumpStack(root, visible) {
    // Legacy signature — stack only when collapsed (foot has ↑↓ when open).
    const Rail = window.TBCCSuiteRail;
    if (Rail) {
      Rail.syncJumpStack({
        stackId: JUMP_ID,
        overlayEl: root,
        visible: !!visible,
        collapsed: overlayCollapsed,
      });
      return;
    }
    let stack = document.getElementById(JUMP_ID);
    if (!stack) {
      stack = document.createElement("div");
      stack.id = JUMP_ID;
      stack.className = "tbcc-suite-jump-stack";
      stack.innerHTML = `
        <button type="button" id="tbccEromeJumpTop" title="Back to top">↑</button>
        <button type="button" id="tbccEromeJumpBottom" title="Back to bottom">↓</button>
      `;
      document.documentElement.appendChild(stack);
      stack.querySelector("#tbccEromeJumpTop")?.addEventListener("click", () => {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
      stack.querySelector("#tbccEromeJumpBottom")?.addEventListener("click", () => {
        const y = Math.max(
          document.documentElement.scrollHeight,
          document.body ? document.body.scrollHeight : 0
        );
        window.scrollTo({ top: y, behavior: "smooth" });
      });
    }
    const show = !!(visible && overlayCollapsed);
    stack.style.display = show ? "flex" : "none";
    if (root) {
      const top = parseInt(root.style.top || "120", 10) || 120;
      stack.style.top = `${top + 120}px`;
    }
  }

  function syncOverlayCollapsed(root) {
    if (!root) return;
    root.classList.toggle("collapsed", overlayCollapsed);
    root.classList.toggle("slim", overlayWidthMode === "slim");
    root.classList.toggle("wide", overlayWidthMode === "wide");
    const chevron = root.querySelector(".tbcc-chevron");
    if (chevron) chevron.textContent = overlayCollapsed ? "ER ▸" : "ER ◂";
    refreshJumpRail();
  }

  function setOverlayCollapsed(next) {
    overlayCollapsed = !!next;
    const root = document.getElementById(OVERLAY_ID);
    if (root) syncOverlayCollapsed(root);
    persistOverlayUi();
    if (!overlayCollapsed) {
      showTab(activeTab);
      startPoll();
    } else {
      stopPoll();
    }
  }

  function cycleWidthMode() {
    overlayWidthMode =
      overlayWidthMode === "slim" ? "normal" : overlayWidthMode === "normal" ? "wide" : "slim";
    const root = document.getElementById(OVERLAY_ID);
    if (root) syncOverlayCollapsed(root);
    persistOverlayUi();
  }

  let activeTab = "intel";
  let pollTimer = null;

  function startPoll() {
    if (pollTimer) return;
    pollTimer = setInterval(() => {
      const root = document.getElementById(OVERLAY_ID);
      if (!root || overlayCollapsed || root.style.display === "none") return;
      if (activeTab === "intel") renderIntelBody(document.getElementById("tbccEtBody"));
      if (activeTab === "videos") renderVideosBody(document.getElementById("tbccEtBody"));
    }, 1500);
  }

  function stopPoll() {
    if (!pollTimer) return;
    clearInterval(pollTimer);
    pollTimer = null;
  }

  function ensureOverlay() {
    ensureStyles();
    // Drop legacy FAB / floating panel if a prior version left them behind.
    document.getElementById("tbcc-erome-transport-fab")?.remove();
    const legacy = document.getElementById("tbcc-erome-transport-root");
    if (legacy && legacy.id !== OVERLAY_ID) legacy.remove();

    let root = document.getElementById(OVERLAY_ID);
    if (!root) {
      const ui = loadOverlayUi();
      overlayCollapsed = ui.collapsed;
      overlayWidthMode = ui.widthMode;

      root = document.createElement("div");
      root.id = OVERLAY_ID;
      root.style.top = `${loadOverlayTop()}px`;
      root.innerHTML = `
        <button type="button" class="tbcc-chevron" title="TBCC Erome — drag to move">ER ▸</button>
        <div class="tbcc-panel">
          <div class="tbcc-head">
            <strong>TBCC Erome</strong>
            <button type="button" class="tbcc-intel-badge" data-act="intel-open" title="Browse intel — click for settings">
              <span aria-hidden="true">▣</span><span data-er-intel-count>0</span>
            </button>
            <button type="button" data-act="width" title="Cycle panel width">Width</button>
            <button type="button" data-act="collapse" title="Collapse panel">Hide</button>
          </div>
          <div class="tabs">
            <button type="button" class="tab active" data-tab="intel">Live intel</button>
            <button type="button" class="tab" data-tab="videos">Videos</button>
            <button type="button" class="tab" data-tab="filters">Filters</button>
            <button type="button" class="tab" data-tab="record">Playwright</button>
          </div>
          <div class="body" id="tbccEtBody"></div>
          <div class="tbcc-foot">
            <button type="button" data-jump="top" title="Back to top">↑</button>
            <button type="button" data-jump="bottom" title="Back to bottom">↓</button>
          </div>
        </div>
      `;
      document.documentElement.appendChild(root);

      const chevron = root.querySelector(".tbcc-chevron");
      const head = root.querySelector(".tbcc-head");
      bindVerticalDrag(root, chevron, { ignoreSelector: "" });
      bindVerticalDrag(root, head, { ignoreSelector: "button" });

      chevron.addEventListener("click", () => {
        if (chevron.dataset.suppressClick === "1") return;
        if (overlayCollapsed && location.pathname.startsWith("/a/")) {
          activeTab = "videos";
          root.querySelectorAll(".tab").forEach((t) => {
            t.classList.toggle("active", t.getAttribute("data-tab") === "videos");
          });
        }
        setOverlayCollapsed(!overlayCollapsed);
      });

      root.querySelector('[data-act="collapse"]')?.addEventListener("click", () => {
        setOverlayCollapsed(true);
      });
      root.querySelector('[data-act="width"]')?.addEventListener("click", () => {
        cycleWidthMode();
      });
      root.querySelector('[data-act="intel-open"]')?.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        openIntelSettingsPanel();
      });
      updateIntelHeaderBadge();
      window.TBCCSuiteRail?.bindFootJumps(root);
      window.TBCCSuiteRail?.ensureStyles();

      root.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
          root.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
          tab.classList.add("active");
          showTab(tab.getAttribute("data-tab"));
        });
      });

      syncOverlayCollapsed(root);
      if (!overlayCollapsed) showTab(activeTab);
    } else if (!root.querySelector('.tab[data-tab="videos"]')) {
      const tabs = root.querySelector(".tabs");
      const recordTab = tabs?.querySelector('.tab[data-tab="record"]');
      const videosTab = document.createElement("button");
      videosTab.type = "button";
      videosTab.className = "tab";
      videosTab.setAttribute("data-tab", "videos");
      videosTab.textContent = "Videos";
      if (recordTab) tabs.insertBefore(videosTab, recordTab);
      else tabs?.appendChild(videosTab);
      videosTab.addEventListener("click", () => {
        root.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
        videosTab.classList.add("active");
        showTab("videos");
      });
    }
    return root;
  }

  function showTab(name) {
    activeTab = name || "intel";
    const body = document.getElementById("tbccEtBody");
    if (!body) return;
    if (activeTab === "record") renderRecordBody(body);
    else if (activeTab === "videos") renderVideosBody(body);
    else if (activeTab === "filters") renderFiltersBody(body);
    else renderIntelBody(body);
  }

  function loadEromeEnhancerSettings() {
    try {
      return Object.assign(
        { titleInclude: "", titleExclude: "" },
        JSON.parse(localStorage.getItem("eromeEnhancerSettings") || "{}")
      );
    } catch (_) {
      return { titleInclude: "", titleExclude: "" };
    }
  }

  function saveEromeEnhancerKeywords(inc, exc) {
    try {
      const cur = loadEromeEnhancerSettings();
      cur.titleInclude = String(inc || "").trim();
      cur.titleExclude = String(exc || "").trim();
      localStorage.setItem("eromeEnhancerSettings", JSON.stringify(cur));
      window.dispatchEvent(new CustomEvent("tbcc-erome-keywords-changed"));
    } catch (_) {}
  }

  function renderFiltersBody(el) {
    const s = loadEromeEnhancerSettings();
    el.innerHTML = `
      <p class="muted">Same Include/Exclude as the sticky grid bar (Erome enhancer). Include = all must match; exclude = hide if any.</p>
      <label style="display:block;margin:6px 0 2px;color:#aaa">Include (all must match)</label>
      <input type="text" id="tbccEtKwInc" placeholder="e.g. milf blonde" value="${escapeHtml(s.titleInclude || "")}" style="width:100%;box-sizing:border-box;background:#12161a;border:1px solid #456;color:#dff;border-radius:8px;padding:8px" />
      <label style="display:block;margin:8px 0 2px;color:#aaa">Exclude (hide if any)</label>
      <input type="text" id="tbccEtKwExc" placeholder="e.g. gay" value="${escapeHtml(s.titleExclude || "")}" style="width:100%;box-sizing:border-box;background:#12161a;border:1px solid #456;color:#dff;border-radius:8px;padding:8px" />
      <div style="display:flex;gap:6px;margin-top:10px">
        <button type="button" class="btn primary" id="tbccEtKwApply">Apply</button>
        <button type="button" class="btn" id="tbccEtKwClear">Clear</button>
      </div>
      <div class="status" id="tbccEtKwStatus"></div>
    `;
    const apply = () => {
      const inc = el.querySelector("#tbccEtKwInc")?.value || "";
      const exc = el.querySelector("#tbccEtKwExc")?.value || "";
      saveEromeEnhancerKeywords(inc, exc);
      const barInc = document.getElementById("eeTitleInclude");
      const barExc = document.getElementById("eeTitleExclude");
      if (barInc) barInc.value = inc.trim();
      if (barExc) barExc.value = exc.trim();
      if (typeof window.__tbccEromeApplyTitleKeywords === "function") {
        window.__tbccEromeApplyTitleKeywords();
      }
      const st = el.querySelector("#tbccEtKwStatus");
      if (st) {
        st.className = "status";
        st.textContent = "Keywords saved — grid will refilter";
      }
    };
    el.querySelector("#tbccEtKwApply")?.addEventListener("click", apply);
    el.querySelector("#tbccEtKwClear")?.addEventListener("click", () => {
      const i = el.querySelector("#tbccEtKwInc");
      const e = el.querySelector("#tbccEtKwExc");
      if (i) i.value = "";
      if (e) e.value = "";
      apply();
    });
  }

  function setVisible(enabled, openPanel) {
    const root = ensureOverlay();
    const on = !!enabled;
    root.style.display = on ? "flex" : "none";
    syncJumpStack(root, on);

    const meta = loadMeta();
    meta.showTransportOverlay = on;
    saveMeta(meta);

    if (on && openPanel === true) setOverlayCollapsed(false);
    else if (on && openPanel === false) {
      /* keep persisted collapsed state */
      syncOverlayCollapsed(root);
      if (!overlayCollapsed) {
        showTab(activeTab);
        startPoll();
      } else stopPoll();
    } else if (!on) {
      stopPoll();
    }
  }

  function setOpen(open) {
    const meta = loadMeta();
    if (!meta.showTransportOverlay && !open) {
      setVisible(false, false);
      return;
    }
    setVisible(true, open);
  }

  function refreshIfOpen() {
    const root = document.getElementById(OVERLAY_ID);
    updateIntelHeaderBadge({ pulse: true });
    if (!root || overlayCollapsed || root.style.display === "none") return;
    if (activeTab === "intel") renderIntelBody(document.getElementById("tbccEtBody"));
    if (activeTab === "videos") renderVideosBody(document.getElementById("tbccEtBody"));
  }

  function boot() {
    const meta = loadMeta();
    // Default on for right-rail parity with ML/TV/FL (opt-out via settings).
    const enabled = meta.showTransportOverlay !== false;
    ensureOverlay();
    setVisible(enabled, false);
    window.addEventListener("tbcc-erome-intel-row", refreshIfOpen);
    window.addEventListener("tbcc-erome-album-videos", () => {
      if (activeTab === "videos") refreshIfOpen();
    });
    window.addEventListener("tbcc-erome-transport-toggle", (ev) => {
      const on = !!(ev && ev.detail && ev.detail.open);
      setVisible(on, on ? false : false);
      if (on) {
        /* show chevron; leave collapsed unless already open */
        syncOverlayCollapsed(document.getElementById(OVERLAY_ID));
      }
    });
    window.addEventListener("resize", () => {
      const root = document.getElementById(OVERLAY_ID);
      if (!root) return;
      root.style.top = `${clampOverlayTop(parseInt(root.style.top || "120", 10) || 120)}px`;
      syncJumpStack(root, root.style.display !== "none");
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
