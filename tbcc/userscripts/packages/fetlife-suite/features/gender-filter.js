/* Hide male profiles on member/kinksters lists (ASL-style sex parse) */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const HIDDEN = 'data-tbcc-fl-gender-hidden';
  const CFG_KEY = 'tbcc_fl_gender_filter_v1';

  const DEFAULT_CFG = {
    hideMale: true,
    /** Also hide FtM (female-to-male). Default off — only cis-coded M. */
    hideFtM: false,
  };

  function loadCfg() {
    const saved = S.storage.get(CFG_KEY, null);
    return { ...DEFAULT_CFG, ...(saved && typeof saved === 'object' ? saved : {}) };
  }

  function saveCfg(cfg) {
    S.storage.set(CFG_KEY, cfg);
  }

  /**
   * Parse FetLife vitals like "28F Domme", "32M sub", "25MtF", "40CD/TV".
   * Mirrors ASL Search getSex heuristics.
   */
  function parseSex(text) {
    const t = String(text || '').replace(/\s+/g, ' ');
    const m =
      t.match(/\b(\d{2})\s*(CD\/TV|MtF|FtM|GF|GQ|IS|TG|TV|CD|[MF])\b/i) ||
      t.match(/\b(\d{2})(CD\/TV|MtF|FtM|GF|GQ|IS|TG|[MF])\b/i);
    if (!m) return null;
    return m[2].toUpperCase();
  }

  function isMaleSex(sex, cfg) {
    if (!sex) return false;
    if (sex === 'M') return !!cfg.hideMale;
    if (sex === 'FTM' && cfg.hideFtM) return true;
    return false;
  }

  function cardRoots() {
    const sels = [
      'a[href*="/users/"]',
      '[data-component*="member" i]',
      'li',
      'article',
      '.user',
    ];
    // Prefer list items that contain a user link + vitals-ish text
    const links = [...document.querySelectorAll('a[href*="/users/"]')].filter((a) =>
      /\/users\/\d+/.test(a.getAttribute('href') || '')
    );
    const cards = new Set();
    for (const a of links) {
      let el = a;
      for (let i = 0; i < 5 && el; i++) {
        const text = el.innerText || '';
        if (text.length > 8 && text.length < 800 && parseSex(text)) {
          cards.add(el);
          break;
        }
        el = el.parentElement;
      }
    }
    return [...cards];
  }

  function apply() {
    const cfg = loadCfg();
    if (!cfg.hideMale && !cfg.hideFtM) {
      document.querySelectorAll(`[${HIDDEN}="1"]`).forEach((el) => el.removeAttribute(HIDDEN));
      return;
    }
    let hidden = 0;
    for (const card of cardRoots()) {
      const sex = parseSex(card.innerText || card.textContent || '');
      if (isMaleSex(sex, cfg)) {
        card.setAttribute(HIDDEN, '1');
        hidden += 1;
      } else {
        card.removeAttribute(HIDDEN);
      }
    }
    if (hidden) console.debug(`[FL suite] genderFilter hid ${hidden} male cards`);
  }

  FL.genderFilter = {
    loadCfg,
    saveCfg,
    parseSex,
    apply,
    isMaleCard(el) {
      const cfg = loadCfg();
      return isMaleSex(parseSex(el?.innerText || el?.textContent || ''), cfg);
    },
  };

  FL.features = FL.features || {};
  FL.features.genderFilter = {
    start() {
      S.ensureStyle(
        'tbcc-fl-gender-style',
        `[${HIDDEN}="1"]{display:none!important}`
      );
      apply();
      this._unsub = S.observer.subscribe(apply);
      this._unsubSpa = S.spa.onChange(() => setTimeout(apply, 200));
    },
    stop() {
      this._unsub?.();
      this._unsubSpa?.();
      document.querySelectorAll(`[${HIDDEN}="1"]`).forEach((el) => el.removeAttribute(HIDDEN));
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
