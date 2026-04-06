/* global chrome */
/**
 * In-panel views (collected / quick tools / options) via top nav links.
 * Click the same link again to return to the main gallery (underlying page visible beside the sidebar).
 * Dashboard opens in a new browser tab (http://127.0.0.1:5173/).
 */
(function () {
  const DASHBOARD_TAB_URL = "http://127.0.0.1:5173/";

  const linkGalleryView = document.getElementById("linkGalleryView");
  const linkPopupTools = document.getElementById("linkPopupTools");
  const linkExtensionOptions = document.getElementById("linkExtensionOptions");
  const linkDashboard = document.getElementById("linkDashboard");

  let panelView = "main";

  const extOrigin = (function () {
    try {
      return new URL(chrome.runtime.getURL("/")).origin;
    } catch (_) {
      return "";
    }
  })();

  function updateFooterActive() {
    [linkGalleryView, linkPopupTools, linkExtensionOptions].forEach((a) => {
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

  function setPanelView(next) {
    if (next !== "main" && panelView === next) {
      next = "main";
    }
    panelView = next;
    ["main", "collected", "tools", "options"].forEach((v) => {
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
    updateFooterActive();
  }

  window.tbccSetPanelView = setPanelView;

  window.addEventListener("message", (ev) => {
    if (!ev.data || ev.data.type !== "tbcc-panel-view") return;
    if (extOrigin && ev.origin !== extOrigin) return;
    const v = ev.data.view;
    if (v === "dashboard") {
      chrome.tabs.create({ url: DASHBOARD_TAB_URL });
      return;
    }
    if (v === "main" || v === "collected" || v === "tools" || v === "options") {
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
      chrome.tabs.create({ url: DASHBOARD_TAB_URL });
    });

  const linkLaunchFull = document.getElementById("linkLaunchFull");
  linkLaunchFull &&
    linkLaunchFull.addEventListener("click", (e) => {
      e.preventDefault();
      if (typeof window.tbccLaunchFullStack === "function") {
        window.tbccLaunchFullStack();
      }
    });

  updateFooterActive();
})();
