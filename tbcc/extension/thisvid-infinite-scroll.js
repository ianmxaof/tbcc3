/**
 * TBCC ThisVid infinite scroll — n+1 HTML fetch engine with hard RAM caps.
 * Shared by content script + Node stress tests (single source of truth).
 *
 * Invariants (must hold under any stress):
 *  - pagesLoadedExtra <= resolveLimits().maxPages <= HARD.MAX_EXTRA_PAGES
 *  - cardCount <= resolveLimits().maxCards <= HARD.MAX_CARDS_IN_DOM (after each successful load)
 *  - at most one in-flight fetch (loadingPage)
 *  - no loads on blocked pathnames / hidden tabs
 *  - bare /members/{id}/ never treated as a page index
 *  - response HTML / thumbs per page bounded
 */
(function (root) {
  'use strict';

  const HARD = Object.freeze({
    MAX_EXTRA_PAGES: 12,
    MAX_CARDS_IN_DOM: 120,
    MAX_THUMBS_PER_PAGE: 60,
    MAX_HTML_BYTES: 1_500_000,
    DEFAULT_EXTRA_PAGES: 3,
    DEFAULT_CARDS: 64,
    DEFAULT_COOLDOWN_MS: 2000,
    MIN_COOLDOWN_MS: 1000,
    MAX_COOLDOWN_MS: 8000,
  });

  function clampInt(raw, min, max, fallback) {
    const n = parseInt(raw, 10);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
  }

  function resolveLimits(settings) {
    const s = settings || {};
    return {
      maxPages: clampInt(s.infiniteMaxPages, 1, HARD.MAX_EXTRA_PAGES, HARD.DEFAULT_EXTRA_PAGES),
      maxCards: clampInt(s.infiniteMaxCards, 24, HARD.MAX_CARDS_IN_DOM, HARD.DEFAULT_CARDS),
      cooldownMs: clampInt(
        s.infiniteCooldownMs,
        HARD.MIN_COOLDOWN_MS,
        HARD.MAX_COOLDOWN_MS,
        HARD.DEFAULT_COOLDOWN_MS
      ),
    };
  }

  /**
   * Trailing /N/ is a list page index. Never treat bare /members/{id}/ as a page.
   */
  function pathPageParts(pathname) {
    const path = String(pathname || '').replace(/\/$/, '') || '';
    if (/^\/members\/\d+$/.test(path)) return null;
    if (/\/videos\/[^/]+$/.test(path)) return null;
    const m = path.match(/^(.*)\/(\d+)$/);
    if (!m) return null;
    const page = parseInt(m[2], 10);
    if (!(page > 0)) return null;
    return { base: m[1], page };
  }

  function pageAllowsInfiniteScroll(pathname, hints) {
    const p = String(pathname || '');
    const h = hints || {};
    if (h.isVideoWatchPage === true) return false;
    if (h.isMemberProfilePage === true) return false;
    if (h.isMemberDirectoryPage === true) return false;
    if (/^\/videos\/[^/]+\/?$/i.test(p)) return false;
    if (/^\/members\/\d+\/?$/.test(p)) return false;
    if (/\/members\/\d+\/(friends|wall|photo|albums)/i.test(p)) return false;
    if (/^\/community(\/|$)/i.test(p)) return false;
    if (/^\/members\/?$/i.test(p)) return false;
    return true;
  }

  function buildUrlForPage(ctx) {
    const page = Math.max(1, parseInt(ctx.page, 10) || 1);
    const href = String(ctx.href || 'https://thisvid.com/');
    const u = new URL(href);
    if (u.searchParams.has('page') || u.searchParams.has('from')) {
      if (u.searchParams.has('page')) u.searchParams.set('page', String(page));
      if (u.searchParams.has('from')) u.searchParams.set('from', String(page));
      return u.href;
    }
    const pathname = ctx.pathname != null ? String(ctx.pathname) : u.pathname;
    const origin = ctx.origin || u.origin;
    const parts = pathPageParts(pathname);
    if (parts) return `${origin}${parts.base}/${page}/`;
    if (ctx.pagerHref) return String(ctx.pagerHref);
    const path = pathname.replace(/\/$/, '') || '';
    if (path && page > 1) return `${origin}${path}/${page}/`;
    u.pathname = pathname;
    u.searchParams.set('page', String(page));
    return u.href;
  }

  function detectCurrentPageFromLocation(href, pathname) {
    const u = new URL(String(href || 'https://thisvid.com/'), 'https://thisvid.com');
    if (u.searchParams.has('page')) {
      return Math.max(1, parseInt(u.searchParams.get('page'), 10) || 1);
    }
    const parts = pathPageParts(pathname != null ? pathname : u.pathname);
    if (parts) return parts.page;
    return 1;
  }

  /**
   * Pure prune: cards are { href, page, mediaBytes? }.
   * Drops oldest pages first, then oldest cards, until <= maxCards.
   */
  function pruneCards(cards, maxCards, currentPage) {
    const list = Array.isArray(cards) ? cards.slice() : [];
    if (list.length <= maxCards) return { cards: list, removed: 0 };

    const byPage = new Map();
    for (const c of list) {
      const p = parseInt(c.page, 10) || 0;
      if (!byPage.has(p)) byPage.set(p, []);
      byPage.get(p).push(c);
    }
    const pagesAsc = [...byPage.keys()].sort((a, b) => a - b);
    let removed = 0;
    let kept = list.slice();

    for (const page of pagesAsc) {
      if (kept.length <= maxCards) break;
      if (page === currentPage && pagesAsc.length > 1) continue;
      const drop = new Set(byPage.get(page) || []);
      const before = kept.length;
      kept = kept.filter((c) => !drop.has(c));
      removed += before - kept.length;
    }

    while (kept.length > maxCards) {
      kept.shift();
      removed += 1;
    }
    return { cards: kept, removed };
  }

  /**
   * Extract video thumb hrefs from ThisVid-like HTML (n+1 response).
   */
  function extractVideoHrefsFromHtml(html) {
    const text = String(html || '');
    const out = [];
    const seen = new Set();
    const re = /href="(https?:\/\/[^"]*\/videos\/[^"]+|\/videos\/[^"]+)"/gi;
    let m;
    while ((m = re.exec(text)) && out.length < HARD.MAX_THUMBS_PER_PAGE * 2) {
      let href = m[1].replace(/#.*$/, '');
      if (!/\/videos\//i.test(href)) continue;
      if (href.startsWith('/')) href = `https://thisvid.com${href}`;
      if (seen.has(href)) continue;
      seen.add(href);
      out.push(href);
      if (out.length >= HARD.MAX_THUMBS_PER_PAGE) break;
    }
    return out;
  }

  /**
   * Headless / injectable n+1 engine used by stress tests and (optionally) the content script.
   *
   * host hooks:
   *  - fetch(url) -> { ok, status, text(), byteLength? }
   *  - getPathname(), getHref(), getOrigin()
   *  - isHidden(), pageHints()
   *  - getSettings()
   *  - onStatus?(msg)
   */
  class InfiniteScrollEngine {
    constructor(host) {
      this.host = host || {};
      this.currentPage = 1;
      this.loadingPage = false;
      this.reachedEnd = false;
      this.pagesLoadedExtra = 0;
      this.seenHrefs = new Set();
      this.cards = [];
      this.stats = {
        fetches: 0,
        bytesFetched: 0,
        appended: 0,
        pruned: 0,
        rejected: 0,
        blocked: 0,
      };
    }

    limits() {
      return resolveLimits(this.host.getSettings ? this.host.getSettings() : {});
    }

    allowed() {
      const pathname = this.host.getPathname ? this.host.getPathname() : '/';
      const hints = this.host.pageHints ? this.host.pageHints() : {};
      return pageAllowsInfiniteScroll(pathname, hints);
    }

    seed(cards) {
      for (const c of cards || []) {
        if (c.href) this.seenHrefs.add(c.href);
        this.cards.push({
          href: c.href,
          page: c.page || this.currentPage,
          mediaBytes: c.mediaBytes || 0,
        });
      }
    }

    resetForSetup(startPage) {
      this.currentPage = Math.max(1, parseInt(startPage, 10) || 1);
      this.reachedEnd = false;
      this.pagesLoadedExtra = 0;
      this.loadingPage = false;
      // Keep existing landing cards; re-seed seen
      this.seenHrefs = new Set(this.cards.map((c) => c.href).filter(Boolean));
      const { maxCards } = this.limits();
      const pruned = pruneCards(this.cards, maxCards, this.currentPage);
      this.stats.pruned += pruned.removed;
      this.cards = pruned.cards;
    }

    assertInvariants() {
      const { maxPages, maxCards } = this.limits();
      if (this.pagesLoadedExtra > maxPages) {
        throw new Error(`invariant: pagesLoadedExtra ${this.pagesLoadedExtra} > maxPages ${maxPages}`);
      }
      if (this.pagesLoadedExtra > HARD.MAX_EXTRA_PAGES) {
        throw new Error(`invariant: pagesLoadedExtra exceeds HARD.MAX_EXTRA_PAGES`);
      }
      if (this.cards.length > maxCards) {
        throw new Error(`invariant: cards ${this.cards.length} > maxCards ${maxCards}`);
      }
      if (this.cards.length > HARD.MAX_CARDS_IN_DOM) {
        throw new Error(`invariant: cards exceed HARD.MAX_CARDS_IN_DOM`);
      }
    }

    async loadNextPage() {
      const settings = this.host.getSettings ? this.host.getSettings() : {};
      if (settings.infiniteScroll === false || this.loadingPage || this.reachedEnd) {
        this.stats.blocked += 1;
        return 0;
      }
      if (!this.allowed()) {
        this.reachedEnd = true;
        this.stats.blocked += 1;
        return 0;
      }
      if (this.host.isHidden && this.host.isHidden()) {
        this.stats.blocked += 1;
        return 0;
      }

      const { maxPages, maxCards } = this.limits();
      if (this.pagesLoadedExtra >= maxPages) {
        this.reachedEnd = true;
        this.stats.blocked += 1;
        return 0;
      }
      if (this.cards.length >= maxCards) {
        const pruned = pruneCards(this.cards, maxCards, this.currentPage);
        this.cards = pruned.cards;
        this.stats.pruned += pruned.removed;
        if (this.cards.length >= maxCards) {
          this.reachedEnd = true;
          this.stats.blocked += 1;
          return 0;
        }
      }

      this.loadingPage = true;
      const nextPage = this.currentPage + 1;
      const href = this.host.getHref ? this.host.getHref() : 'https://thisvid.com/';
      const pathname = this.host.getPathname ? this.host.getPathname() : '/';
      const origin = this.host.getOrigin ? this.host.getOrigin() : 'https://thisvid.com';
      const url = buildUrlForPage({
        href,
        pathname,
        origin,
        page: nextPage,
        currentPage: this.currentPage,
        pagerHref: this.host.getPagerHref ? this.host.getPagerHref(nextPage) : null,
      });

      try {
        if (!this.host.fetch) throw new Error('host.fetch required');
        const res = await this.host.fetch(url);
        this.stats.fetches += 1;
        const html = typeof res.text === 'function' ? await res.text() : String(res.body || '');
        const byteLength =
          res.byteLength != null
            ? res.byteLength
            : typeof Buffer !== 'undefined'
              ? Buffer.byteLength(html, 'utf8')
              : html.length;
        this.stats.bytesFetched += byteLength;

        if (!res.ok) {
          if (res.status === 404 || res.status === 410) this.reachedEnd = true;
          this.stats.rejected += 1;
          throw new Error(`HTTP ${res.status}`);
        }
        if (byteLength > HARD.MAX_HTML_BYTES) {
          this.reachedEnd = true;
          this.stats.rejected += 1;
          if (this.host.onStatus) this.host.onStatus('TBCC infinite · HTML too large');
          return 0;
        }

        const hrefs = extractVideoHrefsFromHtml(html).slice(0, HARD.MAX_THUMBS_PER_PAGE);
        let added = 0;
        const batch = [];
        for (const h of hrefs) {
          if (this.seenHrefs.has(h)) continue;
          this.seenHrefs.add(h);
          batch.push({ href: h, page: nextPage, mediaBytes: 0 });
          added += 1;
        }
        if (!added) {
          this.reachedEnd = true;
          return 0;
        }

        this.cards.push(...batch);
        this.currentPage = nextPage;
        this.pagesLoadedExtra += 1;
        this.stats.appended += added;

        const pruned = pruneCards(this.cards, maxCards, this.currentPage);
        this.cards = pruned.cards;
        this.stats.pruned += pruned.removed;

        if (this.pagesLoadedExtra >= maxPages) this.reachedEnd = true;
        this.assertInvariants();
        return added;
      } catch (err) {
        if (this.host.onStatus) {
          this.host.onStatus(`TBCC infinite · fetch error (${err && err.message ? err.message : err})`);
        }
        return 0;
      } finally {
        this.loadingPage = false;
      }
    }

    /** Fire N parallel loadNextPage calls — must never exceed caps. */
    async stressBurst(n) {
      const jobs = [];
      for (let i = 0; i < n; i += 1) jobs.push(this.loadNextPage());
      await Promise.all(jobs);
      this.assertInvariants();
      return this.snapshot();
    }

    snapshot() {
      const lim = this.limits();
      return {
        currentPage: this.currentPage,
        pagesLoadedExtra: this.pagesLoadedExtra,
        cardCount: this.cards.length,
        reachedEnd: this.reachedEnd,
        loadingPage: this.loadingPage,
        limits: lim,
        stats: { ...this.stats },
        withinCaps:
          this.pagesLoadedExtra <= lim.maxPages &&
          this.pagesLoadedExtra <= HARD.MAX_EXTRA_PAGES &&
          this.cards.length <= lim.maxCards &&
          this.cards.length <= HARD.MAX_CARDS_IN_DOM,
      };
    }
  }

  const api = {
    HARD,
    clampInt,
    resolveLimits,
    pathPageParts,
    pageAllowsInfiniteScroll,
    buildUrlForPage,
    detectCurrentPageFromLocation,
    pruneCards,
    extractVideoHrefsFromHtml,
    InfiniteScrollEngine,
  };

  root.TBCCThisVidInfinite = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
