const API_BASE = "http://localhost:8000";

const inGalleryPanel = typeof window !== "undefined" && window.parent !== window;

async function loadPools() {
  const sel = document.getElementById("poolId");
  try {
    const res = await fetch(`${API_BASE}/pools`);
    const pools = await res.json();
    sel.innerHTML = "";
    if (!pools.length) {
      sel.innerHTML = '<option value="">No pools</option>';
      return;
    }
    for (const p of pools) {
      const opt = document.createElement("option");
      opt.value = String(p.id);
      opt.textContent = p.name || `Pool ${p.id}`;
      sel.appendChild(opt);
    }
    chrome.storage.local.get("tbccPoolId", (data) => {
      if (data.tbccPoolId && pools.some((x) => x.id === data.tbccPoolId)) {
        sel.value = String(data.tbccPoolId);
      } else if (pools.length) {
        sel.value = String(pools[0].id);
        chrome.storage.local.set({ tbccPoolId: pools[0].id });
      }
    });
  } catch (e) {
    sel.innerHTML = '<option value="">Backend offline</option>';
  }
}

function setBackendStatus(ok, text) {
  const dot = document.getElementById("backendDot");
  const el = document.getElementById("backendStatus");
  if (dot) {
    dot.classList.remove("ok", "bad");
    dot.classList.add(ok ? "ok" : "bad");
  }
  if (el) el.textContent = text;
}

async function pingBackend() {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), 4000);
  try {
    const r = await fetch(`${API_BASE}/health`, { signal: ac.signal });
    clearTimeout(t);
    if (r.ok) setBackendStatus(true, "Backend connected (localhost:8000)");
    else setBackendStatus(false, "Backend returned " + r.status);
  } catch (_) {
    clearTimeout(t);
    setBackendStatus(false, "Backend offline");
  }
}

document.getElementById("poolId").addEventListener("change", (e) => {
  const v = e.target.value;
  if (v) chrome.storage.local.set({ tbccPoolId: parseInt(v, 10) });
});

if (!inGalleryPanel) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]?.id) chrome.storage.local.set({ tbccGalleryTabId: tabs[0].id });
  });
}

document.getElementById("openGallery").addEventListener("click", (e) => {
  if (inGalleryPanel) {
    e.preventDefault();
    window.parent.postMessage({ type: "tbcc-panel-view", view: "main" }, "*");
    return;
  }
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tabId = tabs[0]?.id;
    if (tabId) chrome.storage.local.set({ tbccGalleryTabId: tabId });
    chrome.sidePanel.open({ windowId: chrome.windows.WINDOW_ID_CURRENT });
  });
});

document.getElementById("openExtensionOptions").addEventListener("click", (e) => {
  if (inGalleryPanel) {
    e.preventDefault();
    window.parent.postMessage({ type: "tbcc-panel-view", view: "options" }, "*");
    return;
  }
  chrome.runtime.openOptionsPage();
});

async function loadScreenshotUploadPages() {
  const r = await fetch(chrome.runtime.getURL("screenshot-upload-pages.json"));
  if (!r.ok) throw new Error("screenshot-upload-pages.json");
  return r.json();
}

async function openReverseUploadTabs() {
  const j = await loadScreenshotUploadPages();
  const pages = j.pages || [];
  let first = true;
  for (const p of pages) {
    await chrome.tabs.create({ url: p.url, active: first });
    first = false;
  }
}

document.getElementById("btnCaptureReverse").addEventListener("click", async () => {
  const st = document.getElementById("captureStatus");
  st.textContent = "";
  st.className = "";
  let dataUrl;
  try {
    dataUrl = await chrome.tabs.captureVisibleTab(null, { format: "png" });
  } catch (e) {
    st.className = "err";
    st.textContent =
      "Could not capture (restricted pages like chrome:// won't work). " + String(e.message || e);
    return;
  }
  try {
    const res = await fetch(dataUrl);
    const blob = await res.blob();
    const type = blob.type || "image/png";
    await navigator.clipboard.write([new ClipboardItem({ [type]: blob })]);
  } catch (e) {
    st.className = "err";
    st.textContent = "Could not copy to clipboard: " + String(e.message || e);
    return;
  }
  try {
    await openReverseUploadTabs();
  } catch (e) {
    st.className = "err";
    st.textContent = "Copied, but could not open tabs: " + String(e.message || e);
    return;
  }
  st.textContent = "Copied — paste (Ctrl+V) in each new tab.";
});

if (inGalleryPanel) {
  document.body.classList.add("tbcc-in-panel");
  const og = document.getElementById("openGallery");
  if (og) og.textContent = "Back to gallery";
}

const liteCb = document.getElementById("tbccLiteMode");
if (liteCb) {
  chrome.storage.local.get("tbccLiteMode", (o) => {
    liteCb.checked = !!o.tbccLiteMode;
  });
  liteCb.addEventListener("change", () => {
    chrome.storage.local.set({ tbccLiteMode: !!liteCb.checked });
  });
}

loadPools();
pingBackend();
setInterval(pingBackend, 20000);
