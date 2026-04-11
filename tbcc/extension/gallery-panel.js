/* global chrome */
/**
 * In-panel views (collected / quick tools / options) via top nav links.
 * Click the same link again to return to the main gallery (underlying page visible beside the sidebar).
 * Dashboard opens in a new browser tab (http://127.0.0.1:5173/).
 */
(function () {
  const DASHBOARD_TAB_URL = "http://127.0.0.1:5173/";

  const btnBackToGalleryPanel = document.getElementById("btnBackToGalleryPanel");
  const linkPanelMain = document.getElementById("linkPanelMain");
  const linkGalleryView = document.getElementById("linkGalleryView");
  const linkPopupTools = document.getElementById("linkPopupTools");

  let panelView = "main";

  const extOrigin = (function () {
    try {
      return new URL(chrome.runtime.getURL("/")).origin;
    } catch (_) {
      return "";
    }
  })();

  function updateFooterActive() {
    [linkPanelMain, linkGalleryView, linkPopupTools].forEach((a) => {
      if (!a) return;
      const v = a.getAttribute("data-panel");
      a.classList.toggle("active", v === panelView);
    });
    if (linkPanelMain) linkPanelMain.classList.toggle("nav-exit", panelView !== "main");
    if (btnBackToGalleryPanel) btnBackToGalleryPanel.hidden = panelView === "main";
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
    try {
      chrome.storage.local.set({ tbccGalleryPanelView: panelView });
    } catch (_) {}
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

  linkPanelMain &&
    linkPanelMain.addEventListener("click", (e) => {
      e.preventDefault();
      setPanelView("main");
    });
  btnBackToGalleryPanel &&
    btnBackToGalleryPanel.addEventListener("click", () => {
      setPanelView("main");
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
  updateFooterActive();

  /* Always open the sidebar on the main gallery so media scan + grid are visible; sub-views are one click away. */
})();
