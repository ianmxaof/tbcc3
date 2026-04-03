/* global chrome */
/**
 * In-panel views (collected / quick tools / options / dashboard) with footer toggles.
 * Click the same footer link again to return to the main gallery (underlying page visible beside the sidebar).
 */
(function () {
  /** Use IPv4 literal — "localhost" in the side panel often resolves to ::1 while Vite listens on 127.0.0.1 only, causing ERR_CONNECTION_REFUSED. */
  const DASHBOARD_IFRAME_URL = "http://127.0.0.1:5173/";

  const linkGalleryView = document.getElementById("linkGalleryView");
  const linkPopupTools = document.getElementById("linkPopupTools");
  const linkExtensionOptions = document.getElementById("linkExtensionOptions");
  const linkDashboard = document.getElementById("linkDashboard");
  const linkDashboardOpenTab = document.getElementById("linkDashboardOpenTab");

  let panelView = "main";

  const extOrigin = (function () {
    try {
      return new URL(chrome.runtime.getURL("/")).origin;
    } catch (_) {
      return "";
    }
  })();

  function updateFooterActive() {
    [linkGalleryView, linkPopupTools, linkExtensionOptions, linkDashboard].forEach((a) => {
      if (!a) return;
      const v = a.getAttribute("data-panel");
      a.classList.toggle("active", v === panelView);
    });
  }

  function ensureIframe(iframeId, url) {
    const el = document.getElementById(iframeId);
    if (el && !el.getAttribute("src")) {
      el.setAttribute("src", url);
    }
  }

  /** Dashboard iframe must reload each time: first load may fail if Vite is not up yet (ensureIframe alone never retries). */
  function loadDashboardIframe() {
    const el = document.getElementById("iframe-dashboard");
    if (!el) return;
    const u = new URL(DASHBOARD_IFRAME_URL);
    u.searchParams.set("_tbcc", String(Date.now()));
    el.setAttribute("src", u.href);
  }

  function setPanelView(next) {
    if (next !== "main" && panelView === next) {
      next = "main";
    }
    panelView = next;
    ["main", "collected", "tools", "options", "dashboard"].forEach((v) => {
      const el = document.getElementById("view-" + v);
      if (el) el.hidden = v !== panelView;
    });
    if (panelView === "collected") {
      ensureIframe("iframe-collected", chrome.runtime.getURL("gallery-view.html"));
    }
    if (panelView === "tools") {
      ensureIframe("iframe-tools", chrome.runtime.getURL("popup.html"));
    }
    if (panelView === "options") {
      ensureIframe("iframe-options", chrome.runtime.getURL("model-search-options.html?embed=1"));
    }
    if (panelView === "dashboard") {
      loadDashboardIframe();
    }
    updateFooterActive();
  }

  window.tbccSetPanelView = setPanelView;

  window.addEventListener("message", (ev) => {
    if (!ev.data || ev.data.type !== "tbcc-panel-view") return;
    if (extOrigin && ev.origin !== extOrigin) return;
    const v = ev.data.view;
    if (v === "main" || v === "collected" || v === "tools" || v === "options" || v === "dashboard") {
      setPanelView(v);
    }
  });

  linkGalleryView &&
    linkGalleryView.addEventListener("click", (e) => {
      e.preventDefault();
      setPanelView("collected");
    });
  linkPopupTools &&
    linkPopupTools.addEventListener("click", (e) => {
      e.preventDefault();
      setPanelView("tools");
    });
  linkExtensionOptions &&
    linkExtensionOptions.addEventListener("click", (e) => {
      e.preventDefault();
      setPanelView("options");
    });
  linkDashboard &&
    linkDashboard.addEventListener("click", (e) => {
      e.preventDefault();
      setPanelView("dashboard");
    });
  linkDashboardOpenTab &&
    linkDashboardOpenTab.addEventListener("click", (e) => {
      e.preventDefault();
      chrome.tabs.create({ url: DASHBOARD_IFRAME_URL });
    });

  updateFooterActive();
})();
