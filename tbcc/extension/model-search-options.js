/* global chrome */
/* MV3 CSP blocks inline scripts — embed layout flag must live in this file. */
(function () {
  try {
    if (new URLSearchParams(location.search).get("embed") === "1") {
      document.documentElement.classList.add("tbcc-options-embed");
    }
  } catch (_) {}
})();

const STORAGE_ENABLED = "tbccModelSearchEnabledSites";
const STORAGE_MODE = "tbccModelSearchOpenMode";
const STORAGE_REVERSE_ENABLED = "tbccReverseImageEnabledSites";
const STORAGE_REVERSE_MODE = "tbccReverseImageOpenMode";
const STORAGE_MODEL_SEARCH_HISTORY = "tbccModelSearchHistory";
const STORAGE_CUSTOM_ADAPTERS = "tbccCustomGalleryAdapters";
const STORAGE_THEME = "tbccThemePreset";
const STORAGE_PAYMENT_BOT_USERNAME = "tbccPaymentBotUsername";
/** Keep in sync with STORAGE_SAVED_VIDEO_URLS in background.js */
const STORAGE_SAVED_VIDEO_URLS = "tbccSavedVideoUrls";
const SAVED_VIDEO_URLS_CAP = 600;

/** Legacy "dashboard" single-tab aggregator removed — map to foreground tabs. */
function normalizeOpenMode(stored) {
  if (stored === "background") return "background";
  return "foreground";
}

const statusEl = document.getElementById("status");
const siteFields = document.getElementById("siteFields");
const reverseSiteFields = document.getElementById("reverseSiteFields");
const themePresetSelect = document.getElementById("tbccThemePreset");
const historyEl = document.getElementById("modelSearchHistory");
const btnClearHistory = document.getElementById("btnClearModelSearchHistory");
const adapterRulesListEl = document.getElementById("adapterRulesList");
const btnAnalyzeAdapter = document.getElementById("btnAnalyzeAdapter");
const adapterAnalyzeResultEl = document.getElementById("adapterAnalyzeResult");
const adapterDomainEl = document.getElementById("adapterDomain");
const adapterModeEl = document.getElementById("adapterMode");
const adapterFromEl = document.getElementById("adapterFrom");
const adapterToEl = document.getElementById("adapterTo");
const btnAddAdapterRule = document.getElementById("btnAddAdapterRule");

function setStatus(msg, isErr) {
  statusEl.textContent = msg || "";
  statusEl.className = isErr ? "err" : "";
}

function formatHistoryTime(ts) {
  if (!ts || !Number.isFinite(ts)) return "";
  try {
    return new Date(ts).toLocaleString();
  } catch (_) {
    return "";
  }
}

async function renderModelSearchHistory() {
  if (!historyEl) return;
  const data = await new Promise((resolve) => {
    chrome.storage.local.get([STORAGE_MODEL_SEARCH_HISTORY], resolve);
  });
  const rows = Array.isArray(data[STORAGE_MODEL_SEARCH_HISTORY]) ? data[STORAGE_MODEL_SEARCH_HISTORY] : [];
  if (!rows.length) {
    historyEl.textContent = "No usernames searched yet.";
    return;
  }
  historyEl.innerHTML = "";
  rows.forEach((r) => {
    const username = String(r && r.username ? r.username : "").trim();
    if (!username) return;
    const ts = Number(r && r.ts ? r.ts : 0);
    const line = document.createElement("div");
    line.className = "tbcc-history-row";
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "tbcc-history-remove";
    rm.setAttribute("aria-label", "Remove this entry");
    rm.textContent = "×";
    rm.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const latest = await new Promise((resolve) => {
        chrome.storage.local.get([STORAGE_MODEL_SEARCH_HISTORY], resolve);
      });
      const arr = Array.isArray(latest[STORAGE_MODEL_SEARCH_HISTORY]) ? latest[STORAGE_MODEL_SEARCH_HISTORY] : [];
      const filtered = arr.filter(
        (x) =>
          !(
            String(x && x.username ? x.username : "").trim() === username &&
            Number(x && x.ts ? x.ts : 0) === ts
          )
      );
      await new Promise((resolve) =>
        chrome.storage.local.set({ [STORAGE_MODEL_SEARCH_HISTORY]: filtered }, resolve)
      );
      setStatus("History entry removed.");
      await renderModelSearchHistory();
      setTimeout(() => setStatus(""), 1400);
    });
    const mid = document.createElement("div");
    mid.className = "tbcc-history-main";
    const left = document.createElement("code");
    left.textContent = username;
    const right = document.createElement("span");
    right.className = "cat";
    right.textContent = formatHistoryTime(Number(r && r.ts ? r.ts : 0));
    mid.appendChild(left);
    mid.appendChild(right);
    line.appendChild(rm);
    line.appendChild(mid);
    historyEl.appendChild(line);
  });
}

