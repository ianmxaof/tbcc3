/* Place → kinksters navigation (no hardcoded city) */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const CFG_KEY = 'tbcc_fl_place_nav_v1';
  const BOOKMARK_KEY = 'tbcc_fl_kinksters_bookmark_v1';
  const DEFAULT_CFG = {
    country: 'united-states',
    region: 'california',
    lastQuery: '',
    lastPath: '',
  };

  function loadCfg() {
    const saved = S.storage.get(CFG_KEY, null);
    return { ...DEFAULT_CFG, ...(saved && typeof saved === 'object' ? saved : {}) };
  }

  function saveCfg(partial) {
    const next = { ...loadCfg(), ...partial };
    S.storage.set(CFG_KEY, next);
    return next;
  }

  function slugifyPlace(name) {
    return String(name || '')
      .trim()
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/&/g, ' and ')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function kinkstersPath(placeName, cfg) {
    const c = cfg || loadCfg();
    const slug = slugifyPlace(placeName);
    if (!slug) return null;
    const country = slugifyPlace(c.country) || 'united-states';
    const region = slugifyPlace(c.region) || 'california';
    return `/p/${country}/${region}/${slug}/kinksters`;
  }

  function kinkstersUrl(placeName, cfg) {
    const path = kinkstersPath(placeName, cfg);
    if (!path) return null;
    return `https://fetlife.com${path}`;
  }

  /** Places search fallback when slug path is unknown / 404. */
  function placesSearchUrl(placeName) {
    const q = String(placeName || '').trim();
    if (!q) return null;
    // FetLife global search; user lands on results and can open Places → kinksters.
    return `https://fetlife.com/search?q=${encodeURIComponent(q)}`;
  }

  /** Human label from /p/{country}/{region}/{slug}/kinksters */
  function placeLabelFromPath(pathname) {
    const m = String(pathname || location.pathname).match(
      /\/p\/([^/]+)\/([^/]+)\/([^/]+)\/kinksters\/?/i
    );
    if (!m) return '';
    return decodeURIComponent(m[3]).replace(/-/g, ' ').trim();
  }

  function clearPlace() {
    return saveCfg({ lastQuery: '', lastPath: '' });
  }

  function loadBookmark() {
    const b = S.storage.get(BOOKMARK_KEY, null);
    return b && typeof b === 'object' && b.path ? b : null;
  }

  function saveBookmark(partial) {
    const prev = loadBookmark() || {};
    const next = {
      path: String(partial.path || prev.path || '').replace(/\?.*$/, ''),
      page: Math.max(1, Number(partial.page) || Number(prev.page) || 1),
      placeLabel: String(partial.placeLabel != null ? partial.placeLabel : prev.placeLabel || ''),
      ts: Date.now(),
    };
    if (!next.path) return null;
    S.storage.set(BOOKMARK_KEY, next);
    return next;
  }

  function clearBookmark() {
    S.storage.set(BOOKMARK_KEY, null);
  }

  function resumeBookmarkUrl(bm) {
    const b = bm || loadBookmark();
    if (!b?.path) return null;
    const page = Math.max(1, Number(b.page) || 1);
    const base = b.path.startsWith('http') ? b.path : `https://fetlife.com${b.path}`;
    try {
      const u = new URL(base);
      if (page > 1) u.searchParams.set('page', String(page));
      else u.searchParams.delete('page');
      return u.toString();
    } catch (_) {
      return page > 1 ? `${base}${base.includes('?') ? '&' : '?'}page=${page}` : base;
    }
  }

  /** Prefer live kinksters URL slug when on a place list; else lastQuery. */
  function displayPlaceQuery() {
    const fromUrl = placeLabelFromPath(location.pathname);
    if (fromUrl) return fromUrl;
    return loadCfg().lastQuery || '';
  }

  /**
   * Jump to kinksters for a place name.
   * Place is navigation-only — does NOT copy into ASL locationInclude (that caused
   * stale-city filters when switching regions).
   * @param {string} placeName e.g. "Palo Alto"
   * @param {{ syncAsl?: boolean, mode?: 'kinksters'|'search' }} opts
   */
  function goPlace(placeName, opts) {
    const q = String(placeName || '').trim();
    if (!q) return { ok: false, reason: 'empty' };
    const cfg = saveCfg({ lastQuery: q });
    // Opt-in only — never default-sync place into ASL vitals filter.
    if (opts?.syncAsl && FL.genderFilter?.saveCfg && FL.genderFilter?.loadCfg) {
      const g = FL.genderFilter.loadCfg();
      FL.genderFilter.saveCfg({ ...g, locationInclude: q });
      FL.genderFilter.apply?.();
    }
    const mode = opts?.mode || 'kinksters';
    if (mode === 'search') {
      const url = placesSearchUrl(q);
      if (!url) return { ok: false, reason: 'empty' };
      location.assign(url);
      return { ok: true, mode: 'search', url };
    }
    const path = kinkstersPath(q, cfg);
    const url = kinkstersUrl(q, cfg);
    saveCfg({ lastQuery: q, lastPath: path });
    if (path && location.pathname.replace(/\/+$/, '') === path.replace(/\/+$/, '')) {
      FL.overlay?.open?.('autofollow');
      return { ok: true, mode: 'kinksters', url, already: true };
    }
    location.assign(url);
    return { ok: true, mode: 'kinksters', url };
  }

  FL.placeNav = {
    CFG_KEY,
    BOOKMARK_KEY,
    loadCfg,
    saveCfg,
    clearPlace,
    loadBookmark,
    saveBookmark,
    clearBookmark,
    resumeBookmarkUrl,
    displayPlaceQuery,
    slugifyPlace,
    kinkstersPath,
    kinkstersUrl,
    placesSearchUrl,
    placeLabelFromPath,
    goPlace,
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
