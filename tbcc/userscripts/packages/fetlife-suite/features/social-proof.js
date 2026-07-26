/* Profile social-proof counts — client-side DOM pad for Friends / Followers / Following */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const CFG_KEY = 'tbcc_fl_social_proof_v1';
  const ORIG_ATTR = 'data-tbcc-fl-count-orig';
  const KIND_ATTR = 'data-tbcc-fl-count-kind';

  const DEFAULT_CFG = {
    enabled: true,
    /** When set, only patch this profile nickname (e.g. freeUse-LongBoy). */
    nickname: '',
    friends: '',
    followers: '',
    following: '',
  };

  let started = false;

  function loadCfg() {
    const saved = S.storage.get(CFG_KEY, null);
    return { ...DEFAULT_CFG, ...(saved && typeof saved === 'object' ? saved : {}) };
  }

  function saveCfg(cfg) {
    S.storage.set(CFG_KEY, cfg);
  }

  function formatCount(n) {
    const s = String(n == null ? '' : n).replace(/[^\d]/g, '');
    if (!s) return '';
    return Number(s).toLocaleString('en-US');
  }

  function profileNicknameFromPath() {
    const path = location.pathname || '';
    const mUser = path.match(/\/users\/(\d+)/i);
    if (mUser) return null; // numeric id pages — match via link text later
    const mNick = path.match(/^\/([A-Za-z0-9._-]{2,40})\/?$/);
    if (mNick && !/^(home|search|groups|events|places|settings|inbox|notifications|p)$/i.test(mNick[1])) {
      return mNick[1];
    }
    // /nickname/about etc.
    const m2 = path.match(/^\/([A-Za-z0-9._-]{2,40})\//);
    if (m2 && !/^(users|p|home|search|groups|events|places|settings)$/i.test(m2[1])) return m2[1];
    return null;
  }

  function shouldApply(cfg) {
    if (!cfg.enabled) return false;
    const want = String(cfg.nickname || '').trim().toLowerCase();
    if (!want) {
      // No nickname locked — apply on any profile that has the three sections (for screenshots).
      return true;
    }
    const pathNick = (profileNicknameFromPath() || '').toLowerCase();
    if (pathNick && pathNick === want) return true;
    const title = (document.title || '').toLowerCase();
    if (title.includes(want.toLowerCase())) return true;
    // Nickname link in header
    const hit = [...document.querySelectorAll('a[href]')].some((a) => {
      const href = (a.getAttribute('href') || '').toLowerCase();
      return href === '/' + want || href === '/' + want + '/' || href.includes('/' + want);
    });
    return hit && /friends|followers|following/i.test(document.body?.innerText || '');
  }

  function ownText(el) {
    let t = '';
    for (const c of el.childNodes || []) {
      if (c.nodeType === 3) t += c.textContent || '';
    }
    return t.replace(/\s+/g, ' ').trim();
  }

  /**
   * Find nodes that display "N Friends|Followers|Following" (combined or split).
   */
  function findCountTargets() {
    const kinds = {
      friends: /friends/i,
      followers: /followers/i,
      following: /following/i,
    };
    const found = { friends: null, followers: null, following: null };

    const candidates = document.querySelectorAll('a, h1, h2, h3, h4, span, div, strong, button');
    for (const el of candidates) {
      if (el.closest?.('#tbcc-fl-overlay')) continue;
      const direct = ownText(el) || (el.childElementCount === 0 ? (el.textContent || '').replace(/\s+/g, ' ').trim() : '');
      const m = direct.match(/^([\d,]+)\s+(Friends|Followers|Following)$/i);
      if (m) {
        const kind = m[2].toLowerCase();
        if (!found[kind]) found[kind] = { el, mode: 'combined', orig: m[1] };
        continue;
      }
    }

    // Split: element that is only the label, previous sibling / parent starts with number
    for (const el of candidates) {
      if (el.closest?.('#tbcc-fl-overlay')) continue;
      const lab = (ownText(el) || (el.childElementCount === 0 ? (el.textContent || '').trim() : '')).replace(/\s+/g, ' ');
      for (const [kind, re] of Object.entries(kinds)) {
        if (found[kind]) continue;
        if (!re.test(lab) || lab.length > 12) continue;
        if (!/^(Friends|Followers|Following)$/i.test(lab)) continue;
        const parent = el.parentElement;
        if (!parent) continue;
        const pt = (parent.innerText || '').replace(/\s+/g, ' ').trim();
        const pm = pt.match(new RegExp('([\\d,]+)\\s+' + lab, 'i'));
        if (!pm) continue;
        // Prefer a child that is only digits
        let numEl = [...parent.querySelectorAll('span, div, a, strong, b')].find((n) =>
          /^[\d,]+$/.test((n.textContent || '').trim())
        );
        if (!numEl) numEl = parent;
        found[kind] = { el: numEl, mode: numEl === parent ? 'combined' : 'number', orig: pm[1], labelEl: el };
      }
    }

    return found;
  }

  function setNodeCount(target, value, kind) {
    if (!target?.el) return false;
    const el = target.el;
    if (!el.getAttribute(ORIG_ATTR)) {
      el.setAttribute(ORIG_ATTR, target.orig || (el.textContent || '').trim());
    }
    el.setAttribute(KIND_ATTR, kind);
    const formatted = formatCount(value);
    if (!formatted) return false;

    if (target.mode === 'combined' || /friends|followers|following/i.test(el.textContent || '')) {
      const label =
        kind === 'friends' ? 'Friends' : kind === 'followers' ? 'Followers' : 'Following';
      // Preserve structure: if single text node, replace; else set textContent carefully
      if (el.childElementCount === 0) {
        el.textContent = `${formatted} ${label}`;
      } else {
        // Replace first text-ish number occurrence in tree
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        let node;
        let done = false;
        while ((node = walker.nextNode())) {
          if (/^\s*[\d,]+\s*$/.test(node.textContent || '')) {
            node.textContent = formatted;
            done = true;
            break;
          }
          if (/^[\d,]+\s+(Friends|Followers|Following)\s*$/i.test((node.textContent || '').trim())) {
            node.textContent = `${formatted} ${label}`;
            done = true;
            break;
          }
        }
        if (!done) el.textContent = `${formatted} ${label}`;
      }
    } else {
      el.textContent = formatted;
    }
    return true;
  }

  function restoreAll() {
    document.querySelectorAll(`[${ORIG_ATTR}]`).forEach((el) => {
      const orig = el.getAttribute(ORIG_ATTR);
      const kind = el.getAttribute(KIND_ATTR);
      if (orig == null) return;
      if (/friends|followers|following/i.test(el.textContent || '') || !kind) {
        el.textContent = orig;
      } else {
        el.textContent = orig;
      }
      el.removeAttribute(ORIG_ATTR);
      el.removeAttribute(KIND_ATTR);
    });
  }

  function apply() {
    const cfg = loadCfg();
    if (!cfg.enabled || !shouldApply(cfg)) {
      return { ok: false, reason: 'skipped' };
    }
    const targets = findCountTargets();
    const result = { friends: false, followers: false, following: false };
    for (const kind of ['friends', 'followers', 'following']) {
      const raw = cfg[kind];
      if (raw === '' || raw == null) continue;
      if (!String(raw).replace(/[^\d]/g, '')) continue;
      result[kind] = setNodeCount(targets[kind], raw, kind);
    }
    console.info('[FL suite] socialProof apply', result, cfg);
    return { ok: true, result, targets };
  }

  FL.socialProof = {
    loadCfg,
    saveCfg,
    apply,
    restoreAll,
    formatCount,
    profileNicknameFromPath,
    findCountTargets,
  };

  FL.features = FL.features || {};
  FL.features.socialProof = {
    start() {
      if (started) return;
      started = true;
      apply();
      this._unsub = S.observer.subscribe(() => apply());
      this._unsubSpa = S.spa.onChange(() => setTimeout(apply, 250));
      [400, 1200].forEach((ms) => setTimeout(apply, ms));
    },
    stop() {
      started = false;
      this._unsub?.();
      this._unsubSpa?.();
      restoreAll();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