async function getSavedVideoUrlRows() {
  const data = await new Promise((resolve) => chrome.storage.local.get([STORAGE_SAVED_VIDEO_URLS], resolve));
  return Array.isArray(data[STORAGE_SAVED_VIDEO_URLS]) ? data[STORAGE_SAVED_VIDEO_URLS] : [];
}

async function setSavedVideoUrlRows(rows) {
  await new Promise((resolve) =>
    chrome.storage.local.set({ [STORAGE_SAVED_VIDEO_URLS]: rows }, resolve)
  );
}

async function renderSavedVideoUrlsList() {
  const el = document.getElementById("savedVideoUrlsList");
  if (!el) return;
  const rows = await getSavedVideoUrlRows();
  if (!rows.length) {
    el.textContent = "No URLs saved yet.";
    return;
  }
  el.innerHTML = "";
  rows.forEach((row) => {
    const u = String(row && row.url ? row.url : "").trim();
    if (!u) return;
    const ts = Number(row && row.addedAt ? row.addedAt : 0);
    const line = document.createElement("div");
    line.className = "tbcc-history-row";
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "tbcc-history-remove";
    rm.setAttribute("aria-label", "Remove this URL");
    rm.textContent = "×";
    rm.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const latest = await getSavedVideoUrlRows();
      const filtered = latest.filter(
        (x) =>
          !(
            String(x && x.url ? x.url : "").trim() === u &&
            Number(x && x.addedAt ? x.addedAt : 0) === ts
          )
      );
      await setSavedVideoUrlRows(filtered);
      setStatus("Removed from list.");
      await renderSavedVideoUrlsList();
      setTimeout(() => setStatus(""), 1400);
    });
    const mid = document.createElement("div");
    mid.className = "tbcc-history-main";
    const link = document.createElement("a");
    link.href = u;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = u;
    link.style.wordBreak = "break-all";
    link.style.color = "var(--tbcc-accent, #8ab4f8)";
    const right = document.createElement("span");
    right.className = "cat";
    right.textContent = formatHistoryTime(ts);
    mid.appendChild(link);
    mid.appendChild(right);
    line.appendChild(rm);
    line.appendChild(mid);
    el.appendChild(line);
  });
}

function normalizeRuleDomain(raw) {
  const s = String(raw || "").trim().toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, "");
  return s.split("/")[0];
}

async function getAdapterRules() {
  const data = await new Promise((resolve) => chrome.storage.local.get([STORAGE_CUSTOM_ADAPTERS], resolve));
  return Array.isArray(data[STORAGE_CUSTOM_ADAPTERS]) ? data[STORAGE_CUSTOM_ADAPTERS] : [];
}

async function saveAdapterRules(rules) {
  await new Promise((resolve) => chrome.storage.local.set({ [STORAGE_CUSTOM_ADAPTERS]: rules }, resolve));
}

