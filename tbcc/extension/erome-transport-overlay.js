/**
 * Erome transport overlay — Playwright record launcher + live browse-intel (Pareto tops).
 * Shares localStorage with erome-enhancer.js (eromeBrowseIntelRows / Meta).
 */
(function () {
  "use strict";

  const INTEL_KEY = "eromeBrowseIntelRows";
  const INTEL_META_KEY = "eromeBrowseIntelMeta";
  const ROOT_ID = "tbcc-erome-transport-root";
  const FAB_ID = "tbcc-erome-transport-fab";

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
#${ROOT_ID}{position:fixed;z-index:2147483646;right:16px;bottom:148px;width:min(380px,calc(100vw - 24px));
max-height:min(70vh,560px);display:none;flex-direction:column;background:#1b1f24;color:#e8e8e8;
border:1px solid #3a4450;border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.55);overflow:hidden;
font:13px/1.4 system-ui,Segoe UI,sans-serif}
#${ROOT_ID}.open{display:flex}
#${ROOT_ID} .hdr{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:#12161a;border-bottom:1px solid #333}
#${ROOT_ID} .hdr h3{margin:0;font-size:13px;font-weight:700;color:#7ec8e3;letter-spacing:.02em}
#${ROOT_ID} .tabs{display:flex;gap:0;border-bottom:1px solid #333}
#${ROOT_ID} .tab{flex:1;padding:8px;background:#161a1f;border:none;color:#999;cursor:pointer;font-weight:600;font-size:12px}
#${ROOT_ID} .tab.active{color:#fff;background:#243039;border-bottom:2px solid #7ec8e3}
#${ROOT_ID} .body{padding:10px 12px;overflow:auto;flex:1}
#${ROOT_ID} .btn{display:inline-flex;align-items:center;gap:6px;padding:8px 12px;border-radius:8px;border:1px solid #456;
background:#2a4a5a;color:#dff;cursor:pointer;font-weight:600;font-size:12px;width:100%;justify-content:center;margin:4px 0}
#${ROOT_ID} .btn:hover{filter:brightness(1.1)}
#${ROOT_ID} .btn.primary{background:#eb6395;border-color:#eb6395;color:#fff}
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

  function renderIntelBody(el) {
    const rows = loadRows();
    const { ranked, paretoCut, pareto } = paretoTagRanks(rows);
    const maxScore = ranked[0]?.score || 1;
    const recent = rows.slice(-12).reverse();
    const topHtml = ranked.slice(0, 15)
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
    el.querySelector("#tbccPwRecordBtn")?.addEventListener("click", () =>
      start(location.href, "erome-live")
    );
    el.querySelector("#tbccPwRecordEromeBtn")?.addEventListener("click", () =>
      start("https://www.erome.com/", "erome-session")
    );
  }

  function ensureOverlay() {
    ensureStyles();
    let fab = document.getElementById(FAB_ID);
    if (!fab) {
      fab = document.createElement("button");
      fab.id = FAB_ID;
      fab.type = "button";
      fab.title = "TBCC Erome transport — intel + Playwright";
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
    }
    fab.onclick = () => setOpen(!root.classList.contains("open"));
    return { fab, root };
  }

  let activeTab = "intel";
  let pollTimer = null;

  function showTab(name) {
    activeTab = name || "intel";
    const body = document.getElementById("tbccEtBody");
    if (!body) return;
    if (activeTab === "record") renderRecordBody(body);
    else renderIntelBody(body);
  }

  function setVisible(enabled, openPanel) {
    const { fab, root } = ensureOverlay();
    const on = !!enabled;
    fab.style.display = on ? "flex" : "none";
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
          if (activeTab === "intel" && root.classList.contains("open")) {
            renderIntelBody(document.getElementById("tbccEtBody"));
          }
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
    // FAB click: keep feature enabled; only toggle the panel.
    setVisible(true, open);
  }

  function refreshIfOpen() {
    const root = document.getElementById(ROOT_ID);
    if (root && root.classList.contains("open") && activeTab === "intel") {
      renderIntelBody(document.getElementById("tbccEtBody"));
    }
  }

  function boot() {
    const meta = loadMeta();
    ensureOverlay();
    // Settings toggle enables FAB; panel starts closed unless previously open.
    setVisible(!!meta.showTransportOverlay, false);
    window.addEventListener("tbcc-erome-intel-row", refreshIfOpen);
    window.addEventListener("tbcc-erome-transport-toggle", (ev) => {
      const on = !!(ev && ev.detail && ev.detail.open);
      setVisible(on, on);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
