/**
 * TBCC X profile gallery overlay — Comic Looms-style grid on profile pages.
 * Requires x-profile-harvest.js (GraphQL media list).
 */
(function () {
  if (window.__tbccXProfileOverlayLoaded) return;
  window.__tbccXProfileOverlayLoaded = true;

  var STORAGE_KEY = "tbccXProfileGallerySettings";
  var ROOT_ID = "tbcc-x-profile-gallery-root";
  var STYLE_ID = "tbcc-x-profile-gallery-styles";

  var DEFAULT_SETTINGS = {
    maxItems: 120,
    includeVideo: true,
    maxPreloadConcurrent: 2,
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

  function isAlive() {
    try {
      return !!(chrome && chrome.runtime && chrome.runtime.id);
    } catch (_) {
      return false;
    }
  }

  function profileReady() {
    return (
      typeof window.__tbccXProfileIsProfilePage === "function" &&
      window.__tbccXProfileIsProfilePage() &&
      typeof window.__tbccXProfileHarvestRun === "function"
    );
  }

  async function loadSettings() {
    if (!isAlive()) return;
    try {
      var data = await chrome.storage.local.get(STORAGE_KEY);
      var raw = data[STORAGE_KEY];
      if (raw && typeof raw === "object") {
        settings = Object.assign({}, DEFAULT_SETTINGS, raw);
      }
    } catch (_) {}
    settings.maxItems = Math.min(Math.max(Number(settings.maxItems) || 120, 20), 300);
    settings.maxPreloadConcurrent = Math.min(Math.max(Number(settings.maxPreloadConcurrent) || 2, 1), 4);
    if (["grid", "horizontal", "vertical"].indexOf(settings.layout) < 0) settings.layout = "grid";
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
      "#tbcc-x-profile-gallery-root .tbcc-x-tile{position:relative;border:3px solid #536471;border-radius:8px;overflow:hidden;background:#15202b;min-width:120px;min-height:120px;flex:0 0 auto}" +
      "#tbcc-x-profile-gallery-root .tbcc-x-tile.ready{border-color:#00ba7c}" +
      "#tbcc-x-profile-gallery-root .tbcc-x-tile img,#tbcc-x-profile-gallery-root .tbcc-x-tile video{width:100%;height:100%;object-fit:cover;display:block;min-height:120px}" +
      "#tbcc-x-profile-gallery-root .tbcc-x-tile .badge{position:absolute;left:4px;top:4px;background:rgba(0,0,0,.65);padding:2px 5px;border-radius:4px;font-size:10px}" +
      "#tbcc-x-profile-gallery-root .tbcc-x-empty{padding:24px;text-align:center;opacity:.8}";
    (document.head || document.documentElement).appendChild(st);
  }

  function ensureFab() {
    if (!profileReady() || document.getElementById("tbcc-x-fab")) return;
    injectStyles();
    var fab = document.createElement("button");
    fab.id = "tbcc-x-fab";
    fab.type = "button";
    fab.title = "TBCC — profile media gallery";
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

  function renderGrid() {
    var root = getRoot();
    var grid = root.querySelector(".tbcc-x-grid");
    if (!grid) return;
    grid.className = "tbcc-x-grid layout-" + (settings.layout || "grid");
    grid.innerHTML = "";
    if (!items.length) {
      var empty = document.createElement("div");
      empty.className = "tbcc-x-empty";
      empty.textContent = "No media found on this profile.";
      grid.appendChild(empty);
      return;
    }
    for (var i = 0; i < items.length; i++) {
      (function (item, idx) {
        var tile = document.createElement("a");
        tile.className = "tbcc-x-tile" + (readySet[item.url] ? " ready" : "");
        tile.href = item.href || item.url;
        tile.target = "_blank";
        tile.rel = "noopener";
        tile.dataset.url = item.url;
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
    setStatus(readyCount + " / " + items.length + " ready");
    pumpPreload();
  }

  function finalizePreloadStatus() {
    if (preloadActive > 0 || preloadQueue.length > 0) return;
    var readyCount = Object.keys(readySet).length;
    if (readyCount >= items.length) {
      setStatus(readyCount + " / " + items.length + " ready");
    } else {
      setStatus(readyCount + " / " + items.length + " ready (some previews skipped — ZIP still works)");
    }
  }

  function pumpPreload() {
    while (preloadActive < settings.maxPreloadConcurrent && preloadQueue.length) {
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

  function preloadOne(item) {
    var key = item.url;
    var thumb = item.thumbnail_url || item.url;
    var finished = false;
    function finish() {
      if (finished) return;
      finished = true;
      markReady(key);
    }
    var timer = setTimeout(finish, 10000);
    return new Promise(function (resolve) {
      if (item.media_type === "video") {
        var vid = document.createElement("video");
        vid.muted = true;
        vid.preload = "metadata";
        vid.onloadeddata = function () {
          clearTimeout(timer);
          finish();
          resolve();
        };
        vid.onerror = function () {
          var img = new Image();
          img.onload = function () {
            clearTimeout(timer);
            finish();
            resolve();
          };
          img.onerror = function () {
            clearTimeout(timer);
            finish();
            resolve();
          };
          img.src = thumb;
        };
        vid.src = thumb;
        return;
      }
      var img = new Image();
      img.onload = function () {
        clearTimeout(timer);
        finish();
        resolve();
      };
      img.onerror = function () {
        clearTimeout(timer);
        finish();
        resolve();
      };
      img.src = thumb;
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
      void downloadZip();
    });
    bindOverlayButton('[data-act="gallery"]', function () {
      void sendToGallery(false, true);
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
    var root = getRoot();
    root.hidden = true;
    root.setAttribute("aria-hidden", "true");
  }

  async function sendToGallery(autoZip, openPanel) {
    if (!isAlive() || !items.length) return;
    setStatus(openPanel ? "Opening TBCC Gallery…" : "Sending to gallery…");
    try {
      var resp = await chrome.runtime.sendMessage({
        action: "tbcc-x-profile-merge-to-gallery",
        items: items,
        sourceUrl: location.href.split("#")[0],
        adapter: "x-profile",
        autoZip: !!autoZip,
        selectAll: true,
        openPanel: !!openPanel,
      });
      if (resp && resp.ok === false) {
        throw new Error(resp.error || "merge failed");
      }
      setStatus(
        autoZip
          ? "ZIP export started in TBCC Gallery side panel"
          : "Added " + items.length + " item(s) to TBCC Gallery"
      );
    } catch (e) {
      setStatus("Gallery handoff failed: " + String(e.message || e));
    }
  }

  async function downloadZip() {
    var root = getRoot();
    var zipBtn = root.querySelector('[data-act="zip"]');
    if (zipBtn) zipBtn.disabled = true;
    setStatus("Opening TBCC Gallery for ZIP…");
    try {
      await sendToGallery(true, true);
      setStatus("ZIP started in TBCC Gallery side panel");
    } catch (e) {
      setStatus("ZIP failed: " + String(e.message || e));
    } finally {
      if (zipBtn) zipBtn.disabled = false;
    }
  }

  async function openGalleryOverlay() {
    if (!profileReady()) return;
    await loadSettings();
    injectStyles();
    overlayOpen = true;
    readySet = {};
    items = [];
    var root = getRoot();
    buildChrome();
    root.hidden = false;
    root.removeAttribute("aria-hidden");
    setStatus("Harvesting profile media…");

    try {
      var result = await window.__tbccXProfileHarvestRun(
        {
          maxItems: settings.maxItems,
          includeVideo: settings.includeVideo,
          chapterId: settings.chapterId,
          fetchOriginal: settings.fetchOriginal,
        },
        function (p) {
          if (p && p.count != null) setStatus("Harvesting… " + p.count + " / " + (p.max || settings.maxItems));
        }
      );
      if (!result || result.ok === false) throw new Error((result && result.error) || "harvest failed");
      items = Array.isArray(result.list) ? result.list : [];
      if (result.truncated) {
        setStatus(items.length + " items (cap " + settings.maxItems + " — raise in storage if needed)");
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
    if (!profileReady()) {
      removeFab();
      if (overlayOpen) closeOverlay();
      return;
    }
    ensureFab();
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
    if (profileReady()) ensureFab();
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
})();
