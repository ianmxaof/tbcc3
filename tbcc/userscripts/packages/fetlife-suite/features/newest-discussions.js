/* Newest discussions redirect — adapted from GreasyFork script 29395 */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const FL = (US.fetlife = US.fetlife || {});

  function maybeRedirect() {
    const path = location.pathname || '';
    if (!/^\/groups\/\d+$/.test(path)) return;
    if (location.search.includes('order=')) return;
    location.replace(path + '?order=discussions');
  }

  FL.features = FL.features || {};
  FL.features.newestDiscussions = {
    start() {
      maybeRedirect();
      this._unsub = US.shared.spa.onChange(() => setTimeout(maybeRedirect, 50));
    },
    stop() {
      this._unsub?.();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