async function renderAdapterRules() {
  if (!adapterRulesListEl) return;
  const rules = await getAdapterRules();
  if (!rules.length) {
    adapterRulesListEl.innerHTML = '<p class="sub" style="margin:0">No adapter rules yet.</p>';
    return;
  }
  adapterRulesListEl.innerHTML = "";
  rules.forEach((r) => {
    if (!r) return;
    const row = document.createElement("div");
    row.className = "tbcc-details-row tbcc-adapter-rule-row";

    const cbId = `adapter_rule_${r.id}`;
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.id = cbId;
    cb.checked = r.enabled !== false;
    cb.addEventListener("change", async () => {
      const next = await getAdapterRules();
      const idx = next.findIndex((x) => x && x.id === r.id);
      if (idx >= 0) {
        next[idx].enabled = !!cb.checked;
        await saveAdapterRules(next);
        setStatus("Saved.");
        setTimeout(() => setStatus(""), 1200);
      }
    });

    const body = document.createElement("label");
    body.className = "tbcc-details-row-body";
    body.setAttribute("for", cbId);

    const main = document.createElement("div");
    main.className = "tbcc-details-main";
    const title = document.createElement("div");
    title.className = "tbcc-details-title";
    title.innerHTML = `<code>${escapeHtml(r.domain || "")}</code> <span class="cat">${escapeHtml(
      r.mode || "literal"
    )}</span>`;
    const detail = document.createElement("div");
    detail.className = "tbcc-details-sub";
    const detailText = `${r.replaceFrom || ""} → ${r.replaceTo || ""}`;
    detail.title = detailText;
    detail.textContent = detailText.length > 64 ? `${detailText.slice(0, 62)}…` : detailText;
    main.appendChild(title);
    main.appendChild(detail);
    body.appendChild(main);

    const actions = document.createElement("div");
    actions.className = "tbcc-details-actions";
    const del = document.createElement("button");
    del.type = "button";
    del.className = "tbcc-details-remove";
    del.textContent = "Remove";
    del.addEventListener("click", async () => {
      const next = (await getAdapterRules()).filter((x) => x && x.id !== r.id);
      await saveAdapterRules(next);
      await renderAdapterRules();
      setStatus("Rule removed.");
      setTimeout(() => setStatus(""), 1200);
    });
    actions.appendChild(del);

    row.appendChild(cb);
    row.appendChild(body);
    row.appendChild(actions);
    adapterRulesListEl.appendChild(row);
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function analyzeCurrentTabForAdapter() {
  if (!adapterAnalyzeResultEl) return;
  adapterAnalyzeResultEl.textContent = "Analyzing current tab…";
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) {
    adapterAnalyzeResultEl.textContent = "No active tab found.";
    return;
  }
  let resp;
  try {
    resp = await chrome.tabs.sendMessage(tab.id, { action: "tbcc-analyze-gallery-adapter" });
  } catch (_) {
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id, allFrames: true }, files: ["capture.js"] });
      resp = await chrome.tabs.sendMessage(tab.id, { action: "tbcc-analyze-gallery-adapter" });
    } catch (e2) {
      adapterAnalyzeResultEl.textContent = "Could not analyze this tab. Reload the page and try again.";
      return;
    }
  }
  const analysis = resp && resp.analysis ? resp.analysis : null;
  if (!analysis) {
    adapterAnalyzeResultEl.textContent = "No adapter signals found.";
    return;
  }
  const host = normalizeRuleDomain(analysis.host || "");
  const suggestions = Array.isArray(analysis.suggestions) ? analysis.suggestions : [];
  if (!suggestions.length) {
    adapterAnalyzeResultEl.textContent = `Scanned ${analysis.sampleCount || 0} URLs on ${host || "this host"}; no clear rewrite pattern found.`;
    return;
  }
  const best = suggestions[0];
  if (adapterDomainEl && !adapterDomainEl.value) adapterDomainEl.value = host;
  if (adapterModeEl) adapterModeEl.value = best.mode || "literal";
  if (adapterFromEl) adapterFromEl.value = best.replaceFrom || "";
  if (adapterToEl) adapterToEl.value = best.replaceTo || "";
  adapterAnalyzeResultEl.textContent = `Suggested: ${best.label || "rule"} (${analysis.sampleCount || 0} URLs sampled). Review fields below, then click "Add adapter rule".`;
}

async function loadBuiltinModelSearchConfig() {
  const url = chrome.runtime.getURL("model-search-sites.json");
  const r = await fetch(url);
  if (!r.ok) throw new Error("Could not load model-search-sites.json");
  return r.json();
}

function saveEnabled(map) {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [STORAGE_ENABLED]: map }, resolve);
  });
}

function saveMode(mode) {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [STORAGE_MODE]: mode }, resolve);
  });
}

function saveCustomSites(arr) {
  return new Promise((resolve, reject) => {
    chrome.storage.local.set({ [STORAGE_MODEL_SEARCH_CUSTOM_SITES]: arr }, () => {
      const err = chrome.runtime.lastError;
      if (err) reject(new Error(err.message || String(err)));
      else resolve();
    });
  });
}

function collectEnabledFromInputs() {
  const map = {};
  siteFields.querySelectorAll('input[type="checkbox"][data-site-id]').forEach((x) => {
    map[x.dataset.siteId] = x.checked;
  });
  return map;
}

function wireCheckboxListeners() {
  siteFields.querySelectorAll('input[type="checkbox"][data-site-id]').forEach((cb) => {
    cb.addEventListener("change", async () => {
      await saveEnabled(collectEnabledFromInputs());
      setStatus("Saved.");
      setTimeout(() => setStatus(""), 1600);
    });
  });
}

function createModelSearchSourceRow(site, enabledMap, isBuiltin) {
  const row = document.createElement("div");
  row.className = "tbcc-details-row tbcc-source-row";
  const u = (site.url || "").trim();
  if (u) row.title = u;

  const cbId = `site_${site.id}`;
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.id = cbId;
  cb.dataset.siteId = site.id;
  cb.checked = enabledMap[site.id] !== false;
  if (u) cb.title = u;

  const body = document.createElement("label");
  body.className = "tbcc-details-row-body";
  body.setAttribute("for", cbId);
  if (u) body.title = u;

  const main = document.createElement("div");
  main.className = "tbcc-details-main";
  const nameLine = document.createElement("div");
  nameLine.className = "tbcc-details-title";
  nameLine.textContent = site.name || site.id;
  if (u) nameLine.title = u;
  main.appendChild(nameLine);

  const idSpan = document.createElement("span");
  idSpan.className = "cat tbcc-details-id";
  idSpan.textContent = site.id;

  body.appendChild(main);
  body.appendChild(idSpan);

  const actions = document.createElement("div");
  actions.className = "tbcc-details-actions";
  if (!isBuiltin) {
    const del = document.createElement("button");
    del.type = "button";
    del.className = "tbcc-details-remove";
    del.textContent = "Remove";
    del.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const data = await new Promise((resolve) => {
        chrome.storage.local.get([STORAGE_MODEL_SEARCH_CUSTOM_SITES, STORAGE_ENABLED], resolve);
      });
      const arr = Array.isArray(data[STORAGE_MODEL_SEARCH_CUSTOM_SITES])
        ? data[STORAGE_MODEL_SEARCH_CUSTOM_SITES]
        : [];
      const next = arr.filter((x) => x.id !== site.id);
      const em = { ...(data[STORAGE_ENABLED] || {}) };
      delete em[site.id];
      await saveCustomSites(next);
      await saveEnabled(em);
      setStatus("Removed.");
      await refreshModelSearchUi();
      setTimeout(() => setStatus(""), 1600);
    });
    actions.appendChild(del);
  }

  row.appendChild(cb);
  row.appendChild(body);
  row.appendChild(actions);
  return row;
}

