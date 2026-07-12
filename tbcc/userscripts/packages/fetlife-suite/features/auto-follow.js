/* Auto-follow with scroll + speed — adapted from FetLife Auto-Follow */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const SPEED_PRESETS = {
    instant: { min: 10, max: 50, label: 'Instant (10-50ms)' },
    fast: { min: 50, max: 200, label: 'Fast (50-200ms)' },
    normal: { min: 200, max: 500, label: 'Normal (200-500ms)' },
    slow: { min: 500, max: 1000, label: 'Slow (500-1000ms)' },
    stealth: { min: 1000, max: 2000, label: 'Stealth (1-2s)' },
  };

  const CFG_KEY = 'tbcc_fl_autofollow_cfg_v1';
  const DEFAULT_CFG = { speed: 'fast', skipMale: true, autoStartOnKinksters: true };

  let MIN_DELAY = 50;
  let MAX_DELAY = 200;
  const MAX_RETRIES = 3;
  const SCROLL_DELAY = 1000;

  let followCount = 0;
  let isRunning = false;
  let started = false;

  function loadCfg() {
    const saved = S.storage.get(CFG_KEY, null);
    return { ...DEFAULT_CFG, ...(saved && typeof saved === 'object' ? saved : {}) };
  }

  function saveCfg(cfg) {
    S.storage.set(CFG_KEY, cfg);
  }

  function applySpeed(key) {
    const p = SPEED_PRESETS[key] || SPEED_PRESETS.fast;
    MIN_DELAY = p.min;
    MAX_DELAY = p.max;
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function randomDelay() {
    return sleep(Math.random() * (MAX_DELAY - MIN_DELAY) + MIN_DELAY);
  }

  async function scrollToBottom() {
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(SCROLL_DELAY);
  }

  function buttonLabel(btn) {
    const span = btn.querySelector('span');
    return (span ? span.textContent : btn.textContent || '').trim();
  }

  function cardForButton(btn) {
    let el = btn;
    for (let i = 0; i < 8 && el; i++) {
      if (el.querySelector?.('a[href*="/users/"]')) return el;
      el = el.parentElement;
    }
    return btn.parentElement || btn;
  }

  function findFollowButtons() {
    const cfg = loadCfg();
    const buttons = [];
    document.querySelectorAll('button').forEach((btn) => {
      if (buttonLabel(btn) !== 'Follow') return;
      if (cfg.skipMale && FL.genderFilter?.isMaleCard?.(cardForButton(btn))) return;
      if (cardForButton(btn).getAttribute?.('data-tbcc-fl-gender-hidden') === '1') return;
      buttons.push(btn);
    });
    return buttons;
  }

  async function followUser(button, retryCount = 0) {
    if (buttonLabel(button) !== 'Follow') return false;
    button.focus();
    await sleep(10 + Math.random() * 15);
    button.click();
    await sleep(75 + Math.random() * 50);
    const newText = buttonLabel(button);
    if (
      newText === 'Following' ||
      newText === 'Unfollow' ||
      newText === 'Follow pending' ||
      newText === 'Pending' ||
      button.disabled
    ) {
      followCount += 1;
      FL.autoFollow?.onProgress?.(followCount);
      return true;
    }
    if (retryCount < MAX_RETRIES) {
      await sleep(200 + Math.random() * 100);
      return followUser(button, retryCount + 1);
    }
    return false;
  }

  async function startAutoFollow() {
    if (isRunning) return;
    const cfg = loadCfg();
    applySpeed(cfg.speed);
    isRunning = true;
    followCount = 0;
    FL.autoFollow?.onState?.(true, followCount);

    const processed = new WeakSet();
    let consecutiveEmpty = 0;

    while (isRunning) {
      const all = findFollowButtons();
      const fresh = all.filter((b) => !processed.has(b));
      if (!fresh.length) {
        consecutiveEmpty += 1;
        if (consecutiveEmpty >= 3) {
          const before = all.length;
          await scrollToBottom();
          await sleep(SCROLL_DELAY / 2);
          const after = findFollowButtons().length;
          if (after <= before) break;
          consecutiveEmpty = 0;
          continue;
        }
        await sleep(200);
        continue;
      }
      consecutiveEmpty = 0;
      for (const btn of fresh) {
        if (!isRunning) break;
        processed.add(btn);
        await followUser(btn);
        if (isRunning) await randomDelay();
      }
      if (!isRunning) break;
      if (fresh.length < 10) await scrollToBottom();
      else await sleep(50);
    }

    isRunning = false;
    FL.autoFollow?.onState?.(false, followCount);
  }

  function stopAutoFollow() {
    isRunning = false;
    FL.autoFollow?.onState?.(false, followCount);
  }

  function isKinkstersPage() {
    return /\/kinksters/i.test(location.pathname);
  }

  FL.autoFollow = {
    SPEED_PRESETS,
    loadCfg,
    saveCfg,
    start: startAutoFollow,
    stop: stopAutoFollow,
    isRunning: () => isRunning,
    getCount: () => followCount,
    onProgress: null,
    onState: null,
  };

  FL.features = FL.features || {};
  FL.features.autoFollow = {
    start() {
      if (started) return;
      started = true;
      const cfg = loadCfg();
      applySpeed(cfg.speed);
      // Auto-open suite overlay + optionally start on kinksters
      if (isKinkstersPage()) {
        setTimeout(() => {
          FL.overlay?.open?.('autofollow');
          if (cfg.autoStartOnKinksters && !isRunning) {
            startAutoFollow();
          }
        }, 800);
      }
      this._unsubSpa = S.spa.onChange(() => {
        if (isKinkstersPage()) setTimeout(() => FL.overlay?.open?.('autofollow'), 400);
      });
    },
    stop() {
      started = false;
      stopAutoFollow();
      this._unsubSpa?.();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
