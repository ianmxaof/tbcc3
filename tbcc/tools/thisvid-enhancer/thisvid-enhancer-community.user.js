// ==UserScript==
// @name         ThisVid Enhancer
// @namespace    https://sleazyfork.org/users/1618643-ianmxaof
// @homepageURL  https://telegram.me/aofsubscriptions_bot
// @version      1.0.0
// @license      MIT
// @author       AOF community fork
// @description  ThisVid browsing: title filters, privacy/duration/views sort, infinite scroll, download buttons, mass-friend helpers. Community build — no analytics, no upload library.
// Privacy: settings stay in localStorage; fetches go to thisvid.com.
// @match        https://thisvid.com/*
// @match        https://www.thisvid.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==


(function (global) {
  'use strict';
  function tbccWaitForModule(_id, fn) { fn(); }
  function tbccBindModuleDisableListener() {}
  global.tbccWaitForModule = tbccWaitForModule;
  global.tbccBindModuleDisableListener = tbccBindModuleDisableListener;
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/**
 * TBCC ThisVid enhancer — title include/exclude, privacy/duration/views sort,
 * strict no-gay filter, mass friend request, download, R2/media upload library → form fill.
 * Passive content script; toggle via TBCC: Site tools → ThisVid enhancer.
 * No tray/backend required for browse features (browser extension only).
 */
tbccWaitForModule('thisvid_enhancer', function () {
  (function () {
    'use strict';

    const COMMUNITY = typeof GM_info !== 'undefined';
    const SUITE_TITLE = COMMUNITY ? 'ThisVid Enhancer' : 'TBCC ThisVid';
    const STORE_KEY = 'tbccThisVidEnhancerSettings';
    const DEFAULTS = {
      titleInclude: '',
      titleExclude: '',
      downloadButton: true,
      infiniteScroll: true,
      /** Extra pages appended after the landing page (hard stop). Keep low — HD thumbs eat RAM. */
      infiniteMaxPages: 3,
      /** Sliding DOM cap — oldest loaded pages pruned when exceeded. */
      infiniteMaxCards: 64,
      /** Min ms between page fetches. */
      infiniteCooldownMs: 2000,
      /** @type {'all'|'public'|'private'} */
      privacyFilter: 'all',
      /** @type {'none'|'duration-desc'|'duration-asc'|'views-desc'|'views-asc'} */
      sortBy: 'none',
      /** Hide male/gay-coded titles + skip Gay orientation on mass-friend. */
      noGay: true,
      friendConcurrency: 3,
      friendDelayMs: 450,
      /** Your ThisVid channel — attached to friend-request messages for funnel routing. */
      promoProfileId: COMMUNITY ? '' : '7366294',
      useFriendMessage: !COMMUNITY,
      friendMessage: COMMUNITY
        ? ''
        : 'Hey — free daily drops on my channel → https://thisvid.com/members/7366294/',
    };

    const FRIEND_SENT_KEY = 'tbcc_tv_friend_sent_v1';

    /** Built-in deny list when noGay is on (title / attribute haystack). */
    const NO_GAY_KEYWORDS = [
      'gay',
      'gays',
      'twink',
      'twinks',
      'barebackgay',
      'gaysian',
      'm4m',
      'man4man',
      'men only',
      'only men',
      'boysex',
      'leather daddy',
      'daddy bears',
      'gay bear',
      'gay bears',
      'male only',
      'guys only',
      'frott',
      'bros fuck',
      'pigfuck',
      'bareback studs',
      'hung studs',
      'gay sex',
      'gayporn',
      'gay porn',
      'homo',
      'homosexual',
    ];

    function loadSettings() {
      try {
        return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(STORE_KEY) || '{}'));
      } catch (_) {
        return Object.assign({}, DEFAULTS);
      }
    }

    function saveSettings() {
      try {
        localStorage.setItem(STORE_KEY, JSON.stringify(settings));
      } catch (_) {
        /* ignore */
      }
    }

    let settings = loadSettings();

    function parseKeywords(raw) {
      return String(raw || '')
        .toLowerCase()
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
    }

    function cardTitle(el) {
      const link =
        (el.matches && el.matches('a[href*="/videos/"], a[href*="/video/"]') && el) ||
        el.closest?.('a[href*="/videos/"], a[href*="/video/"]') ||
        el.querySelector?.('a[href*="/videos/"], a[href*="/video/"]');
      const bits = [
        link?.getAttribute('title'),
        el.querySelector?.('.title')?.textContent,
        el.getAttribute?.('title'),
        link?.textContent,
      ];
      return bits
        .map((b) => String(b || '').trim())
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
    }

    function cardNodes() {
      return Array.from(
        document.querySelectorAll(
          'a.tumbpu, .tumbpu, .thumb-holder, .thumbs .thumb, a[href*="/videos/"], a[href*="/video/"]'
        )
      );
    }

    function cardWrap(el) {
      return el.closest('.tumbpu, .thumb-holder, .item, .thumb, .video-item') || el;
    }

    function parseDurationSeconds(raw) {
      const t = String(raw || '').trim();
      if (!t) return 0;
      const parts = t.split(':').map((p) => parseInt(p, 10));
      if (parts.some((n) => Number.isNaN(n))) return 0;
      if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
      if (parts.length === 2) return parts[0] * 60 + parts[1];
      return parts[0] || 0;
    }

    function parseViews(raw) {
      if (typeof globalThis.tbccParseAbbrevNumber === 'function') {
        return globalThis.tbccParseAbbrevNumber(raw);
      }
      // Fallback: do not strip commas before reading K/M (4,7M → 4.7M).
      const t = String(raw || '').trim();
      if (!t) return 0;
      const m = t.match(/(\d[\d.,]*)\s*([kmb])?/i);
      if (!m) return parseInt(t.replace(/\D/g, ''), 10) || 0;
      let rawNum = m[1];
      const u = (m[2] || '').toLowerCase();
      if (u) {
        rawNum = rawNum.replace(/,/g, '.');
        const parts = rawNum.split('.');
        if (parts.length > 2) rawNum = parts[0] + '.' + parts.slice(1).join('');
      } else {
        rawNum = rawNum.replace(/,/g, '');
      }
      let n = parseFloat(rawNum);
      if (Number.isNaN(n)) return 0;
      if (u === 'k') n *= 1e3;
      else if (u === 'm') n *= 1e6;
      else if (u === 'b') n *= 1e9;
      return Math.round(n);
    }

    function durationBandTag(sec) {
      const n = Number(sec) || 0;
      if (n <= 0) return null;
      if (n < 180) return 'dur_0_3m';
      if (n < 600) return 'dur_3_10m';
      if (n < 1200) return 'dur_10_20m';
      return 'dur_20m_plus';
    }

    function cardMeta(el) {
      const root = cardWrap(el);
      const durationEl = root.querySelector?.('.duration');
      const viewsEl = root.querySelector?.('.view, .views, .video-views');
      const authorEl =
        root.querySelector?.(
          'a[href*="/members/"]:not([href*="/friends"]):not([href*="/videos"])'
        ) ||
        root.querySelector?.('.username a[href*="/members/"], .author a[href*="/members/"], a.username');
      const isPrivate = !!(
        root.querySelector?.('.private, .icon-private') ||
        root.classList?.contains?.('private') ||
        /\bprivate\b/i.test(root.getAttribute?.('class') || '')
      );
      const uploader = String(authorEl?.textContent || '')
        .trim()
        .replace(/^@/, '')
        .slice(0, 80);
      return {
        root,
        duration: parseDurationSeconds(durationEl?.textContent),
        views: parseViews(viewsEl?.textContent),
        private: isPrivate,
        title: cardTitle(el),
        uploader: uploader || null,
      };
    }

    function matchesNoGay(title) {
      if (!settings.noGay) return true;
      const hay = String(title || '').toLowerCase();
      if (!hay) return true;
      // Word-ish match so "gay" does not false-positive on unrelated stems when possible
      return !NO_GAY_KEYWORDS.some((k) => {
        if (k.includes(' ')) return hay.includes(k);
        return new RegExp(`(?:^|[^a-z])${k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:[^a-z]|$)`, 'i').test(
          hay
        );
      });
    }

    function matchesTitle(el) {
      const title = cardTitle(el);
      if (!matchesNoGay(title)) return false;
      if (!title) return true;
      const exclude = parseKeywords(settings.titleExclude);
      if (exclude.some((k) => title.includes(k))) return false;
      const include = parseKeywords(settings.titleInclude);
      if (include.length && !include.every((k) => title.includes(k))) return false;
      return true;
    }

    function matchesPrivacy(el) {
      const mode = settings.privacyFilter || 'all';
      if (mode === 'all') return true;
      const { private: isPrivate } = cardMeta(el);
      if (mode === 'public') return !isPrivate;
      if (mode === 'private') return isPrivate;
      return true;
    }

    function cardVisible(el) {
      return matchesTitle(el) && matchesPrivacy(el);
    }

    function applyTitleFilter() {
      applyCardFilters();
    }

    function applyCardFilters() {
      cardNodes().forEach((el) => {
        const hide = !cardVisible(el);
        const wrap = cardWrap(el);
        wrap.classList.toggle('tbcc-tv-title-filtered', hide);
        if (wrap !== el) el.classList.toggle('tbcc-tv-title-filtered', hide);
      });
    }

    function applySort() {
      const mode = settings.sortBy || 'none';
      if (mode === 'none') return;
      const grid = findGridContainer();
      if (!grid) return;
      const nodes = cardNodes().filter((el) => {
        // Prefer top-level thumbs that are direct-ish children of grid
        const wrap = cardWrap(el);
        return wrap.parentElement === grid || el.parentElement === grid;
      });
      // Dedupe by wrap
      const seen = new Set();
      const wraps = [];
      for (const el of nodes) {
        const wrap = cardWrap(el);
        if (seen.has(wrap)) continue;
        seen.add(wrap);
        wraps.push(wrap);
      }
      if (wraps.length < 2) return;
      const scored = wraps.map((wrap) => {
        const meta = cardMeta(wrap);
        return { wrap, duration: meta.duration, views: meta.views };
      });
      scored.sort((a, b) => {
        if (mode === 'duration-desc') return b.duration - a.duration;
        if (mode === 'duration-asc') return a.duration - b.duration;
        if (mode === 'views-desc') return b.views - a.views;
        if (mode === 'views-asc') return a.views - b.views;
        return 0;
      });
      const frag = document.createDocumentFragment();
      scored.forEach(({ wrap }) => frag.appendChild(wrap));
      grid.appendChild(frag);
    }

    function applyAllGridControls() {
      applyCardFilters();
      applySort();
    }

    function isMemberProfilePage() {
      return /^\/members\/\d+\/?$/.test(location.pathname);
    }

    function isOwnMemberPage() {
      return !!(isMemberProfilePage() && document.querySelector('.my-avatar'));
    }

    /** Community / member directory (new members, search, girls/guys lists). */
    function isMemberDirectoryPage() {
      const p = location.pathname.replace(/\/+$/, '') || '/';
      if (/^\/community(\/|$)/i.test(p)) return true;
      if (/^\/members\/?$/i.test(p)) return true;
      if (/search.*member|members_search|list_members/i.test(p + location.search)) return true;
      // Heuristic: many member thumbs, few video links
      const memberThumbs = document.querySelectorAll('a.tumbpu[href*="/members/"], .tumbpu[href*="/members/"]');
      const videoThumbs = document.querySelectorAll('a.tumbpu[href*="/videos/"]');
      return memberThumbs.length >= 8 && memberThumbs.length > videoThumbs.length;
    }

    function memberIdFromPath(pathname) {
      const m = String(pathname || location.pathname).match(/\/members\/(\d+)/);
      return m ? m[1] : null;
    }

    function promoProfileId() {
      const raw = String(settings.promoProfileId || '').replace(/\D/g, '');
      if (raw) return raw;
      return COMMUNITY ? '' : '7366294';
    }

    function friendRequestMessage() {
      if (settings.useFriendMessage === false) return '';
      const msg = String(settings.friendMessage || '').trim();
      if (msg) return msg.slice(0, 400);
      return `Hey — free daily drops → https://thisvid.com/members/${promoProfileId()}/`.slice(0, 400);
    }

    function loadFriendSentSet() {
      try {
        const arr = JSON.parse(localStorage.getItem(FRIEND_SENT_KEY) || '[]');
        return new Set(Array.isArray(arr) ? arr.map(String) : []);
      } catch (_) {
        return new Set();
      }
    }

    function markFriendSent(id) {
      const set = loadFriendSentSet();
      set.add(String(id));
      // Cap so localStorage stays sane
      const list = [...set];
      if (list.length > 8000) list.splice(0, list.length - 8000);
      try {
        localStorage.setItem(FRIEND_SENT_KEY, JSON.stringify(list));
      } catch (_) {
        /* ignore */
      }
    }

    function collectVisibleMemberIds() {
      const own = promoProfileId();
      const seen = new Set();
      const ids = [];
      const nodes = document.querySelectorAll(
        'a.tumbpu[href*="/members/"], a[href*="/members/"][href]'
      );
      nodes.forEach((a) => {
        if (a.closest?.(`#${OVERLAY_ID}`)) return;
        const href = a.getAttribute('href') || a.href || '';
        // Skip friends-list pagination chrome links without a clear id
        const m = href.match(/\/members\/(\d+)/);
        if (!m) return;
        const id = m[1];
        if (!id || id === own || seen.has(id)) return;
        // Prefer avatar/card links over random nav
        const looksLikeCard =
          a.classList.contains('tumbpu') ||
          a.querySelector?.('img') ||
          a.closest?.('.tumbpu, .thumb-holder, .item');
        if (!looksLikeCard && !isMemberDirectoryPage()) return;
        seen.add(id);
        ids.push(id);
      });
      return ids;
    }

    function sleep(ms) {
      return new Promise((r) => setTimeout(r, ms));
    }

    async function fetchHtml(url) {
      const res = await fetch(url, {
        credentials: 'include',
        headers: { Accept: 'text/html', 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const html = await res.text();
      return new DOMParser().parseFromString(html, 'text/html');
    }

    function sendFriendRequest(id, message) {
      const mid = String(id || '').replace(/\D/g, '');
      if (!mid) return Promise.resolve(null);
      const msg = message == null ? friendRequestMessage() : String(message);
      const q = new URLSearchParams({
        action: 'add_to_friends_complete',
        function: 'get_block',
        block_id: 'member_profile_view_view_profile',
        format: 'json',
        mode: 'async',
        message: msg,
      });
      return fetch(`https://thisvid.com/members/${mid}/?${q}`, {
        credentials: 'include',
        headers: { Accept: 'application/json, text/javascript, */*; q=0.01', 'X-Requested-With': 'XMLHttpRequest' },
      });
    }

    function parseOrientation(doc) {
      let orientation = '';
      doc.querySelectorAll('.profile span, .user-info span, .info span').forEach((s) => {
        const t = String(s.textContent || '');
        if (/Orientation:/i.test(t)) {
          orientation = String(s.querySelector('a, b, strong, em')?.textContent || s.textContent || '')
            .replace(/Orientation:/i, '')
            .trim();
        }
      });
      return orientation;
    }

    function parseProfileCount(doc, selector) {
      const el = doc.querySelector(selector);
      if (!el) return 0;
      const m = String(el.textContent || '').match(/(\d[\d,]*)\s*$/);
      return m ? parseInt(m[1].replace(/,/g, ''), 10) || 0 : 0;
    }

    async function getMemberData(id) {
      const doc = await fetchHtml(`/members/${id}/`);
      return {
        orientation: parseOrientation(doc),
        friendsCount:
          parseProfileCount(doc, '#list_members_friends span') ||
          parseProfileCount(doc, '#list_members_friends .headline span') ||
          0,
        uploadedPrivate: parseProfileCount(
          doc,
          '.headline:has(+ #list_videos_private_videos_items) span'
        ),
        uploadedPublic: parseProfileCount(
          doc,
          '.headline:has(+ #list_videos_public_videos_items) span'
        ),
      };
    }

    function extractFriendIds(doc) {
      const root = doc.querySelector('#list_members_friends_items') || doc;
      return Array.from(root.querySelectorAll('a.tumbpu[href*="/members/"], a[href*="/members/"]'))
        .map((a) => {
          const m = (a.getAttribute('href') || '').match(/\/members\/(\d+)/);
          return m ? m[1] : null;
        })
        .filter(Boolean);
    }

    async function* iterMemberFriends(memberId) {
      const data = await getMemberData(memberId);
      const pages = Math.max(1, Math.ceil((data.friendsCount || 24) / 24));
      const seen = new Set();
      for (let p = 1; p <= pages; p++) {
        const doc = await fetchHtml(`https://thisvid.com/members/${memberId}/friends/${p}/`);
        for (const fid of extractFriendIds(doc)) {
          if (seen.has(fid)) continue;
          seen.add(fid);
          yield fid;
        }
      }
    }

    function orientationAllowed(orientation, mode) {
      const o = String(orientation || '').trim().toLowerCase();
      if (mode === 'everyone') return true;
      if (mode === 'no-gay') {
        // Strict: block Gay; allow Straight / Lesbian / Bisexual / empty
        return o !== 'gay';
      }
      if (mode === 'straight-lesbian') {
        return o === 'straight' || o === 'lesbian' || o === '';
      }
      return true;
    }

    let friendAbort = false;

    async function massFriendIdList(ids, mode, onProgress) {
      friendAbort = false;
      const concurrency = Math.max(1, Math.min(8, Number(settings.friendConcurrency) || 3));
      const delay = Math.max(100, Number(settings.friendDelayMs) || 450);
      const already = loadFriendSentSet();
      const own = promoProfileId();
      let sent = 0;
      let skipped = 0;
      let failed = 0;
      let deduped = 0;
      const queue = [...ids].filter((id) => {
        if (!id || id === own) return false;
        if (already.has(String(id))) {
          deduped += 1;
          return false;
        }
        return true;
      });

      async function handleOne(fid) {
        if (friendAbort) return;
        try {
          if (mode === 'everyone') {
            await sendFriendRequest(fid);
            markFriendSent(fid);
            sent += 1;
          } else {
            const data = await getMemberData(fid);
            if (!orientationAllowed(data.orientation, mode)) {
              skipped += 1;
            } else {
              await sendFriendRequest(fid);
              markFriendSent(fid);
              sent += 1;
            }
          }
        } catch (_) {
          failed += 1;
        }
        onProgress?.({ sent, skipped, failed, deduped, left: queue.length });
        await sleep(delay);
      }

      while (queue.length && !friendAbort) {
        const batch = queue.splice(0, concurrency);
        await Promise.all(batch.map((id) => handleOne(id)));
      }
      return { sent, skipped, failed, deduped, aborted: friendAbort };
    }

    async function massFriendRequests(mode, onProgress) {
      const memberId = memberIdFromPath();
      if (!memberId) throw new Error('Not on a member profile');
      await sendFriendRequest(memberId);
      markFriendSent(memberId);
      const ids = [];
      for await (const fid of iterMemberFriends(memberId)) {
        ids.push(fid);
      }
      return massFriendIdList(ids, mode, onProgress);
    }

    async function massFriendDirectoryVisible(mode, onProgress) {
      const ids = collectVisibleMemberIds();
      if (!ids.length) throw new Error('No member cards found on this page');
      return massFriendIdList(ids, mode, onProgress);
    }

    const OVERLAY_ID = 'tbcc-tv-overlay';
    const OVERLAY_TOP_KEY = 'tbcc_tv_overlay_top_v1';
    const OVERLAY_UI_KEY = 'tbcc_tv_overlay_ui_v1';
    const OVERLAY_PAGES_ALL = [
      { id: 'filters', title: 'Filters' },
      { id: 'friends', title: 'Friends' },
      { id: 'upload', title: 'Upload' },
      { id: 'meta', title: 'Meta' },
      { id: 'intel', title: 'Intel' },
      { id: 'grow', title: 'Grow' },
    ];
    const OVERLAY_PAGES = COMMUNITY
      ? OVERLAY_PAGES_ALL.filter((p) => p.id !== 'intel' && p.id !== 'upload')
      : OVERLAY_PAGES_ALL;

    const META_VIDEOS_KEY = 'tbcc_tv_meta_videos_v1';
    const TAG_LISTS_KEY = 'tbcc_tv_tag_lists_v1';
    const INTEL_ROWS_KEY = 'tbcc_tv_intel_rows_v1';
    const INTEL_META_KEY = 'tbcc_tv_intel_meta_v1';
    /** R2 /  queue for ThisVid my_video_upload form fill. */
    const UPLOAD_LIB_KEY = 'tbcc_tv_upload_library_v1';
    const UPLOAD_LIB_MAX = 80;

    let overlayCollapsed = true;
    let overlayPageIndex = 0;
    let overlayWidthMode = 'slim';
    let friendStatusText = 'Ready — No Gay skips orientation=Gay';
    let lastIntelBadgeCount = 0;

    function intelHeaderCount() {
      try {
        if (intelRowsCache && Array.isArray(intelRowsCache)) return intelRowsCache.length;
      } catch (_) {}
      return loadIntelRows().length;
    }

    function updateIntelHeaderBadge(opts) {
      if (COMMUNITY) return;
      const o = opts || {};
      const el = document.querySelector(`#${OVERLAY_ID} [data-tv-intel-count]`);
      const btn = document.querySelector(`#${OVERLAY_ID} .tbcc-intel-badge`);
      if (!el) return;
      const count = intelHeaderCount();
      const recording = loadIntelMeta().recordIntel !== false;
      el.textContent = String(count);
      if (btn) {
        btn.classList.toggle('off', !recording);
        btn.title = recording
          ? `Browse intel: ${count} rows · click for Intel settings`
          : 'Recording off — click to open Intel settings';
      }
      if (o.pulse && count > lastIntelBadgeCount) {
        el.style.transition = 'color 0.2s ease, transform 0.2s ease';
        el.style.color = '#fff';
        el.style.transform = 'scale(1.25)';
        setTimeout(() => {
          el.style.color = '';
          el.style.transform = '';
        }, 400);
      }
      lastIntelBadgeCount = count;
    }

    function openIntelSettingsPanel() {
      const idx = OVERLAY_PAGES.findIndex((p) => p.id === 'intel');
      if (idx >= 0) overlayPageIndex = idx;
      setOverlayCollapsed(false);
      renderOverlay();
      const root = document.getElementById(OVERLAY_ID);
      const body = root && root.querySelector('.tbcc-body');
      if (body) {
        body.scrollTop = 0;
        body.style.outline = '1px solid #7ec8e3';
        setTimeout(() => {
          body.style.outline = '';
        }, 900);
      }
    }

    function clampOverlayTop(px) {
      const max = Math.max(8, window.innerHeight - 140);
      return Math.min(max, Math.max(8, Math.round(Number(px) || 72)));
    }

    function loadOverlayTop() {
      try {
        return clampOverlayTop(JSON.parse(localStorage.getItem(OVERLAY_TOP_KEY) || '72'));
      } catch (_) {
        return 72;
      }
    }

    function saveOverlayTop(px) {
      try {
        localStorage.setItem(OVERLAY_TOP_KEY, JSON.stringify(clampOverlayTop(px)));
      } catch (_) {
        /* ignore */
      }
    }

    function loadOverlayUi() {
      try {
        const ui = JSON.parse(localStorage.getItem(OVERLAY_UI_KEY) || '{}');
        let idx = Number(ui.pageIndex);
        if (!Number.isFinite(idx) || idx < 0 || idx >= OVERLAY_PAGES.length) idx = 0;
        const w = String(ui.widthMode || 'slim');
        return {
          collapsed: ui.collapsed !== false,
          pageIndex: idx,
          widthMode: w === 'wide' || w === 'normal' || w === 'slim' ? w : 'slim',
        };
      } catch (_) {
        return { collapsed: true, pageIndex: 0, widthMode: 'slim' };
      }
    }

    function persistOverlayUi() {
      try {
        localStorage.setItem(
          OVERLAY_UI_KEY,
          JSON.stringify({
            collapsed: !!overlayCollapsed,
            pageIndex: overlayPageIndex,
            widthMode: overlayWidthMode,
          })
        );
      } catch (_) {
        /* ignore */
      }
    }

    function bindVerticalDrag(root, handle, opts = {}) {
      let drag = null;
      const DRAG_THRESHOLD = 5;
      const suppressClick = opts.suppressClickAfterDrag !== false;

      handle.addEventListener('pointerdown', (e) => {
        if (e.button != null && e.button !== 0) return;
        // Title bar: don't start drag from Hide / other controls
        if (opts.ignoreSelector && e.target?.closest?.(opts.ignoreSelector)) return;
        drag = {
          pointerId: e.pointerId,
          startY: e.clientY,
          startTop: root.getBoundingClientRect().top,
          moved: false,
        };
        try {
          handle.setPointerCapture(e.pointerId);
        } catch (_) {
          /* ignore */
        }
        e.preventDefault();
      });

      handle.addEventListener('pointermove', (e) => {
        if (!drag || e.pointerId !== drag.pointerId) return;
        const dy = e.clientY - drag.startY;
        if (!drag.moved && Math.abs(dy) < DRAG_THRESHOLD) return;
        drag.moved = true;
        root.style.top = `${clampOverlayTop(drag.startTop + dy)}px`;
        handle.style.cursor = 'grabbing';
      });

      const endDrag = (e) => {
        if (!drag || (e && e.pointerId !== drag.pointerId)) return;
        const wasDrag = drag.moved;
        if (wasDrag) saveOverlayTop(root.getBoundingClientRect().top);
        handle.style.cursor = 'grab';
        try {
          if (e) handle.releasePointerCapture(e.pointerId);
        } catch (_) {
          /* ignore */
        }
        drag = null;
        if (wasDrag && suppressClick) {
          handle.dataset.suppressClick = '1';
          setTimeout(() => {
            delete handle.dataset.suppressClick;
          }, 0);
        }
      };

      handle.addEventListener('pointerup', endDrag);
      handle.addEventListener('pointercancel', endDrag);
      handle.addEventListener('lostpointercapture', () => {
        if (drag) {
          if (drag.moved) saveOverlayTop(root.getBoundingClientRect().top);
          drag = null;
          handle.style.cursor = 'grab';
        }
      });
    }

    function bindChevronDrag(root, chevron) {
      bindVerticalDrag(root, chevron);
    }

    function syncOverlayCollapsed(root) {
      root.classList.toggle('collapsed', overlayCollapsed);
      root.classList.toggle('slim', overlayWidthMode === 'slim');
      root.classList.toggle('wide', overlayWidthMode === 'wide');
      const chevron = root.querySelector('.tbcc-chevron');
      if (chevron) chevron.textContent = overlayCollapsed ? 'TV ▸' : 'TV ◂';
      window.TBCCSuiteRail?.syncJumpStack({
        stackId: 'tbcc-tv-jump-stack',
        overlayEl: root,
        visible: true,
        collapsed: overlayCollapsed,
      });
    }

    function setOverlayCollapsed(next) {
      overlayCollapsed = !!next;
      const root = document.getElementById(OVERLAY_ID);
      if (root) syncOverlayCollapsed(root);
      persistOverlayUi();
    }

    function setFriendStatus(text) {
      friendStatusText = String(text || '');
      const el = document.getElementById('tbccTvFriendStatus');
      if (el) el.textContent = friendStatusText;
    }

    async function runFriendAction(mode, scope) {
      if (mode === 'stop') {
        friendAbort = true;
        setFriendStatus('Stopping…');
        return;
      }
      const root = document.getElementById(OVERLAY_ID);
      const buttons = root ? [...root.querySelectorAll('[data-mode]')] : [];
      if (mode === 'self') {
        const id = memberIdFromPath();
        setFriendStatus('Sending friend request…');
        try {
          await sendFriendRequest(id);
          markFriendSent(id);
          setFriendStatus('Friend request sent to this profile');
        } catch (err) {
          setFriendStatus(`Failed: ${err.message || err}`);
        }
        return;
      }
      const useDirectory = scope === 'community' || (scope !== 'profile' && isMemberDirectoryPage());
      setFriendStatus(
        useDirectory
          ? `Community bulk (${mode}) · ${collectVisibleMemberIds().length} visible…`
          : `Profile mass friend (${mode})…`
      );
      buttons.forEach((b) => {
        if (b.getAttribute('data-mode') !== 'stop') b.disabled = true;
      });
      try {
        const runner = useDirectory ? massFriendDirectoryVisible : massFriendRequests;
        const result = await runner(mode, ({ sent, skipped, failed, deduped }) => {
          setFriendStatus(
            `sent ${sent} · skipped ${skipped} · failed ${failed}` +
              (deduped ? ` · already ${deduped}` : '')
          );
        });
        setFriendStatus(
          `Done — sent ${result.sent} · skipped ${result.skipped} · failed ${result.failed}` +
            (result.deduped ? ` · already ${result.deduped}` : '') +
            (result.aborted ? ' (stopped)' : '')
        );
      } catch (err) {
        setFriendStatus(`Mass friend error: ${err.message || err}`);
      } finally {
        buttons.forEach((b) => {
          b.disabled = false;
        });
      }
    }

    function renderOverlayFilters(body) {
      body.innerHTML = `
        <p class="hint">Title filters + privacy/sort. No Gay is on by default (title deny-list).</p>
        <label class="field">Include (all must match)
          <input type="text" id="tbccTvInc" placeholder="e.g. milf blonde" autocomplete="off" />
        </label>
        <label class="field">Exclude (hide if any)
          <input type="text" id="tbccTvExc" placeholder="extra keywords" autocomplete="off" />
        </label>
        <label class="field">Privacy
          <select id="tbccTvPrivacy">
            <option value="all">All</option>
            <option value="public">Public only</option>
            <option value="private">Private only</option>
          </select>
        </label>
        <label class="field">Sort
          <select id="tbccTvSort">
            <option value="none">Default</option>
            <option value="duration-desc">Duration ↓</option>
            <option value="duration-asc">Duration ↑</option>
            <option value="views-desc">Views ↓</option>
            <option value="views-asc">Views ↑</option>
          </select>
        </label>
        <label class="row"><input type="checkbox" id="tbccTvNoGay" /> No Gay</label>
        <label class="row"><input type="checkbox" id="tbccTvInfinite" /> Infinite scroll</label>
        <label class="field">Max extra pages
          <input type="number" id="tbccTvInfPages" min="1" max="12" step="1" />
        </label>
        <label class="field">Max cards in DOM
          <input type="number" id="tbccTvInfCards" min="24" max="120" step="8" />
        </label>
        <p class="hint">Hard caps (≤12 pages / ≤120 cards). Profile &amp; directory pages never infinite-scroll (RAM).</p>
        <label class="row"><input type="checkbox" id="tbccTvDlBtn" /> Download button (watch pages)</label>
        <button type="button" class="ghost" id="tbccTvKwClear">Clear filters</button>
      `;

      const inc = body.querySelector('#tbccTvInc');
      const exc = body.querySelector('#tbccTvExc');
      const inf = body.querySelector('#tbccTvInfinite');
      const noGay = body.querySelector('#tbccTvNoGay');
      const dlBtn = body.querySelector('#tbccTvDlBtn');
      const infPages = body.querySelector('#tbccTvInfPages');
      const infCards = body.querySelector('#tbccTvInfCards');
      const privacy = body.querySelector('#tbccTvPrivacy');
      const sortBy = body.querySelector('#tbccTvSort');
      inc.value = settings.titleInclude || '';
      exc.value = settings.titleExclude || '';
      inf.checked = settings.infiniteScroll !== false;
      noGay.checked = settings.noGay !== false;
      dlBtn.checked = settings.downloadButton !== false;
      infPages.value = String(clampInt(settings.infiniteMaxPages, 1, 12, 3));
      infCards.value = String(clampInt(settings.infiniteMaxCards, 24, 120, 64));
      privacy.value = settings.privacyFilter || 'all';
      sortBy.value = settings.sortBy || 'none';

      let t = null;
      const live = () => {
        settings.titleInclude = inc.value.trim();
        settings.titleExclude = exc.value.trim();
        settings.infiniteScroll = !!inf.checked;
        settings.noGay = !!noGay.checked;
        settings.downloadButton = !!dlBtn.checked;
        settings.infiniteMaxPages = clampInt(infPages.value, 1, 12, 3);
        settings.infiniteMaxCards = clampInt(infCards.value, 24, 120, 64);
        settings.privacyFilter = privacy.value || 'all';
        settings.sortBy = sortBy.value || 'none';
        saveSettings();
        applyAllGridControls();
        updateScrollStatus();
        const bar = document.getElementById('tbcc-tv-kw-bar');
        if (bar) {
          const bi = bar.querySelector('[data-kw="inc"]');
          const be = bar.querySelector('[data-kw="exc"]');
          if (bi) bi.value = settings.titleInclude;
          if (be) be.value = settings.titleExclude;
        }
        if (settings.downloadButton) {
          addDownloadButton().catch(() => {});
        } else {
          removeDownloadButtons();
        }
      };
      const onInput = () => {
        clearTimeout(t);
        t = setTimeout(live, 250);
      };
      inc.addEventListener('input', onInput);
      exc.addEventListener('input', onInput);
      noGay.addEventListener('change', live);
      dlBtn.addEventListener('change', live);
      infPages.addEventListener('change', live);
      infCards.addEventListener('change', live);
      privacy.addEventListener('change', live);
      sortBy.addEventListener('change', live);
      inf.addEventListener('change', () => {
        live();
        if (inf.checked) {
          reachedEnd = false;
          pagesLoadedExtra = 0;
          setupInfiniteScroll();
        } else {
          window.removeEventListener('scroll', onScrollInfinite);
          document.getElementById('tbcc-tv-scroll-status')?.classList.remove('on');
        }
      });
      body.querySelector('#tbccTvKwClear').addEventListener('click', () => {
        inc.value = '';
        exc.value = '';
        privacy.value = 'all';
        sortBy.value = 'none';
        live();
      });
    }

    function loadJson(key, fallback) {
      try {
        const v = JSON.parse(localStorage.getItem(key) || 'null');
        return v == null ? fallback : v;
      } catch (_) {
        return fallback;
      }
    }

    function saveJson(key, value) {
      try {
        localStorage.setItem(key, JSON.stringify(value));
      } catch (_) {
        /* ignore */
      }
    }

    function loadMetaVideos() {
      const rows = loadJson(META_VIDEOS_KEY, []);
      return Array.isArray(rows) ? rows : [];
    }

    function saveMetaVideos(rows) {
      saveJson(META_VIDEOS_KEY, rows.slice(-500));
    }

    function loadTagLists() {
      const rows = loadJson(TAG_LISTS_KEY, []);
      return Array.isArray(rows) ? rows : [];
    }

    function saveTagLists(rows) {
      saveJson(TAG_LISTS_KEY, rows.slice(0, 80));
    }

    function loadIntelMeta() {
      if (COMMUNITY) {
        return { recordIntel: false, maxIntelRows: 0, tbccApiUrl: '' };
      }
      return Object.assign(
        {
          recordIntel: true,
          maxIntelRows: 5000,
          tbccApiUrl: '',
        },
        loadJson(INTEL_META_KEY, {})
      );
    }

    function saveIntelMeta(meta) {
      saveJson(INTEL_META_KEY, meta);
    }

    function loadIntelRows() {
      const rows = loadJson(INTEL_ROWS_KEY, []);
      return Array.isArray(rows) ? rows : [];
    }

    function saveIntelRows(rows, opts) {
      const o = opts || {};
      const meta = loadIntelMeta();
      if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.saveWithCapAndMaybePush === 'function') {
        globalThis.tbccBrowseIntel.saveWithCapAndMaybePush({
          rows,
          meta,
          skipAutoPush: !!o.skipAutoPush,
          applyTrimmed: (stored) => saveJson(INTEL_ROWS_KEY, stored),
          toast: (msg) => {
            try {
              showTvToast(msg);
            } catch (_) {}
          },
        });
        return;
      }
      const cap = Math.max(500, Number(meta.maxIntelRows) || 5000);
      saveJson(INTEL_ROWS_KEY, rows.slice(-cap));
    }

    function isVideoWatchPage() {
      return /^\/videos\/[^/]+\/?$/i.test(location.pathname);
    }

    function videoIdFromUrl(url) {
      const m = String(url || location.href).match(/\/videos\/([^/?#]+)/i);
      return m ? decodeURIComponent(m[1]).slice(0, 120) : '';
    }

    function scrapePageTags(doc) {
      const root = doc || document;
      const tags = [];
      root
        .querySelectorAll(
          '.tags a, .video-tags a, .categories a, a[href*="/categories/"], a[href*="/tags/"], a[href*="/tag/"], .info a[href*="search"]'
        )
        .forEach((a) => {
          const t = String(a.textContent || '')
            .trim()
            .replace(/^#/, '');
          if (t && t.length < 40 && !/^(home|login|upload|community)$/i.test(t)) {
            tags.push(t.toLowerCase());
          }
        });
      return [...new Set(tags)].slice(0, 40);
    }

    function scrapeCurrentVideoMeta() {
      const url = location.href.split('#')[0];
      const title =
        document.querySelector('h1, .headline h1, .video-title, .title-container h1')?.textContent?.trim() ||
        document.title.replace(/\s*[|\-–].*$/, '').replace(/ThisVid\.com/gi, '').trim();
      const tags = scrapePageTags(document);
      const author =
        document.querySelector('a.author, .username a[href*="/members/"], .video-author a')?.textContent?.trim() ||
        '';
      return {
        id: videoIdFromUrl(url) || String(Date.now()),
        url,
        title: String(title || '').slice(0, 200),
        tags,
        uploader: author.slice(0, 80),
        ts: Date.now(),
      };
    }

    function upsertMetaVideo(entry) {
      const rows = loadMetaVideos().filter((r) => r.url !== entry.url && r.id !== entry.id);
      rows.push(entry);
      saveMetaVideos(rows);
      return rows.length;
    }

    function dayKey(ts) {
      return new Date(ts || Date.now()).toISOString().slice(0, 10);
    }

    let intelRowsCache = null;
    let intelSeenDay = '';
    const intelSeenIds = new Set();

    function resetIntelMemoryCache() {
      intelRowsCache = null;
      intelSeenDay = '';
      intelSeenIds.clear();
    }

    function ensureIntelMemoryCache() {
      const day = new Date().toISOString().slice(0, 10);
      if (intelRowsCache && intelSeenDay === day) return intelRowsCache;
      intelRowsCache = loadIntelRows();
      intelSeenDay = day;
      intelSeenIds.clear();
      for (const r of intelRowsCache) {
        const id = String(r.album_id || r.entity_id || '');
        if (id && dayKey(r.captured_at) === day) intelSeenIds.add(id);
      }
      return intelRowsCache;
    }

    function recordIntelRowsBatch(newRows) {
      const list = Array.isArray(newRows) ? newRows : [];
      if (!list.length) return 0;
      const meta = loadIntelMeta();
      if (meta.recordIntel === false) return 0;
      const rows = ensureIntelMemoryCache();
      let added = 0;
      for (const row of list) {
        if (!row) continue;
        const id = String(row.album_id || row.entity_id || '');
        if (!id || intelSeenIds.has(id)) continue;
        intelSeenIds.add(id);
        rows.push(row);
        added += 1;
      }
      if (added) {
        intelRowsCache = rows;
        saveIntelRows(rows);
        try {
          updateIntelHeaderBadge({ pulse: true });
        } catch (_) {}
      }
      return added;
    }

    function recordIntelRow(row) {
      return recordIntelRowsBatch([row]) > 0;
    }

    function thumbToIntelRow(el) {
      const meta = cardMeta(el);
      const a =
        (el.matches?.('a[href*="/videos/"]') && el) ||
        el.querySelector?.('a[href*="/videos/"]') ||
        el.closest?.('a[href*="/videos/"]');
      const href = (a?.href || a?.getAttribute?.('href') || '').split('#')[0];
      if (!href || !/\/videos\//i.test(href)) return null;
      const id = videoIdFromUrl(href);
      if (!id) return null;
      const title = meta.title || cardTitle(el) || id;
      const tags = [];
      const band = durationBandTag(meta.duration);
      if (band) tags.push(band);
      if (meta.private) tags.push('private');
      else tags.push('public');
      return {
        platform: 'thisvid',
        captured_at: new Date().toISOString(),
        album_url: href.startsWith('http') ? href : `https://thisvid.com${href}`,
        album_id: id,
        entity_id: id,
        entity_url: href.startsWith('http') ? href : `https://thisvid.com${href}`,
        title: String(title).slice(0, 200),
        views: meta.views || null,
        likes: null,
        videos: 1,
        images: 0,
        total_duration_sec: meta.duration || 0,
        avg_duration_sec: meta.duration || 0,
        longest_clip_sec: meta.duration || 0,
        tags,
        format_bucket: meta.private ? 'private_video' : 'single_video',
        page_context: { path: location.pathname, page_num: currentPage || 1 },
        uploader: meta.uploader || null,
      };
    }

    function scanGridIntel() {
      const meta = loadIntelMeta();
      if (meta.recordIntel === false) return 0;
      ensureIntelMemoryCache();
      const pending = [];
      cardNodes().forEach((el) => {
        if (el.dataset.tbccTvIntel === '1') return;
        const row = thumbToIntelRow(el);
        el.dataset.tbccTvIntel = '1';
        if (!row) return;
        const id = String(row.album_id || row.entity_id || '');
        if (!id || intelSeenIds.has(id)) return;
        pending.push(row);
      });
      return recordIntelRowsBatch(pending);
    }

    function exportIntelJsonl() {
      const rows = loadIntelRows();
      const name = `thisvid-browse-intel-${new Date().toISOString().slice(0, 10)}.jsonl`;
      if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.exportJsonlSaveAs === 'function') {
        void globalThis.tbccBrowseIntel.exportJsonlSaveAs(rows, name).then((r) => {
          showTvToast(r && r.ok !== false ? `Save As · ${name}` : 'Export failed');
        });
        return;
      }
      const blob = new Blob(
        [rows.map((r) => JSON.stringify(r)).join('\n') + (rows.length ? '\n' : '')],
        { type: 'application/x-ndjson' }
      );
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      URL.revokeObjectURL(a.href);
    }

    async function pushIntelToTbcc() {
      const meta = loadIntelMeta();
      const rows = loadIntelRows();
      if (!rows.length) throw new Error('No intel rows');
      const url = String(meta.tbccApiUrl || '').trim();
      if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.postIntelRows === 'function') {
        const resp = await globalThis.tbccBrowseIntel.postIntelRows(url, rows);
        const keep = Math.max(100, Math.floor(Math.max(500, meta.maxIntelRows || 5000) * 0.2));
        saveIntelRows(rows.slice(-keep), { skipAutoPush: true });
        return resp.appended != null ? resp.appended : rows.length;
      }
      if (!url) throw new Error('Set TBCC ingest URL in Intel');
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return rows.length;
    }

    function parseTagLine(raw) {
      return String(raw || '')
        .split(/[,;\n]+/)
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean);
    }

    function loadUploadLibrary() {
      try {
        const rows = JSON.parse(localStorage.getItem(UPLOAD_LIB_KEY) || '[]');
        return Array.isArray(rows) ? rows : [];
      } catch (_) {
        return [];
      }
    }

    function saveUploadLibrary(rows) {
      try {
        localStorage.setItem(UPLOAD_LIB_KEY, JSON.stringify((rows || []).slice(0, UPLOAD_LIB_MAX)));
      } catch (_) {
        /* ignore */
      }
    }

    function extractHttpUrls(raw) {
      const found = String(raw || '').match(/https?:\/\/[^\s<>"']+/gi) || [];
      return found.map((u) => u.replace(/[),.;]+$/g, '')).filter(Boolean);
    }

    function stemFromMediaUrl(url) {
      try {
        const path = new URL(url).pathname;
        const base = decodeURIComponent(path.split('/').pop() || '');
        return base.replace(/\.(mp4|webm|mov|m4v|mkv)$/i, '') || base;
      } catch (_) {
        return '';
      }
    }

    /** Build title/tags/description defaults from AOF_*_t.me_aofmainhub style CDN names. */
    function draftFromMediaUrls(urls) {
      const list = (urls || []).map((u) => String(u || '').trim()).filter(Boolean);
      const primary =
        list.find((u) => /media\.powercore\.app/i.test(u)) ||
        list.find((u) => /\.r2\.dev/i.test(u)) ||
        list[0] ||
        '';
      const alt = list.find((u) => u !== primary) || '';
      const stem = stemFromMediaUrl(primary) || stemFromMediaUrl(alt);
      const parts = stem.split(/[_-]+/).filter(Boolean);
      const skip = new Set(['t', 'me', 'telegram', 'com', 'www']);
      const tagBits = parts
        .map((p) => p.replace(/^@+/, '').toLowerCase())
        .filter((p) => p.length >= 2 && !skip.has(p) && !/^\d+$/.test(p));
      // Prefer readable title: "AOF favs 00025" from AOF_favs_00025_…
      let title = stem.replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
      const m = stem.match(/^AOF[_-](.+?)[_-](\d{3,})[_-]/i);
      if (m) {
        title = `AOF ${m[1].replace(/[_-]+/g, ' ')} ${m[2]}`.replace(/\s+/g, ' ').trim();
      }
      if (/aofmainhub/i.test(stem) && !/aofmainhub/i.test(title)) {
        title = `${title} · telegram.me/aofmainhub`.slice(0, 120);
      }
      const tags = Array.from(new Set(['aof', 'aofmainhub'].concat(tagBits))).slice(0, 16);
      const linkBlock = [primary, alt].filter(Boolean).join('\n');
      const description = [
        title,
        '',
        'Full clip · telegram.me/aofmainhub',
        linkBlock,
      ]
        .filter((line, i, arr) => !(line === '' && arr[i - 1] === ''))
        .join('\n')
        .slice(0, 4000);
      return {
        id: `up_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
        url: primary,
        altUrl: alt,
        urls: list.slice(0, 4),
        stem,
        title: title.slice(0, 120),
        tags,
        description,
        ts: Date.now(),
      };
    }

    function upsertUploadLibraryEntry(entry) {
      if (!entry || !entry.url) return;
      const rows = loadUploadLibrary().filter(
        (x) => x.url !== entry.url && x.altUrl !== entry.url && !(entry.altUrl && x.url === entry.altUrl)
      );
      rows.unshift(entry);
      saveUploadLibrary(rows);
    }

    function isThisVidUploadPage() {
      const p = `${location.pathname}${location.search}`.toLowerCase();
      return /my_video_upload|\/upload|video_upload|edit_video/i.test(p);
    }

    function findUploadFormField(kind) {
      const map = {
        title: [
          'input[name="title"]',
          'input#title',
          'input[placeholder*="title" i]',
          'input[aria-label*="title" i]',
        ],
        description: [
          'textarea[name="description"]',
          'textarea#description',
          'textarea[placeholder*="Describe" i]',
          'textarea[placeholder*="description" i]',
          'textarea[aria-label*="description" i]',
        ],
        tags: [
          'input[name="tags"]',
          'input#tags',
          'input[placeholder*="tag" i]',
          'textarea[name="tags"]',
          'input[aria-label*="tag" i]',
        ],
      };
      const sels = map[kind] || [];
      for (let i = 0; i < sels.length; i++) {
        const el = document.querySelector(sels[i]);
        if (el && !el.disabled && el.offsetParent !== null) return el;
      }
      // Label-proximity fallback (ThisVid markup drifts)
      const labels = Array.from(document.querySelectorAll('label, .form-group, .field, .control-group, div'));
      const re =
        kind === 'title'
          ? /^title\b/i
          : kind === 'description'
            ? /^description\b/i
            : /^tags?\b/i;
      for (let j = 0; j < labels.length; j++) {
        const t = String(labels[j].textContent || '').trim();
        if (!re.test(t.split('\n')[0] || '')) continue;
        const inp = labels[j].querySelector(
          kind === 'description' ? 'textarea' : 'input[type="text"], input:not([type]), textarea'
        );
        if (inp && !inp.disabled) return inp;
      }
      return null;
    }

    /** Fill ThisVid upload details (post-file) and/or remote URL tab. */
    function fillThisVidUploadForm(payload, opts) {
      const o = opts || {};
      if (!payload) return { ok: false, filled: [] };
      const filled = [];
      if (typeof selectFromUrlUploadMode === 'function') selectFromUrlUploadMode();
      else if (typeof clickUrlUploadTab === 'function') clickUrlUploadTab();
      if (payload.url && typeof findDirectUrlInput === 'function' && !findDirectUrlInput()) {
        if (typeof clickContinueIfNeeded === 'function') clickContinueIfNeeded();
      }
      if (payload.url) {
        const urlInput = findDirectUrlInput();
        if (urlInput) {
          setInputValue(urlInput, payload.url);
          filled.push('url');
          try {
            urlInput.scrollIntoView({ block: 'center', behavior: 'smooth' });
          } catch (_) {}
        }
      }
      if (payload.title) {
        const titleEl = findUploadFormField('title');
        if (titleEl && (o.force || !String(titleEl.value || '').trim())) {
          setInputValue(titleEl, payload.title);
          filled.push('title');
        }
      }
      if (payload.description) {
        const descEl = findUploadFormField('description');
        if (descEl && (o.force || !String(descEl.value || '').trim())) {
          setInputValue(descEl, payload.description);
          filled.push('description');
        }
      }
      const tagStr = Array.isArray(payload.tags)
        ? payload.tags.join(', ')
        : String(payload.tags || '').trim();
      if (tagStr) {
        const tagsEl = findUploadFormField('tags');
        if (tagsEl && (o.force || !String(tagsEl.value || '').trim())) {
          setInputValue(tagsEl, tagStr);
          filled.push('tags');
        }
      }
      return { ok: filled.length > 0, filled };
    }

    function renderOverlayUpload(body) {
      const lib = loadUploadLibrary();
      const onUpload = isThisVidUploadPage();
      body.innerHTML = `
        <p class="hint">Queue R2 /  clips, then one-click fill Title · Description · Tags on <code>my_video_upload</code>.</p>
        <label class="field">Paste media URL(s)
          <textarea id="tbccTvUpPaste" rows="3" placeholder="/….mp4&#10;https://pub-….r2.dev/….mp4"></textarea>
        </label>
        <label class="field">Title override
          <input type="text" id="tbccTvUpTitle" placeholder="auto from filename" />
        </label>
        <label class="field">Tags override
          <input type="text" id="tbccTvUpTags" placeholder="auto: aof, favs, aofmainhub…" />
        </label>
        <label class="field">Description override
          <textarea id="tbccTvUpDesc" rows="2" placeholder="auto includes both CDN links"></textarea>
        </label>
        <div class="friend-grid">
          <button type="button" class="accent" id="tbccTvUpAdd">Add to library</button>
          <button type="button" class="accent-btn" id="tbccTvUpFillLatest" ${onUpload ? '' : 'disabled'}>
            Fill form (latest)
          </button>
        </div>
        ${
          onUpload
            ? `<p class="hint" style="color:#8dcc9a">On upload page — Fill writes into the ThisVid fields below.</p>`
            : `<p class="hint">Open <a href="https://thisvid.com/my_video_upload/" target="_blank" rel="noopener" style="color:#f5a8c4">my_video_upload</a> (after file upload or URL step), then Fill.</p>`
        }
        <div class="stat">${lib.length} queued</div>
        <div class="meta-list" id="tbccTvUpList"></div>
      `;

      const listEl = body.querySelector('#tbccTvUpList');
      lib.slice(0, 40).forEach((item) => {
        const row = document.createElement('div');
        row.className = 'meta-row';
        const linkBits = [item.url, item.altUrl].filter(Boolean);
        row.innerHTML = `
          <strong>${(item.title || item.stem || 'clip').slice(0, 56)}</strong>
          <div class="meta-tags">${(item.tags || []).slice(0, 10).join(', ') || '—'}</div>
          <div class="hint" style="word-break:break-all">${linkBits.map((u) => u.slice(0, 64)).join('<br/>')}</div>
          <div class="meta-actions">
            <button type="button" data-act="fill">Fill form</button>
            <button type="button" data-act="copy">Copy links</button>
            <button type="button" data-act="del">Delete</button>
          </div>`;
        row.querySelector('[data-act="fill"]').addEventListener('click', () => {
          if (!isThisVidUploadPage()) {
            showTvToast('Open my_video_upload first');
            window.open('https://thisvid.com/my_video_upload/', '_blank');
            return;
          }
          const r = fillThisVidUploadForm(item, { force: true });
          showTvToast(r.ok ? `Filled ${r.filled.join(' · ')}` : 'Form fields not found — paste manually');
          try {
            const focusEl =
              findUploadFormField('title') || findUploadFormField('description') || findDirectUrlInput();
            focusEl?.scrollIntoView({ block: 'center', behavior: 'smooth' });
          } catch (_) {}
        });
        row.querySelector('[data-act="copy"]').addEventListener('click', () => {
          const t = linkBits.join('\n');
          navigator.clipboard?.writeText(t).then(
            () => showTvToast('Links copied'),
            () => showTvToast(t)
          );
        });
        row.querySelector('[data-act="del"]').addEventListener('click', () => {
          saveUploadLibrary(loadUploadLibrary().filter((x) => x.id !== item.id));
          renderOverlay();
        });
        listEl.appendChild(row);
      });
      if (!lib.length) {
        listEl.innerHTML = '<p class="hint">Library empty — paste a  or R2 .mp4 URL above.</p>';
      }

      body.querySelector('#tbccTvUpAdd').addEventListener('click', () => {
        const paste = body.querySelector('#tbccTvUpPaste').value;
        const urls = extractHttpUrls(paste);
        if (!urls.length) {
          showTvToast('Paste at least one https:// media URL');
          return;
        }
        const draft = draftFromMediaUrls(urls);
        const tOv = body.querySelector('#tbccTvUpTitle').value.trim();
        const tagsOv = parseTagLine(body.querySelector('#tbccTvUpTags').value);
        const dOv = body.querySelector('#tbccTvUpDesc').value.trim();
        if (tOv) draft.title = tOv.slice(0, 120);
        if (tagsOv.length) draft.tags = tagsOv;
        if (dOv) draft.description = dOv.slice(0, 4000);
        upsertUploadLibraryEntry(draft);
        showTvToast(`Queued · ${draft.title.slice(0, 40)}`);
        body.querySelector('#tbccTvUpPaste').value = '';
        renderOverlay();
      });

      body.querySelector('#tbccTvUpFillLatest').addEventListener('click', () => {
        const latest = loadUploadLibrary()[0];
        if (!latest) {
          showTvToast('Library empty');
          return;
        }
        if (!isThisVidUploadPage()) {
          showTvToast('Open my_video_upload first');
          return;
        }
        const r = fillThisVidUploadForm(latest, { force: true });
        showTvToast(r.ok ? `Filled ${r.filled.join(' · ')}` : 'Form fields not found');
      });
    }

    function renderOverlayMeta(body) {
      const videos = loadMetaVideos().slice().reverse();
      const lists = loadTagLists();
      const onWatch = isVideoWatchPage();
      body.innerHTML = `
        <p class="hint">Video metadata repo — save watch-page URLs/titles/tags + reusable tag lists (tune what converts).</p>
        ${
          onWatch
            ? `<button type="button" class="accent-btn" id="tbccTvSaveCurrent">Save this video to repo</button>`
            : `<p class="hint">Open a <code>/videos/…</code> page to one-click save, or paste below.</p>`
        }
        <label class="field">Paste URL
          <input type="url" id="tbccTvMetaUrl" placeholder="https://thisvid.com/videos/…" />
        </label>
        <label class="field">Title
          <input type="text" id="tbccTvMetaTitle" placeholder="optional" />
        </label>
        <label class="field">Tags (comma-separated)
          <input type="text" id="tbccTvMetaTags" placeholder="milf, taboo, …" />
        </label>
        <button type="button" class="ghost" id="tbccTvMetaAdd">Add / update entry</button>
        <div class="stat">${videos.length} videos stored</div>
        <div class="meta-list" id="tbccTvMetaList"></div>
        <hr class="divider" />
        <strong class="subhead">Tag lists</strong>
        <label class="field">List name
          <input type="text" id="tbccTvListName" placeholder="e.g. AOF STIM upload" />
        </label>
        <label class="field">Tags
          <textarea id="tbccTvListTags" rows="2" placeholder="comma-separated"></textarea>
        </label>
        <label class="field">Tune notes (what works / doesn't)
          <input type="text" id="tbccTvListNotes" placeholder="e.g. 'milf' lifts CTR; drop 'arab'" />
        </label>
        <button type="button" class="ghost" id="tbccTvListSave">Save tag list</button>
        <div class="meta-list" id="tbccTvListList"></div>
      `;

      const listEl = body.querySelector('#tbccTvMetaList');
      videos.slice(0, 40).forEach((v) => {
        const row = document.createElement('div');
        row.className = 'meta-row';
        row.innerHTML = `
          <a href="${v.url}" target="_blank" rel="noopener">${(v.title || v.id || 'video').slice(0, 48)}</a>
          <div class="meta-tags">${(v.tags || []).slice(0, 8).join(', ') || '—'}</div>
          <div class="meta-actions">
            <button type="button" data-act="copy-tags">Copy tags</button>
            <button type="button" data-act="del">Delete</button>
          </div>`;
        row.querySelector('[data-act="copy-tags"]').addEventListener('click', () => {
          const t = (v.tags || []).join(', ');
          navigator.clipboard?.writeText(t).then(
            () => showTvToast('Tags copied'),
            () => showTvToast(t || 'No tags')
          );
        });
        row.querySelector('[data-act="del"]').addEventListener('click', () => {
          saveMetaVideos(loadMetaVideos().filter((x) => x.url !== v.url));
          renderOverlay();
        });
        listEl.appendChild(row);
      });

      const listsEl = body.querySelector('#tbccTvListList');
      lists.forEach((L) => {
        const row = document.createElement('div');
        row.className = 'meta-row';
        row.innerHTML = `
          <strong>${L.name}</strong>
          <div class="meta-tags">${(L.tags || []).join(', ')}</div>
          <div class="hint">${L.notes || ''}</div>
          <div class="meta-actions">
            <button type="button" data-act="copy">Copy</button>
            <button type="button" data-act="use">Load into form</button>
            <button type="button" data-act="del">Delete</button>
          </div>`;
        row.querySelector('[data-act="copy"]').addEventListener('click', () => {
          navigator.clipboard?.writeText((L.tags || []).join(', '));
          showTvToast('Tag list copied');
        });
        row.querySelector('[data-act="use"]').addEventListener('click', () => {
          body.querySelector('#tbccTvListName').value = L.name;
          body.querySelector('#tbccTvListTags').value = (L.tags || []).join(', ');
          body.querySelector('#tbccTvListNotes').value = L.notes || '';
        });
        row.querySelector('[data-act="del"]').addEventListener('click', () => {
          saveTagLists(loadTagLists().filter((x) => x.id !== L.id));
          renderOverlay();
        });
        listsEl.appendChild(row);
      });

      body.querySelector('#tbccTvSaveCurrent')?.addEventListener('click', () => {
        const entry = scrapeCurrentVideoMeta();
        upsertMetaVideo(entry);
        // Also fold tags into intel
        recordIntelRow({
          platform: 'thisvid',
          captured_at: new Date().toISOString(),
          album_url: entry.url,
          album_id: entry.id,
          entity_id: entry.id,
          entity_url: entry.url,
          title: entry.title,
          tags: entry.tags,
          videos: 1,
          images: 0,
          format_bucket: 'single_video',
          uploader: entry.uploader || null,
          page_context: { path: location.pathname },
        });
        showTvToast(`Saved · ${entry.tags.length} tags`);
        renderOverlay();
      });

      body.querySelector('#tbccTvMetaAdd').addEventListener('click', () => {
        const url = body.querySelector('#tbccTvMetaUrl').value.trim();
        if (!url) {
          showTvToast('URL required');
          return;
        }
        const title = body.querySelector('#tbccTvMetaTitle').value.trim();
        const tags = parseTagLine(body.querySelector('#tbccTvMetaTags').value);
        upsertMetaVideo({
          id: videoIdFromUrl(url) || String(Date.now()),
          url,
          title: title || videoIdFromUrl(url) || 'untitled',
          tags,
          ts: Date.now(),
        });
        showTvToast('Entry saved');
        renderOverlay();
      });

      body.querySelector('#tbccTvListSave').addEventListener('click', () => {
        const name = body.querySelector('#tbccTvListName').value.trim();
        const tags = parseTagLine(body.querySelector('#tbccTvListTags').value);
        const notes = body.querySelector('#tbccTvListNotes').value.trim();
        if (!name || !tags.length) {
          showTvToast('Name + tags required');
          return;
        }
        const rows = loadTagLists().filter((x) => x.name.toLowerCase() !== name.toLowerCase());
        rows.push({ id: `tl_${Date.now()}`, name, tags, notes, updated: Date.now() });
        saveTagLists(rows);
        showTvToast('Tag list saved');
        renderOverlay();
      });
    }

    function renderOverlayIntel(body) {
      const meta = loadIntelMeta();
      const rows = loadIntelRows();
      const liveHtml =
        globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.renderParetoLiveHtml === 'function'
          ? globalThis.tbccBrowseIntel.renderParetoLiveHtml(rows)
          : '';
      body.innerHTML = `
        <p class="hint"><b>Passive:</b> leave Record checked and browse — intel fills as cards appear (no Scan required). At max rows it auto-pushes to TBCC and keeps the last 20% local. Scan is only a one-shot refresh.</p>
        <label class="row"><input type="checkbox" id="tbccTvIntelRec" /> Record browse intel (passive)</label>
        <label class="field">Max local rows
          <input type="number" id="tbccTvIntelMax" min="500" max="50000" />
        </label>
        <label class="field">TBCC ingest URL
          <input type="text" id="tbccTvIntelUrl" placeholder="" />
        </label>
        <div class="friend-grid">
          <button type="button" class="accent" id="tbccTvIntelScan">Scan visible now (optional)</button>
          <button type="button" id="tbccTvIntelExport">Export JSONL</button>
          <button type="button" id="tbccTvIntelPush">Push to TBCC</button>
          <button type="button" class="danger" id="tbccTvIntelClear">Clear</button>
        </div>
        <div class="stat" id="tbccTvIntelStat">${rows.length} rows stored</div>
        ${liveHtml}
      `;
      body.querySelector('#tbccTvIntelRec').checked = meta.recordIntel !== false;
      body.querySelector('#tbccTvIntelMax').value = meta.maxIntelRows || 5000;
      body.querySelector('#tbccTvIntelUrl').value = meta.tbccApiUrl || '';

      const persistMeta = () => {
        saveIntelMeta({
          recordIntel: !!body.querySelector('#tbccTvIntelRec').checked,
          maxIntelRows: Math.max(500, Number(body.querySelector('#tbccTvIntelMax').value) || 5000),
          tbccApiUrl: body.querySelector('#tbccTvIntelUrl').value.trim(),
        });
      };
      body.querySelector('#tbccTvIntelRec').addEventListener('change', persistMeta);
      body.querySelector('#tbccTvIntelMax').addEventListener('change', persistMeta);
      body.querySelector('#tbccTvIntelUrl').addEventListener('change', persistMeta);

      body.querySelector('#tbccTvIntelScan').addEventListener('click', () => {
        persistMeta();
        const n = scanGridIntel();
        showTvToast(`Intel scan · touched ${n} thumbs`);
        renderOverlay();
      });
      body.querySelector('#tbccTvIntelExport').addEventListener('click', () => {
        exportIntelJsonl();
      });
      body.querySelector('#tbccTvIntelPush').addEventListener('click', async () => {
        persistMeta();
        try {
          const n = await pushIntelToTbcc();
          showTvToast(`Pushed ${n} rows`);
        } catch (err) {
          showTvToast(`Push failed: ${err.message || err}`);
        }
      });
      body.querySelector('#tbccTvIntelClear').addEventListener('click', () => {
        if (!confirm('Clear all ThisVid intel rows?')) return;
        resetIntelMemoryCache();
        saveIntelRows([], { skipAutoPush: true });
        document.querySelectorAll('[data-tbcc-tv-intel]').forEach((el) => {
          delete el.dataset.tbccTvIntel;
        });
        renderOverlay();
      });
    }

    function renderOverlayFriends(body) {
      const onProfile = isMemberProfilePage() && !isOwnMemberPage();
      const onDirectory = isMemberDirectoryPage();
      const visibleCount = onDirectory ? collectVisibleMemberIds().length : 0;

      let html = '';
      if (onDirectory) {
        html += `
        <p class="hint"><strong>Community / new members</strong> — bulk-friend <em>visible</em> cards (${visibleCount}). Tip: site sidebar → <em>Girls Only</em> + Sort <em>Videos popularity</em>, then run No Gay.</p>
        <div class="friend-grid">
          <button type="button" data-scope="community" data-mode="no-gay" class="accent">Bulk · no Gay (${visibleCount})</button>
          <button type="button" data-scope="community" data-mode="straight-lesbian">Bulk · Straight/Lesbian</button>
          <button type="button" data-scope="community" data-mode="everyone">Bulk · everyone</button>
          <button type="button" data-mode="stop" class="danger">Stop</button>
        </div>`;
      }
      if (onProfile) {
        html += `
        <p class="hint">Mass-friend this member’s friends list (rate-limited).</p>
        <div class="friend-grid">
          <button type="button" data-scope="profile" data-mode="self">Friend this user</button>
          <button type="button" data-scope="profile" data-mode="no-gay" class="accent">Mass · no Gay</button>
          <button type="button" data-scope="profile" data-mode="straight-lesbian">Mass · Straight/Lesbian</button>
          <button type="button" data-scope="profile" data-mode="everyone">Mass · everyone</button>
          <button type="button" data-mode="stop" class="danger">Stop</button>
        </div>`;
      }
      if (!onDirectory && !onProfile) {
        html += `<p class="hint">Open <code>/community/</code> (new members) or another member profile to enable bulk friend tools.</p>`;
      }
      html += `<div class="stat" id="tbccTvFriendStatus">${friendStatusText}</div>`;
      body.innerHTML = html;
      body.querySelectorAll('button[data-mode]').forEach((btn) => {
        btn.addEventListener('click', () => {
          void runFriendAction(btn.getAttribute('data-mode'), btn.getAttribute('data-scope') || '');
        });
      });
    }

    function renderOverlayGrow(body) {
      body.innerHTML = `
        <p class="hint">Route community traffic → your channel. Friend-request message is the cleanest non-spam lever on ThisVid.</p>
        <label class="field">Your member ID
          <input type="text" id="tbccTvPromoId" inputmode="numeric" placeholder="7366294" />
        </label>
        <label class="row"><input type="checkbox" id="tbccTvUseMsg" /> Attach CTA message to friend requests</label>
        <label class="field">Friend request message
          <textarea id="tbccTvFriendMsg" rows="3" maxlength="400" placeholder="Short CTA + your profile URL"></textarea>
        </label>
        <button type="button" class="ghost" id="tbccTvOpenPromo">Open my channel</button>
        <button type="button" class="ghost" id="tbccTvClearSent">Clear “already friended” memory</button>
        <div class="tips">
          <strong>Playbook</strong>
          <ol>
            <li>Community → <em>Girls Only</em> (or your niche link).</li>
            <li>Sort by <em>Videos popularity</em> (active posters reciprocate).</li>
            <li>Scroll / infinite-load a page of faces → Friends tab → <em>Bulk · no Gay</em>.</li>
            <li>CTA in the request opens your channel when they accept / read it.</li>
            <li>Keep uploads + watermarked ThisVid clips fresh so visits convert.</li>
          </ol>
        </div>
      `;
      const idEl = body.querySelector('#tbccTvPromoId');
      const useEl = body.querySelector('#tbccTvUseMsg');
      const msgEl = body.querySelector('#tbccTvFriendMsg');
      idEl.value = settings.promoProfileId || '7366294';
      useEl.checked = settings.useFriendMessage !== false;
      msgEl.value = settings.friendMessage || '';
      const persist = () => {
        settings.promoProfileId = String(idEl.value || '').replace(/\D/g, '') || '7366294';
        settings.useFriendMessage = !!useEl.checked;
        settings.friendMessage = msgEl.value.trim().slice(0, 400);
        saveSettings();
      };
      idEl.addEventListener('change', persist);
      idEl.addEventListener('input', persist);
      useEl.addEventListener('change', persist);
      msgEl.addEventListener('input', persist);
      body.querySelector('#tbccTvOpenPromo').addEventListener('click', () => {
        persist();
        window.open(`https://thisvid.com/members/${promoProfileId()}/`, '_blank');
      });
      body.querySelector('#tbccTvClearSent').addEventListener('click', () => {
        try {
          localStorage.removeItem(FRIEND_SENT_KEY);
        } catch (_) {
          /* ignore */
        }
        setFriendStatus('Cleared already-friended memory');
      });
    }

    function renderOverlay() {
      const root = document.getElementById(OVERLAY_ID);
      if (!root) return;
      const page = OVERLAY_PAGES[overlayPageIndex] || OVERLAY_PAGES[0];
      root.querySelectorAll('.tbcc-tabs button').forEach((b) => {
        b.classList.toggle('active', b.dataset.page === page.id);
      });
      const ind = root.querySelector('.page-ind');
      if (ind) ind.textContent = `${overlayPageIndex + 1} / ${OVERLAY_PAGES.length} · ${page.title}`;
      const body = root.querySelector('.tbcc-body');
      if (!body) return;
      if (page.id === 'friends') renderOverlayFriends(body);
      else if (page.id === 'upload') renderOverlayUpload(body);
      else if (page.id === 'meta') renderOverlayMeta(body);
      else if (page.id === 'intel') renderOverlayIntel(body);
      else if (page.id === 'grow') renderOverlayGrow(body);
      else renderOverlayFilters(body);
      persistOverlayUi();
      updateIntelHeaderBadge();
    }

    function mountOverlay() {
      if (document.getElementById(OVERLAY_ID)) return;
      ensureStyle();
      const ui = loadOverlayUi();
      overlayCollapsed = ui.collapsed;
      overlayPageIndex = ui.pageIndex;
      overlayWidthMode = ui.widthMode || 'slim';
      // Prefer Friends tab on profiles / community directory; Upload on upload form.
      if (!localStorage.getItem(OVERLAY_UI_KEY)) {
        if (isThisVidUploadPage()) {
          overlayPageIndex = OVERLAY_PAGES.findIndex((p) => p.id === 'upload');
          if (overlayPageIndex < 0) overlayPageIndex = 0;
        } else if (isMemberProfilePage() && !isOwnMemberPage()) overlayPageIndex = 1;
        else if (isMemberDirectoryPage()) overlayPageIndex = 1;
      } else if (isThisVidUploadPage()) {
        const upIdx = OVERLAY_PAGES.findIndex((p) => p.id === 'upload');
        if (upIdx >= 0) overlayPageIndex = upIdx;
      }

      const root = document.createElement('div');
      root.id = OVERLAY_ID;
      root.style.top = `${loadOverlayTop()}px`;
      root.innerHTML = `
        <button type="button" class="tbcc-chevron" title="${SUITE_TITLE} · drag up/down">TV ▸</button>
        <div class="tbcc-panel">
          <div class="tbcc-head" title="Drag up/down to reposition">
            <strong>${SUITE_TITLE}</strong>
            ${
              COMMUNITY
                ? ''
                : `<button type="button" class="tbcc-intel-badge" data-act="intel-open" title="Browse intel — click for settings">
              <span aria-hidden="true">▣</span><span data-tv-intel-count>0</span>
            </button>`
            }
            <button type="button" data-act="width" title="Cycle panel width">Width</button>
            <button type="button" data-act="collapse">Hide</button>
          </div>
          <div class="tbcc-tabs"></div>
          <div class="tbcc-body"></div>
          <div class="tbcc-foot">
            <button type="button" data-jump="top" title="Back to top">↑</button>
            <button type="button" data-act="prev">Prev</button>
            <span class="page-ind"></span>
            <button type="button" data-act="next">Next</button>
            <button type="button" data-jump="bottom" title="Back to bottom">↓</button>
          </div>
        </div>
      `;
      document.documentElement.appendChild(root);

      const tabs = root.querySelector('.tbcc-tabs');
      OVERLAY_PAGES.forEach((p, i) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.textContent = p.title;
        b.dataset.page = p.id;
        b.addEventListener('click', () => {
          overlayPageIndex = i;
          renderOverlay();
        });
        tabs.appendChild(b);
      });

      const chevron = root.querySelector('.tbcc-chevron');
      const head = root.querySelector('.tbcc-head');
      bindChevronDrag(root, chevron);
      bindVerticalDrag(root, head, { ignoreSelector: 'button, a, input, select, textarea' });
      chevron.addEventListener('click', () => {
        if (chevron.dataset.suppressClick) return;
        setOverlayCollapsed(!overlayCollapsed);
      });
      root.querySelector('[data-act="collapse"]').addEventListener('click', () => {
        setOverlayCollapsed(true);
      });
      root.querySelector('[data-act="width"]')?.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        overlayWidthMode =
          overlayWidthMode === 'slim' ? 'normal' : overlayWidthMode === 'normal' ? 'wide' : 'slim';
        syncOverlayCollapsed(root);
        persistOverlayUi();
      });
      root.querySelector('[data-act="intel-open"]')?.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        openIntelSettingsPanel();
      });
      root.querySelector('[data-act="prev"]').addEventListener('click', () => {
        overlayPageIndex = (overlayPageIndex + OVERLAY_PAGES.length - 1) % OVERLAY_PAGES.length;
        renderOverlay();
      });
      root.querySelector('[data-act="next"]').addEventListener('click', () => {
        overlayPageIndex = (overlayPageIndex + 1) % OVERLAY_PAGES.length;
        renderOverlay();
      });

      window.TBCCSuiteRail?.bindFootJumps(root);
      window.TBCCSuiteRail?.ensureStyles();

      // Native <select> menus must not be destroyed mid-interaction
      root.addEventListener('mousedown', (e) => {
        if (e.target && (e.target.tagName === 'SELECT' || e.target.closest?.('select'))) {
          e.stopPropagation();
        }
      });

      syncOverlayCollapsed(root);
      renderOverlay();
    }

    function ensureOverlayMounted() {
      if (!document.getElementById(OVERLAY_ID)) mountOverlay();
    }

    /** Keep overlay alive without re-rendering (prevents select collapse). */
    function mountFriendPanel() {
      ensureOverlayMounted();
    }

    function ensureStyle() {
      if (document.getElementById('tbcc-tv-enhancer-style')) return;
      const style = document.createElement('style');
      style.id = 'tbcc-tv-enhancer-style';
      // ThisVid palette: near-black + brand pink (#eb6395) with TBCC chevron drawer chrome
      style.textContent = `
        #${OVERLAY_ID} {
          position: fixed; z-index: 1000000; top: 72px; right: 0;
          display: flex; align-items: stretch; font: 13px/1.4 system-ui, sans-serif;
          color: #e8e8e8; pointer-events: none;
        }
        #${OVERLAY_ID} * { box-sizing: border-box; }
        #${OVERLAY_ID} .tbcc-chevron {
          pointer-events: auto; width: 28px; min-height: 120px;
          background: #141014; border: 1px solid #3a2a33; border-right: none;
          border-radius: 10px 0 0 10px; cursor: grab; color: #eb6395;
          display: flex; align-items: center; justify-content: center;
          writing-mode: vertical-rl; text-orientation: mixed; letter-spacing: .08em;
          font-size: 11px; font-weight: 700; padding: 10px 0;
          touch-action: none; user-select: none;
        }
        #${OVERLAY_ID} .tbcc-chevron:active { cursor: grabbing; }
        #${OVERLAY_ID} .tbcc-panel {
          pointer-events: auto; width: min(300px, calc(100vw - 40px));
          max-height: min(72vh, 560px); background: #121012; border: 1px solid #3a2a33;
          border-right: none; border-radius: 12px 0 0 12px;
          box-shadow: -8px 0 28px rgba(0,0,0,.5); display: flex; flex-direction: column;
          overflow: hidden;
        }
        #${OVERLAY_ID}.collapsed .tbcc-panel { display: none; }
        #${OVERLAY_ID}.slim .tbcc-panel { width: min(240px, calc(100vw - 40px)); }
        #${OVERLAY_ID}.wide .tbcc-panel { width: min(360px, calc(100vw - 40px)); }
        #${OVERLAY_ID} .tbcc-head {
          display: flex; align-items: center; gap: 8px; padding: 10px 12px;
          background: #1a1218; border-bottom: 1px solid #2a1f26;
          cursor: grab; touch-action: none; user-select: none;
        }
        #${OVERLAY_ID} .tbcc-head:active { cursor: grabbing; }
        #${OVERLAY_ID} .tbcc-head strong {
          flex: 1; font-size: 13px; color: #f3d0df; cursor: grab; pointer-events: none; min-width: 0;
        }
        #${OVERLAY_ID} .tbcc-head .tbcc-intel-badge {
          cursor: pointer; touch-action: auto; user-select: none; flex-shrink: 0;
          display: inline-flex; align-items: center; gap: 4px;
          background: #1a2830; color: #7ec8e3; border: 1px solid #3a5560; border-radius: 6px;
          padding: 3px 8px; font-size: 12px; font-weight: 700;
        }
        #${OVERLAY_ID} .tbcc-head .tbcc-intel-badge:hover { filter: brightness(1.12); border-color: #7ec8e3; }
        #${OVERLAY_ID} .tbcc-head .tbcc-intel-badge.off { opacity: 0.45; }
        #${OVERLAY_ID} .tbcc-head button {
          cursor: pointer; touch-action: auto; user-select: auto;
        }
        #${OVERLAY_ID} .tbcc-head button, #${OVERLAY_ID} .tbcc-foot button, #${OVERLAY_ID} .ghost {
          background: #2a2228; color: #eee; border: 1px solid #514049; border-radius: 6px;
          padding: 6px 10px; cursor: pointer;
        }
        #${OVERLAY_ID} .tbcc-head button:hover, #${OVERLAY_ID} .tbcc-foot button:hover,
        #${OVERLAY_ID} .ghost:hover {
          border-color: #eb6395; color: #fff;
        }
        #${OVERLAY_ID} .tbcc-tabs {
          display: flex; gap: 4px; padding: 8px; border-bottom: 1px solid #2a1f26; overflow-x: auto;
        }
        #${OVERLAY_ID} .tbcc-tabs button {
          flex: 0 0 auto; background: transparent; border: 1px solid #3a2a33; color: #aaa;
          border-radius: 999px; padding: 4px 10px; cursor: pointer; font-size: 11px;
        }
        #${OVERLAY_ID} .tbcc-tabs button.active {
          background: #eb6395; border-color: #eb6395; color: #1a0a12; font-weight: 700;
        }
        #${OVERLAY_ID} .tbcc-body { padding: 12px; overflow: auto; flex: 1; }
        #${OVERLAY_ID} .tbcc-foot {
          display: flex; gap: 8px; padding: 8px 12px; border-top: 1px solid #2a1f26; background: #1a1218;
        }
        #${OVERLAY_ID} .tbcc-foot .page-ind { flex: 1; color: #888; font-size: 12px; align-self: center; }
        #${OVERLAY_ID} .hint { color: #9a8790; font-size: 12px; margin: 0 0 10px; }
        #${OVERLAY_ID} label.field {
          display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; color: #b9a4ae; font-size: 12px;
        }
        #${OVERLAY_ID} label.row {
          display: flex; gap: 8px; align-items: center; padding: 6px 0; cursor: pointer; color: #ddd;
        }
        #${OVERLAY_ID} select, #${OVERLAY_ID} input[type="text"], #${OVERLAY_ID} input[type="number"],
        #${OVERLAY_ID} input[type="url"] {
          width: 100%; background: #1e161c; color: #eee; border: 1px solid #514049;
          border-radius: 6px; padding: 6px 8px;
        }
        #${OVERLAY_ID} .ghost { width: 100%; margin-top: 4px; }
        #${OVERLAY_ID} .friend-grid {
          display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px;
        }
        #${OVERLAY_ID} .friend-grid button {
          background: #2a2228; color: #eee; border: 1px solid #514049; border-radius: 6px;
          padding: 7px 10px; cursor: pointer; font-size: 12px;
        }
        #${OVERLAY_ID} .friend-grid button.accent {
          background: linear-gradient(135deg, #3a8a5a, #1a4030); border-color: #4aaa6a;
        }
        #${OVERLAY_ID} .friend-grid button.danger {
          background: #422028; border-color: #844050;
        }
        #${OVERLAY_ID} .friend-grid button:disabled { opacity: .55; cursor: wait; }
        #${OVERLAY_ID} .stat {
          font-variant-numeric: tabular-nums; color: #f5a8c4; margin-top: 8px; font-size: 12px;
        }
        #${OVERLAY_ID} .subhead { display: block; margin: 8px 0; color: #f3d0df; }
        #${OVERLAY_ID} .divider {
          border: 0; border-top: 1px solid #2a1f26; margin: 14px 0;
        }
        #${OVERLAY_ID} .accent-btn {
          width: 100%; background: #eb6395; color: #1a0a12; border: none; border-radius: 6px;
          padding: 8px 10px; cursor: pointer; font-weight: 700; margin-bottom: 10px;
        }
        #${OVERLAY_ID} .meta-list { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
        #${OVERLAY_ID} .meta-row {
          border: 1px solid #2a1f26; border-radius: 8px; padding: 8px; background: #181218;
        }
        #${OVERLAY_ID} .meta-row a { color: #f5a8c4; text-decoration: none; font-weight: 600; }
        #${OVERLAY_ID} .meta-tags { color: #9a8790; font-size: 11px; margin-top: 4px; word-break: break-word; }
        #${OVERLAY_ID} .meta-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
        #${OVERLAY_ID} .meta-actions button {
          background: #2a2228; color: #eee; border: 1px solid #514049; border-radius: 6px;
          padding: 4px 8px; cursor: pointer; font-size: 11px;
        }
        #${OVERLAY_ID} select {
          /* Keep opens stable; avoid remount destroying native popup */
          color-scheme: dark;
        }
        #${OVERLAY_ID} textarea {
          width: 100%; background: #1e161c; color: #eee; border: 1px solid #514049;
          border-radius: 6px; padding: 6px 8px; resize: vertical; min-height: 64px;
          font: 12px/1.35 system-ui, sans-serif;
        }
        #${OVERLAY_ID} .tips {
          margin-top: 12px; padding: 10px; border: 1px solid #2a1f26; border-radius: 8px;
          background: #181218; color: #cbb4bf; font-size: 12px;
        }
        #${OVERLAY_ID} .tips strong { color: #f3d0df; display: block; margin-bottom: 6px; }
        #${OVERLAY_ID} .tips ol { margin: 0; padding-left: 18px; }
        #${OVERLAY_ID} .tips li { margin: 4px 0; }
        .tbcc-tv-title-filtered { display: none !important; }
        a.__tbcc_tv_dl span { color: #fff; font-size: 32px; }
        a.__tbcc_tv_dl {
          display: inline-flex; align-items: center; justify-content: center;
          text-decoration: none; cursor: pointer; min-width: 28px;
        }
        /* Owned by TBCC — fixed chrome survives ThisVid tools-bar rebuilds */
        #tbcc-tv-dl-fab {
          position: fixed; z-index: 999990; right: 18px; bottom: 72px;
          display: none; align-items: center; gap: 8px;
          padding: 10px 16px; border-radius: 999px; border: 1px solid #eb6395;
          background: linear-gradient(135deg, #eb6395, #b83d6c); color: #1a0a12;
          font: 700 13px/1.2 system-ui, sans-serif; cursor: pointer;
          box-shadow: 0 8px 24px rgba(0,0,0,.45);
        }
        #tbcc-tv-dl-fab.on { display: inline-flex; }
        #tbcc-tv-dl-fab:hover { filter: brightness(1.06); }
        #tbcc-tv-dl-fab[disabled] { opacity: .65; cursor: wait; }
        [data-tbcc-tv-pager-hidden="1"] { display: none !important; }
        .tbcc-tv-page-sep {
          grid-column: 1 / -1; width: 100%; display: flex; align-items: center;
          gap: 12px; margin: 16px 0 8px; color: #eb6395; font: 600 13px/1 system-ui, sans-serif;
        }
        .tbcc-tv-page-sep::before, .tbcc-tv-page-sep::after {
          content: ''; flex: 1; height: 1px; background: linear-gradient(90deg, transparent, #514049, transparent);
        }
        #tbcc-tv-scroll-status {
          position: fixed; z-index: 999989; left: 50%; transform: translateX(-50%); bottom: 24px;
          background: rgba(20,12,16,.92); color: #ddd; border: 1px solid #514049; border-radius: 999px;
          padding: 6px 14px; font: 12px/1.3 system-ui, sans-serif; pointer-events: none;
          display: none;
        }
        #tbcc-tv-scroll-status.on { display: block; }
      `;
      document.documentElement.appendChild(style);
    }

    /* ---------- Infinite scroll (capped + sliding DOM window) ---------- */
    const TVInf = globalThis.TBCCThisVidInfinite;
    if (!TVInf) {
      console.error('[TBCC ThisVid] thisvid-infinite-scroll.js missing — infinite scroll disabled');
    }

    let currentPage = 1;
    let loadingPage = false;
    let scrollLocked = false;
    let reachedEnd = false;
    let pagesLoadedExtra = 0;
    let seenHrefs = new Set();

    function clampInt(raw, min, max, fallback) {
      return TVInf ? TVInf.clampInt(raw, min, max, fallback) : Math.max(min, Math.min(max, parseInt(raw, 10) || fallback));
    }

    function infiniteLimits() {
      if (TVInf) return TVInf.resolveLimits(settings);
      return {
        maxPages: clampInt(settings.infiniteMaxPages, 1, 12, 3),
        maxCards: clampInt(settings.infiniteMaxCards, 24, 120, 64),
        cooldownMs: clampInt(settings.infiniteCooldownMs, 1000, 8000, 2000),
      };
    }

    /** Pages where infinite scroll is unsafe or useless (preview grids / avatars / watch). */
    function pageAllowsInfiniteScroll() {
      if (TVInf) {
        return TVInf.pageAllowsInfiniteScroll(location.pathname, {
          isVideoWatchPage: isVideoWatchPage(),
          isMemberProfilePage: isMemberProfilePage(),
          isMemberDirectoryPage: isMemberDirectoryPage(),
        });
      }
      if (isVideoWatchPage()) return false;
      if (isMemberProfilePage()) return false;
      if (isMemberDirectoryPage()) return false;
      const p = location.pathname;
      if (/\/members\/\d+\/(friends|wall|photo|albums)/i.test(p)) return false;
      return true;
    }

    function detachThumbMedia(el) {
      el?.querySelectorAll?.('img').forEach((img) => {
        try {
          img.removeAttribute('srcset');
          img.removeAttribute('sizes');
          img.src = '';
          img.removeAttribute('src');
        } catch (_) {
          /* ignore */
        }
      });
    }

    /** Keep decoded bitmap cost down on appended pages. */
    function demoteThumbMedia(node) {
      node.querySelectorAll?.('img').forEach((img) => {
        try {
          img.loading = 'lazy';
          img.decoding = 'async';
          // Drop srcset so the browser doesn't pull 2×/3× posters for offscreen cards
          img.removeAttribute('srcset');
          img.removeAttribute('sizes');
          const src = img.getAttribute('src') || img.getAttribute('data-src') || '';
          if (src && !img.getAttribute('src')) img.setAttribute('src', src);
        } catch (_) {
          /* ignore */
        }
      });
    }

    function gridThumbCards() {
      const grid = findGridContainer();
      if (!grid) return [];
      return [...grid.querySelectorAll('a.tumbpu, .tumbpu, [data-tbcc-tv-page]')].filter((el) => {
        if (el.classList?.contains('tbcc-tv-page-sep')) return false;
        return !!(thumbHref(el) || el.querySelector?.('img'));
      });
    }

    function tagCardsWithPage(page) {
      const grid = findGridContainer();
      if (!grid) return;
      extractThumbs(document).forEach((node) => {
        if (!grid.contains(node)) return;
        if (!node.getAttribute('data-tbcc-tv-page')) {
          node.setAttribute('data-tbcc-tv-page', String(page));
        }
      });
    }

    /** Drop oldest infinite-scroll pages until under card/RAM budget. */
    function pruneGridToCap() {
      const { maxCards } = infiniteLimits();
      const grid = findGridContainer();
      if (!grid) return 0;
      let cards = gridThumbCards();
      if (cards.length <= maxCards) return 0;

      const byPage = new Map();
      for (const el of cards) {
        const p = parseInt(el.getAttribute('data-tbcc-tv-page') || '0', 10) || 0;
        if (!byPage.has(p)) byPage.set(p, []);
        byPage.get(p).push(el);
      }
      const pagesAsc = [...byPage.keys()].sort((a, b) => a - b);
      let removed = 0;

      for (const page of pagesAsc) {
        if (cards.length - removed <= maxCards) break;
        // Never prune the newest page we just loaded
        if (page === currentPage && pagesAsc.length > 1) continue;
        const group = byPage.get(page) || [];
        for (const el of group) {
          // Detach images first so decoded bitmaps can GC
          detachThumbMedia(el);
          el.remove();
          removed += 1;
        }
        grid.querySelectorAll(`.tbcc-tv-page-sep`).forEach((sep) => {
          if ((sep.textContent || '').includes(`Page ${page}`)) sep.remove();
        });
      }

      // If still over (single giant page), trim oldest DOM children in grid
      cards = gridThumbCards();
      while (cards.length > maxCards) {
        const el = cards.shift();
        detachThumbMedia(el);
        el?.remove();
        removed += 1;
        cards = gridThumbCards();
      }
      return removed;
    }

    function seedSeenFromDom() {
      cardNodes().forEach((el) => {
        const a =
          (el.matches?.('a[href*="/videos/"]') && el) ||
          el.querySelector?.('a[href*="/videos/"], a[href*="/video/"]') ||
          el.closest?.('a[href*="/videos/"], a[href*="/video/"]');
        const href = a?.getAttribute?.('href') || a?.href || '';
        if (href) seenHrefs.add(href.replace(/#.*$/, ''));
      });
    }

    function findPaginationRoot() {
      const rel = document.querySelector('a[rel="next"]');
      if (rel) return rel.closest('.pagination, .pages, nav, ul, div') || rel.parentElement;
      const nodes = [...document.querySelectorAll('.pagination, .pages, .paginator, .paging, nav')];
      for (const el of nodes) {
        if (el.closest?.('#tbcc-tv-overlay, #tbcc-tv-title-filter-bar')) continue;
        const links = el.querySelectorAll('a');
        if (links.length >= 3 && /\d/.test(el.textContent || '')) return el;
      }
      // Heuristic: compact control with many numeric page links (ThisVid circles)
      for (const el of document.querySelectorAll('div, ul, nav, ol')) {
        if (el.closest?.('#tbcc-tv-overlay, #tbcc-tv-title-filter-bar, #tbcc-fl-overlay')) continue;
        const text = (el.innerText || '').replace(/\s+/g, ' ').trim();
        if (text.length > 180 || text.length < 5) continue;
        const nums = [...el.querySelectorAll('a, button, span')].filter((n) =>
          /^\d+$/.test((n.textContent || '').trim())
        );
        if (nums.length >= 5) return el;
      }
      return null;
    }

    function hidePagination() {
      const root = findPaginationRoot();
      if (root) root.setAttribute('data-tbcc-tv-pager-hidden', '1');
      document.querySelectorAll('a[rel="next"], a[rel="prev"]').forEach((a) => {
        const wrap = a.closest('.pagination, .pages, nav, ul, div');
        if (wrap) wrap.setAttribute('data-tbcc-tv-pager-hidden', '1');
      });
    }

    /**
     * Trailing /N/ is a list page index. Never treat bare /members/{id}/ as a page —
     * that id is the profile, and bumping it 404s (e.g. /members/143460/).
     */
    function pathPageParts(pathname) {
      if (TVInf) return TVInf.pathPageParts(pathname);
      const path = String(pathname || '').replace(/\/$/, '') || '';
      if (/^\/members\/\d+$/.test(path)) return null;
      if (/\/videos\/[^/]+$/.test(path)) return null;
      const m = path.match(/^(.*)\/(\d+)$/);
      if (!m) return null;
      const page = parseInt(m[2], 10);
      if (!(page > 0)) return null;
      return { base: m[1], page };
    }

    function detectCurrentPage() {
      if (TVInf) {
        const fromLoc = TVInf.detectCurrentPageFromLocation(location.href, location.pathname);
        if (fromLoc > 1 || new URL(location.href).searchParams.has('page') || pathPageParts(location.pathname)) {
          return fromLoc;
        }
      } else {
        const u = new URL(location.href);
        if (u.searchParams.has('page')) {
          return Math.max(1, parseInt(u.searchParams.get('page'), 10) || 1);
        }
        const parts = pathPageParts(location.pathname);
        if (parts) return parts.page;
      }
      const pag = findPaginationRoot();
      if (pag) {
        const active =
          pag.querySelector('.active, .current, .selected, [aria-current="page"]') ||
          [...pag.querySelectorAll('a, span, button')].find((el) => {
            const t = (el.textContent || '').trim();
            if (!/^\d+$/.test(t)) return false;
            const cs = getComputedStyle(el);
            const c = cs.backgroundColor || '';
            return /rgb\(\s*2\d\d/.test(c) || el.className?.toLowerCase?.().includes('active');
          });
        const n = parseInt((active?.textContent || '').trim(), 10);
        if (n > 0) return n;
      }
      return 1;
    }

    function urlForPage(page) {
      let pagerHref = null;
      const pag = findPaginationRoot();
      if (pag) {
        const link = [...pag.querySelectorAll('a[href]')].find(
          (a) => (a.textContent || '').trim() === String(page)
        );
        if (link?.href) pagerHref = link.href;
        else {
          const next = pag.querySelector('a[rel="next"]');
          if (next?.href && page === currentPage + 1) pagerHref = next.href;
        }
      }
      if (TVInf) {
        return TVInf.buildUrlForPage({
          href: location.href,
          pathname: location.pathname,
          origin: location.origin,
          page,
          currentPage,
          pagerHref,
        });
      }
      const u = new URL(location.href);
      if (u.searchParams.has('page') || u.searchParams.has('from')) {
        if (u.searchParams.has('page')) u.searchParams.set('page', String(page));
        if (u.searchParams.has('from')) u.searchParams.set('from', String(page));
        return u.href;
      }
      const parts = pathPageParts(location.pathname);
      if (parts) return `${location.origin}${parts.base}/${page}/`;
      if (pagerHref) return pagerHref;
      const path = location.pathname.replace(/\/$/, '') || '';
      if (path && page > 1) return `${location.origin}${path}/${page}/`;
      u.searchParams.set('page', String(page));
      return u.href;
    }

    function lowestCommonAncestor(a, b) {
      const path = new Set();
      for (let el = a; el; el = el.parentElement) path.add(el);
      for (let el = b; el; el = el.parentElement) {
        if (!path.has(el)) continue;
        if (el === document.body || el === document.documentElement) return null;
        return el;
      }
      return null;
    }

    function findGridContainer() {
      const preferred = document.querySelector(
        '#list_videos_common_videos_list, .list-videos, .thumbs.videos, .video-list'
      );
      if (preferred && preferred.querySelectorAll('a.tumbpu, .tumbpu, a[href*="/videos/"]').length >= 2) {
        return preferred;
      }
      // Prefer video thumbs — member profile "friends" rows first in DOM and blew RAM when used as grid
      const videoThumbs = [
        ...document.querySelectorAll('a.tumbpu[href*="/videos/"], .tumbpu[href*="/videos/"]'),
      ];
      if (videoThumbs.length >= 2) {
        const lca = lowestCommonAncestor(videoThumbs[0], videoThumbs[1]);
        if (lca) return lca;
      }
      const thumbs = [...document.querySelectorAll('a.tumbpu, .tumbpu')];
      if (thumbs.length >= 2) {
        const lca = lowestCommonAncestor(thumbs[0], thumbs[1]);
        if (lca) return lca;
      }
      return document.querySelector('.thumbs, .list-videos, .video-list, .videos') || null;
    }

    function extractThumbs(doc) {
      const nodes = [...doc.querySelectorAll('a.tumbpu, .tumbpu')];
      if (nodes.length) return nodes;
      return [...doc.querySelectorAll('a[href*="/videos/"]')].filter((a) => {
        const href = a.getAttribute('href') || '';
        return /\/videos\/[^/]+\/?$/.test(href) && a.querySelector('img');
      });
    }

    function thumbHref(node) {
      const a =
        (node.matches?.('a[href]') && node) ||
        node.querySelector?.('a[href*="/videos/"]') ||
        node.closest?.('a[href*="/videos/"]');
      return (a?.getAttribute('href') || a?.href || '').replace(/#.*$/, '');
    }

    function updateScrollStatus(msg) {
      let el = document.getElementById('tbcc-tv-scroll-status');
      if (!el) {
        el = document.createElement('div');
        el.id = 'tbcc-tv-scroll-status';
        document.documentElement.appendChild(el);
      }
      if (!settings.infiniteScroll) {
        el.classList.remove('on');
        return;
      }
      const { maxPages, maxCards } = infiniteLimits();
      const nCards = gridThumbCards().length;
      el.classList.add('on');
      el.textContent =
        msg ||
        `TBCC infinite · p${currentPage} · +${pagesLoadedExtra}/${maxPages} · ${nCards}/${maxCards} cards` +
          (loadingPage ? ' · loading…' : '') +
          (reachedEnd ? ' · capped' : '');
    }

    async function loadNextPage() {
      if (!settings.infiniteScroll || loadingPage || reachedEnd) return 0;
      if (!pageAllowsInfiniteScroll()) {
        reachedEnd = true;
        return 0;
      }
      if (document.hidden) return 0;
      const { maxPages, maxCards } = infiniteLimits();
      if (pagesLoadedExtra >= maxPages) {
        reachedEnd = true;
        updateScrollStatus(`TBCC infinite · page cap (${maxPages} extra)`);
        return 0;
      }
      // Already at DOM budget — prune first; if still full, stop (don't keep fetching)
      if (gridThumbCards().length >= maxCards) {
        pruneGridToCap();
        if (gridThumbCards().length >= maxCards) {
          reachedEnd = true;
          updateScrollStatus(`TBCC infinite · card cap (${maxCards})`);
          return 0;
        }
      }
      loadingPage = true;
      updateScrollStatus();
      const nextPage = currentPage + 1;
      const url = urlForPage(nextPage);
      try {
        const res = await fetch(url, {
          credentials: 'include',
          headers: { Accept: 'text/html', 'X-Requested-With': 'XMLHttpRequest' },
        });
        if (!res.ok) {
          // Stop retry spam in Extensions Errors (esp. former member-id-as-page 404s)
          if (res.status === 404 || res.status === 410) reachedEnd = true;
          throw new Error(`HTTP ${res.status}`);
        }
        const html = await res.text();
        const htmlBytes = typeof TextEncoder !== 'undefined' ? new TextEncoder().encode(html).length : html.length;
        const maxHtml = TVInf?.HARD?.MAX_HTML_BYTES || 1_500_000;
        if (htmlBytes > maxHtml) {
          reachedEnd = true;
          updateScrollStatus('TBCC infinite · HTML too large (RAM guard)');
          return 0;
        }
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const maxThumbs = TVInf?.HARD?.MAX_THUMBS_PER_PAGE || 60;
        const thumbs = extractThumbs(doc)
          .filter((n) => {
            const href = thumbHref(n);
            return href && /\/videos\//i.test(href);
          })
          .slice(0, maxThumbs);
        const grid = findGridContainer();
        if (!grid || !thumbs.length) {
          reachedEnd = true;
          updateScrollStatus(`TBCC infinite · end at page ${currentPage}`);
          return 0;
        }
        const frag = document.createDocumentFragment();
        const sep = document.createElement('div');
        sep.className = 'tbcc-tv-page-sep';
        sep.textContent = `Page ${nextPage}`;
        frag.appendChild(sep);

        let added = 0;
        for (const remote of thumbs) {
          const href = thumbHref(remote);
          if (href && seenHrefs.has(href)) continue;
          const node = document.importNode(remote, true);
          node.querySelectorAll?.('script').forEach((s) => s.remove());
          demoteThumbMedia(node);
          const localHref = thumbHref(node);
          if (localHref) seenHrefs.add(localHref);
          if (href) seenHrefs.add(href);
          node.setAttribute('data-tbcc-tv-page', String(nextPage));
          frag.appendChild(node);
          added += 1;
        }
        if (!added) {
          reachedEnd = true;
          updateScrollStatus(`TBCC infinite · no new thumbs @ ${nextPage}`);
          return 0;
        }
        grid.appendChild(frag);
        currentPage = nextPage;
        pagesLoadedExtra += 1;
        hidePagination();
        const pruned = pruneGridToCap();
        applyAllGridControls();
        if (pagesLoadedExtra >= maxPages) {
          reachedEnd = true;
        }
        updateScrollStatus(
          `TBCC infinite · p${currentPage} · +${pagesLoadedExtra}/${maxPages} · ${gridThumbCards().length}/${maxCards}` +
            (pruned ? ` · pruned ${pruned}` : '') +
            (reachedEnd ? ' · capped' : '')
        );
        console.info(
          '[TBCC ThisVid] infinite +',
          added,
          '→ page',
          currentPage,
          'extra',
          pagesLoadedExtra,
          pruned ? `pruned ${pruned}` : ''
        );
        return added;
      } catch (err) {
        console.warn('[TBCC ThisVid] infinite fetch failed', err);
        updateScrollStatus(`TBCC infinite · fetch error (${err.message || err})`);
        return 0;
      } finally {
        loadingPage = false;
      }
    }

    function nearBottom() {
      const doc = document.documentElement;
      const scrollPos = window.scrollY + window.innerHeight;
      const height = Math.max(doc.scrollHeight, document.body?.scrollHeight || 0);
      return scrollPos >= height - 700;
    }

    function onScrollInfinite() {
      if (!settings.infiniteScroll || scrollLocked || loadingPage || reachedEnd) return;
      if (document.hidden) return;
      if (!pageAllowsInfiniteScroll()) return;
      if (!nearBottom()) return;
      scrollLocked = true;
      const { cooldownMs } = infiniteLimits();
      loadNextPage().finally(() => {
        setTimeout(() => {
          scrollLocked = false;
        }, cooldownMs);
      });
    }

    function setupInfiniteScroll() {
      window.removeEventListener('scroll', onScrollInfinite);
      if (!settings.infiniteScroll) {
        updateScrollStatus();
        return;
      }
      if (!pageAllowsInfiniteScroll()) {
        reachedEnd = true;
        updateScrollStatus('TBCC infinite · off on this page (RAM)');
        return;
      }
      const grid = findGridContainer();
      if (!grid || cardNodes().length < 2) return;
      currentPage = detectCurrentPage();
      reachedEnd = false;
      pagesLoadedExtra = 0;
      seedSeenFromDom();
      tagCardsWithPage(currentPage);
      pruneGridToCap();
      hidePagination();
      updateScrollStatus();
      window.addEventListener('scroll', onScrollInfinite, { passive: true });
      // No soft top-up — auto-fetch on short pages was a multi-GB tab footgun
      console.info('[TBCC ThisVid] infinite scroll on @ page', currentPage, infiniteLimits());
    }

    function mountTitleFilterBar() {
      const Rail = window.TBCCSuiteRail;
      if (!Rail) {
        mountOverlay();
        return;
      }
      Rail.mountKeywordBar({
        barId: 'tbcc-tv-kw-bar',
        hint: 'Refines video titles on this grid (space/comma separated). Same Include/Exclude as Filters tab · No Gay still applies.',
        getInclude: () => settings.titleInclude || '',
        getExclude: () => settings.titleExclude || '',
        shouldMount: () => !/\/videos\/\d+/i.test(location.pathname || ''),
        onChange: (inc, exc) => {
          settings.titleInclude = inc;
          settings.titleExclude = exc;
          saveSettings();
          applyAllGridControls();
          // Keep overlay Filters fields in sync if open
          const root = document.getElementById(OVERLAY_ID);
          const oi = root?.querySelector('#tbccTvInc');
          const oe = root?.querySelector('#tbccTvExc');
          if (oi) oi.value = inc;
          if (oe) oe.value = exc;
        },
      });
      mountOverlay();
    }

    const wait = (ms) => new Promise((r) => setTimeout(r, ms));

    function snakeCase(str) {
      return String(str || '')
        .replace(/\W+/g, ' ')
        .toLowerCase()
        .trim()
        .split(/\s+/)
        .join('_');
    }

    function isWatchPage() {
      return /\/videos?\//i.test(location.pathname);
    }

    function removeDownloadButtons() {
      document.querySelectorAll('a.__tbcc_tv_dl').forEach((el) => el.closest('li')?.remove() || el.remove());
      document.getElementById('tbcc-tv-dl-fab')?.remove();
      document.getElementById('tbcc-tv-dl-fallback')?.remove();
      if (dlGuardObserver) {
        dlGuardObserver.disconnect();
        dlGuardObserver = null;
      }
    }

    function resolveVideoFileUrl(video) {
      if (!video) return '';
      const direct = String(video.currentSrc || video.src || '').trim();
      if (direct && !direct.startsWith('blob:')) return direct;
      const source = video.querySelector?.('source[src]');
      const fromSource = String(source?.getAttribute('src') || source?.src || '').trim();
      if (fromSource && !fromSource.startsWith('blob:')) return fromSource;
      // KVS / flashvars often embed video_url or video_alt_url
      try {
        const scripts = Array.from(document.querySelectorAll('script:not([src])'));
        for (const s of scripts) {
          const t = s.textContent || '';
          if (!/video_url|video_alt_url|flashvars/i.test(t)) continue;
          const m =
            t.match(/(?:video_alt_url|video_url)\s*[:=]\s*['"]([^'"]+)['"]/i) ||
            t.match(/['"](https?:\/\/[^'"]+\.mp4[^'"]*)['"]/i);
          if (m && m[1]) return m[1].replace(/\\u0026/g, '&').replace(/\\\//g, '/');
        }
      } catch (_) {
        /* ignore */
      }
      return direct || fromSource || '';
    }

    async function ensureVideoElement() {
      let video = document.querySelector('#kt_player video, .fp-player video, video');
      if (video) return video;
      const playButton = document.querySelector(
        '#kt_player a.fp-play, .fp-ui a.fp-play, .fp-play, #kt_player > div.fp-player > div.fp-ui > div.fp-controls a.fp-play'
      );
      if (playButton) {
        try {
          playButton.click();
        } catch (_) {
          /* ignore */
        }
        await wait(600);
        video = document.querySelector('#kt_player video, .fp-player video, video');
      }
      return video || null;
    }

    async function getVid(fileURL) {
      let controller = new AbortController();
      let { signal } = controller;
      const { title } = document;
      document.title = `[↓] ${title.replace(/\[↓\]/g, '')}`;
      const fileName =
        snakeCase(title.replace(/ThisVid\.com|at ThisVid tube/gi, '').trim()) || 'thisvid_video';

      let resp = await fetch(fileURL, { method: 'GET', redirect: 'follow', signal, credentials: 'include' });
      if (resp.redirected) {
        controller.abort();
        controller = new AbortController();
        signal = controller.signal;
        resp = await fetch(resp.url, { method: 'GET', signal, credentials: 'include' });
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      let url;
      try {
        url = URL.createObjectURL(blob);
      } catch (_) {
        window.open(resp.url || fileURL);
        return false;
      }
      const a = document.createElement('a');
      document.title = `[✓] ${title.replace(/\[✓\]/g, '')}`;
      a.style.display = 'none';
      a.href = url;
      a.download = `${fileName}.mp4`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      a.remove();
      return true;
    }

    function bindDownloadClick(el, getUrl) {
      if (el.__tbccTvDlBound) return;
      el.__tbccTvDlBound = true;
      el.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const fileURL = typeof getUrl === 'function' ? getUrl() : getUrl;
        if (!fileURL) {
          showTvToast('Play the video once, then retry Download');
          addDownloadButton().catch(() => {});
          return;
        }
        el.setAttribute('disabled', '1');
        try {
          await getVid(fileURL);
          showTvToast('Download started');
        } catch (_) {
          document.title = `[✗] ${document.title.replace(/\[✗\]/g, '')}`;
          window.open(fileURL);
        } finally {
          el.removeAttribute('disabled');
        }
      });
    }

    function currentDlUrl() {
      return (
        resolveVideoFileUrl(document.querySelector('#kt_player video, .fp-player video, video')) ||
        document.getElementById('tbcc-tv-dl-fab')?.dataset?.fileUrl ||
        ''
      );
    }

    /** Persistent FAB on documentElement — same survival model as #tbcc-tv-scroll-status. */
    function ensureDownloadFab(fileURL) {
      let btn = document.getElementById('tbcc-tv-dl-fab');
      if (!btn) {
        btn = document.createElement('button');
        btn.type = 'button';
        btn.id = 'tbcc-tv-dl-fab';
        btn.textContent = '↓ Download';
        btn.title = 'TBCC ThisVid download';
        document.documentElement.appendChild(btn);
        bindDownloadClick(btn, () => currentDlUrl());
      }
      if (fileURL) btn.dataset.fileUrl = fileURL;
      btn.classList.add('on');
      // Re-home if site somehow yanked the node into a disposable subtree
      if (btn.parentElement !== document.documentElement) {
        document.documentElement.appendChild(btn);
      }
      return btn;
    }

    function mountClassicShareDownload(fileURL) {
      if (document.querySelector('#flagging_container a.__tbcc_tv_dl, .share_buttons a.__tbcc_tv_dl')) {
        return true;
      }
      const flagContainer =
        document.querySelector('#flagging_container') ||
        document.querySelector(
          '#video_share_list, ul.share_list, .share_buttons, .tools-right, .video_tools ul, .rate-holder + ul'
        );
      if (!flagContainer) return false;

      const li = document.createElement('li');
      const a = document.createElement('a');
      const span = document.createElement('span');
      li.classList.add('share_button');
      li.setAttribute('data-tbcc-tv-dl', '1');
      a.classList.add('__dl', '__tbcc_tv_dl');
      a.href = fileURL || '#';
      a.title = 'Download video';
      a.innerHTML = '<span class="tooltip">download</span>';
      span.textContent = '↓';
      a.appendChild(span);
      bindDownloadClick(a, () => currentDlUrl() || fileURL);
      li.appendChild(a);
      flagContainer.appendChild(li);
      return true;
    }

    function ensureDlGuard() {
      if (dlGuardObserver || !isWatchPage()) return;
      dlGuardObserver = new MutationObserver(() => {
        if (!settings.downloadButton || !isWatchPage()) return;
        const fab = document.getElementById('tbcc-tv-dl-fab');
        if (!fab || !fab.isConnected || fab.parentElement !== document.documentElement) {
          ensureDownloadFab(currentDlUrl());
        } else if (!fab.classList.contains('on')) {
          fab.classList.add('on');
        }
      });
      dlGuardObserver.observe(document.documentElement, { childList: true, subtree: true });
    }

    async function addDownloadButton() {
      if (!settings.downloadButton || !isWatchPage()) {
        document.getElementById('tbcc-tv-dl-fab')?.classList.remove('on');
        return;
      }

      // Never pause / remount player on a timer — that rebuilds the tools bar and eats in-page buttons.
      let fileURL = currentDlUrl();
      if (!fileURL) {
        const video = await ensureVideoElement();
        fileURL = resolveVideoFileUrl(video);
        if (!fileURL && video) {
          await wait(350);
          fileURL = resolveVideoFileUrl(video);
        }
      }

      ensureDownloadFab(fileURL);
      mountClassicShareDownload(fileURL); // nice-to-have; site may wipe it — FAB is source of truth
      ensureDlGuard();

      const video = document.querySelector('#kt_player video, .fp-player video, video');
      if (video && !video.__tbccTvDlBound) {
        video.__tbccTvDlBound = true;
        const refresh = () => {
          const url = resolveVideoFileUrl(video);
          if (!url) return;
          const fab = ensureDownloadFab(url);
          fab.dataset.fileUrl = url;
          const a = document.querySelector('a.__tbcc_tv_dl');
          if (a) a.href = url;
          else mountClassicShareDownload(url);
        };
        video.addEventListener('loadedmetadata', refresh);
        video.addEventListener('play', refresh);
        video.addEventListener('durationchange', refresh);
      }
    }

    let observer = null;
    let dlTimer = null;
    let dlGuardObserver = null;

    function teardown() {
      if (observer) {
        observer.disconnect();
        observer = null;
      }
      if (dlTimer) {
        clearInterval(dlTimer);
        dlTimer = null;
      }
      window.removeEventListener('scroll', onScrollInfinite);
      friendAbort = true;
      document.getElementById(OVERLAY_ID)?.remove();
      document.getElementById('tbcc-tv-title-filter-bar')?.remove();
      document.getElementById('tbcc-tv-enhancer-style')?.remove();
      document.getElementById('tbcc-tv-scroll-status')?.remove();
      document.getElementById('tbcc-tv-friend-panel')?.remove();
      document.querySelectorAll('[data-tbcc-tv-pager-hidden]').forEach((el) => {
        el.removeAttribute('data-tbcc-tv-pager-hidden');
      });
      document.querySelectorAll('.tbcc-tv-title-filtered').forEach((el) => {
        el.classList.remove('tbcc-tv-title-filtered');
      });
      removeDownloadButtons();
    }

    const THISVID_PENDING_KEY = 'tbccThisVidPendingUpload';

    function findDirectUrlInput() {
      const candidates = [
        'input[name="url"]',
        'input[name="video_url"]',
        'input[name="remote_url"]',
        'input[name="file_url"]',
        'input#url',
        'textarea[name="url"]',
        'input[placeholder*="URL" i]',
        'input[placeholder*="http" i]',
        'input[placeholder*="link" i]',
        'input[aria-label*="URL" i]',
        'input[aria-label*="link" i]',
      ];
      for (let i = 0; i < candidates.length; i++) {
        const el = document.querySelector(candidates[i]);
        if (el && !el.disabled && el.offsetParent !== null) return el;
      }
      // Prefer text inputs near "URL" / "direct" labels on upload pages
      const labels = Array.from(document.querySelectorAll('label, .form-group, .field, div'));
      for (let j = 0; j < labels.length; j++) {
        const t = String(labels[j].textContent || '').toLowerCase();
        if (!/(direct\s*link|video\s*url|from\s*url|remote\s*url|^url\b)/i.test(t)) continue;
        const inp = labels[j].querySelector('input[type="text"], input[type="url"], input:not([type]), textarea');
        if (inp && !inp.disabled) return inp;
      }
      return null;
    }

    /** Select "From a URL" radio / tab on my_video_upload step 1. */
    function selectFromUrlUploadMode() {
      const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
      for (let i = 0; i < radios.length; i++) {
        const r = radios[i];
        const id = String(r.id || '');
        const name = String(r.name || '');
        const val = String(r.value || '');
        let labelText = '';
        if (id) {
          const esc =
            typeof CSS !== 'undefined' && CSS.escape
              ? CSS.escape(id)
              : String(id).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
          const lab = document.querySelector(`label[for="${esc}"]`);
          if (lab) labelText = lab.textContent || '';
        }
        if (!labelText && r.parentElement) {
          labelText = r.parentElement.textContent || '';
        }
        const blob = `${labelText} ${val} ${name} ${id}`.toLowerCase();
        if (/(from\s*a\s*url|from\s*url|remote\s*url|direct\s*link|by\s*url|url\s*upload)/i.test(blob) && !/device|file|local|computer/i.test(blob)) {
          try {
            if (!r.checked) {
              r.click();
              r.checked = true;
              r.dispatchEvent(new Event('change', { bubbles: true }));
              r.dispatchEvent(new Event('input', { bubbles: true }));
            }
          } catch (_) {}
          return true;
        }
      }
      // Label click fallback
      const labs = Array.from(document.querySelectorAll('label, .radio, .form-check, span, div'));
      for (let j = 0; j < labs.length; j++) {
        const t = String(labs[j].textContent || '').replace(/\s+/g, ' ').trim();
        if (/^from a url$/i.test(t) || /^from url$/i.test(t) || /from a url/i.test(t) && t.length < 40) {
          try {
            labs[j].click();
          } catch (_) {}
          return true;
        }
      }
      return clickUrlUploadTab();
    }

    function clickContinueIfNeeded() {
      if (findDirectUrlInput()) return false;
      const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], a.btn, .btn'));
      for (let i = 0; i < buttons.length; i++) {
        const t = String(buttons[i].textContent || buttons[i].value || '')
          .trim()
          .toLowerCase();
        if (/^continue$|^next$|^proceed$/i.test(t)) {
          try {
            buttons[i].click();
          } catch (_) {}
          return true;
        }
      }
      return false;
    }

    function clickUrlUploadTab() {
      const nodes = Array.from(document.querySelectorAll('a, button, [role="tab"], .nav-link, .tab, label, span'));
      for (let i = 0; i < nodes.length; i++) {
        const t = String(nodes[i].textContent || '').trim().toLowerCase();
        if (
          /^(url|link|from url|from a url|remote|direct link|upload by url)$/i.test(t) ||
          /direct\s*link|from\s*a?\s*url|by\s*url/.test(t)
        ) {
          try {
            nodes[i].click();
          } catch (_) {}
          return true;
        }
      }
      return false;
    }

    function setInputValue(el, value) {
      el.focus();
      el.value = value;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function showTvToast(msg) {
      document.querySelectorAll('.tbcc-tv-toast').forEach((n) => n.remove());
      const el = document.createElement('div');
      el.className = 'tbcc-tv-toast';
      el.textContent = msg;
      el.style.cssText =
        'position:fixed;z-index:1000001;left:50%;bottom:24px;transform:translateX(-50%);' +
        'background:rgba(20,20,20,.94);color:#eee;border:1px solid #444;border-radius:8px;' +
        'padding:10px 14px;font:13px/1.3 system-ui,sans-serif;pointer-events:none;';
      document.documentElement.appendChild(el);
      setTimeout(() => el.remove(), 3200);
    }

    function consumePendingPayload(cb) {
      try {
        if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
          chrome.storage.local.get(THISVID_PENDING_KEY, (got) => {
            const payload = got && got[THISVID_PENDING_KEY];
            if (payload && payload.url) {
              chrome.storage.local.remove(THISVID_PENDING_KEY, () => cb(payload));
            } else cb(null);
          });
          return;
        }
      } catch (_) {}
      try {
        const raw = localStorage.getItem(THISVID_PENDING_KEY);
        if (raw) {
          localStorage.removeItem(THISVID_PENDING_KEY);
          cb(JSON.parse(raw));
          return;
        }
      } catch (_) {}
      cb(null);
    }

    function tryFillPendingThisVidUrl() {
      if (!isThisVidUploadPage()) return;
      if (window.__tbccTvPendingFillBusy) return;
      window.__tbccTvPendingFillBusy = true;
      consumePendingPayload((payload) => {
        window.__tbccTvPendingFillBusy = false;
        if (!payload || !payload.url) return;
        if (payload.ts && Date.now() - Number(payload.ts) > 30 * 60 * 1000) {
          showTvToast('Pending URL expired — re-queue from Upload tab or album');
          return;
        }
        // Queue into Upload library for the overlay list
        try {
          const entry = draftFromMediaUrls([payload.url]);
          if (payload.title) entry.title = String(payload.title).slice(0, 120);
          if (payload.albumUrl) {
            entry.description = [entry.description, '', `Source: ${payload.albumUrl}`]
              .join('\n')
              .slice(0, 4000);
          }
          upsertUploadLibraryEntry(entry);
        } catch (_) {}

        const attempt = (n) => {
          selectFromUrlUploadMode();
          if (!findDirectUrlInput()) clickContinueIfNeeded();
          const r = fillThisVidUploadForm(payload, { force: false });
          if (r.ok) {
            showTvToast(`Filled ${r.filled.join(' · ')} — review & submit`);
            try {
              (findDirectUrlInput() || findUploadFormField('title'))?.scrollIntoView({
                block: 'center',
                behavior: 'smooth',
              });
            } catch (_) {}
            return;
          }
          if (n < 5) {
            setTimeout(() => attempt(n + 1), 500);
            return;
          }
          showTvToast('ThisVid fields not ready — use Upload tab → Fill form');
          try {
            navigator.clipboard.writeText(payload.url);
          } catch (_) {}
        };
        attempt(0);
      });
    }

    function boot() {
      // Drop leftover pre-chevron chrome if an old inject stuck in the tab
      document.getElementById('tbcc-tv-title-filter-bar')?.remove();
      document.getElementById('tbcc-tv-friend-panel')?.remove();
      ensureStyle();
      window.TBCCSuiteRail?.ensureStyles();
      mountTitleFilterBar();
      applyAllGridControls();
      setupInfiniteScroll();
      addDownloadButton().catch(() => {});
      tryFillPendingThisVidUrl();
      dlTimer = setInterval(() => {
        addDownloadButton().catch(() => {});
        tryFillPendingThisVidUrl();
      }, 4000);

      observer = new MutationObserver((mutations) => {
        // Ignore our own overlay mutations — remounting killed open <select> menus
        if (
          mutations.length &&
          mutations.every((m) => {
            const t = m.target;
            return t && (t.id === OVERLAY_ID || t.closest?.(`#${OVERLAY_ID}`));
          })
        ) {
          return;
        }
        clearTimeout(observer._t);
        observer._t = setTimeout(() => {
          if (document.activeElement?.closest?.(`#${OVERLAY_ID}`)) return;
          applyCardFilters();
          ensureOverlayMounted();
          addDownloadButton().catch(() => {});
          if (settings.infiniteScroll) hidePagination();
          if (loadIntelMeta().recordIntel !== false) {
            try {
              scanGridIntel();
            } catch (_) {
              /* ignore */
            }
          }
        }, 500);
      });
      observer.observe(document.documentElement, { childList: true, subtree: true });

      try {
        if (loadIntelMeta().recordIntel !== false) scanGridIntel();
      } catch (_) {}

      if (typeof tbccBindModuleDisableListener === 'function') {
        tbccBindModuleDisableListener('thisvid_enhancer', teardown);
      }
      if (!COMMUNITY) {
        try {
          if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.flushIfAtCap === 'function') {
            globalThis.tbccBrowseIntel.flushIfAtCap({
              rows: loadIntelRows(),
              meta: loadIntelMeta(),
              applyTrimmed: (stored) => saveJson(INTEL_ROWS_KEY, stored),
              toast: (msg) => {
                try {
                  showTvToast(msg);
                } catch (_) {}
              },
            });
          }
        } catch (_) {}
      }
      console.info(COMMUNITY ? '[AOF ThisVid Enhancer] community ready' : '[TBCC ThisVid] enhancer ready (chevron · download · meta · intel)');
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', boot);
    } else {
      boot();
    }
  })();
});
