/* global chrome */
(function () {
  const STORAGE_KEY = "tbccThemePreset";
  const VALID = new Set(["dark", "chatgpt", "github", "obsidian", "cursor"]);

  function normalizeTheme(value) {
    const v = String(value || "").trim().toLowerCase();
    return VALID.has(v) ? v : "dark";
  }

  function applyTheme(value) {
    const theme = normalizeTheme(value);
    document.documentElement.setAttribute("data-tbcc-theme", theme);
  }

  try {
    chrome.storage.local.get([STORAGE_KEY], (data) => {
      applyTheme(data ? data[STORAGE_KEY] : null);
    });
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local" || !changes[STORAGE_KEY]) return;
      applyTheme(changes[STORAGE_KEY].newValue);
    });
  } catch (_) {
    applyTheme("dark");
  }
})();
