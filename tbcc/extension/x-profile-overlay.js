/**

 * TBCC X profile gallery overlay — Comic Looms-style grid on profile pages.

 * Requires x-profile-harvest.js + x-profile-looms-shared.js.

 */

(function () {

  if (typeof tbccWaitForModule !== "function") return;
  tbccWaitForModule("x_profile_gallery", function () {

  if (window.__tbccXProfileOverlayLoaded) return;

  window.__tbccXProfileOverlayLoaded = true;



  var Looms = window.TbccXProfileLooms;

  var STORAGE_KEY = Looms ? Looms.STORAGE_KEY : "tbccXProfileGallerySettings";

  var ROOT_ID = "tbcc-x-profile-gallery-root";

  var STYLE_ID = "tbcc-x-profile-gallery-styles";



  var DEFAULT_SETTINGS = Looms

    ? Looms.LOOMS_DEFAULTS

    : {

        maxItems: 120,

        includeVideo: true,

        idleThreads: 2,

        browseThreads: 4,

        downloadThreads: 8,

        timeoutSec: 20,

        layout: "grid",

        fetchOriginal: false,

        chapterId: 1,

      };



  var settings = Object.assign({}, DEFAULT_SETTINGS);

  var overlayOpen = false;

  var items = [];

  var preloadQueue = [];

  var preloadActive = 0;

  var readySet = {};

  var zipReadySet = {};

  var activeMergeId = "";



  function isAlive() {

    try {

      return !!(chrome && chrome.runtime && chrome.runtime.id);

    } catch (_) {

      return false;

    }

  }



  function overlayReady() {
    return (
      typeof window.__tbccXProfileIsOverlayPage === "function" &&
      window.__tbccXProfileIsOverlayPage() &&
      typeof window.__tbccXProfileHarvestRun === "function"
    );
  }

  function overlayFabTitle() {
    if (typeof window.__tbccXProfileIsHomeFeedPage === "function" && window.__tbccXProfileIsHomeFeedPage()) {
      var mode =
        typeof window.__tbccXProfileHomeFeedMode === "function" ? window.__tbccXProfileHomeFeedMode() : "for_you";
      return mode === "following" ? "TBCC — Following feed gallery" : "TBCC — For you feed gallery";
    }
    return "TBCC — profile media gallery";
  }



  function normalizeSettings(raw) {

    if (Looms) return Looms.clampLoomsSettings(raw);

    var s = Object.assign({}, DEFAULT_SETTINGS, raw || {});

    s.maxItems = Math.min(Math.max(Number(s.maxItems) || 120, 20), 300);

    s.idleThreads = Math.min(Math.max(Number(s.idleThreads) || 2, 1), 4);

    s.browseThreads = Math.min(Math.max(Number(s.browseThreads) || 4, 1), 4);

    s.downloadThreads = Math.min(Math.max(Number(s.downloadThreads) || 8, 1), 12);

    s.timeoutSec = Math.min(Math.max(Number(s.timeoutSec) || 20, 2), 60);

    if (["grid", "horizontal", "vertical"].indexOf(s.layout) < 0) s.layout = "grid";

    return s;

  }



  async function loadSettings() {

    if (!isAlive()) return;

    try {

      if (Looms) {

        settings = await Looms.loadLoomsSettings();

        return;

      }

      var data = await chrome.storage.local.get(STORAGE_KEY);

      settings = normalizeSettings(data[STORAGE_KEY]);

    } catch (_) {

      settings = normalizeSettings(null);

    }

  }



  function effectivePreloadCap() {

    var idle = settings.idleThreads || 2;

    var browse = settings.browseThreads || 4;

    if (preloadQueue.length > idle * 2) return Math.max(idle, browse);

    return idle;

  }



  function injectStyles() {

    if (document.getElementById(STYLE_ID)) return;

    var st = document.createElement("style");

    st.id = STYLE_ID;

    st.textContent =

      "#tbcc-x-fab{position:fixed;z-index:2147483640;right:18px;bottom:88px;width:48px;height:48px;border-radius:50%;" +

      "border:2px solid rgba(29,155,240,.85);background:#0f1419;color:#e7e9ea;font:600 13px/1 system-ui,sans-serif;" +

      "cursor:pointer;box-shadow:0 4px 18px rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center}" +

      "#tbcc-x-fab:hover{background:#1a2733}" +

      "#" +

      ROOT_ID +

      "{position:fixed;inset:0;z-index:2147483641;background:rgba(0,0,0,.92);color:#e7e9ea;font:13px/1.35 system-ui,sans-serif;display:flex;flex-direction:column}" +

      "#" +

      ROOT_ID +

      "[hidden]{display:none!important}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-top{display:flex;gap:8px;align-items:center;padding:10px 12px;border-bottom:1px solid #38444d;flex-wrap:wrap}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-top button{background:#1d9bf0;border:0;color:#fff;border-radius:999px;padding:6px 12px;cursor:pointer;font:inherit}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-top button.secondary{background:#38444d}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-top button:disabled{opacity:.45;cursor:default}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-status{margin-left:auto;opacity:.85;font-size:12px}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-grid{flex:1;overflow:auto;padding:10px;gap:8px}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-grid.layout-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));align-content:start}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-grid.layout-horizontal{display:flex;flex-direction:row;flex-wrap:nowrap;align-items:stretch}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-grid.layout-vertical{display:flex;flex-direction:column;flex-wrap:nowrap;align-items:center}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-tile{position:relative;border:3px solid #536471;border-radius:8px;overflow:hidden;background:#15202b;min-width:120px;min-height:120px;flex:0 0 auto;" +

      "transition:border-color .35s ease,box-shadow .35s ease}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-tile.ready{border-color:#6b7f8f}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-tile.zip-ready{border-color:#00ba7c;box-shadow:0 0 0 2px rgba(0,186,124,.45)}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-tile img,#tbcc-x-profile-gallery-root .tbcc-x-tile video{width:100%;height:100%;object-fit:cover;display:block;min-height:120px}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-tile .badge{position:absolute;left:4px;top:4px;background:rgba(0,0,0,.65);padding:2px 5px;border-radius:4px;font-size:10px}" +

      "#tbcc-x-profile-gallery-root .tbcc-x-empty{padding:24px;text-align:center;opacity:.8}";

    (document.head || document.documentElement).appendChild(st);

  }



  function ensureFab() {

    if (!overlayReady() || document.getElementById("tbcc-x-fab")) return;

    injectStyles();

    var fab = document.createElement("button");

    fab.id = "tbcc-x-fab";

    fab.type = "button";

    fab.title = overlayFabTitle();

    fab.textContent = "⊞";

    fab.addEventListener("click", function () {

      void openGalleryOverlay();

    });

    document.documentElement.appendChild(fab);

  }



  function removeFab() {

    var fab = document.getElementById("tbcc-x-fab");

    if (fab) fab.remove();

  }



  function getRoot() {

    var el = document.getElementById(ROOT_ID);

    if (!el) {

      el = document.createElement("div");

      el.id = ROOT_ID;

      el.hidden = true;

      document.documentElement.appendChild(el);

    }

    return el;

  }



  function setStatus(text) {

    var root = getRoot();

    var st = root.querySelector(".tbcc-x-status");

    if (st) st.textContent = text || "";

  }



  function tileByIndex(index) {

    var root = getRoot();

    return root.querySelector('.tbcc-x-tile[data-index="' + index + '"]');

  }



  function renderGrid() {

    var root = getRoot();

    var grid = root.querySelector(".tbcc-x-grid");

    if (!grid) return;

    grid.className = "tbcc-x-grid layout-" + (settings.layout || "grid");

    grid.innerHTML = "";

    if (!items.length) {

      var empty = document.createElement("div");

      empty.className = "tbcc-x-empty";

      empty.textContent = "No media found in this view.";

      grid.appendChild(empty);

      return;

    }

    for (var i = 0; i < items.length; i++) {

      (function (item, idx) {

        var tile = document.createElement("a");

        var cls = "tbcc-x-tile";

        if (readySet[item.url]) cls += " ready";

        if (zipReadySet[idx]) cls += " zip-ready";

        tile.className = cls;

        tile.href = item.href || item.url;

        tile.target = "_blank";

        tile.rel = "noopener";

        tile.dataset.url = item.url;

        tile.dataset.index = String(idx);

        var badge = document.createElement("span");

        badge.className = "badge";

        badge.textContent = item.media_type === "video" ? "MP4" : "IMG";

        tile.appendChild(badge);

        if (item.media_type === "video") {

          var vid = document.createElement("video");

          vid.muted = true;

          vid.playsInline = true;

          vid.preload = "metadata";

          vid.poster = item.thumbnail_url || "";

          vid.src = item.thumbnail_url || item.url;

          tile.appendChild(vid);

        } else {

          var img = document.createElement("img");

          img.loading = "lazy";

          img.alt = item.filename || "media " + (idx + 1);

          img.src = item.thumbnail_url || item.url;

          tile.appendChild(img);

        }

        grid.appendChild(tile);

      })(items[i], i);

    }

  }



  function markReady(url) {

    if (!url || readySet[url]) return;

    readySet[url] = 1;

    var root = getRoot();

    var tile = root.querySelector('.tbcc-x-tile[data-url="' + CSS.escape(url) + '"]');

    if (tile) tile.classList.add("ready");

    var readyCount = Object.keys(readySet).length;

    if (!activeMergeId) setStatus(readyCount + " / " + items.length + " ready");

    pumpPreload();

  }



  function markZipReadyByIndex(index) {

    if (index == null || index < 0 || zipReadySet[index]) return;

    zipReadySet[index] = 1;

    var tile = tileByIndex(index);

    if (tile) tile.classList.add("zip-ready");

    var n = Object.keys(zipReadySet).length;

    setStatus("ZIP fetch " + n + " / " + items.length + " — mirroring gallery…");

  }



  function finalizePreloadStatus() {

    if (preloadActive > 0 || preloadQueue.length > 0 || activeMergeId) return;

    var readyCount = Object.keys(readySet).length;

    if (readyCount >= items.length) {

      setStatus(readyCount + " / " + items.length + " ready");

    } else {

      setStatus(readyCount + " / " + items.length + " ready (some previews skipped — ZIP still works)");

    }

  }



  function pumpPreload() {

    var cap = effectivePreloadCap();

    while (preloadActive < cap && preloadQueue.length) {

      var item = preloadQueue.shift();

      if (!item || !item.url || readySet[item.url]) continue;

      preloadActive++;

      void preloadOne(item).finally(function () {

        preloadActive--;

        pumpPreload();

        finalizePreloadStatus();

      });

    }

    finalizePreloadStatus();

  }



  function fetchBlobWithStallTimeout(url, stallMs) {

    return new Promise(function (resolve, reject) {

      var xhr = new XMLHttpRequest();

      xhr.open("GET", url, true);

      xhr.responseType = "blob";

      xhr.withCredentials = true;

      var timer = null;

      function bump() {

        if (timer) clearTimeout(timer);

        timer = setTimeout(function () {

          try {

            xhr.abort();

          } catch (_) {}

          reject(new Error("timeout"));

        }, stallMs);

      }

      xhr.onloadstart = bump;

      xhr.onprogress = bump;

      xhr.onload = function () {

        if (timer) clearTimeout(timer);

        if (xhr.status >= 200 && xhr.status < 300 && xhr.response) resolve(xhr.response);

        else reject(new Error(String(xhr.status || "fetch failed")));

      };

      xhr.onerror = function () {

        if (timer) clearTimeout(timer);

        reject(new Error("network"));

      };

      xhr.onabort = function () {

        if (timer) clearTimeout(timer);

        reject(new Error("timeout"));

      };

      bump();

      try {

        xhr.send();

      } catch (e) {

        if (timer) clearTimeout(timer);

        reject(e);

      }

    });

  }



  function preloadOne(item) {

    var key = item.url;

    var thumb = item.thumbnail_url || item.url;

    var fetchUrl = item.url;

    var stallMs = Math.max(2000, (settings.timeoutSec || 9) * 1000);

    return fetchBlobWithStallTimeout(fetchUrl, stallMs)

      .then(function (blob) {

        if (blob && blob.size > 0) item._prefetchSize = blob.size;

        markReady(key);

      })

      .catch(function () {

        if (item.media_type === "video") {

          return new Promise(function (resolve) {

            var vid = document.createElement("video");

            vid.muted = true;

            vid.preload = "metadata";

            var timer = setTimeout(function () {

              markReady(key);

              resolve();

            }, stallMs);

            vid.onloadeddata = function () {

              clearTimeout(timer);

              markReady(key);

              resolve();

            };

            vid.onerror = function () {

              clearTimeout(timer);

              markReady(key);

              resolve();

            };

            vid.src = fetchUrl || thumb;

          });

        }

        return new Promise(function (resolve) {

          var img = new Image();

          var timer = setTimeout(function () {

            markReady(key);

            resolve();

          }, stallMs);

          img.onload = function () {

            clearTimeout(timer);

            markReady(key);

            resolve();

          };

          img.onerror = function () {

            clearTimeout(timer);

            markReady(key);

            resolve();

          };

          img.src = thumb;

        });

      });

  }



  function queuePreloads() {

    preloadQueue = items.slice();

    pumpPreload();

  }



  function bindOverlayButton(sel, handler) {

    var root = getRoot();

    var btn = root.querySelector(sel);

    if (!btn) return;

    btn.addEventListener("click", function (e) {

      e.preventDefault();

      e.stopPropagation();

      handler(e);

    });

  }



  function buildChrome() {

    var root = getRoot();

    root.innerHTML =

      '<div class="tbcc-x-top">' +

      '<button type="button" data-act="zip">ZIP all</button>' +

      '<button type="button" class="secondary" data-act="gallery">Open in TBCC Gallery</button>' +

      '<button type="button" class="secondary" data-act="layout">Layout: ' +

      String(settings.layout || "grid") +

      "</button>" +

      '<button type="button" class="secondary" data-act="close">Close</button>' +

      '<span class="tbcc-x-status"></span>' +

      "</div>" +

      '<div class="tbcc-x-grid layout-grid"></div>';



    bindOverlayButton('[data-act="close"]', closeOverlay);

    bindOverlayButton('[data-act="zip"]', function () {

      try {
        chrome.runtime.sendMessage({ action: "tbcc-x-open-side-panel-sync" });
      } catch (_) {}

      void downloadZip();

    });

    bindOverlayButton('[data-act="gallery"]', function () {

      try {
        chrome.runtime.sendMessage({ action: "tbcc-x-open-side-panel-sync" });
      } catch (_) {}

      void sendToGallery(false, false);

    });

    bindOverlayButton('[data-act="layout"]', function () {

      var order = ["grid", "horizontal", "vertical"];

      var ix = order.indexOf(settings.layout);

      settings.layout = order[(ix + 1) % order.length];

      var btn = root.querySelector('[data-act="layout"]');

      if (btn) btn.textContent = "Layout: " + settings.layout;

      if (isAlive()) chrome.storage.local.set({ [STORAGE_KEY]: settings });

      renderGrid();

    });

  }



  function closeOverlay() {

    overlayOpen = false;

    preloadQueue = [];

    preloadActive = 0;

    activeMergeId = "";

    zipReadySet = {};

    var root = getRoot();

    root.hidden = true;

    root.setAttribute("aria-hidden", "true");

  }



  async function sendToGallery(autoZip, openPanel, loomsZip) {

    if (!isAlive() || !items.length) return;

    var mergeId = "looms-" + Date.now() + "-" + Math.random().toString(36).slice(2, 7);

    if (loomsZip) activeMergeId = mergeId;

    setStatus(openPanel ? "Opening TBCC Gallery…" : "Sending to gallery…");

    try {

      var resp = await chrome.runtime.sendMessage({

        action: "tbcc-x-profile-merge-to-gallery",

        items: items,

        sourceUrl: location.href.split("#")[0],

        adapter: "x-profile",

        autoZip: !!autoZip,

        loomsZip: !!loomsZip,

        mergeId: mergeId,

        selectAll: loomsZip ? false : true,

        openPanel: !!openPanel,

        tabId: null,

      });

      if (resp && resp.ok === false) {

        throw new Error(resp.error || "merge failed");

      }

      if (resp && resp.panelWarning && openPanel) {

        setStatus("Gallery opened — ZIP continuing…");

      } else if (loomsZip) {

        setStatus("ZIP all — fetching media (parallel ×" + (settings.downloadThreads || 4) + ")…");

      } else if (autoZip) {

        setStatus("ZIP export started in TBCC Gallery side panel");

      } else {

        setStatus("Added " + items.length + " item(s) to TBCC Gallery");

      }

    } catch (e) {

      activeMergeId = "";

      setStatus("Gallery handoff failed: " + String(e.message || e));

      throw e;

    }

  }



  async function downloadZip() {

    var root = getRoot();

    var zipBtn = root.querySelector('[data-act="zip"]');

    if (zipBtn) zipBtn.disabled = true;

    zipReadySet = {};

    try {

      await sendToGallery(true, false, true);

    } catch (e) {

      setStatus("ZIP failed: " + String(e.message || e));

    } finally {

      if (zipBtn) zipBtn.disabled = false;

    }

  }



  async function openGalleryOverlay() {

    if (!overlayReady()) return;

    await loadSettings();

    injectStyles();

    overlayOpen = true;

    readySet = {};

    zipReadySet = {};

    activeMergeId = "";

    items = [];

    var root = getRoot();

    buildChrome();

    root.hidden = false;

    root.removeAttribute("aria-hidden");

    var onHome =
      typeof window.__tbccXProfileIsHomeFeedPage === "function" && window.__tbccXProfileIsHomeFeedPage();

    setStatus(onHome ? "Harvesting home feed media…" : "Harvesting profile media…");



    try {

      var result = await window.__tbccXProfileHarvestRun(

        {

          maxItems: settings.maxItems,

          includeVideo: settings.includeVideo,

          chapterId: settings.chapterId,

          fetchOriginal: settings.fetchOriginal,

          feedMode: "auto",

        },

        function (p) {

          if (p && p.count != null) setStatus("Harvesting… " + p.count + " / " + (p.max || settings.maxItems));

        }

      );

      if (!result || result.ok === false) throw new Error((result && result.error) || "harvest failed");

      items = Array.isArray(result.list) ? result.list : [];

      if (result.truncated) {

        setStatus(items.length + " items (cap " + settings.maxItems + " — raise in Options → X overlay)");

      } else {

        setStatus(items.length + " items — preloading…");

      }

      renderGrid();

      queuePreloads();

    } catch (e) {

      setStatus(String(e.message || e));

    }

  }



  function onNav() {

    if (!overlayReady()) {

      removeFab();

      if (overlayOpen) closeOverlay();

      return;

    }

    var fab = document.getElementById("tbcc-x-fab");

    if (fab) fab.title = overlayFabTitle();

    ensureFab();

  }



  if (isAlive()) {

    chrome.runtime.onMessage.addListener(function (msg) {

      if (!msg || msg.action !== "tbcc-looms-zip-progress") return;

      if (activeMergeId && msg.mergeId && msg.mergeId !== activeMergeId) return;

      if (msg.phase === "fetched" && msg.index != null) markZipReadyByIndex(Number(msg.index));

      if (msg.phase === "zip-start") setStatus("ZIP all — fetching media…");

      if (msg.phase === "packing") setStatus("Compressing ZIP…");

      if (msg.phase === "done") {

        activeMergeId = "";

        setStatus("ZIP saved — check Downloads/tbcc/");

      }

      if (msg.phase === "error") {

        activeMergeId = "";

        setStatus(String(msg.error || "ZIP failed"));

      }

    });

  }



  loadSettings().then(function () {

    onNav();

  });



  var navTimer;

  function scheduleNavCheck() {

    clearTimeout(navTimer);

    navTimer = setTimeout(onNav, 400);

  }



  window.addEventListener("popstate", scheduleNavCheck);

  window.addEventListener("hashchange", scheduleNavCheck);

  try {

    var obs = new MutationObserver(scheduleNavCheck);

    obs.observe(document.documentElement, { childList: true, subtree: true });

  } catch (_) {}



  setInterval(function () {

    if (overlayReady()) ensureFab();

  }, 2500);



  document.addEventListener(

    "keydown",

    function (e) {

      if (!overlayOpen || e.key !== "Escape") return;

      e.preventDefault();

      e.stopPropagation();

      closeOverlay();

    },

    true

  );

  if (typeof tbccBindModuleDisableListener === "function") {
    tbccBindModuleDisableListener("x_profile_gallery", function () {
      try {
        closeOverlay();
      } catch (_) {}
    });
  }

  });

})();