/** Two sections only: OnlyFans search + Live cam search. Bundled JSON + user URLs merged per category. */
function renderMergedModelSearchSources(cfg, customSites, enabledMap) {
  const builtinByCat = {
    [MODEL_SEARCH_CATEGORY_ONLYFANS]: [],
    [MODEL_SEARCH_CATEGORY_LIVECAMS]: [],
    [MODEL_SEARCH_CATEGORY_VIDEOS]: [],
    [MODEL_SEARCH_CATEGORY_MACRO]: [],
  };
  for (const s of cfg.sites || []) {
    const c = normalizeModelSearchCategory(s.category);
    if (builtinByCat[c]) builtinByCat[c].push(s);
  }
  const customByCat = {
    [MODEL_SEARCH_CATEGORY_ONLYFANS]: [],
    [MODEL_SEARCH_CATEGORY_LIVECAMS]: [],
    [MODEL_SEARCH_CATEGORY_VIDEOS]: [],
    [MODEL_SEARCH_CATEGORY_MACRO]: [],
  };
  for (const s of customSites) {
    customByCat[normalizeModelSearchCategory(s.category)].push(s);
  }

  for (const cat of [
    MODEL_SEARCH_CATEGORY_MACRO,
    MODEL_SEARCH_CATEGORY_ONLYFANS,
    MODEL_SEARCH_CATEGORY_LIVECAMS,
    MODEL_SEARCH_CATEGORY_VIDEOS,
  ]) {
    const fs = document.createElement("fieldset");
    const leg = document.createElement("legend");
    leg.textContent = modelSearchCategoryLabel(cat);
    fs.appendChild(leg);

    const bundled = builtinByCat[cat] || [];
    const custom = customByCat[cat] || [];
    const merged = [
      ...bundled.map((s) => ({ site: s, isBuiltin: true })),
      ...custom.map((s) => ({ site: s, isBuiltin: false })),
    ];

    if (!merged.length) {
      const empty = document.createElement("p");
      empty.className = "sub";
      empty.style.margin = "0";
      empty.textContent = "No sources in this category yet.";
      fs.appendChild(empty);
    } else {
      for (const { site, isBuiltin } of merged) {
        fs.appendChild(createModelSearchSourceRow(site, enabledMap, isBuiltin));
      }
    }
    siteFields.appendChild(fs);
  }
}

