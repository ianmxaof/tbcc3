/* GM storage helpers with in-memory fallback for unit tests / missing grants */
(function (global) {
  'use strict';
  const S = global.__TBCC_US__.shared;
  const mem = Object.create(null);

  function hasGM() {
    return typeof GM_getValue === 'function' && typeof GM_setValue === 'function';
  }

  S.storage = {
    get(key, fallback) {
      try {
        if (hasGM()) {
          const v = GM_getValue(key, fallback);
          return v === undefined ? fallback : v;
        }
      } catch (_) { /* ignore */ }
      return key in mem ? mem[key] : fallback;
    },
    set(key, value) {
      try {
        if (hasGM()) {
          GM_setValue(key, value);
          return;
        }
      } catch (_) { /* ignore */ }
      mem[key] = value;
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
