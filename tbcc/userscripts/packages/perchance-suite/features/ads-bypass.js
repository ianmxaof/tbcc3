/* Fuck Ads, Perchance — adapted (Teraskull / GPLv3). Inbox: fuck-ads-perchance.user.js */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const PC = (US.perchance = US.perchance || {});
  PC.features = PC.features || {};

  let listening = false;
  function onMessage(e) {
    try {
      if (e.data && e.data.type === 'usingAdPoweredPlugin') {
        e.data.type = 'fuckYourAdPoweredPlugin';
      }
    } catch (_) { /* ignore */ }
  }

  PC.features.adsBypass = {
    start() {
      if (listening) return;
      window.addEventListener('message', onMessage);
      listening = true;
    },
    stop() {
      if (!listening) return;
      window.removeEventListener('message', onMessage);
      listening = false;
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