function validateCustomUrl(url) {
  const u = (url || "").trim();
  if (!/^https?:\/\//i.test(u)) return "URL must start with http:// or https://";
  if (!u.includes("{username}")) return "URL must include {username} where the search term goes.";
  try {
    const probe = u.split("{username}").join("probe");
    new URL(probe);
  } catch (_) {
    return "Invalid URL.";
  }
  return null;
}

async function refreshModelSearchUi() {
  let cfg;
  try {
    cfg = await loadBuiltinModelSearchConfig();
  } catch (e) {
    setStatus(String(e.message || e), true);
    return;
  }
  const data = await new Promise((resolve) => {
    chrome.storage.local.get(
      [STORAGE_ENABLED, STORAGE_MODE, STORAGE_MODEL_SEARCH_CUSTOM_SITES],
      resolve
    );
  });
  let enabledMap = data[STORAGE_ENABLED];
  if (!enabledMap || typeof enabledMap !== "object") {
    enabledMap = {};
    for (const s of cfg.sites || []) {
      enabledMap[s.id] = true;
    }
  }
  const custom = Array.isArray(data[STORAGE_MODEL_SEARCH_CUSTOM_SITES])
    ? data[STORAGE_MODEL_SEARCH_CUSTOM_SITES]
    : [];
  for (const s of custom) {
    if (enabledMap[s.id] === undefined) enabledMap[s.id] = true;
  }
  await saveEnabled(enabledMap);

  siteFields.innerHTML = "";
  renderMergedModelSearchSources(cfg, custom, enabledMap);
  wireCheckboxListeners();
}

(async () => {
  try {
    await refreshModelSearchUi();
  } catch (e) {
    setStatus(String(e.message || e), true);
    return;
  }

  const btnAdd = document.getElementById("btnAddCustomSite");
  if (btnAdd) {
    btnAdd.addEventListener("click", async () => {
      const nameEl = document.getElementById("customSiteName");
      const urlEl = document.getElementById("customSiteUrl");
      const catEl = document.getElementById("customSiteCat");
      const name = (nameEl && nameEl.value.trim()) || "";
      const url = (urlEl && urlEl.value.trim()) || "";
      const category = normalizeModelSearchCategory((catEl && catEl.value.trim()) || MODEL_SEARCH_CATEGORY_ONLYFANS);
      const err = validateCustomUrl(url);
      if (!name) {
        setStatus("Enter a display name.", true);
        return;
      }
      if (err) {
        setStatus(err, true);
        return;
      }
      const id = "custom_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
      const site = { id, name, url, category };
      const data = await new Promise((resolve) => {
        chrome.storage.local.get(STORAGE_MODEL_SEARCH_CUSTOM_SITES, resolve);
      });
      const arr = Array.isArray(data[STORAGE_MODEL_SEARCH_CUSTOM_SITES])
        ? data[STORAGE_MODEL_SEARCH_CUSTOM_SITES]
        : [];
      arr.push(site);
      try {
        await saveCustomSites(arr);
      } catch (e) {
        setStatus(String(e.message || e), true);
        return;
      }
      const em = collectEnabledFromInputs();
      em[id] = true;
      await saveEnabled(em);
      if (nameEl) nameEl.value = "";
      if (urlEl) urlEl.value = "";
      setStatus("Source added.");
      await refreshModelSearchUi();
      setTimeout(() => setStatus(""), 1600);
    });
  }

  const data = await new Promise((resolve) => {
    chrome.storage.local.get([STORAGE_MODE], resolve);
  });
  const mode = normalizeOpenMode(data[STORAGE_MODE]);
  if (data[STORAGE_MODE] !== mode) await saveMode(mode);
  document.querySelectorAll('input[name="openMode"]').forEach((r) => {
    r.checked = r.value === mode;
    r.addEventListener("change", async () => {
      if (r.checked) {
        await saveMode(r.value);
        setStatus("Saved.");
        setTimeout(() => setStatus(""), 1600);
      }
    });
  });
  await renderModelSearchHistory();
  await renderSavedVideoUrlsList();
})();

(function () {
  const el = document.getElementById("tbccPaymentBotUsername");
  if (!el) return;
  chrome.storage.local.get([STORAGE_PAYMENT_BOT_USERNAME], (data) => {
    el.value = data?.[STORAGE_PAYMENT_BOT_USERNAME] || "";
  });
  el.addEventListener("blur", () => {
    const next = String(el.value || "").trim().replace(/^@+/, "");
    chrome.storage.local.set({ [STORAGE_PAYMENT_BOT_USERNAME]: next }, () => {
      setStatus("Saved.");
      setTimeout(() => setStatus(""), 1600);
    });
  });
})();

if (btnClearHistory) {
  btnClearHistory.addEventListener("click", async () => {
    await new Promise((resolve) => chrome.storage.local.set({ [STORAGE_MODEL_SEARCH_HISTORY]: [] }, resolve));
    await renderModelSearchHistory();
    setStatus("Username history cleared.");
    setTimeout(() => setStatus(""), 1600);
  });
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local" || !changes[STORAGE_SAVED_VIDEO_URLS]) return;
  void renderSavedVideoUrlsList();
});

