/**
 * Comic Looms–style concurrency + timeout defaults for TBCC X profile overlay.
 * Shared by x-profile-overlay.js (content) and gallery.js (side panel).
 */
(function (root) {
  var STORAGE_KEY = "tbccXProfileGallerySettings";

  var LOOMS_DEFAULTS = {
    idleThreads: 2,
    browseThreads: 4,
    downloadThreads: 4,
    timeoutSec: 9,
    maxItems: 120,
    includeVideo: true,
    layout: "grid",
    fetchOriginal: false,
    chapterId: 1,
    /** AOF harvest ZIP names — PowerRename-style; {name} = profile, {index:5} = counter, {ext} = type */
    zipNameTemplate: "AOF_{name}_{index:5}_t.me_aofmainhub",
    zipSkipWatermark: true,
  };

  function clampInt(n, min, max, fallback) {
    var v = parseInt(String(n), 10);
    if (isNaN(v)) v = fallback;
    return Math.min(Math.max(v, min), max);
  }

  function clampLoomsSettings(raw) {
    var s = raw && typeof raw === "object" ? Object.assign({}, LOOMS_DEFAULTS, raw) : Object.assign({}, LOOMS_DEFAULTS);
    s.idleThreads = clampInt(s.idleThreads, 1, 4, LOOMS_DEFAULTS.idleThreads);
    s.browseThreads = clampInt(s.browseThreads, 1, 4, LOOMS_DEFAULTS.browseThreads);
    s.downloadThreads = clampInt(s.downloadThreads, 1, 4, LOOMS_DEFAULTS.downloadThreads);
    s.timeoutSec = clampInt(s.timeoutSec, 2, 40, LOOMS_DEFAULTS.timeoutSec);
    s.maxItems = clampInt(s.maxItems, 20, 300, LOOMS_DEFAULTS.maxItems);
    s.chapterId = clampInt(s.chapterId, 0, 3, LOOMS_DEFAULTS.chapterId);
    if (["grid", "horizontal", "vertical"].indexOf(s.layout) < 0) s.layout = "grid";
    s.includeVideo = s.includeVideo !== false;
    s.fetchOriginal = !!s.fetchOriginal;
    s.maxPreloadConcurrent = s.idleThreads;
    var tpl = s.zipNameTemplate != null ? String(s.zipNameTemplate).trim() : "";
    s.zipNameTemplate = tpl || LOOMS_DEFAULTS.zipNameTemplate;
    s.zipSkipWatermark = s.zipSkipWatermark !== false;
    return s;
  }

  function loadLoomsSettings() {
    return new Promise(function (resolve) {
      try {
        if (!root.chrome || !chrome.storage || !chrome.storage.local) {
          resolve(clampLoomsSettings(null));
          return;
        }
        chrome.storage.local.get(STORAGE_KEY, function (data) {
          resolve(clampLoomsSettings(data && data[STORAGE_KEY]));
        });
      } catch (_) {
        resolve(clampLoomsSettings(null));
      }
    });
  }

  function saveLoomsSettings(partial) {
    return new Promise(function (resolve) {
      loadLoomsSettings().then(function (cur) {
        var next = clampLoomsSettings(Object.assign({}, cur, partial || {}));
        try {
          chrome.storage.local.set({ [STORAGE_KEY]: next }, function () {
            resolve(next);
          });
        } catch (_) {
          resolve(next);
        }
      });
    });
  }

  /**
   * Worker pool — preserves completion order callbacks via ordered reveal in consumer.
   */
  function runConcurrentPool(items, workerFn, maxConcurrency) {
    var n = items.length;
    if (n === 0) return Promise.resolve([]);
    var cap = Math.min(Math.max(1, maxConcurrency || 1), n);
    var results = new Array(n);
    var nextIndex = 0;
    function worker() {
      return (function loop() {
        var idx = nextIndex++;
        if (idx >= n) return Promise.resolve();
        return Promise.resolve(workerFn(items[idx], idx))
          .then(function (res) {
            results[idx] = res;
          })
          .catch(function (err) {
            results[idx] = { error: err };
          })
          .then(loop);
      })();
    }
    var workers = [];
    for (var w = 0; w < cap; w++) workers.push(worker());
    return Promise.all(workers).then(function () {
      return results;
    });
  }

  /**
   * Ordered reveal: call onReveal(i) for i=0,1,… only when each index is ready (parallel fetch underneath).
   */
  function createOrderedReveal(total, onReveal) {
    var slots = new Array(total);
    var next = 0;
    return function markDone(index, payload) {
      slots[index] = payload;
      while (next < total && slots[next] !== undefined) {
        try {
          onReveal(next, slots[next]);
        } catch (_) {}
        next++;
      }
      return next;
    };
  }

  root.TbccXProfileLooms = {
    STORAGE_KEY: STORAGE_KEY,
    LOOMS_DEFAULTS: LOOMS_DEFAULTS,
    clampLoomsSettings: clampLoomsSettings,
    loadLoomsSettings: loadLoomsSettings,
    saveLoomsSettings: saveLoomsSettings,
    runConcurrentPool: runConcurrentPool,
    createOrderedReveal: createOrderedReveal,
  };
})(typeof window !== "undefined" ? window : self);
