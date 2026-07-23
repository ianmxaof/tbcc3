/* Login / home → last kinksters place (no hardcoded city) */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const SESSION_KEY = 'tbcc_fl_login_redirect_done';

  function destUrl() {
    const place = FL.placeNav?.loadCfg?.() || {};
    if (place.lastPath) return `https://fetlife.com${place.lastPath}`;
    if (place.lastQuery && FL.placeNav?.kinkstersUrl) {
      return FL.placeNav.kinkstersUrl(place.lastQuery, place);
    }
    return null;
  }

  function shouldRedirect() {
    const path = (location.pathname || '').replace(/\/+$/, '') || '/';
    if (path !== '/' && path !== '/home') return false;
    const dest = destUrl();
    if (!dest) return false;
    try {
      const destPath = new URL(dest).pathname.replace(/\/+$/, '');
      if (path === destPath) return false;
    } catch (_) {
      /* ignore */
    }
    return true;
  }

  function go() {
    if (sessionStorage.getItem(SESSION_KEY)) return;
    if (!shouldRedirect()) return;
    const dest = destUrl();
    if (!dest) return;
    sessionStorage.setItem(SESSION_KEY, '1');
    location.replace(dest);
  }

  FL.features = FL.features || {};
  FL.features.loginRedirect = {
    start() {
      go();
      this._unsub = S.spa.onChange(() => setTimeout(go, 80));
    },
    stop() {
      this._unsub?.();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
