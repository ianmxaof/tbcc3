/* global chrome */
/**
 * Run tbcc/start.ps1 -Full from the extension: local daemon (:8765) first, then API fallback.
 */
(function (global) {
  const DAEMON_URL = "http://127.0.0.1:8765/launch-full";
  const API_URL = "http://127.0.0.1:8000/internal/launch-full-stack";
  const STORAGE_KEY = "tbccInternalApiKey";

  function notify(message) {
    try {
      chrome.notifications.create({
        type: "basic",
        iconUrl: chrome.runtime.getURL("icons/icon16.png"),
        title: "TBCC",
        message: String(message).slice(0, 250),
      });
    } catch (_) {}
  }

  function getInternalKey() {
    return new Promise((resolve) => {
      chrome.storage.local.get([STORAGE_KEY], (x) => {
        resolve((x[STORAGE_KEY] || "").trim());
      });
    });
  }

  async function launchFullStack() {
    try {
      const d = await fetch(DAEMON_URL, { method: "POST", mode: "cors" });
      const dj = await d.json().catch(() => ({}));
      if (d.status === 429) {
        notify(String(dj.detail || dj.error || "Wait a few seconds between launches."));
        return { ok: false, via: "daemon", data: dj };
      }
      if (d.ok) {
        notify(dj.detail ? String(dj.detail) : "Full stack launch started (local daemon).");
        return { ok: true, via: "daemon", data: dj };
      }
    } catch (_) {}

    const headers = {};
    const key = await getInternalKey();
    if (key) headers["X-TBCC-Internal-Key"] = key;

    try {
      const r = await fetch(API_URL, { method: "POST", mode: "cors", headers });
      const j = await r.json().catch(() => ({}));
      if (r.ok) {
        notify("Full stack launch started (API).");
        return { ok: true, via: "api", data: j };
      }
      const detail = (j && (j.detail || j.error)) || r.statusText;
      notify(
        "Launch failed: " +
          detail +
          ". Run tbcc\\tools\\tbcc-launch-daemon.ps1, or set TBCC internal key in Extension options."
      );
      return { ok: false, error: detail, data: j };
    } catch (e) {
      notify(
        "No daemon :8765 or API :8000. Run: cd tbcc\\tools && .\\tbcc-launch-daemon.ps1 — or start the API and optional key in options."
      );
      return { ok: false, error: String(e.message || e) };
    }
  }

  global.tbccLaunchFullStack = launchFullStack;
})(typeof window !== "undefined" ? window : self);
