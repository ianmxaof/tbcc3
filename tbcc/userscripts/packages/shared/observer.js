/* Debounced document MutationObserver bus */
(function (global) {
  'use strict';
  const S = global.__TBCC_US__.shared;
  const listeners = new Set();
  let mo = null;
  let timer = null;

  function flush() {
    timer = null;
    for (const fn of listeners) {
      try {
        fn();
      } catch (err) {
        console.warn('[TBCC_US] observer listener error', err);
      }
    }
  }

  S.observer = {
    subscribe(fn) {
      listeners.add(fn);
      if (!mo && typeof MutationObserver !== 'undefined' && document.documentElement) {
        mo = new MutationObserver(() => {
          if (timer) return;
          timer = setTimeout(flush, 120);
        });
        mo.observe(document.documentElement, { childList: true, subtree: true });
      }
      return () => listeners.delete(fn);
    },
    ping() {
      flush();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
