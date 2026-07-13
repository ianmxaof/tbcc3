/* global chrome */
/**
 * In-panel views (collected / quick tools / options) via top nav tab buttons.
 * Click the same tab again to return to the main gallery.
 * Dashboard opens in a new browser tab (http://127.0.0.1:5173/).
 */
(function () {
  const DASHBOARD_TAB_URL = "http://127.0.0.1:5173/";

  const btnBackToGalleryPanel = document.getElementById("btnBackToGalleryPanel");
  const linkPanelMain = document.getElementById("linkPanelMain");
  const linkGalleryView = document.getElementById("linkGalleryView");
  const linkModelLookup = document.getElementById("linkModelLookup");
  const linkPopupTools = document.getElementById("linkPopupTools");
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
    [linkPanelMain, linkGalleryView, linkModelLookup, linkPopupTools].forEach((a) => {
      if (!a) return;
      const v = a.getAttribute("data-panel");
      const on = v === panelView;
      a.classList.toggle("active", on);
      a.setAttribute("aria-selected", on ? "true" : "false");
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
    ["main", "collected", "lookup", "tools", "options"].forEach((v) => {
      const el = document.getElementById("view-" + v);
      if (el) el.hidden = v !== panelView;
    });
    if (panelView === "collected") {
      ensureIframe("iframe-collected", chrome.runtime.getURL("gallery-view.html"));
    }
    if (panelView === "lookup") {
      ensureIframe("iframe-lookup", chrome.runtime.getURL("model-search-panel.html"));
    }
    if (panelView === "tools") {
      ensureIframe("iframe-tools", chrome.runtime.getURL("popup.html"));
    }
    if (panelView === "options") {
      ensureIframe("iframe-options", chrome.runtime.getURL("model-search-options.html?embed=1"));
    }
    updateFooterActive();
  }

  function scrollOptionsIframe(targetId) {
    if (!targetId) return;
    const iframe = document.getElementById("iframe-options");
    if (!iframe || !iframe.contentWindow) return;
    const send = () => {
      try {
        iframe.contentWindow.postMessage({ type: "tbcc-options-scroll", id: targetId }, "*");
      } catch (_) {}
    };
    if (iframe.getAttribute("src")) {
      send();
      window.setTimeout(send, 400);
    }
  }

  window.tbccSetPanelView = setPanelView;

  window.addEventListener("message", (ev) => {
    if (!ev.data || typeof ev.data.type !== "string") return;
    if (extOrigin && ev.origin !== extOrigin) return;
    if (ev.data.type === "tbcc-collected-send-saved") {
      if (typeof window.tbccBeginCollectedStageInDest === "function") {
        void window.tbccBeginCollectedStageInDest(ev.data.items || [], { destMode: "saved" });
      } else if (typeof window.tbccBeginCollectedSendToSaved === "function") {
        void window.tbccBeginCollectedSendToSaved(ev.data.items || []);
      }
      return;
    }
    if (ev.data.type === "tbcc-collected-stage-dest") {
      if (typeof window.tbccBeginCollectedStageInDest === "function") {
        void window.tbccBeginCollectedStageInDest(ev.data.items || [], {
          destMode: ev.data.destMode || "saved",
          tagsCsv: ev.data.tagsCsv || "",
          caption: ev.data.caption || "",
          poolId: ev.data.poolId,
          autoSend: !!ev.data.autoSend,
        });
      }
      return;
    }
    if (ev.data.type === "tbcc-open-gallery-popout") {
      try {
        chrome.windows.create(
          {
            url: chrome.runtime.getURL("gallery.html"),
            type: "popup",
            width: 560,
            height: 920,
            focused: true,
          },
          () => {
            const err = chrome.runtime.lastError;
            if (err) console.warn("TBCC pop-out:", err.message);
          }
        );
      } catch (e) {
        console.warn("TBCC pop-out:", e);
      }
      return;
    }
    if (ev.data.type !== "tbcc-panel-view") return;
    const v = ev.data.view;
    if (v === "dashboard") {
      chrome.tabs.create({ url: DASHBOARD_TAB_URL });
      return;
    }
    if (v === "main" || v === "collected" || v === "lookup" || v === "tools" || v === "options") {
      setPanelView(v);
      if (v === "options" && ev.data.scrollTo) {
        window.setTimeout(() => scrollOptionsIframe(String(ev.data.scrollTo)), 80);
      }
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
  linkModelLookup &&
    linkModelLookup.addEventListener("click", (e) => {
      e.preventDefault();
      setPanelView("lookup");
    });
  linkPopupTools &&
    linkPopupTools.addEventListener("click", (e) => {
      e.preventDefault();
      setPanelView("tools");
    });
  linkDashboard &&
    linkDashboard.addEventListener("click", (e) => {
      e.preventDefault();
      chrome.tabs.create({ url: DASHBOARD_TAB_URL });
    });
  updateFooterActive();

  /* Always open the sidebar on the main gallery so media scan + grid are visible; sub-views are one click away. */
})();
