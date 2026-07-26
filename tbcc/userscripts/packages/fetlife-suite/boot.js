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
    infiniteScroll: true,
    socialProof: true,
    privacyConsole: true,
  };

  const LABELS = {
    loginRedirect: 'Redirect login/home → last kinksters place',
    homeFeed: 'Home feed masonry + pills',
    storyFilter: 'Client-side story type filter',
    mute: 'Comment mute buttons',
    newestDiscussions: 'Groups → newest discussions',
    genderFilter: 'ASL filter (female / location)',
    autoFollow: 'Auto-follow controls (panel)',
    infiniteScroll: 'Kinksters infinite scroll (fill gaps)',
    socialProof: 'Profile count padding (Friends/Followers/Following)',
    privacyConsole: 'FLConsole privacy presets',
  };

  const flags = S.createFlags(FLAG_KEY, DEFAULTS);
  // Force-enable new defaults for users who already have an old flags blob
  {
    const saved = S.storage.get(FLAG_KEY, null);
    const upgrade = (key) => {
      if (!saved || typeof saved !== 'object' || !(key in saved)) flags.set(key, true);
    };
    upgrade('autoFollow');
    upgrade('genderFilter');
    upgrade('loginRedirect');
    upgrade('infiniteScroll');
    upgrade('socialProof');
    upgrade('privacyConsole');
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

  function onRemoteFlags() {
    flags.hydrate?.();
    syncFeatures();
    FL.overlay.refresh?.();
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

    // Keep module flags live across FetLife tabs.
    if (typeof S.storage.subscribe === 'function') {
      S.storage.subscribe(FLAG_KEY, onRemoteFlags);
    }

    // Open overlay on kinksters landing (persists open state to other tabs).
    if (/\/kinksters/i.test(location.pathname)) {
      setTimeout(() => FL.overlay.open('autofollow'), 700);
    }

    console.info('[TBCC FetLife Suite] v1.8 ready', flags.all());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
