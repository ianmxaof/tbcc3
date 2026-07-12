/**
 * Content-script gate: defer module boot until storage confirms the module is enabled.
 */
(function (root) {
  const STORAGE_KEY = "tbccExtensionModuleEnabled";

  function moduleEnabled(map, moduleId) {
    if (!map || typeof map !== "object") return true;
    return map[moduleId] !== false;
  }

  root.tbccWaitForModule = function tbccWaitForModule(moduleId, run) {
    if (typeof run !== "function") return;
    try {
      chrome.storage.local.get([STORAGE_KEY], (d) => {
        const map = d && d[STORAGE_KEY];
        if (!moduleEnabled(map, moduleId)) return;
        run();
      });
    } catch (_) {
      run();
    }
  };

  root.tbccBindModuleDisableListener = function tbccBindModuleDisableListener(moduleId, teardown) {
    if (typeof teardown !== "function") return;
    try {
      chrome.runtime.onMessage.addListener((msg) => {
        if (msg && msg.action === "tbcc-extension-module-disabled" && msg.moduleId === moduleId) {
          try {
            teardown();
          } catch (_) {}
        }
        return false;
      });
    } catch (_) {}
  };
})(typeof window !== "undefined" ? window : globalThis);
