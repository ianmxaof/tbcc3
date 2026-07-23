/* ASL-style list filter: hide males / require female / require location text */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const HIDDEN = 'data-tbcc-fl-gender-hidden';
  const CFG_KEY = 'tbcc_fl_gender_filter_v1';
  const STYLE_ID = 'tbcc-fl-gender-style';

  const DEFAULT_CFG = {
    hideMale: true,
    hideFtM: false,
    /**
     * Hide cards whose sex parses as something other than F.
     * Unknown sex stays visible; auto-follow still refuses non-F when skip is on.
     */
    femaleOnly: true,
    locationInclude: '',
  };

  function loadCfg() {
    const saved = S.storage.get(CFG_KEY, null);
    return { ...DEFAULT_CFG, ...(saved && typeof saved === 'object' ? saved : {}) };
  }

  function saveCfg(cfg) {
    S.storage.set(CFG_KEY, cfg);
  }

  function ensureHideCss() {
    S.ensureStyle(
      STYLE_ID,
      `[${HIDDEN}="1"]{display:none!important;pointer-events:none!important;height:0!important;overflow:hidden!important;margin:0!important;padding:0!important;border:none!important}`
    );
  }

  /**
   * Parse FetLife vitals: "28F Domme", "27M Switch", "25MtF", "47CD/TV", "46M Exploring".
   */
  function parseSex(text) {
    const t = String(text || '')
      .replace(/\u00a0/g, ' ')
      .replace(/[\u200b\u200c\u200d\ufeff]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (!t) return null;
    const m =
      t.match(/\b(\d{1,2})\s*(CD\/TV|MtF|FtM|GF|GQ|IS|TG|TV|CD|[MF])\b/i) ||
      t.match(/\b(\d{1,2})(CD\/TV|MtF|FtM|GF|GQ|IS|TG|TV|CD|[MF])\b/i) ||
      t.match(/(?:^|[^\dA-Za-z])(\d{2})\s*([MF])(?=[^a-zA-Z]|$)/);
    if (!m) return null;
    return String(m[2]).toUpperCase();
  }

  function controlLabel(btn) {
    const span = btn.querySelector?.('span');
    return (span ? span.textContent : btn.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function isFollowControl(btn) {
    return /^(Follow|Following|Follow Pending|Follow Back|Unfollow)$/i.test(controlLabel(btn));
  }

  function followControls(el) {
    if (!el || !el.querySelectorAll) return [];
    return [...el.querySelectorAll('button')].filter(isFollowControl);
  }

  /**
   * Prefer short vitals nodes; fall back to full card text.
   * Does not depend on /users/id URLs (FetLife often uses nickname links).
   */
  function vitalsText(card) {
    if (!card) return '';
    const nodes = card.querySelectorAll?.(
      '.fl-member-card__info, [class*="member-card__info"], span, div, p, a'
    );
    if (nodes && nodes.length) {
      let best = '';
      for (const n of nodes) {
        // Own text only — avoid sucking in the whole grid.
        let own = '';
        for (const child of n.childNodes || []) {
          if (child.nodeType === 3) own += child.textContent || '';
        }
        own = own.replace(/\s+/g, ' ').trim();
        if (!own || own.length > 80) continue;
        if (parseSex(own)) return own;
        if (!best && /\d{2}/.test(own)) best = own;
      }
      if (best) return best;
    }
    return (card.innerText || card.textContent || '').replace(/\s+/g, ' ').trim();
  }

  /**
   * Walk up from a Follow button (or vitals node) to the single-profile card.
   * Stop when the ancestor contains more than one Follow control (grid).
   */
  function resolveMemberCard(start) {
    if (!start) return null;
    let el = start.nodeType === 1 ? start : start.parentElement;
    let fallback = null;
    for (let i = 0; i < 20 && el && el !== document.body && el !== document.documentElement; i++) {
      const controls = followControls(el);
      if (controls.length > 1) break;

      const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
      const sex = parseSex(vitalsText(el)) || parseSex(text);
      const hasImg = !!el.querySelector?.('img');

      if (controls.length === 1) {
        fallback = el;
        // Card sweet spot: one follow control + vitals and/or avatar.
        if (sex || (hasImg && text.length > 12 && text.length < 900)) {
          return el;
        }
      }

      // Started from a vitals span — grow until we pick up the Follow button.
      if (controls.length === 0 && sex && text.length < 120) {
        fallback = fallback || el;
      }

      el = el.parentElement;
    }
    return fallback;
  }

  function isMaleSex(sex, cfg) {
    if (!sex) return false;
    if (sex === 'M') return !!cfg.hideMale;
    if (sex === 'FTM' && cfg.hideFtM) return true;
    return false;
  }

  function locationNeedles(cfg) {
    return String(cfg.locationInclude || '')
      .split(/[,]+/)
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
  }

  function onGeoScopedListPage() {
    return /\/p\/[^/]+\/[^/]+\/[^/]+\/kinksters/i.test(location.pathname || '');
  }

  /** Single-member profile (not kinksters lists) — never ASL-remove header actions. */
  function onMemberProfilePage() {
    const path = String(location.pathname || '').replace(/\/+$/, '') || '/';
    if (/\/kinksters(\/|$)/i.test(path)) return false;
    if (/^\/users\/\d+(\/|$)/i.test(path)) return true;
    const m = path.match(
      /^\/([^/]+)(?:\/(about|pictures|videos|posts|friends|followers|following|activity|wall|relations))?$/i
    );
    if (!m) return false;
    const reserved = new Set([
      'home',
      'search',
      'login',
      'signup',
      'groups',
      'events',
      'videos',
      'pictures',
      'posts',
      'inbox',
      'notifications',
      'settings',
      'support',
      'p',
      'explore',
      'feed',
      'kinksters',
      'city',
      'places',
      'fetishes',
      'writings',
      'ads',
      'admin',
      'api',
      'oauth',
      'logout',
      'chat',
      'messages',
    ]);
    return !reserved.has(String(m[1] || '').toLowerCase());
  }

  function locationOk(text, cfg) {
    const needles = locationNeedles(cfg);
    if (!needles.length) return true;
    if (onGeoScopedListPage()) return true;
    const t = String(text || '').toLowerCase();
    return needles.some((n) => t.includes(n));
  }

  function shouldHideCard(text, cfg) {
    const sex = parseSex(text);
    if (isMaleSex(sex, cfg)) return true;
    if (cfg.femaleOnly && sex && sex !== 'F') return true;
    if (!locationOk(text, cfg)) return true;
    return false;
  }

  function shouldSkipFollow(card, cfg) {
    const c = cfg || loadCfg();
    const text = vitalsText(card) || (card?.innerText || card?.textContent || '');
    const sex = parseSex(text);
    if (isMaleSex(sex, c)) return true;
    if (c.femaleOnly) return sex !== 'F';
    if (c.hideMale && sex === 'M') return true;
    if (!locationOk(text, c)) return true;
    return false;
  }

  function hideCard(card) {
    if (!card || !card.isConnected) return;
    card.setAttribute(HIDDEN, '1');
    // Remove from DOM so flex/grid gaps collapse (display:none left empty slots).
    try {
      card.remove();
    } catch (_) {
      try {
        card.style.setProperty('display', 'none', 'important');
      } catch (__) { /* ignore */ }
    }
  }

  function unhideCard(card) {
    if (!card) return;
    card.removeAttribute(HIDDEN);
    try {
      card.style.removeProperty('display');
    } catch (_) { /* ignore */ }
  }

  /** Common parent of member cards (kinksters list). */
  function listRoot() {
    const marked = document.querySelector('[data-tbcc-fl-list="1"]');
    if (marked) return marked;
    const cards = cardRoots().filter((c) => c && c.isConnected);
    if (cards.length >= 2) {
      let a = cards[0];
      let b = cards[1];
      const path = new Set();
      for (let el = a; el; el = el.parentElement) path.add(el);
      for (let el = b; el; el = el.parentElement) {
        if (path.has(el) && el !== document.body && el !== document.documentElement) {
          return el;
        }
      }
    }
    if (cards[0]?.parentElement) return cards[0].parentElement;
    return null;
  }

  function cardRootsIn(root) {
    if (!root) return cardRoots();
    const cards = new Set();
    root.querySelectorAll('button').forEach((btn) => {
      if (!isFollowControl(btn)) return;
      const card = resolveMemberCard(btn);
      if (card && root.contains(card)) cards.add(card);
    });
    return [...cards];
  }

  function ensureListLayout(root) {
    if (!root) return;
    root.setAttribute('data-tbcc-fl-list', '1');
    S.ensureStyle(
      'tbcc-fl-list-layout',
      `[data-tbcc-fl-list="1"]{
        display:flex!important;flex-direction:column!important;flex-wrap:nowrap!important;
        gap:10px!important;width:100%!important;
      }
      [data-tbcc-fl-list="1"]>*{width:100%!important;max-width:100%!important;float:none!important;
        position:relative!important;left:auto!important;right:auto!important;grid-column:auto!important;
        grid-row:auto!important;}`
    );
  }

  /**
   * Discover cards primarily via Follow controls — works without /users/\d+ hrefs.
   */
  function cardRoots() {
    const cards = new Set();

    document.querySelectorAll('button').forEach((btn) => {
      if (!isFollowControl(btn)) return;
      const card = resolveMemberCard(btn);
      if (card) cards.add(card);
    });

    // Also anchor on short vitals text nodes (age+sex) in case Follow label differs.
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT, {
      acceptNode(node) {
        if (!node || node.id === 'tbcc-fl-overlay') return NodeFilter.FILTER_REJECT;
        if (node.closest?.('#tbcc-fl-overlay')) return NodeFilter.FILTER_REJECT;
        const tag = node.tagName;
        if (tag !== 'SPAN' && tag !== 'DIV' && tag !== 'P' && tag !== 'A' && tag !== 'LI') {
          return NodeFilter.FILTER_SKIP;
        }
        let own = '';
        for (const child of node.childNodes || []) {
          if (child.nodeType === 3) own += child.textContent || '';
        }
        own = own.replace(/\s+/g, ' ').trim();
        if (own.length < 3 || own.length > 64) return NodeFilter.FILTER_SKIP;
        if (!parseSex(own)) return NodeFilter.FILTER_SKIP;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    let n;
    while ((n = walker.nextNode())) {
      const card = resolveMemberCard(n);
      if (card) cards.add(card);
    }

    return [...cards];
  }

  function apply() {
    ensureHideCss();
    if (onMemberProfilePage()) {
      // Profile header Follow/Friend/Message share one ancestor with vitals — never strip them.
      return { cards: 0, hidden: 0, kept: 0, skipped: 'profile' };
    }
    const cfg = loadCfg();
    const active =
      cfg.hideMale || cfg.hideFtM || cfg.femaleOnly || locationNeedles(cfg).length > 0;

    // Mark list root *before* removals so infinite scroll can still append into an emptied list.
    const root = listRoot();
    if (root) ensureListLayout(root);

    if (!active) {
      return { cards: 0, hidden: 0, kept: cardRoots().length };
    }

    const cards = cardRoots();
    let hidden = 0;
    let kept = 0;
    for (const card of cards) {
      if (!card.isConnected) continue;
      const text = vitalsText(card) || card.innerText || card.textContent || '';
      if (shouldHideCard(text, cfg)) {
        hideCard(card);
        hidden += 1;
      } else {
        kept += 1;
      }
    }

    console.info(`[FL suite] ASL apply: ${cards.length} cards, ${hidden} removed, ${kept} kept`, cfg);
    return { cards: cards.length, hidden, kept };
  }

  FL.genderFilter = {
    loadCfg,
    saveCfg,
    parseSex,
    vitalsText,
    resolveMemberCard,
    cardRoots,
    cardRootsIn,
    listRoot,
    ensureListLayout,
    apply,
    onMemberProfilePage,
    shouldHideCard,
    shouldSkipFollow,
    isMaleCard(el) {
      const card = resolveMemberCard(el) || el;
      return shouldHideCard(vitalsText(card) || card?.innerText || '', loadCfg());
    },
    isFilteredCard(el) {
      const card = resolveMemberCard(el) || el;
      if (card?.getAttribute?.(HIDDEN) === '1') return true;
      return shouldHideCard(vitalsText(card) || card?.innerText || '', loadCfg());
    },
  };

  FL.features = FL.features || {};
  FL.features.genderFilter = {
    start() {
      ensureHideCss();
      apply();
      this._unsub = S.observer.subscribe(() => apply());
      this._unsubSpa = S.spa.onChange(() => setTimeout(apply, 200));
      [400, 1200, 2500].forEach((ms) => setTimeout(apply, ms));
    },
    stop() {
      this._unsub?.();
      this._unsubSpa?.();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