const btnSavedVideoAddManual = document.getElementById("btnSavedVideoAddManual");
const btnSavedVideoCopyAll = document.getElementById("btnSavedVideoCopyAll");
const btnSavedVideoClear = document.getElementById("btnSavedVideoClear");
if (btnSavedVideoAddManual) {
  btnSavedVideoAddManual.addEventListener("click", async () => {
    const inp = document.getElementById("savedVideoManualUrl");
    const raw = String(inp && inp.value ? inp.value : "").trim();
    if (!raw || !/^https?:\/\//i.test(raw)) {
      setStatus("Enter a valid http(s) URL.", true);
      return;
    }
    if (raw.startsWith("blob:") || raw.startsWith("data:")) {
      setStatus("Blob/data URLs cannot be stored.", true);
      return;
    }
    const rows = await getSavedVideoUrlRows();
    if (rows.some((x) => String(x && x.url ? x.url : "").trim() === raw)) {
      setStatus("That URL is already in the list.");
      return;
    }
    await setSavedVideoUrlRows([{ url: raw, addedAt: Date.now() }, ...rows].slice(0, SAVED_VIDEO_URLS_CAP));
    if (window.TbccMasterArchive) void TbccMasterArchive.recordUrl(raw, { source: "options_inbox" });
    if (inp) inp.value = "";
    setStatus("URL added.");
    await renderSavedVideoUrlsList();
    setTimeout(() => setStatus(""), 1600);
  });
}
if (btnSavedVideoCopyAll) {
  btnSavedVideoCopyAll.addEventListener("click", async () => {
    const rows = await getSavedVideoUrlRows();
    const lines = rows.map((x) => String(x && x.url ? x.url : "").trim()).filter(Boolean);
    const text = lines.join("\n");
    if (!text) {
      setStatus("Nothing to copy.", true);
      return;
    }
    try {
      const clip = globalThis.TbccClipboard;
      if (clip && clip.copyText) {
        await clip.copyText(text, { anchor: btnSavedVideoCopyAll || undefined });
        setStatus(`Copied ${lines.length} URL(s).`);
      } else {
        await navigator.clipboard.writeText(text);
        setStatus(`Copied ${lines.length} URL(s) to clipboard.`);
      }
    } catch (_) {
      setStatus("Clipboard permission denied — copy from the list manually.", true);
    }
    setTimeout(() => setStatus(""), 2200);
  });
}
if (btnSavedVideoClear) {
  btnSavedVideoClear.addEventListener("click", async () => {
    await setSavedVideoUrlRows([]);
    setStatus("Saved video list cleared (master archive unchanged).");
    await renderSavedVideoUrlsList();
    setTimeout(() => setStatus(""), 1600);
  });
}

const masterArchiveListOpts = document.getElementById("masterArchiveListOpts");
const masterArchiveStatusOpts = document.getElementById("masterArchiveStatusOpts");
const masterArchivePagerOpts = document.getElementById("masterArchivePagerOpts");
const masterArchiveFilterOpts = document.getElementById("masterArchiveFilterOpts");
const masterArchiveKindOpts = document.getElementById("masterArchiveKindOpts");

const masterArchiveOptsUi =
  window.TbccArchiveListUi && window.TbccMasterArchive && masterArchiveListOpts
    ? window.TbccArchiveListUi.createArchiveListController({
        listEl: masterArchiveListOpts,
        statusEl: masterArchiveStatusOpts,
        pagerEl: masterArchivePagerOpts,
        mode: "readonly",
        getEntries: () => TbccMasterArchive.getEntries(),
        getFilters: () => ({
          q: (masterArchiveFilterOpts && masterArchiveFilterOpts.value) || "",
          kind: (masterArchiveKindOpts && masterArchiveKindOpts.value) || "",
          ...(window.TbccMasterArchive && TbccMasterArchive.readSortOptsFromDom
            ? TbccMasterArchive.readSortOptsFromDom("Opts")
            : {}),
        }),
      })
    : null;

async function renderMasterArchiveOpts() {
  if (masterArchiveOptsUi) {
    await masterArchiveOptsUi.refresh();
    return;
  }
  if (masterArchiveStatusOpts) masterArchiveStatusOpts.textContent = "Archive UI not loaded.";
}

masterArchiveFilterOpts &&
  masterArchiveFilterOpts.addEventListener("input", () => {
    if (masterArchiveOptsUi) masterArchiveOptsUi.resetPage();
    void renderMasterArchiveOpts();
  });
masterArchiveKindOpts &&
  masterArchiveKindOpts.addEventListener("change", () => {
    if (masterArchiveOptsUi) masterArchiveOptsUi.resetPage();
    void renderMasterArchiveOpts();
  });
function onMasterArchiveOptsSortChange() {
  if (masterArchiveOptsUi) masterArchiveOptsUi.resetPage();
  void renderMasterArchiveOpts();
}
["masterArchiveSort1Opts", "masterArchiveSort1DirOpts", "masterArchiveSort2Opts", "masterArchiveSort2DirOpts"].forEach(
  (id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", onMasterArchiveOptsSortChange);
  }
);
const btnMasterOptsSelectAll = document.getElementById("btnMasterOptsSelectAll");
const btnMasterOptsDeselectAll = document.getElementById("btnMasterOptsDeselectAll");
const btnMasterOptsCopyUrls = document.getElementById("btnMasterOptsCopyUrls");
btnMasterOptsSelectAll &&
  btnMasterOptsSelectAll.addEventListener("click", () => masterArchiveOptsUi && masterArchiveOptsUi.selectAllOnPage());
btnMasterOptsDeselectAll &&
  btnMasterOptsDeselectAll.addEventListener("click", () => masterArchiveOptsUi && masterArchiveOptsUi.deselectAllOnPage());
