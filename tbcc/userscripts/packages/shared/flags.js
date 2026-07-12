/* Feature flags: defaults + persisted overrides */
(function (global) {
  'use strict';
  const S = global.__TBCC_US__.shared;

  S.createFlags = function createFlags(storageKey, defaults) {
    const saved = S.storage.get(storageKey, null) || {};
    const state = { ...defaults, ...(typeof saved === 'object' ? saved : {}) };

    return {
      get(name) {
        return state[name] !== false;
      },
      raw(name) {
        return state[name];
      },
      set(name, on) {
        state[name] = !!on;
        S.storage.set(storageKey, { ...state });
      },
      all() {
        return { ...state };
      },
      defaults: { ...defaults },
    };
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
