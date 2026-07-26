/* GM storage helpers; Chrome extension uses localStorage; mem last-resort */
(function (global) {
  'use strict';
  const S = global.__TBCC_US__.shared;
  const mem = Object.create(null);
  const LS_PREFIX = 'tbcc_us_';

  function hasGM() {
    return typeof GM_getValue === 'function' && typeof GM_setValue === 'function';
  }

  function lsGet(key, fallback) {
    try {
      if (typeof localStorage === 'undefined') return fallback;
      const raw = localStorage.getItem(LS_PREFIX + key);
      if (raw == null) return fallback;
      return JSON.parse(raw);
    } catch (_) {
      return fallback;
    }
  }

  function lsSet(key, value) {
    try {
      if (typeof localStorage === 'undefined') return false;
      localStorage.setItem(LS_PREFIX + key, JSON.stringify(value));
      return true;
    } catch (_) {
      return false;
    }
  }

  S.storage = {
    get(key, fallback) {
      try {
        if (hasGM()) {
          const v = GM_getValue(key, fallback);
          return v === undefined ? fallback : v;
        }
      } catch (_) { /* ignore */ }
      if (typeof localStorage !== 'undefined') {
        return lsGet(key, key in mem ? mem[key] : fallback);
      }
      return key in mem ? mem[key] : fallback;
    },
    set(key, value) {
      try {
        if (hasGM()) {
          GM_setValue(key, value);
          return;
        }
      } catch (_) { /* ignore */ }
      if (lsSet(key, value)) return;
      mem[key] = value;
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
