/* FetLife suite boot — flags + overlay + feature sync */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const FLAG_KEY = 'tbcc_fl_suite_flags_v1';
  const DEFAULTS = {
    loginRedirect: true,
    homeFeed: true,
    storyFilter: true,
    mute: true,
    newestDiscussions: true,
    genderFilter: true,
    autoFollow: true,
  };

  const LABELS = {
    loginRedirect: 'Redirect login/home → San Jose kinksters',
    homeFeed: 'Home feed masonry + pills',
    storyFilter: 'Client-side story type filter',
    mute: 'Comment mute buttons',
    newestDiscussions: 'Groups → newest discussions',
    genderFilter: 'Hide male profiles on lists',
    autoFollow: 'Auto-follow controls (panel)',
  };

  const flags = S.createFlags(FLAG_KEY, DEFAULTS);
  // Force-enable new defaults for users who already have an old flags blob
  if (flags.raw('autoFollow') === undefined || flags.raw('autoFollow') === false) {
    // Only upgrade if key missing from saved object — if user explicitly saved false, respect it.
    const saved = S.storage.get(FLAG_KEY, null);
    if (!saved || typeof saved !== 'object' || !('autoFollow' in saved)) {
      flags.set('autoFollow', true);
    }
    if (!saved || typeof saved !== 'object' || !('genderFilter' in saved)) {
      flags.set('genderFilter', true);
    }
    if (!saved || typeof saved !== 'object' || !('loginRedirect' in saved)) {
      flags.set('loginRedirect', true);
    }
  }

  const running = Object.create(null);

  function syncFeatures() {
    const feats = FL.features || {};
    for (const name of Object.keys(DEFAULTS)) {
      const want = flags.get(name);
      const feat = feats[name];
      if (!feat) continue;
      if (want && !running[name]) {
        feat.start();
        running[name] = true;
      } else if (!want && running[name]) {
        feat.stop?.();
        running[name] = false;
      }
    }
  }

  function boot() {
    FL.overlay.mount({
      flags,
      labels: LABELS,
      onFlagsChange() {
        syncFeatures();
      },
    });
    syncFeatures();

    // Open overlay on kinksters landing
    if (/\/kinksters/i.test(location.pathname)) {
      setTimeout(() => FL.overlay.open('autofollow'), 700);
    }

    console.info('[TBCC FetLife Suite] v1.1 ready', flags.all());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
