/* Kinksters infinite scroll — append next pages; ASL-filter as we go */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const STATUS_ID = 'tbcc-fl-infinite-status';
  const MIN_KEEPERS = 16;
  const MAX_PAGES_PER_TOPUP = 8;
  const FETCH_GAP_MS = 450;

  let started = false;
  let loading = false;
  let stopped = false;
  let nextPage = null;
  let totalResults = null;
  let pageSize = 20;
  let pagesFetched = 0;
  let keepersAppended = 0;
  let seenKeys = new Set();
  let onScroll = null;
  let topUpTimer = null;

  function isKinkstersList() {
    return /\/kinksters/i.test(location.pathname || '');
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function parseResultMeta() {
    const text = document.body?.innerText || '';
    const m = text.match(/(\d[\d,]*)\s*[-–]\s*(\d[\d,]*)\s+of\s+(\d[\d,]*)/i);
    if (!m) return null;
    const start = parseInt(m[1].replace(/,/g, ''), 10);
    const end = parseInt(m[2].replace(/,/g, ''), 10);
    const total = parseInt(m[3].replace(/,/g, ''), 10);
    const size = Math.max(1, end - start + 1);
    const page = Math.max(1, Math.ceil(end / size));
    return { start, end, total, pageSize: size, page };
  }

  function pageFromUrl() {
    try {
      const p = new URL(location.href).searchParams.get('page');
      if (p) return Math.max(1, parseInt(p, 10) || 1);
    } catch (_) { /* ignore */ }
    return null;
  }

  function urlForPage(page) {
    const u = new URL(location.href);
    u.searchParams.set('page', String(page));
    return u.href;
  }

  function cardKey(card) {
    const links = [...(card.querySelectorAll?.('a[href]') || [])];
    for (const a of links) {
      const href = a.getAttribute('href') || '';
      if (/\/users\/\d+/.test(href)) return href.replace(/#.*$/, '');
      if (/^\/[A-Za-z0-9._-]{2,40}\/?$/.test(href)) return href.replace(/\/$/, '');
    }
    const t = (card.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60);
    return t || Math.random().toString(36);
  }

  function seedSeenFromDom() {
    const gf = FL.genderFilter;
    const cards = gf?.cardRoots?.() || [];
    for (const c of cards) seenKeys.add(cardKey(c));
  }

  function hidePagination() {
    S.ensureStyle(
      'tbcc-fl-hide-pager',
      `[data-tbcc-fl-pager-hidden="1"]{display:none!important}`
    );
    const candidates = [...document.querySelectorAll('nav, div, ul, ol')];
    for (const el of candidates) {
      if (el.closest?.('#tbcc-fl-overlay')) continue;
      const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
      if (t.length > 120) continue;
      if (/\bPrev\b/i.test(t) && /\bNext\b/i.test(t) && /\b\d+\b/.test(t)) {
        el.setAttribute('data-tbcc-fl-pager-hidden', '1');
      }
    }
  }

  function ensureStatus() {
    let el = document.getElementById(STATUS_ID);
    if (el) return el;
    S.ensureStyle(
      STATUS_ID + '-css',
      `#${STATUS_ID}{
        position:fixed;z-index:999990;left:50%;transform:translateX(-50%);bottom:18px;
        background:#141414;color:#e8e8e8;border:1px solid #333;border-radius:999px;
        padding:8px 16px;font:12px/1.3 system-ui,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.45);
        max-width:min(92vw,520px);text-align:center;pointer-events:none;
      }`
    );
    el = document.createElement('div');
    el.id = STATUS_ID;
    document.documentElement.appendChild(el);
    return el;
  }

  function updateStatus(extra) {
    const el = ensureStatus();
    const kept = FL.genderFilter?.cardRoots?.()?.length ?? 0;
    const total = totalResults != null ? totalResults.toLocaleString() : '?';
    const page = nextPage != null ? nextPage - 1 : '?';
    el.textContent =
      extra ||
      `TBCC infinite · ${kept} on page · through index page ${page} · ${total} total` +
        (loading ? ' · loading…' : stopped ? ' · done' : '');
  }

  function nearBottom() {
    const doc = document.documentElement;
    const scrollPos = window.scrollY + window.innerHeight;
    const height = Math.max(doc.scrollHeight, document.body?.scrollHeight || 0);
    return scrollPos >= height - 900;
  }

  async function fetchDoc(page) {
    const url = urlForPage(page);
    const res = await fetch(url, {
      credentials: 'include',
      headers: {
        Accept: 'text/html',
        'X-Requested-With': 'XMLHttpRequest',
      },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const html = await res.text();
    return new DOMParser().parseFromString(html, 'text/html');
  }

  /**
   * Extract member cards from a fetched document using Follow controls.
   */
  function extractCards(doc) {
    const gf = FL.genderFilter;
    if (!gf?.resolveMemberCard) return [];
    const out = [];
    const seen = new Set();
    doc.querySelectorAll('button').forEach((btn) => {
      const span = btn.querySelector('span');
      const lab = (span ? span.textContent : btn.textContent || '').replace(/\s+/g, ' ').trim();
      if (!/^(Follow|Following|Follow Pending|Follow Back|Unfollow)$/i.test(lab)) return;
      const card = gf.resolveMemberCard(btn);
      if (!card || seen.has(card)) return;
      seen.add(card);
      out.push(card);
    });
    return out;
  }

  function appendKeepers(cards) {
    const gf = FL.genderFilter;
    const cfg = gf?.loadCfg?.() || {};
    const root = gf?.listRoot?.();
    if (!root || !gf) return 0;
    gf.ensureListLayout?.(root);
    let added = 0;
    for (const remote of cards) {
      const text = gf.vitalsText(remote) || remote.innerText || '';
      if (gf.shouldHideCard(text, cfg)) continue;
      const key = cardKey(remote);
      if (seenKeys.has(key)) continue;
      const node = document.importNode(remote, true);
      // Strip scripts from imported HTML
      node.querySelectorAll?.('script').forEach((s) => s.remove());
      const localKey = cardKey(node);
      if (seenKeys.has(localKey)) continue;
      seenKeys.add(key);
      seenKeys.add(localKey);
      node.setAttribute('data-tbcc-fl-appended', '1');
      root.appendChild(node);
      added += 1;
      keepersAppended += 1;
    }
    return added;
  }

  async function loadNextPage() {
    if (loading || stopped || nextPage == null) return 0;
    loading = true;
    updateStatus();
    try {
      const doc = await fetchDoc(nextPage);
      const cards = extractCards(doc);
      const added = appendKeepers(cards);
      pagesFetched += 1;
      nextPage += 1;
      // Breadcrumb: last completed page while scrolling kinksters.
      try {
        const path = location.pathname.replace(/\/+$/, '');
        if (/\/kinksters$/i.test(path)) {
          FL.placeNav?.saveBookmark?.({
            path,
            page: Math.max(1, nextPage - 1),
            placeLabel: FL.placeNav.placeLabelFromPath?.(path) || '',
          });
        }
      } catch (_) { /* ignore */ }
      // Stop when a page returns no cards at all (end of list / blocked).
      if (!cards.length) {
        stopped = true;
      }
      // Soft cap: if we've passed total/pageSize
      if (totalResults != null && pageSize > 0) {
        const maxPage = Math.ceil(totalResults / pageSize);
        if (nextPage > maxPage + 1) stopped = true;
      }
      console.info(`[FL suite] infinite page→ +${added} keepers (${cards.length} raw)`, {
        nextPage,
        keepersAppended,
      });
      return added;
    } catch (err) {
      console.warn('[FL suite] infinite fetch failed', err);
      updateStatus(`TBCC infinite · fetch error — retry on scroll (${String(err.message || err)})`);
      return 0;
    } finally {
      loading = false;
      updateStatus();
      // Re-run ASL on any leftover males that snuck in via markup quirks
      try {
        FL.genderFilter?.apply?.();
      } catch (_) { /* ignore */ }
    }
  }

  async function topUp(minKeepers) {
    const target = minKeepers ?? MIN_KEEPERS;
    let guard = 0;
    while (!stopped && guard < MAX_PAGES_PER_TOPUP) {
      const kept = FL.genderFilter?.cardRoots?.()?.filter((c) => c.isConnected).length || 0;
      if (kept >= target && !nearBottom()) break;
      if (!nearBottom() && kept >= Math.min(8, target)) break;
      guard += 1;
      await loadNextPage();
      await sleep(FETCH_GAP_MS);
      if (stopped) break;
    }
    updateStatus();
  }

  function scheduleTopUp() {
    if (topUpTimer) clearTimeout(topUpTimer);
    topUpTimer = setTimeout(() => {
      topUpTimer = null;
      void topUp(MIN_KEEPERS);
    }, 200);
  }

  function onScrollHandler() {
    if (!started || stopped) return;
    if (nearBottom()) void topUp(MIN_KEEPERS);
  }

  FL.infiniteScroll = {
    status: () => ({
      nextPage,
      totalResults,
      pagesFetched,
      keepersAppended,
      loading,
      stopped,
    }),
    loadMore: () => topUp(MIN_KEEPERS + 20),
  };

  FL.features = FL.features || {};
  FL.features.infiniteScroll = {
    start() {
      if (started) return;
      if (!isKinkstersList()) return;
      started = true;
      stopped = false;
      loading = false;
      keepersAppended = 0;
      pagesFetched = 0;
      seenKeys = new Set();

      const meta = parseResultMeta();
      if (meta) {
        totalResults = meta.total;
        pageSize = meta.pageSize;
        nextPage = meta.page + 1;
      } else {
        nextPage = (pageFromUrl() || 1) + 1;
      }

      seedSeenFromDom();
      hidePagination();
      FL.genderFilter?.ensureListLayout?.(FL.genderFilter.listRoot?.());
      FL.genderFilter?.apply?.();
      updateStatus();

      onScroll = onScrollHandler;
      window.addEventListener('scroll', onScroll, { passive: true });
      this._unsubSpa = S.spa.onChange(() => {
        if (!isKinkstersList()) return;
        setTimeout(() => {
          hidePagination();
          seedSeenFromDom();
          scheduleTopUp();
        }, 300);
      });

      // After ASL removes males, refill the viewport from following pages.
      [600, 1500, 3000].forEach((ms) => setTimeout(scheduleTopUp, ms));
      console.info('[FL suite] infinite scroll on', { nextPage, totalResults, pageSize });
    },
    stop() {
      started = false;
      stopped = true;
      if (onScroll) window.removeEventListener('scroll', onScroll);
      onScroll = null;
      if (topUpTimer) clearTimeout(topUpTimer);
      this._unsubSpa?.();
      document.getElementById(STATUS_ID)?.remove();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
