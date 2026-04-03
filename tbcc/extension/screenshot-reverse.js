/* global chrome */

const statusEl = document.getElementById("status");
const preview = document.getElementById("preview");

function setStatus(msg, isErr) {
  statusEl.textContent = msg || "";
  statusEl.className = isErr ? "err" : "";
}

async function loadUploadPages() {
  const r = await fetch(chrome.runtime.getURL("screenshot-upload-pages.json"));
  if (!r.ok) throw new Error("screenshot-upload-pages.json");
  return r.json();
}

function openUploadTabs() {
  return loadUploadPages().then((j) => {
    const pages = j.pages || [];
    let first = true;
    for (const p of pages) {
      chrome.tabs.create({ url: p.url, active: first });
      first = false;
    }
  });
}

(async () => {
  const p = new URLSearchParams(window.location.search);
  const k = (p.get("k") || "").trim();
  if (!k) {
    setStatus("Missing key. Use the extension popup or context menu to capture.", true);
    return;
  }

  const data = await new Promise((resolve) => {
    chrome.storage.local.get(k, resolve);
  });
  const dataUrl = data[k];
  try {
    chrome.storage.local.remove(k);
  } catch (_) {}

  if (!dataUrl || typeof dataUrl !== "string" || !dataUrl.startsWith("data:image/")) {
    setStatus("Screenshot expired or missing. Capture again from the popup or context menu.", true);
    return;
  }

  preview.src = dataUrl;
  preview.hidden = false;

  document.getElementById("btnCopy").addEventListener("click", async () => {
    try {
      const res = await fetch(dataUrl);
      const blob = await res.blob();
      const type = blob.type || "image/png";
      await navigator.clipboard.write([new ClipboardItem({ [type]: blob })]);
      setStatus("Copied. Paste (Ctrl+V) in each search tab.");
    } catch (e) {
      setStatus(String(e.message || e), true);
    }
  });

  document.getElementById("btnOpenTabs").addEventListener("click", () => {
    setStatus("Opening tabs…");
    openUploadTabs()
      .then(() => setStatus("Opened — use Copy image, then paste in each tab."))
      .catch((e) => setStatus(String(e.message || e), true));
  });
})();
