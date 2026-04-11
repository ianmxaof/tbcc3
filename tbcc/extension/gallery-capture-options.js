/* global chrome */
/** Sync gallery capture settings (same storage as gallery.js `tbcc_gallery_settings`). */
(function () {
  const STORAGE_SETTINGS = "tbcc_gallery_settings";
  const STORAGE_COLLECTED = "tbcc_collected";

  const elFormat = document.getElementById("captureSettingFormat");
  const elAuto = document.getElementById("captureSettingAutoRefresh");
  const elHard = document.getElementById("captureSettingHardRefresh");
  const elRt = document.getElementById("captureSettingResourceTiming");
  const elLazy = document.getElementById("captureSettingLazyDelay");
  const btnClear = document.getElementById("captureSettingClearCache");
  const apiStatus = document.getElementById("tbccApiStatus");

  function mergeSave(partial) {
    return new Promise((resolve) => {
      chrome.storage.local.get(STORAGE_SETTINGS, (o) => {
        const cur = (o[STORAGE_SETTINGS] && typeof o[STORAGE_SETTINGS] === "object") ? o[STORAGE_SETTINGS] : {};
        const next = { ...cur, ...partial };
        chrome.storage.local.set({ [STORAGE_SETTINGS]: next }, resolve);
      });
    });
  }

  async function load() {
    const o = await new Promise((r) => chrome.storage.local.get(STORAGE_SETTINGS, r));
    const s = o[STORAGE_SETTINGS] || {};
    if (elFormat) elFormat.value = s.format === "jpeg" ? "jpeg" : "original";
    if (elAuto) elAuto.checked = s.autoRefresh !== false;
    if (elHard) elHard.checked = s.refreshHard !== false;
    if (elRt) elRt.checked = s.resourceTimingAllImages === true;
    if (elLazy) {
      const d = parseInt(String(s.captureLazyDelayMs || 0), 10);
      elLazy.value = String(isNaN(d) ? 0 : Math.max(0, Math.min(3000, d)));
    }
  }

  if (elFormat)
    elFormat.addEventListener("change", () => mergeSave({ format: elFormat.value }));
  if (elAuto)
    elAuto.addEventListener("change", () => mergeSave({ autoRefresh: !!elAuto.checked }));
  if (elHard)
    elHard.addEventListener("change", () => mergeSave({ refreshHard: !!elHard.checked }));
  if (elRt)
    elRt.addEventListener("change", () => mergeSave({ resourceTimingAllImages: !!elRt.checked }));
  if (elLazy)
    elLazy.addEventListener("change", () => {
      let d = parseInt(elLazy.value, 10);
      if (isNaN(d)) d = 0;
      mergeSave({ captureLazyDelayMs: Math.max(0, Math.min(3000, d)) });
    });
  if (btnClear)
    btnClear.addEventListener("click", async () => {
      if (!confirm("Clear collected media cache in the gallery?")) return;
      await new Promise((r) => chrome.storage.local.remove(STORAGE_COLLECTED, r));
      btnClear.textContent = "Cleared";
      setTimeout(() => {
        btnClear.textContent = "Clear gallery cache";
      }, 2000);
    });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes[STORAGE_SETTINGS]) load();
  });

  async function pingApi() {
    if (!apiStatus) return;
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 4000);
    try {
      const r = await fetch("http://localhost:8000/health", { method: "GET", signal: ac.signal });
      clearTimeout(t);
      if (r.ok) {
        apiStatus.textContent = "● API reachable (localhost:8000)";
        apiStatus.style.color = "#a6e3a1";
      } else {
        apiStatus.textContent = "○ API returned " + r.status;
        apiStatus.style.color = "#fab387";
      }
    } catch (_) {
      clearTimeout(t);
      apiStatus.textContent = "○ API offline — start TBCC backend";
      apiStatus.style.color = "#6c7086";
    }
  }

  load();
  pingApi();
  setInterval(pingApi, 30000);
})();
