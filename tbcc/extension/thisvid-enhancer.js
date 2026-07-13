/**
 * TBCC ThisVid enhancer — title include/exclude (Erome-parity) + video download button.
 * Passive content script; toggle via TBCC: Site tools → ThisVid enhancer.
 */
tbccWaitForModule('thisvid_enhancer', function () {
  (function () {
    'use strict';

    const STORE_KEY = 'tbccThisVidEnhancerSettings';
    const DEFAULTS = {
      titleInclude: '',
      titleExclude: '',
      downloadButton: true,
      infiniteScroll: true,
    };

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

    function matchesTitle(el) {
      const title = cardTitle(el);
      if (!title) return true;
      const exclude = parseKeywords(settings.titleExclude);
      if (exclude.some((k) => title.includes(k))) return false;
      const include = parseKeywords(settings.titleInclude);
      if (include.length && !include.every((k) => title.includes(k))) return false;
      return true;
    }

    function applyTitleFilter() {
      cardNodes().forEach((el) => {
        const hide = !matchesTitle(el);
        const wrap = el.closest('.tumbpu, .thumb-holder, .item, .thumb, .video-item') || el;
        wrap.classList.toggle('tbcc-tv-title-filtered', hide);
        if (wrap !== el) el.classList.toggle('tbcc-tv-title-filtered', hide);
      });
    }

    function ensureStyle() {
      if (document.getElementById('tbcc-tv-enhancer-style')) return;
      const style = document.createElement('style');
      style.id = 'tbcc-tv-enhancer-style';
      style.textContent = `
        #tbcc-tv-title-filter-bar {
          position: fixed; z-index: 999990; left: 12px; bottom: 16px;
          display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
          max-width: min(520px, calc(100vw - 24px));
          padding: 10px 12px; background: rgba(30,30,30,.94); color: #ddd;
          border: 1px solid #444; border-radius: 10px;
          box-shadow: 0 8px 24px rgba(0,0,0,.45); font: 12px/1.3 system-ui, sans-serif;
        }
        #tbcc-tv-title-filter-bar label {
          display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 140px; color: #aaa;
        }
        #tbcc-tv-title-filter-bar input {
          background: #222; border: 1px solid #555; color: #eee; border-radius: 6px;
          padding: 6px 8px; width: 100%;
        }
        #tbcc-tv-title-filter-bar .ee-tf-hint { width: 100%; color: #777; font-size: 11px; }
        #tbcc-tv-title-filter-bar button {
          background: #333; color: #eee; border: 1px solid #555; border-radius: 6px;
          padding: 6px 10px; cursor: pointer; align-self: flex-end;
        }
        .tbcc-tv-title-filtered { display: none !important; }
        a.__tbcc_tv_dl span { color: #fff; font-size: 32px; }
        [data-tbcc-tv-pager-hidden="1"] { display: none !important; }
        .tbcc-tv-page-sep {
          grid-column: 1 / -1; width: 100%; display: flex; align-items: center;
          gap: 12px; margin: 16px 0 8px; color: #c44; font: 600 13px/1 system-ui, sans-serif;
        }
        .tbcc-tv-page-sep::before, .tbcc-tv-page-sep::after {
          content: ''; flex: 1; height: 1px; background: linear-gradient(90deg, transparent, #444, transparent);
        }
        #tbcc-tv-scroll-status {
          position: fixed; z-index: 999989; left: 50%; transform: translateX(-50%); bottom: 72px;
          background: rgba(20,20,20,.92); color: #ddd; border: 1px solid #444; border-radius: 999px;
          padding: 6px 14px; font: 12px/1.3 system-ui, sans-serif; pointer-events: none;
          display: none;
        }
        #tbcc-tv-scroll-status.on { display: block; }
      `;
      document.documentElement.appendChild(style);
    }

    /* ---------- Infinite scroll (Erome n+1 parity) ---------- */
    let currentPage = 1;
    let loadingPage = false;
    let scrollLocked = false;
    let reachedEnd = false;
    let seenHrefs = new Set();

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
        if (el.closest?.('#tbcc-tv-title-filter-bar')) continue;
        const links = el.querySelectorAll('a');
        if (links.length >= 3 && /\d/.test(el.textContent || '')) return el;
      }
      // Heuristic: compact control with many numeric page links (ThisVid circles)
      for (const el of document.querySelectorAll('div, ul, nav, ol')) {
        if (el.closest?.('#tbcc-tv-title-filter-bar, #tbcc-fl-overlay')) continue;
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

    function detectCurrentPage() {
      const u = new URL(location.href);
      if (u.searchParams.has('page')) {
        return Math.max(1, parseInt(u.searchParams.get('page'), 10) || 1);
      }
      const pathM = location.pathname.match(/\/(\d+)\/?$/);
      if (pathM && !/\/videos\/[^/]+\/?$/.test(location.pathname)) {
        return Math.max(1, parseInt(pathM[1], 10) || 1);
      }
      const pag = findPaginationRoot();
      if (pag) {
        const active =
          pag.querySelector('.active, .current, .selected, [aria-current="page"]') ||
          [...pag.querySelectorAll('a, span, button')].find((el) => {
            const t = (el.textContent || '').trim();
            if (!/^\d+$/.test(t)) return false;
            const cs = getComputedStyle(el);
            // ThisVid highlights current page in red
            const c = cs.backgroundColor || '';
            return /rgb\(\s*2\d\d/.test(c) || el.className?.toLowerCase?.().includes('active');
          });
        const n = parseInt((active?.textContent || '').trim(), 10);
        if (n > 0) return n;
      }
      return 1;
    }

    function urlForPage(page) {
      const u = new URL(location.href);
      if (u.searchParams.has('page') || u.searchParams.has('from')) {
        if (u.searchParams.has('page')) u.searchParams.set('page', String(page));
        if (u.searchParams.has('from')) u.searchParams.set('from', String(page));
        return u.href;
      }
      const path = location.pathname.replace(/\/$/, '') || '';
      const pathM = path.match(/^(.*)\/(\d+)$/);
      if (pathM && !/\/videos\/[^/]+$/.test(path)) {
        return `${location.origin}${pathM[1]}/${page}/`;
      }
      // Prefer explicit next link pattern from pager when possible
      const pag = findPaginationRoot();
      if (pag) {
        const link = [...pag.querySelectorAll('a[href]')].find(
          (a) => (a.textContent || '').trim() === String(page)
        );
        if (link?.href) return link.href;
        const next = pag.querySelector('a[rel="next"]');
        if (next?.href && page === currentPage + 1) return next.href;
      }
      u.searchParams.set('page', String(page));
      return u.href;
    }

    function findGridContainer() {
      const thumbs = [...document.querySelectorAll('a.tumbpu, .tumbpu')];
      if (thumbs.length >= 2) {
        let a = thumbs[0];
        let b = thumbs[1];
        const path = new Set();
        for (let el = a; el; el = el.parentElement) path.add(el);
        for (let el = b; el; el = el.parentElement) {
          if (path.has(el) && el !== document.body) return el;
        }
      }
      return (
        document.querySelector(
          '.thumbs, .list-videos, #list_videos_common_videos_list, .video-list, .videos'
        ) || null
      );
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
      el.classList.add('on');
      el.textContent = msg || `TBCC infinite · page ${currentPage}` + (loadingPage ? ' · loading…' : '');
    }

    async function loadNextPage() {
      if (!settings.infiniteScroll || loadingPage || reachedEnd) return 0;
      loadingPage = true;
      updateScrollStatus();
      const nextPage = currentPage + 1;
      const url = urlForPage(nextPage);
      try {
        const res = await fetch(url, {
          credentials: 'include',
          headers: { Accept: 'text/html', 'X-Requested-With': 'XMLHttpRequest' },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const html = await res.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const thumbs = extractThumbs(doc);
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
        hidePagination();
        applyTitleFilter();
        updateScrollStatus(`TBCC infinite · page ${currentPage} (+${added})`);
        console.info('[TBCC ThisVid] infinite +', added, '→ page', currentPage);
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
      if (!nearBottom()) return;
      scrollLocked = true;
      loadNextPage().finally(() => {
        setTimeout(() => {
          scrollLocked = false;
        }, 800);
      });
    }

    function setupInfiniteScroll() {
      window.removeEventListener('scroll', onScrollInfinite);
      if (!settings.infiniteScroll) {
        updateScrollStatus();
        return;
      }
      // Skip pure video watch pages (single player, no grid)
      const grid = findGridContainer();
      if (!grid || cardNodes().length < 2) return;
      currentPage = detectCurrentPage();
      reachedEnd = false;
      seedSeenFromDom();
      hidePagination();
      updateScrollStatus();
      window.addEventListener('scroll', onScrollInfinite, { passive: true });
      // Soft top-up if viewport is short after title-filter removes many cards
      setTimeout(() => {
        if (!settings.infiniteScroll) return;
        if (nearBottom() || document.documentElement.scrollHeight < window.innerHeight + 400) {
          void loadNextPage();
        }
      }, 600);
      console.info('[TBCC ThisVid] infinite scroll on @ page', currentPage);
    }

    function mountTitleFilterBar() {
      if (document.getElementById('tbcc-tv-title-filter-bar')) return;
      // Video watch pages: still allow keywords if a related grid exists; always mount for consistency
      ensureStyle();
      const bar = document.createElement('div');
      bar.id = 'tbcc-tv-title-filter-bar';
      bar.innerHTML = `
        <label>Include (all must match)<input type="text" id="tbccTvInc" placeholder="e.g. milf blonde" autocomplete="off"></label>
        <label>Exclude (hide if any)<input type="text" id="tbccTvExc" placeholder="e.g. gay" autocomplete="off"></label>
        <label style="flex:0 0 auto;flex-direction:row;align-items:center;gap:6px;min-width:auto">
          <input type="checkbox" id="tbccTvInfinite" style="width:auto" /> Infinite scroll
        </label>
        <button type="button" id="tbccTvKwClear">Clear</button>
        <div class="ee-tf-hint">Refines video titles on this grid (space/comma separated). Infinite scroll loads page n+1 like Erome.</div>
      `;
      document.documentElement.appendChild(bar);

      const inc = bar.querySelector('#tbccTvInc');
      const exc = bar.querySelector('#tbccTvExc');
      const inf = bar.querySelector('#tbccTvInfinite');
      inc.value = settings.titleInclude || '';
      exc.value = settings.titleExclude || '';
      inf.checked = settings.infiniteScroll !== false;

      let t = null;
      const live = () => {
        settings.titleInclude = inc.value.trim();
        settings.titleExclude = exc.value.trim();
        settings.infiniteScroll = !!inf.checked;
        saveSettings();
        applyTitleFilter();
        updateScrollStatus();
      };
      const onInput = () => {
        clearTimeout(t);
        t = setTimeout(live, 250);
      };
      inc.addEventListener('input', onInput);
      exc.addEventListener('input', onInput);
      inf.addEventListener('change', () => {
        live();
        if (inf.checked) {
          reachedEnd = false;
          setupInfiniteScroll();
        } else {
          window.removeEventListener('scroll', onScrollInfinite);
          document.getElementById('tbcc-tv-scroll-status')?.classList.remove('on');
        }
      });
      bar.querySelector('#tbccTvKwClear').addEventListener('click', () => {
        inc.value = '';
        exc.value = '';
        live();
      });
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

    async function getVid(fileURL) {
      let controller = new AbortController();
      let { signal } = controller;
      const { title } = document;
      document.title = `[↓] ${title.replace(/\[↓\]/g, '')}`;
      const fileName =
        snakeCase(title.replace(/ThisVid\.com|at ThisVid tube/gi, '').trim()) || 'thisvid_video';

      let resp = await fetch(fileURL, { method: 'GET', redirect: 'follow', signal });
      if (resp.redirected) {
        controller.abort();
        controller = new AbortController();
        signal = controller.signal;
        resp = await fetch(resp.url, { method: 'GET', signal });
      }
      const blob = await resp.blob();
      let url;
      try {
        url = URL.createObjectURL(blob);
      } catch (_) {
        window.open(resp.url);
        return false;
      }
      const a = document.createElement('a');
      document.title = `[✓] ${title.replace(/\[✓\]/g, '')}`;
      a.style.display = 'none';
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      a.remove();
      return true;
    }

    async function addDownloadButton() {
      if (!settings.downloadButton || document.querySelector('a.__tbcc_tv_dl')) return;
      const flagContainer = document.querySelector('#flagging_container');
      if (!flagContainer) return;

      let video = document.querySelector('video');
      if (!video) {
        const playButton = document.querySelector(
          '#kt_player a.fp-play, .fp-play, #kt_player > div.fp-player > div.fp-ui > div.fp-controls.fade > a.fp-play'
        );
        if (playButton) {
          playButton.click();
          await wait(500);
          video = document.querySelector('video');
        }
      }
      if (!video?.src) return;
      try {
        video.pause();
      } catch (_) {
        /* ignore */
      }

      const fileURL = video.src;
      const li = document.createElement('li');
      const a = document.createElement('a');
      const span = document.createElement('span');
      li.classList.add('share_button');
      a.classList.add('__dl', '__tbcc_tv_dl');
      a.href = fileURL;
      a.innerHTML = '<span class="tooltip">download</span>';
      span.textContent = '↓';
      a.appendChild(span);
      a.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        try {
          await getVid(fileURL);
        } catch (_) {
          document.title = `[✗] ${document.title.replace(/\[✗\]/g, '')}`;
          window.open(fileURL);
        }
      });
      li.appendChild(a);
      flagContainer.appendChild(li);
    }

    let observer = null;
    let dlTimer = null;

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
      document.getElementById('tbcc-tv-title-filter-bar')?.remove();
      document.getElementById('tbcc-tv-enhancer-style')?.remove();
      document.getElementById('tbcc-tv-scroll-status')?.remove();
      document.querySelectorAll('[data-tbcc-tv-pager-hidden]').forEach((el) => {
        el.removeAttribute('data-tbcc-tv-pager-hidden');
      });
      document.querySelectorAll('.tbcc-tv-title-filtered').forEach((el) => {
        el.classList.remove('tbcc-tv-title-filtered');
      });
      document.querySelectorAll('a.__tbcc_tv_dl').forEach((el) => el.closest('li')?.remove());
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

    function clickUrlUploadTab() {
      const nodes = Array.from(document.querySelectorAll('a, button, [role="tab"], .nav-link, .tab'));
      for (let i = 0; i < nodes.length; i++) {
        const t = String(nodes[i].textContent || '').trim().toLowerCase();
        if (/^(url|link|from url|remote|direct link|upload by url)$/i.test(t) || /direct\s*link|from\s*url|by\s*url/.test(t)) {
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
      if (!/\/upload/i.test(location.pathname + location.search)) return;
      if (window.__tbccTvPendingFillBusy) return;
      window.__tbccTvPendingFillBusy = true;
      consumePendingPayload((payload) => {
        window.__tbccTvPendingFillBusy = false;
        if (!payload || !payload.url) return;
        if (payload.ts && Date.now() - Number(payload.ts) > 30 * 60 * 1000) {
          showTvToast('Pending Erome URL expired — copy again from album');
          return;
        }
        clickUrlUploadTab();
        const fill = () => {
          const input = findDirectUrlInput();
          if (!input) {
            showTvToast('ThisVid URL field not found — paste manually');
            try {
              navigator.clipboard.writeText(payload.url);
            } catch (_) {}
            return false;
          }
          setInputValue(input, payload.url);
          if (payload.title) {
            const titleEl =
              document.querySelector('input[name="title"], input[placeholder*="Title" i], input#title') ||
              null;
            if (titleEl && !String(titleEl.value || '').trim()) setInputValue(titleEl, payload.title);
          }
          showTvToast('Filled direct link from Erome — review & submit');
          try {
            input.scrollIntoView({ block: 'center', behavior: 'smooth' });
          } catch (_) {}
          return true;
        };
        if (!fill()) setTimeout(fill, 600);
      });
    }

    function boot() {
      ensureStyle();
      mountTitleFilterBar();
      applyTitleFilter();
      setupInfiniteScroll();
      addDownloadButton().catch(() => {});
      tryFillPendingThisVidUrl();
      dlTimer = setInterval(() => {
        addDownloadButton().catch(() => {});
        tryFillPendingThisVidUrl();
      }, 4000);

      observer = new MutationObserver(() => {
        clearTimeout(observer._t);
        observer._t = setTimeout(() => {
          applyTitleFilter();
          addDownloadButton().catch(() => {});
          if (settings.infiniteScroll) hidePagination();
        }, 400);
      });
      observer.observe(document.documentElement, { childList: true, subtree: true });

      if (typeof tbccBindModuleDisableListener === 'function') {
        tbccBindModuleDisableListener('thisvid_enhancer', teardown);
      }
      console.info('[TBCC ThisVid] enhancer ready (infinite scroll)');
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', boot);
    } else {
      boot();
    }
  })();
});
