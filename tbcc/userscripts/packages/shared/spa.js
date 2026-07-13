/* SPA navigation hooks (pushState / replaceState / popstate) */
(function (global) {
  'use strict';
  const S = global.__TBCC_US__.shared;
  const listeners = new Set();
  let hooked = false;

  function emit() {
    for (const fn of listeners) {
      try {
        fn(location.href);
      } catch (err) {
        console.warn('[TBCC_US] spa listener error', err);
      }
    }
  }

  function hookHistory(method) {
    const orig = history[method];
    history[method] = function () {
      const ret = orig.apply(this, arguments);
      setTimeout(emit, 50);
      return ret;
    };
  }

  S.spa = {
    onChange(fn) {
      listeners.add(fn);
      if (!hooked) {
        hooked = true;
        hookHistory('pushState');
        hookHistory('replaceState');
        window.addEventListener('popstate', () => setTimeout(emit, 50));
      }
      return () => listeners.delete(fn);
    },
    path() {
      return location.pathname || '';
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