btnMasterOptsCopyUrls &&
  btnMasterOptsCopyUrls.addEventListener("click", async () => {
    if (!masterArchiveOptsUi) return;
    const r = await masterArchiveOptsUi.copyCheckedUrlsOnPage();
    if (masterArchiveStatusOpts) {
      masterArchiveStatusOpts.textContent = r.ok
        ? `Copied ${r.count} URL(s) from this page.`
        : r.error || "Copy failed.";
    }
    if (r.ok) {
      const clip = globalThis.TbccClipboard;
      if (clip && clip.showCopied) clip.showCopied();
    }
  });
const btnMasterOptsExportJson = document.getElementById("btnMasterOptsExportJson");
const btnMasterOptsExportCsv = document.getElementById("btnMasterOptsExportCsv");
const btnMasterOptsImport = document.getElementById("btnMasterOptsImport");
const masterArchiveImportFileOpts = document.getElementById("masterArchiveImportFileOpts");
async function getMasterArchiveOptsFiltered() {
  const all = await TbccMasterArchive.getEntries();
  return TbccMasterArchive.filterEntries(all, {
    q: (masterArchiveFilterOpts && masterArchiveFilterOpts.value) || "",
    kind: (masterArchiveKindOpts && masterArchiveKindOpts.value) || "",
    ...(TbccMasterArchive.readSortOptsFromDom ? TbccMasterArchive.readSortOptsFromDom("Opts") : {}),
  });
}
btnMasterOptsExportJson &&
  btnMasterOptsExportJson.addEventListener("click", async () => {
    const entries = await getMasterArchiveOptsFiltered();
    TbccMasterArchive.downloadText(
      `tbcc-master-${new Date().toISOString().slice(0, 10)}.json`,
      TbccMasterArchive.exportJson(entries),
      "application/json"
    );
  });
btnMasterOptsExportCsv &&
  btnMasterOptsExportCsv.addEventListener("click", async () => {
    const entries = await getMasterArchiveOptsFiltered();
    TbccMasterArchive.downloadText(
      `tbcc-master-${new Date().toISOString().slice(0, 10)}.csv`,
      TbccMasterArchive.exportCsv(entries),
      "text/csv"
    );
  });
btnMasterOptsImport &&
  btnMasterOptsImport.addEventListener("click", () => {
    if (masterArchiveImportFileOpts) masterArchiveImportFileOpts.click();
  });
masterArchiveImportFileOpts &&
  masterArchiveImportFileOpts.addEventListener("change", async () => {
    const file = masterArchiveImportFileOpts.files && masterArchiveImportFileOpts.files[0];
    masterArchiveImportFileOpts.value = "";
    if (!file) return;
    const parsed = TbccMasterArchive.parseImportText(await file.text());
    const r = await TbccMasterArchive.importEntries(parsed, true);
    const statusEl = document.getElementById("masterArchiveStatusOpts");
    if (statusEl) statusEl.textContent = r.ok ? `Imported ${r.added} new entries.` : r.error || "Failed.";
    await renderMasterArchiveOpts();
  });
if (window.TbccMasterArchive) {
  void TbccMasterArchive.restoreFromBackupIfEmpty().then(() => renderMasterArchiveOpts());
}

if (btnAnalyzeAdapter) {
  btnAnalyzeAdapter.addEventListener("click", () => {
    void analyzeCurrentTabForAdapter();
  });
}

if (btnAddAdapterRule) {
  btnAddAdapterRule.addEventListener("click", async () => {
    const domain = normalizeRuleDomain(adapterDomainEl && adapterDomainEl.value);
    const mode = String((adapterModeEl && adapterModeEl.value) || "literal").toLowerCase() === "regex" ? "regex" : "literal";
    const replaceFrom = String((adapterFromEl && adapterFromEl.value) || "").trim();
    const replaceTo = String((adapterToEl && adapterToEl.value) || "");
    if (!domain) {
      setStatus("Adapter rule needs a domain.", true);
      return;
    }
    if (!replaceFrom) {
      setStatus("Adapter rule needs a 'replace from' pattern.", true);
      return;
    }
    if (mode === "regex") {
      try {
        new RegExp(replaceFrom, "i");
      } catch (_) {
        setStatus("Invalid regex pattern.", true);
        return;
      }
    }
    const rules = await getAdapterRules();
    const next = [
      {
        id: "rule_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8),
        domain,
        mode,
        replaceFrom,
        replaceTo,
        enabled: true,
        createdAt: Date.now(),
      },
      ...rules,
    ].slice(0, 300);
    await saveAdapterRules(next);
    await renderAdapterRules();
    if (adapterAnalyzeResultEl) adapterAnalyzeResultEl.textContent = "";
    if (adapterFromEl) adapterFromEl.value = "";
    if (adapterToEl) adapterToEl.value = "";
    setStatus("Adapter rule saved.");
    setTimeout(() => setStatus(""), 1600);
  });
}

async function loadReverseConfig() {
  const url = chrome.runtime.getURL("reverse-image-sites.json");
  const r = await fetch(url);
  if (!r.ok) throw new Error("Could not load reverse-image-sites.json");
  return r.json();
}

