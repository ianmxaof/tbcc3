/* Login / home → preferred kinksters landing */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const DEST =
    'https://fetlife.com/p/united-states/california/san-jose/kinksters';
  const SESSION_KEY = 'tbcc_fl_login_redirect_done';

  function shouldRedirect() {
    const path = location.pathname || '';
    if (/\/p\/united-states\/california\/san-jose\/kinksters/i.test(path)) return false;
    if (path === '/' || path === '/home' || path === '/home/') return true;
    return false;
  }

  function go() {
    if (sessionStorage.getItem(SESSION_KEY)) return;
    if (!shouldRedirect()) return;
    sessionStorage.setItem(SESSION_KEY, '1');
    location.replace(DEST);
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
