/* global chrome */
/**
 * TBCC local launch from the extension: daemon on :8765 first, API fallback when API is up.
 */
(function (global) {
  const DAEMON_BASE = "http://127.0.0.1:8765";
  const DAEMON_LAUNCH_FULL = DAEMON_BASE + "/launch-full";
  const DAEMON_LAUNCH_SUPERVISOR = DAEMON_BASE + "/launch-supervisor";
  const API_LAUNCH_FULL = "http://127.0.0.1:8000/internal/launch-full-stack";
  const API_LAUNCH_SUPERVISOR = "http://127.0.0.1:8000/internal/launch-supervisor";
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

  async function postDaemon(path) {
    const r = await fetch(DAEMON_BASE + path, { method: "POST", mode: "cors" });
    const j = await r.json().catch(() => ({}));
    return { response: r, data: j };
  }

  async function postApi(path, needKey) {
    const headers = {};
    const key = await getInternalKey();
    if (needKey && key) headers["X-TBCC-Internal-Key"] = key;
    const r = await fetch("http://127.0.0.1:8000" + path, { method: "POST", mode: "cors", headers });
    const j = await r.json().catch(() => ({}));
    return { response: r, data: j };
  }

  async function launchFullStack() {
    try {
      const { response: d, data: dj } = await postDaemon("/launch-full");
      if (d.status === 429) {
        notify(String(dj.detail || dj.error || "Wait a few seconds between launches."));
        return { ok: false, via: "daemon", data: dj };
      }
      if (d.ok) {
        notify(dj.detail ? String(dj.detail) : "Full stack launch started (local daemon).");
        return { ok: true, via: "daemon", data: dj };
      }
    } catch (_) {}

    try {
      const { response: r, data: j } = await postApi("/internal/launch-full-stack", true);
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

  async function launchSupervisor() {
    try {
      const { response: d, data: dj } = await postDaemon("/launch-supervisor");
      if (d.status === 429) {
        notify(String(dj.detail || dj.error || "Wait a few seconds between launches."));
        return { ok: false, via: "daemon", data: dj };
      }
      if (d.ok) {
        const msg = dj.already_running
          ? "Tray supervisor is already running (notification area)."
          : dj.detail
            ? String(dj.detail)
            : "Tray supervisor started. Right-click the TBCC icon near the clock.";
        notify(msg);
        return { ok: true, via: "daemon", data: dj };
      }
    } catch (_) {}

    try {
      const { response: r, data: j } = await postApi("/internal/launch-supervisor", true);
      if (r.ok) {
        const msg = j.already_running
          ? "Tray supervisor is already running."
          : "Tray supervisor started (API). Check the notification area.";
        notify(msg);
        return { ok: true, via: "api", data: j };
      }
      const detail = (j && (j.detail || j.error)) || r.statusText;
      notify(
        "Supervisor launch failed: " +
          detail +
          ". Start tbcc\\tools\\tbcc-launch-daemon.ps1 first, or set TBCC internal key in Extension options."
      );
      return { ok: false, error: detail, data: j };
    } catch (e) {
      notify(
        "No daemon on :8765. Run: cd tbcc\\tools && .\\tbcc-launch-daemon.ps1 — then retry, or use API fallback with internal key."
      );
      return { ok: false, error: String(e.message || e) };
    }
  }

  global.tbccLaunchFullStack = launchFullStack;
  global.tbccLaunchSupervisor = launchSupervisor;
})(typeof window !== "undefined" ? window : self);
