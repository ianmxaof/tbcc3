/* Home feed masonry — adapted from FetLife Suite - Home Feed (RYSTA, MIT) */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const FILTERS = [
    { label: 'All', path: '/home' },
    { label: 'Pics', path: '/home/pictures' },
    { label: 'Vids', path: '/home/videos' },
    { label: 'Text', path: '/home/statuses' },
    { label: 'Writings', path: '/home/writings' },
    { label: 'AMA', path: '/home/ama' },
    { label: 'Audio', path: '/home/audio' },
    { label: 'For You', path: '/home/for-you' },
  ];

  let masonryWrap = null;
  let columns = [];
  let placedItems = new WeakSet();
  let currentColCount = 0;
  let postObserver = null;
  let started = false;

  function getColumnCount() {
    const w = window.innerWidth;
    if (w >= 2400) return 4;
    if (w >= 1200) return 3;
    if (w >= 720) return 2;
    return 1;
  }

  function getShortestColumn() {
    let shortest = 0;
    let minHeight = Infinity;
    columns.forEach((col, i) => {
      const h = col.offsetHeight;
      if (h < minHeight) {
        minHeight = h;
        shortest = i;
      }
    });
    return columns[shortest];
  }

  function getThemeVars() {
    const rgb = window.getComputedStyle(document.body).backgroundColor.match(/\d+/g);
    const isDark =
      !rgb || parseInt(rgb[0], 10) * 0.299 + parseInt(rgb[1], 10) * 0.587 + parseInt(rgb[2], 10) * 0.114 < 128;
    return isDark
      ? '--card-bg:#121212; --card-border:none; --card-shadow:none; --avatar-border:2px solid #333;'
      : '--card-bg:#f0f0f0; --card-border:1px solid #e2e8f0; --card-shadow:none; --avatar-border:2px solid #e2e8f0;';
  }

  function injectStyles() {
    S.ensureStyle(
      'tbcc-fl-home-feed-style',
      `
      #tbcc-fl-back-to-top {
        position: fixed; bottom: 28px; right: 100px; z-index: 9999;
        width: 44px; height: 44px; border-radius: 50%;
        background: rgba(30,30,30,.85); border: 1px solid #444; color: #ccc;
        cursor: pointer; display: flex; align-items: center; justify-content: center;
        opacity: 0; visibility: hidden; transition: opacity .25s, visibility .25s;
      }
      #tbcc-fl-back-to-top.fl-visible { opacity: 1; visibility: visible; }
      #tbcc-fl-back-to-top:hover { background: #e11d48; border-color: #e11d48; color: #fff; }
      #fl-feed-filters {
        display: flex; gap: 6px; padding: 8px 0 10px; flex-wrap: wrap; width: 100%; box-sizing: border-box;
      }
      #fl-feed-filters a {
        display: inline-block; padding: 5px 14px; border-radius: 20px; font-size: 12px; font-weight: 600;
        text-decoration: none; color: #aaa; background: #1e1e1e; border: 1px solid #333;
      }
      #fl-feed-filters a.fl-filter-active { color: #fff; background: #e11d48; border-color: #e11d48; }
      body.fl-home-active { ${getThemeVars()} }
      body.fl-home-active .max-w-screen-xl { max-width: 100vw !important; padding-left: 1.5rem !important; padding-right: 1.5rem !important; }
      body.fl-home-active .mx-auto.max-w-3xl { max-width: 100% !important; margin: 0 !important; }
      body.fl-home-active .flex.flex-col.lg\\:flex-row > aside { display: none !important; }
      #fl-masonry-wrap { display: flex !important; gap: 1.5rem; width: 100%; align-items: flex-start; }
      .fl-masonry-col { flex: 1; display: flex; flex-direction: column; gap: 1.5rem; min-width: 0; }
      .fl-masonry-col > div {
        border-radius: 12px; padding: 0 1.5rem !important;
        background-color: var(--card-bg) !important; border: var(--card-border) !important;
      }
      .fl-masonry-col > div header a.flex-none { width: 72px !important; height: 72px !important; margin-right: 1.25rem !important; }
      .fl-masonry-col > div header a.flex-none img {
        width: 100% !important; height: 100% !important; border-radius: 50% !important; object-fit: cover;
        border: var(--avatar-border) !important;
      }
      body.fl-home-active header.flex.h-14 { position: sticky !important; top: 0; z-index: 50; }
    `
    );
  }

  function mountBackToTop() {
    if (document.getElementById('tbcc-fl-back-to-top')) return;
    const btn = document.createElement('button');
    btn.id = 'tbcc-fl-back-to-top';
    btn.type = 'button';
    btn.title = 'Back to top';
    btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4l-8 8h5v8h6v-8h5z"/></svg>';
    btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
    document.body.appendChild(btn);
    window.addEventListener('scroll', () => {
      btn.classList.toggle('fl-visible', window.scrollY > 600);
    });
  }

  function getCurrentFilter() {
    const path = window.location.pathname;
    if (path === '/home') return '/home';
    for (const f of FILTERS) if (f.path !== '/home' && path.startsWith(f.path)) return f.path;
    return '/home';
  }

  function injectFilterBar() {
    if (document.getElementById('fl-feed-filters')) return;
    if (!/^\/home(\/|$)/.test(location.pathname)) return;
    const bar = document.createElement('div');
    bar.id = 'fl-feed-filters';
    const current = getCurrentFilter();
    FILTERS.forEach((f) => {
      const a = document.createElement('a');
      a.href = f.path;
      a.textContent = f.label;
      if (f.path === current) a.classList.add('fl-filter-active');
      bar.appendChild(a);
    });
    const main = document.getElementById('responsive-feed') || document.querySelector('main');
    if (main) main.insertBefore(bar, main.firstChild);
  }

  function createMasonryContainer(storiesList) {
    if (masonryWrap) {
      masonryWrap.remove();
      masonryWrap = null;
      columns = [];
    }
    currentColCount = getColumnCount();
    masonryWrap = document.createElement('div');
    masonryWrap.id = 'fl-masonry-wrap';
    for (let i = 0; i < currentColCount; i++) {
      const col = document.createElement('div');
      col.className = 'fl-masonry-col';
      masonryWrap.appendChild(col);
      columns.push(col);
    }
    storiesList.parentNode.insertBefore(masonryWrap, storiesList);
  }

  function distributeNewItems(storiesList) {
    const items = [];
    for (const child of Array.from(storiesList.children)) {
      if (child.nodeType !== 1) continue;
      if (child.classList.contains('infinite-loading-container')) continue;
      if (placedItems.has(child)) continue;
      items.push(child);
    }
    items.forEach((item) => {
      placedItems.add(item);
      getShortestColumn().appendChild(item);
    });
  }

  function fixInfiniteLoader() {
    let attempts = 0;
    const interval = setInterval(() => {
      attempts += 1;
      const masonry = document.getElementById('fl-masonry-wrap');
      const storiesList = document.getElementById('stories-list');
      const loader = document.querySelector('.infinite-loading-container');
      if (masonry && storiesList && loader && storiesList.contains(loader)) {
        masonry.parentElement.appendChild(loader);
        clearInterval(interval);
      }
      if (attempts > 30) clearInterval(interval);
    }, 500);
  }

  function initMasonry() {
    const storiesList = document.getElementById('stories-list');
    if (!storiesList) return;
    if (!masonryWrap) createMasonryContainer(storiesList);
    distributeNewItems(storiesList);
    if (postObserver) postObserver.disconnect();
    postObserver = new MutationObserver(() => {
      setTimeout(() => distributeNewItems(storiesList), 150);
    });
    postObserver.observe(storiesList, { childList: true });
    fixInfiniteLoader();
  }

  function teardownMasonry() {
    if (postObserver) postObserver.disconnect();
    postObserver = null;
    if (masonryWrap) {
      const storiesList = document.getElementById('stories-list');
      if (storiesList) {
        columns.forEach((col) => {
          while (col.firstChild) storiesList.appendChild(col.firstChild);
        });
      }
      masonryWrap.remove();
      masonryWrap = null;
      columns = [];
      placedItems = new WeakSet();
      currentColCount = 0;
    }
  }

  function checkPage() {
    const isHome = location.pathname.startsWith('/home');
    document.body.classList.toggle('fl-home-active', isHome);
    injectFilterBar();
    if (isHome) setTimeout(initMasonry, 400);
    else teardownMasonry();
  }

  FL.features = FL.features || {};
  FL.features.homeFeed = {
    start() {
      if (started) return;
      started = true;
      injectStyles();
      mountBackToTop();
      checkPage();
      this._unsubSpa = S.spa.onChange(() => setTimeout(checkPage, 100));
      this._onResize = () => {
        if (!location.pathname.startsWith('/home')) return;
        const n = getColumnCount();
        if (n === currentColCount) return;
        const storiesList = document.getElementById('stories-list');
        if (!storiesList) return;
        columns.forEach((col) => {
          while (col.firstChild) {
            placedItems.delete(col.firstChild);
            storiesList.insertBefore(col.firstChild, storiesList.querySelector('.infinite-loading-container'));
          }
        });
        createMasonryContainer(storiesList);
        distributeNewItems(storiesList);
      };
      window.addEventListener('resize', this._onResize);
    },
    stop() {
      started = false;
      this._unsubSpa?.();
      if (this._onResize) window.removeEventListener('resize', this._onResize);
      teardownMasonry();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
