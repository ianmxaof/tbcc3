/* Perchance suite boot */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const PC = (US.perchance = US.perchance || {});

  const FLAG_KEY = 'tbcc_pc_suite_flags_v1';
  const DEFAULTS = {
    adsBypass: true,
    lazyQueue: true,
    promptBridge: true,
    jobsPanel: true,
    promptHistory: true,
    sendWinners: true,
  };

  const LABELS = {
    adsBypass: 'Ads bypass (Fuck Ads port)',
    lazyQueue: 'Lazy iframe queue',
    promptBridge: 'Last-prompt metadata bridge',
    jobsPanel: 'Gemini-parity job presets',
    promptHistory: 'Prompt history panel',
    sendWinners: 'Send winners / tag for TBCC',
  };

  const flags = S.createFlags(FLAG_KEY, DEFAULTS);
  const running = Object.create(null);

  function syncFeatures() {
    const feats = PC.features || {};
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
    S.mountFlagPanel({
      id: 'tbcc-pc-flags',
      title: 'TBCC Perchance Suite',
      fabLabel: 'PC',
      menuLabel: 'TBCC Perchance: flags',
      flags,
      labels: LABELS,
      onChange() {
        syncFeatures();
      },
    });
    syncFeatures();
    console.info('[TBCC Perchance Suite] ready', flags.all(), {
      jobs: (PC.jobsData && PC.jobsData.jobs && PC.jobsData.jobs.length) || 0,
    });
  }

  // Ads bypass must run as early as possible
  if (PC.features && PC.features.adsBypass && flags.get('adsBypass')) {
    PC.features.adsBypass.start();
    running.adsBypass = true;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
