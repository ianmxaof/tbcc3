/**
 * Adversarial stress suite for ThisVid n+1 HTML infinite scroll.
 * Proves hard caps cannot be breached under burst / huge-page / blocked-path abuse.
 *
 * Run: node --test tbcc/extension/tests/thisvid-infinite-scroll-stress.test.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { describe, it } from 'node:test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const TV = require(path.join(__dirname, '..', 'thisvid-infinite-scroll.js'));

const { HARD, resolveLimits, pathPageParts, pageAllowsInfiniteScroll, buildUrlForPage, InfiniteScrollEngine } =
  TV;

function fakePageHtml(page, count) {
  const bits = [];
  for (let i = 0; i < count; i += 1) {
    bits.push(
      `<a class="tumbpu" href="https://thisvid.com/videos/p${page}-v${i}/"><img srcset="a 1x, b 2x, c 3x" src="https://cdn.example/t${i}.jpg"></a>`
    );
  }
  // Pad with junk so size is realistic but under / over caps in specific tests
  return `<html><body><div class="thumbs">${bits.join('')}</div>${'<!--x-->'.repeat(50)}</body></html>`;
}

function makeHost(overrides = {}) {
  let hidden = false;
  let pathname = overrides.pathname || '/latest-updates/';
  let settings = {
    infiniteScroll: true,
    infiniteMaxPages: overrides.maxPages ?? 3,
    infiniteMaxCards: overrides.maxCards ?? 64,
    infiniteCooldownMs: 1000,
    ...(overrides.settings || {}),
  };
  const pageThumbs = overrides.pageThumbs ?? 48;
  const maxPage = overrides.serverPages ?? 200;

  return {
    getSettings: () => settings,
    setSettings: (s) => {
      settings = { ...settings, ...s };
    },
    getPathname: () => pathname,
    setPathname: (p) => {
      pathname = p;
    },
    getHref: () => `https://thisvid.com${pathname}`,
    getOrigin: () => 'https://thisvid.com',
    isHidden: () => hidden,
    setHidden: (v) => {
      hidden = v;
    },
    pageHints: () => overrides.pageHints || {},
    fetch: async (url) => {
      const u = new URL(url);
      let page = 1;
      const m = u.pathname.match(/\/(\d+)\/?$/);
      if (m && !/^\/members\/\d+$/.test(u.pathname.replace(/\/$/, ''))) {
        page = parseInt(m[1], 10);
      } else if (u.searchParams.has('page')) {
        page = parseInt(u.searchParams.get('page'), 10) || 1;
      }
      if (page > maxPage) return { ok: false, status: 404, text: async () => '' };
      if (overrides.hugeHtml) {
        const pad = 'x'.repeat(HARD.MAX_HTML_BYTES + 10_000);
        return { ok: true, status: 200, byteLength: pad.length, text: async () => pad };
      }
      const html = fakePageHtml(page, pageThumbs);
      return {
        ok: true,
        status: 200,
        byteLength: Buffer.byteLength(html, 'utf8'),
        text: async () => html,
      };
    },
  };
}

describe('ThisVid infinite n+1 — policy', () => {
  it('never treats bare /members/{id}/ as a page index', () => {
    assert.equal(pathPageParts('/members/143459/'), null);
    assert.equal(pathPageParts('/members/143459'), null);
    assert.deepEqual(pathPageParts('/members/143459/public_videos/2/'), {
      base: '/members/143459/public_videos',
      page: 2,
    });
    const next = buildUrlForPage({
      href: 'https://thisvid.com/members/143459/',
      pathname: '/members/143459/',
      origin: 'https://thisvid.com',
      page: 2,
    });
    // Must NOT become /members/143460/
    assert.equal(next.includes('/members/143460'), false);
    assert.match(next, /\/members\/143459\//);
  });

  it('blocks profile, watch, community, friends paths', () => {
    assert.equal(pageAllowsInfiniteScroll('/members/143459/'), false);
    assert.equal(pageAllowsInfiniteScroll('/videos/some-slug/'), false);
    assert.equal(pageAllowsInfiniteScroll('/community/'), false);
    assert.equal(pageAllowsInfiniteScroll('/members/1/friends/'), false);
    assert.equal(pageAllowsInfiniteScroll('/latest-updates/'), true);
    assert.equal(pageAllowsInfiniteScroll('/members/1/public_videos/'), true);
    assert.equal(pageAllowsInfiniteScroll('/categories/amateurs/'), true);
  });

  it('clamps legacy 40/600 settings to HARD ceilings', () => {
    const lim = resolveLimits({ infiniteMaxPages: 40, infiniteMaxCards: 600 });
    assert.equal(lim.maxPages, HARD.MAX_EXTRA_PAGES);
    assert.equal(lim.maxCards, HARD.MAX_CARDS_IN_DOM);
  });
});

describe('ThisVid infinite n+1 — stress', () => {
  it('sequential scroll never exceeds page or card caps', async () => {
    const host = makeHost({ maxPages: 3, maxCards: 64, pageThumbs: 48 });
    const eng = new InfiniteScrollEngine(host);
    eng.seed(
      Array.from({ length: 40 }, (_, i) => ({
        href: `https://thisvid.com/videos/seed-${i}/`,
        page: 1,
      }))
    );
    eng.resetForSetup(1);

    for (let i = 0; i < 50; i += 1) {
      await eng.loadNextPage();
      eng.assertInvariants();
    }

    const snap = eng.snapshot();
    assert.equal(snap.withinCaps, true);
    assert.ok(snap.pagesLoadedExtra <= 3);
    assert.ok(snap.cardCount <= 64);
    assert.equal(snap.reachedEnd, true);
    assert.ok(snap.stats.fetches <= 3);
  });

  it('100 parallel loadNextPage bursts never exceed caps (single-flight)', async () => {
    const host = makeHost({ maxPages: 5, maxCards: 80, pageThumbs: 60 });
    const eng = new InfiniteScrollEngine(host);
    eng.seed(
      Array.from({ length: 30 }, (_, i) => ({
        href: `https://thisvid.com/videos/seed-${i}/`,
        page: 1,
      }))
    );
    eng.resetForSetup(1);

    // Several waves of concurrent abuse (scroll spam)
    for (let wave = 0; wave < 8; wave += 1) {
      await eng.stressBurst(100);
      assert.equal(eng.snapshot().withinCaps, true);
    }

    const snap = eng.snapshot();
    assert.ok(snap.pagesLoadedExtra <= 5);
    assert.ok(snap.cardCount <= 80);
    assert.ok(snap.stats.fetches <= 5, `fetches ${snap.stats.fetches} should be <= 5`);
    assert.ok(snap.stats.blocked > 0, 'expected blocked attempts from single-flight / caps');
  });

  it('adversarial 500 thumbs/page still caps per-page extract and DOM cards', async () => {
    const host = makeHost({ maxPages: 12, maxCards: 120, pageThumbs: 500 });
    const eng = new InfiniteScrollEngine(host);
    eng.resetForSetup(1);

    for (let i = 0; i < 30; i += 1) await eng.loadNextPage();

    const snap = eng.snapshot();
    assert.ok(snap.pagesLoadedExtra <= HARD.MAX_EXTRA_PAGES);
    assert.ok(snap.cardCount <= HARD.MAX_CARDS_IN_DOM);
    // Each accepted page contributes at most MAX_THUMBS_PER_PAGE unique hrefs before prune
    assert.ok(snap.stats.appended <= HARD.MAX_EXTRA_PAGES * HARD.MAX_THUMBS_PER_PAGE);
    assert.equal(snap.withinCaps, true);
  });

  it('rejects oversized HTML and stops (no DOM growth)', async () => {
    const host = makeHost({ hugeHtml: true, maxPages: 12, maxCards: 120 });
    const eng = new InfiniteScrollEngine(host);
    eng.seed([{ href: 'https://thisvid.com/videos/a/', page: 1 }]);
    eng.resetForSetup(1);
    const before = eng.cards.length;
    const added = await eng.loadNextPage();
    assert.equal(added, 0);
    assert.equal(eng.cards.length, before);
    assert.equal(eng.reachedEnd, true);
    assert.ok(eng.stats.rejected >= 1);
  });

  it('hidden tab does not fetch', async () => {
    const host = makeHost({ maxPages: 8 });
    const eng = new InfiniteScrollEngine(host);
    eng.resetForSetup(1);
    host.setHidden(true);
    await eng.stressBurst(20);
    assert.equal(eng.stats.fetches, 0);
    assert.ok(eng.stats.blocked >= 20);
  });

  it('member profile pathname never fetches n+1', async () => {
    const host = makeHost({ pathname: '/members/143459/', maxPages: 12 });
    const eng = new InfiniteScrollEngine(host);
    eng.resetForSetup(1);
    await eng.stressBurst(50);
    assert.equal(eng.stats.fetches, 0);
    assert.equal(eng.reachedEnd, true);
  });

  it('public_videos path uses /N/ not member-id bump', async () => {
    const urls = [];
    const host = makeHost({
      pathname: '/members/143459/public_videos/',
      maxPages: 2,
      pageThumbs: 20,
    });
    const rawFetch = host.fetch;
    host.fetch = async (url) => {
      urls.push(url);
      return rawFetch(url);
    };
    const eng = new InfiniteScrollEngine(host);
    eng.resetForSetup(1);
    await eng.loadNextPage();
    assert.ok(urls[0].includes('/members/143459/public_videos/2/'));
    assert.equal(urls[0].includes('/members/143460'), false);
  });

  it('max-settings ceiling stress: 12 pages × 60 thumbs → ≤120 cards', async () => {
    const host = makeHost({
      maxPages: 999,
      maxCards: 9999,
      pageThumbs: 60,
      settings: { infiniteMaxPages: 999, infiniteMaxCards: 9999 },
    });
    // resolveLimits must clamp
    assert.equal(resolveLimits(host.getSettings()).maxPages, HARD.MAX_EXTRA_PAGES);
    assert.equal(resolveLimits(host.getSettings()).maxCards, HARD.MAX_CARDS_IN_DOM);

    const eng = new InfiniteScrollEngine(host);
    eng.resetForSetup(1);
    for (let i = 0; i < 100; i += 1) await eng.loadNextPage();
    const snap = eng.snapshot();
    assert.ok(snap.pagesLoadedExtra <= HARD.MAX_EXTRA_PAGES);
    assert.ok(snap.cardCount <= HARD.MAX_CARDS_IN_DOM);
    assert.equal(snap.withinCaps, true);
  });

  it('duplicate href pages stop without unbounded growth', async () => {
    const host = makeHost({ maxPages: 12, maxCards: 120, pageThumbs: 40 });
    // Always return the same thumbs (page 1 content)
    host.fetch = async () => {
      const html = fakePageHtml(1, 40);
      return { ok: true, status: 200, byteLength: html.length, text: async () => html };
    };
    const eng = new InfiniteScrollEngine(host);
    eng.seed(
      Array.from({ length: 40 }, (_, i) => ({
        href: `https://thisvid.com/videos/p1-v${i}/`,
        page: 1,
      }))
    );
    eng.resetForSetup(1);
    for (let i = 0; i < 20; i += 1) await eng.loadNextPage();
    assert.ok(eng.cards.length <= 120);
    assert.equal(eng.reachedEnd, true);
    // Only first fetch can add nothing new → stop; at most 1 fetch that finds dupes
    assert.ok(eng.stats.fetches <= 2);
  });
});
