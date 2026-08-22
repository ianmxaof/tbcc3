/**
 * Static (non-dynamic) chrome.contextMenus descriptors — single source of truth shared by
 * background.js (registers them) and context-menu-editor.html (lets the user reorder/toggle
 * them via STORAGE_CONTEXT_MENU_CONFIG, applied through tbcc-context-menu-plan.js).
 * Dynamic submenus (AOF pools, Storage Hub topics, model-search sites) are generated from
 * live data at registration time and always render after this list; they're not part of
 * the editor's reorder surface. menuFamily groups items for the editor UI only —
 * chrome.contextMenus.create() doesn't take it (stripped by buildMenuPlan).
 */
(function (root) {
  const TBCC_STATIC_MENU_ITEMS = [
    { id: "sendToTBCC", title: "TBCC: Save to pool (default)", contexts: ["image", "video", "link"], menuFamily: "media" },
    { id: "saveAofWatch", title: "TBCC: Save AOF (watermark + watch)", contexts: ["image", "video", "link"], menuFamily: "media" },
    { id: "uploadR2Library", title: "TBCC: Watermark → R2 aof-media (library)", contexts: ["image", "video", "link"], menuFamily: "media" },
    { id: "uploadR2SfwXPromo", title: "TBCC: Watermark → R2 SFW X promo", contexts: ["image", "video", "link"], menuFamily: "media" },
    { id: "sendToSaved", title: "TBCC: Saved Messages", contexts: ["image", "video", "link"], menuFamily: "media" },
    { id: "sendPageToTBCC", title: "TBCC: Save to pool (this tab URL)", contexts: ["page", "frame"], menuFamily: "media" },
    { id: "sendPageToSaved", title: "TBCC: Saved Messages (this tab URL)", contexts: ["page", "frame"], menuFamily: "media" },
    { id: "sendSelectionToTBCC", title: "TBCC: Save to pool (selected URL)", contexts: ["selection"], menuFamily: "media" },
    { id: "sendSelectionToSaved", title: "TBCC: Saved Messages (selected URL)", contexts: ["selection"], menuFamily: "media" },
    {
      id: "tbccCaptureSecretSelection",
      title: "TBCC: Save selection as API key to .env (browser)",
      contexts: ["selection"],
      menuFamily: "media",
    },
    {
      id: "tbccLoadApiSlotSelection",
      title: "TBCC: Load API from clipboard",
      contexts: ["selection"],
      menuFamily: "media",
    },
    {
      id: "tbccAddVideoUrlToList",
      title: "TBCC: Save URL to master archive",
      contexts: ["selection", "link", "page", "frame", "video"],
      menuFamily: "media",
    },
    {
      id: "tbccAddAllVideoUrlsToList",
      title: "TBCC: Save all video URLs to master archive",
      contexts: ["page", "frame", "video", "link"],
      menuFamily: "media",
    },
    { id: "tbccReverseImageFanout", title: "TBCC: Reverse image search", contexts: ["image"], menuFamily: "media" },
    { id: "tbccCaptureTabReverse", title: "TBCC: Capture tab for reverse search", contexts: ["page", "frame"], menuFamily: "media" },
    {
      id: "tbccMotherlessGalleryZip",
      title: "TBCC: Motherless gallery → ZIP",
      contexts: ["page", "frame", "link"],
      menuFamily: "media",
      documentUrlPatterns: [
        "*://motherless.com/*",
        "*://*.motherless.com/*",
        "*://motherless.xxx/*",
        "*://*.motherless.xxx/*",
      ],
    },
    {
      id: "tbccMotherlessGalleryDownload",
      title: "TBCC: Motherless gallery → download files",
      contexts: ["page", "frame", "link"],
      menuFamily: "media",
      documentUrlPatterns: [
        "*://motherless.com/*",
        "*://*.motherless.com/*",
        "*://motherless.xxx/*",
        "*://*.motherless.xxx/*",
      ],
    },
    { id: "tbccDockGallery", title: "TBCC: Dock gallery to this tab", contexts: ["page", "frame"], menuFamily: "media" },
    { id: "tbccActionOpenGallery", title: "TBCC: Open gallery", contexts: ["action"], menuFamily: "action" },
    { id: "tbccActionDockGallery", title: "TBCC: Open gallery (docked to this tab)", contexts: ["action"], menuFamily: "action" },
    { id: "tbccActionStartApi", title: "TBCC: Launch full stack (daemon/API)", contexts: ["action"], menuFamily: "action" },
  ];

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { TBCC_STATIC_MENU_ITEMS };
  } else {
    root.TBCC_STATIC_MENU_ITEMS = TBCC_STATIC_MENU_ITEMS;
  }
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
