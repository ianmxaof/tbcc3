/**
 * Erome transport overlay — Playwright record launcher + live browse-intel (Pareto tops)
 * + album video URLs (copy / ThisVid) + jump top/bottom under FAB.
 * Shares localStorage with erome-enhancer.js (eromeBrowseIntelRows / Meta).
 */
(function () {
  "use strict";

  const INTEL_KEY = "eromeBrowseIntelRows";
  const INTEL_META_KEY = "eromeBrowseIntelMeta";
  const ROOT_ID = "tbcc-erome-transport-root";
  const FAB_ID = "tbcc-erome-transport-fab";
  const JUMP_ID = "tbcc-erome-jump-stack";
  const THISVID_PENDING_KEY = "tbccThisVidPendingUpload";
  const THISVID_UPLOAD_URL = "https://www.thisvid.com/upload.php";
  const VIDEOS_PAGE_SIZE = 1;

  function loadMeta() {
    try {
      return Object.assign(
        {
          recordIntel: true,
          showTransportOverlay: false,
          showIntelLivePanel: true,
          tbccApiUrl: "http://127.0.0.1:8000/analytics/erome-browse-intel",
          maxIntelRows: 5000,
        },
        JSON.parse(localStorage.getItem(INTEL_META_KEY) || "{}")
      );
    } catch (_) {
      return { showTransportOverlay: false, showIntelLivePanel: true };
    }
  }

  function saveMeta(meta) {
    localStorage.setItem(INTEL_META_KEY, JSON.stringify(meta));
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
#${FAB_ID}{position:fixed;z-index:2147483645;right:16px;bottom:88px;width:48px;height:48px;border-radius:50%;
border:none;cursor:pointer;background:linear-gradient(145deg,#1a3a4a,#0d222c);color:#7ec8e3;font-size:18px;
box-shadow:0 4px 16px rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center}
#${FAB_ID}:hover{filter:brightness(1.15)}
#${FAB_ID}.open{outline:2px solid #7ec8e3}
#${JUMP_ID}{position:fixed;z-index:2147483645;right:16px;bottom:16px;display:none;flex-direction:column;gap:6px}
#${JUMP_ID} button{width:48px;height:36px;border-radius:10px;border:1px solid #3a4450;cursor:pointer;
background:#1b1f24;color:#bcd;font-size:14px;font-weight:700;box-shadow:0 4px 12px rgba(0,0,0,.4)}
#${JUMP_ID} button:hover{filter:brightness(1.12);color:#fff}
#${ROOT_ID}{position:fixed;z-index:2147483646;right:16px;bottom:148px;width:min(400px,calc(100vw - 24px));
max-height:min(72vh,580px);display:none;flex-direction:column;background:#1b1f24;color:#e8e8e8;
border:1px solid #3a4450;border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.55);overflow:hidden;
font:13px/1.4 system-ui,Segoe UI,sans-serif}
#${ROOT_ID}.open{display:flex}
#${ROOT_ID} .hdr{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:#12161a;border-bottom:1px solid #333}
#${ROOT_ID} .hdr h3{margin:0;font-size:13px;font-weight:700;color:#7ec8e3;letter-spacing:.02em}
#${ROOT_ID} .tabs{display:flex;gap:0;border-bottom:1px solid #333}
#${ROOT_ID} .tab{flex:1;padding:8px 4px;background:#161a1f;border:none;color:#999;cursor:pointer;font-weight:600;font-size:11px}
#${ROOT_ID} .tab.active{color:#fff;background:#243039;border-bottom:2px solid #7ec8e3}
#${ROOT_ID} .body{padding:10px 12px;overflow:auto;flex:1}
#${ROOT_ID} .btn{display:inline-flex;align-items:center;gap:6px;padding:8px 12px;border-radius:8px;border:1px solid #456;
background:#2a4a5a;color:#dff;cursor:pointer;font-weight:600;font-size:12px;width:100%;justify-content:center;margin:4px 0}
#${ROOT_ID} .btn:hover{filter:brightness(1.1)}
#${ROOT_ID} .btn.primary{background:#eb6395;border-color:#eb6395;color:#fff}
#${ROOT_ID} .btn.row{width:auto;flex:1;margin:0}
#${ROOT_ID} .muted{color:#888;font-size:11px;margin:6px 0 10px}
#${ROOT_ID} .stat{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px}
#${ROOT_ID} .chip{background:#243039;border-radius:6px;padding:4px 8px;font-size:11px;color:#bcd}
#${ROOT_ID} .pareto-row{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px}
#${ROOT_ID} .pareto-row .bar{height:6px;border-radius:3px;background:#7ec8e3;min-width:2px}
#${ROOT_ID} .pareto-row.top{color:#fff;font-weight:700}
#${ROOT_ID} .pareto-row.top .bar{background:#eb6395}
#${ROOT_ID} .feed{margin-top:8px;border-top:1px solid #333;padding-top:8px;max-height:160px;overflow:auto}
#${ROOT_ID} .feed-item{font-size:11px;color:#aaa;padding:3px 0;border-bottom:1px solid #2a2a2a}
#${ROOT_ID} .feed-item strong{color:#ddd}
#${ROOT_ID} .status{font-size:11px;color:#9c9;margin-top:6px;min-height:1.2em}
#${ROOT_ID} .status.err{color:#f88}
#${ROOT_ID} .vid-pager{display:flex;align-items:center;gap:8px;margin:8px 0;justify-content:space-between}
#${ROOT_ID} .vid-pager button{flex:0 0 auto;width:auto;padding:6px 10px;margin:0}
#${ROOT_ID} .vid-url-field{width:100%;box-sizing:border-box;background:#12161a;border:1px solid #456;color:#dff;
border-radius:8px;padding:8px 10px;font:12px/1.35 ui-monospace,Consolas,monospace;resize:vertical;min-height:64px}
#${ROOT_ID} .vid-actions{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
#${ROOT_ID} .vid-alt{margin-top:10px;border-top:1px solid #333;padding-top:8px}
#${ROOT_ID} .vid-alt .chip{display:inline-block;margin:2px 4px 2px 0;cursor:pointer;max-width:100%;overflow:hidden;text-overflow:ellipsis}
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

  function sendToThisVid(srcUrl) {
    if (typeof window.__tbccEromeSendToThisVid === "function") {
      window.__tbccEromeSendToThisVid(srcUrl);
      return;
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
        return;
      }
    } catch (_) {}
    try {
      localStorage.setItem(THISVID_PENDING_KEY, JSON.stringify(payload));
    } catch (_) {}
    openUpload();
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      return false;
    }
  }

  function renderIntelBody(el) {
    const rows = loadRows();
    const { ranked, paretoCut, pareto } = paretoTagRanks(rows);
    const maxScore = ranked[0]?.score || 1;
    const recent = rows.slice(-12).reverse();
    const topHtml = ranked
      .slice(0, 15)
      .map((r, i) => {
        const pct = Math.round((r.score / maxScore) * 100);
        const isPareto = i < paretoCut;
        return `<div class="pareto-row${isPareto ? " top" : ""}">
          <span style="width:18px;color:#666">${i + 1}</span>
          <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(r.tag)}</span>
          <div class="bar" style="width:${Math.max(8, pct * 0.9)}px"></div>
          <span style="width:64px;text-align:right;font-variant-numeric:tabular-nums">${Math.round(r.score)}${r.metric === "vpd" ? "/d" : ""}</span>
        </div>`;
      })
      .join("");
    const feedHtml = recent
      .map(
        (r) =>
          `<div class="feed-item"><strong>${escapeHtml((r.title || r.album_id || "").slice(0, 40))}</strong>
          · ${r.views ?? "?"} views · ${(r.tags || []).slice(0, 3).map(escapeHtml).join(", ")}</div>`
      )
      .join("");
    el.innerHTML = `
      <div class="stat">
        <span class="chip">rows ${rows.length}</span>
        <span class="chip">tags ${ranked.length}</span>
        <span class="chip">Pareto top ${pareto.length}/${ranked.length || 0}</span>
      </div>
      <div class="muted">Pareto (≈ top 20% by median views/day). Rises as you browse with likes/intel on.</div>
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
      sendToThisVid(item.url);
      status.className = "status";
      status.textContent = "Opening ThisVid upload…";
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

  function ensureJumpStack(visible) {
    let stack = document.getElementById(JUMP_ID);
    if (!stack) {
      stack = document.createElement("div");
      stack.id = JUMP_ID;
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
    stack.style.display = visible ? "flex" : "none";
  }

  function ensureOverlay() {
    ensureStyles();
    let fab = document.getElementById(FAB_ID);
    if (!fab) {
      fab = document.createElement("button");
      fab.id = FAB_ID;
      fab.type = "button";
      fab.title = "TBCC Erome transport — intel + videos + Playwright";
      fab.textContent = "◈";
      document.documentElement.appendChild(fab);
    }
    let root = document.getElementById(ROOT_ID);
    if (!root) {
      root = document.createElement("div");
      root.id = ROOT_ID;
      root.innerHTML = `
        <div class="hdr"><h3>TBCC transport</h3><button type="button" id="tbccEtClose" style="background:none;border:none;color:#888;cursor:pointer;font-size:18px">×</button></div>
        <div class="tabs">
          <button type="button" class="tab active" data-tab="intel">Live intel</button>
          <button type="button" class="tab" data-tab="videos">Videos</button>
          <button type="button" class="tab" data-tab="record">Playwright</button>
        </div>
        <div class="body" id="tbccEtBody"></div>
      `;
      document.documentElement.appendChild(root);
      root.querySelector("#tbccEtClose")?.addEventListener("click", () => setOpen(false));
      root.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
          root.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
          tab.classList.add("active");
          showTab(tab.getAttribute("data-tab"));
        });
      });
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
    fab.onclick = () => {
      const opening = !root.classList.contains("open");
      if (opening && location.pathname.startsWith("/a/")) {
        activeTab = "videos";
        root.querySelectorAll(".tab").forEach((t) => {
          t.classList.toggle("active", t.getAttribute("data-tab") === "videos");
        });
      }
      setOpen(opening);
    };
    return { fab, root };
  }

  let activeTab = "intel";
  let pollTimer = null;

  function showTab(name) {
    activeTab = name || "intel";
    const body = document.getElementById("tbccEtBody");
    if (!body) return;
    if (activeTab === "record") renderRecordBody(body);
    else if (activeTab === "videos") renderVideosBody(body);
    else renderIntelBody(body);
  }

  function setVisible(enabled, openPanel) {
    const { fab, root } = ensureOverlay();
    const on = !!enabled;
    fab.style.display = on ? "flex" : "none";
    ensureJumpStack(on);
    const open = on && !!openPanel;
    root.classList.toggle("open", open);
    fab.classList.toggle("open", open);
    const meta = loadMeta();
    meta.showTransportOverlay = on;
    saveMeta(meta);
    if (open) {
      showTab(activeTab);
      if (!pollTimer) {
        pollTimer = setInterval(() => {
          if (!root.classList.contains("open")) return;
          if (activeTab === "intel") renderIntelBody(document.getElementById("tbccEtBody"));
          if (activeTab === "videos") renderVideosBody(document.getElementById("tbccEtBody"));
        }, 1500);
      }
    } else if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
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
    const root = document.getElementById(ROOT_ID);
    if (!root || !root.classList.contains("open")) return;
    if (activeTab === "intel") renderIntelBody(document.getElementById("tbccEtBody"));
    if (activeTab === "videos") renderVideosBody(document.getElementById("tbccEtBody"));
  }

  function boot() {
    const meta = loadMeta();
    ensureOverlay();
    setVisible(!!meta.showTransportOverlay, false);
    window.addEventListener("tbcc-erome-intel-row", refreshIfOpen);
    window.addEventListener("tbcc-erome-album-videos", () => {
      if (activeTab === "videos") refreshIfOpen();
    });
    window.addEventListener("tbcc-erome-transport-toggle", (ev) => {
      const on = !!(ev && ev.detail && ev.detail.open);
      setVisible(on, on);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
