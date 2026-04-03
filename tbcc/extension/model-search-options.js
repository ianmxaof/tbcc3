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

const statusEl = document.getElementById("status");
const siteFields = document.getElementById("siteFields");
const reverseSiteFields = document.getElementById("reverseSiteFields");

function setStatus(msg, isErr) {
  statusEl.textContent = msg || "";
  statusEl.className = isErr ? "err" : "";
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
  return new Promise((resolve) => {
    chrome.storage.local.set({ [STORAGE_MODEL_SEARCH_CUSTOM_SITES]: arr }, resolve);
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

function renderBuiltinSites(cfg, enabledMap) {
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
    leg.textContent = cat + " (built-in)";
    fs.appendChild(leg);
    for (const s of byCat[cat]) {
      const id = `site_${s.id}`;
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
    siteFields.appendChild(fs);
  }
}

function renderCustomSites(customSites, enabledMap) {
  if (!customSites.length) return;
  const fs = document.createElement("fieldset");
  const leg = document.createElement("legend");
  leg.textContent = "Your added sources";
  fs.appendChild(leg);
  for (const s of customSites) {
    const row = document.createElement("div");
    row.className = "row";
    row.style.cssText = "align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid #313244;";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.dataset.siteId = s.id;
    cb.checked = enabledMap[s.id] !== false;
    const mid = document.createElement("div");
    mid.style.flex = "1";
    mid.style.minWidth = "0";
    const title = document.createElement("div");
    title.textContent = s.name || s.id;
    title.style.fontWeight = "500";
    const urlLine = document.createElement("div");
    urlLine.style.cssText = "font-size:11px;color:#6c7086;word-break:break-all;margin-top:2px;";
    urlLine.textContent = s.url || "";
    mid.appendChild(title);
    mid.appendChild(urlLine);
    const del = document.createElement("button");
    del.type = "button";
    del.textContent = "Remove";
    del.dataset.deleteSiteId = s.id;
    del.style.cssText =
      "padding:4px 10px;border:1px solid #45475a;border-radius:4px;background:#313244;color:#f38ba8;cursor:pointer;font-size:11px;flex-shrink:0;";
    del.addEventListener("click", async () => {
      const data = await new Promise((resolve) => {
        chrome.storage.local.get([STORAGE_MODEL_SEARCH_CUSTOM_SITES, STORAGE_ENABLED], resolve);
      });
      const arr = Array.isArray(data[STORAGE_MODEL_SEARCH_CUSTOM_SITES])
        ? data[STORAGE_MODEL_SEARCH_CUSTOM_SITES]
        : [];
      const next = arr.filter((x) => x.id !== s.id);
      const em = { ...(data[STORAGE_ENABLED] || {}) };
      delete em[s.id];
      await saveCustomSites(next);
      await saveEnabled(em);
      setStatus("Removed.");
      await refreshModelSearchUi();
      setTimeout(() => setStatus(""), 1600);
    });
    row.appendChild(cb);
    row.appendChild(mid);
    row.appendChild(del);
    fs.appendChild(row);
  }
  siteFields.appendChild(fs);
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
  renderBuiltinSites(cfg, enabledMap);
  renderCustomSites(custom, enabledMap);
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
      const category = (catEl && catEl.value.trim()) || "custom";
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
      await saveCustomSites(arr);
      const em = collectEnabledFromInputs();
      em[id] = true;
      await saveEnabled(em);
      if (nameEl) nameEl.value = "";
      if (urlEl) urlEl.value = "";
      if (catEl) catEl.value = "";
      setStatus("Source added.");
      await refreshModelSearchUi();
      setTimeout(() => setStatus(""), 1600);
    });
  }

  const data = await new Promise((resolve) => {
    chrome.storage.local.get([STORAGE_MODE], resolve);
  });
  const mode = data[STORAGE_MODE] || "dashboard";
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
})();

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

  const mode = data[STORAGE_REVERSE_MODE] || "dashboard";
  document.querySelectorAll('input[name="openModeReverse"]').forEach((r) => {
    r.checked = r.value === mode;
    r.addEventListener("change", async () => {
      if (r.checked) {
        await saveReverseMode(r.value);
        setStatus("Saved.");
        setTimeout(() => setStatus(""), 1600);
      }
    });
  });
})();