function saveReverseEnabled(map) {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [STORAGE_REVERSE_ENABLED]: map }, resolve);
  });
}

function saveReverseMode(mode) {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [STORAGE_REVERSE_MODE]: mode }, resolve);
  });
}

function renderReverseSites(cfg, enabledMap) {
  reverseSiteFields.innerHTML = "";
  const byCat = {};
  for (const s of cfg.sites || []) {
    const c = s.category || "other";
    if (!byCat[c]) byCat[c] = [];
    byCat[c].push(s);
  }
  const cats = Object.keys(byCat).sort();
  for (const cat of cats) {
    const fs = document.createElement("fieldset");
    const leg = document.createElement("legend");
    leg.textContent = cat;
    fs.appendChild(leg);
    for (const s of byCat[cat]) {
      const id = `rev_${s.id}`;
      const label = document.createElement("label");
      label.className = "row";
      label.setAttribute("for", id);
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.id = id;
      cb.dataset.siteId = s.id;
      cb.checked = enabledMap[s.id] !== false;
      const span = document.createElement("span");
      span.textContent = s.name || s.id;
      const small = document.createElement("span");
      small.className = "cat";
      small.textContent = s.id;
      label.appendChild(cb);
      label.appendChild(span);
      label.appendChild(small);
      fs.appendChild(label);
    }
    reverseSiteFields.appendChild(fs);
  }

  reverseSiteFields.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.addEventListener("change", async () => {
      const map = {};
      reverseSiteFields.querySelectorAll('input[type="checkbox"]').forEach((x) => {
        map[x.dataset.siteId] = x.checked;
      });
      await saveReverseEnabled(map);
      setStatus("Saved.");
      setTimeout(() => setStatus(""), 1600);
    });
  });
}

(async () => {
  let cfg;
  try {
    cfg = await loadReverseConfig();
  } catch (e) {
    if (reverseSiteFields) {
      reverseSiteFields.innerHTML =
        "<p class=\"err\" style=\"margin:0\">" + String(e.message || e) + "</p>";
    }
    return;
  }

  const data = await new Promise((resolve) => {
    chrome.storage.local.get([STORAGE_REVERSE_ENABLED, STORAGE_REVERSE_MODE], resolve);
  });
  let enabledMap = data[STORAGE_REVERSE_ENABLED];
  if (!enabledMap || typeof enabledMap !== "object") {
    enabledMap = {};
    for (const s of cfg.sites || []) {
      enabledMap[s.id] = true;
    }
    await saveReverseEnabled(enabledMap);
  }

  renderReverseSites(cfg, enabledMap);

  const revMode = normalizeOpenMode(data[STORAGE_REVERSE_MODE]);
  if (data[STORAGE_REVERSE_MODE] !== revMode) await saveReverseMode(revMode);
  document.querySelectorAll('input[name="openModeReverse"]').forEach((r) => {
    r.checked = r.value === revMode;
    r.addEventListener("change", async () => {
      if (r.checked) {
        await saveReverseMode(r.value);
        setStatus("Saved.");
        setTimeout(() => setStatus(""), 1600);
      }
    });
  });
})();

const STORAGE_TBCC_INTERNAL_KEY = "tbccInternalApiKey";
(function () {
  const el = document.getElementById("tbccInternalApiKey");
  if (!el) return;
  chrome.storage.local.get([STORAGE_TBCC_INTERNAL_KEY], (data) => {
    el.value = data[STORAGE_TBCC_INTERNAL_KEY] || "";
  });
  el.addEventListener("blur", () => {
    chrome.storage.local.set({ [STORAGE_TBCC_INTERNAL_KEY]: (el.value || "").trim() }, () => {
      setStatus("Saved.");
      setTimeout(() => setStatus(""), 1600);
    });
  });
})();

(function () {
  if (!themePresetSelect) return;
  const valid = new Set(["dark", "chatgpt", "github", "obsidian", "cursor"]);
  chrome.storage.local.get([STORAGE_THEME], (data) => {
    const current = String(data?.[STORAGE_THEME] || "dark").toLowerCase();
    themePresetSelect.value = valid.has(current) ? current : "dark";
  });
  themePresetSelect.addEventListener("change", () => {
    const next = String(themePresetSelect.value || "dark").toLowerCase();
    chrome.storage.local.set({ [STORAGE_THEME]: valid.has(next) ? next : "dark" }, () => {
      setStatus("Saved.");
      setTimeout(() => setStatus(""), 1600);
    });
  });
})();

void renderAdapterRules();

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes[STORAGE_MODEL_SEARCH_HISTORY]) {
    void renderModelSearchHistory();
  }
  if (changes[STORAGE_CUSTOM_ADAPTERS]) {
    void renderAdapterRules();
  }
});
