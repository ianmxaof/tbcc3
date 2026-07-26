/* TBCC-style chevron overlay: collapsible + paginated suite control */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const ROOT_ID = 'tbcc-fl-overlay';
  const TOP_KEY = 'tbcc_fl_overlay_top_v1';
  const UI_KEY = 'tbcc_fl_overlay_ui_v1';
  const SYNC_KEYS = [
    UI_KEY,
    TOP_KEY,
    'tbcc_fl_suite_flags_v1',
    'tbcc_fl_gender_filter_v1',
    'tbcc_fl_autofollow_cfg_v1',
    'tbcc_fl_social_proof_v1',
    'tbcc_fl_story_enabled_v1',
    'tbcc_fl_muted_users_v1',
    'tbcc_fl_place_nav_v1',
    'tbcc_fl_kinksters_bookmark_v1',
    'tbcc_fl_privacy_active_v1',
    'tbcc_fl_intel_rows_v1',
    'tbcc_fl_intel_meta_v1',
    'tbcc_fl_title_kw_v1',
  ];
  const INTEL_ROWS_KEY = 'tbcc_fl_intel_rows_v1';
  const INTEL_META_KEY = 'tbcc_fl_intel_meta_v1';
  const KW_KEY = 'tbcc_fl_title_kw_v1';
  const JUMP_STACK_ID = 'tbcc-fl-jump-stack';
  const PAGES = [
    { id: 'features', title: 'Features' },
    { id: 'autofollow', title: 'Auto-follow' },
    { id: 'gender', title: 'ASL filter' },
    { id: 'keywords', title: 'Keywords' },
    { id: 'flconsole', title: 'FLConsole' },
    { id: 'stories', title: 'Profile & stories' },
    { id: 'mute', title: 'Mute' },
    { id: 'intel', title: 'Intel' },
  ];

  let pageIndex = 0;
  let collapsed = true;
  let widthMode = 'slim';
  let hooks = {};
  let suppressUiPersist = false;
  let syncBound = false;

  function clampOverlayTop(px) {
    const max = Math.max(8, window.innerHeight - 140);
    return Math.min(max, Math.max(8, Math.round(Number(px) || 72)));
  }

  function loadOverlayTop() {
    const saved = S.storage.get(TOP_KEY, 72);
    return clampOverlayTop(saved);
  }

  function saveOverlayTop(px) {
    S.storage.set(TOP_KEY, clampOverlayTop(px));
  }

  function loadUiState() {
    const saved = S.storage.get(UI_KEY, null);
    const ui = saved && typeof saved === 'object' ? saved : {};
    let idx = Number(ui.pageIndex);
    if (!Number.isFinite(idx) || idx < 0 || idx >= PAGES.length) idx = 0;
    return {
      // Default collapsed when no saved UI (keeps Friend/Follow/Message clickable).
      collapsed: ui.collapsed !== false,
      pageIndex: idx,
      widthMode: (() => {
        const w = String(ui.widthMode || 'slim');
        return w === 'wide' || w === 'normal' || w === 'slim' ? w : 'slim';
      })(),
    };
  }

  function persistUiState() {
    if (suppressUiPersist) return;
    S.storage.set(UI_KEY, {
      collapsed: !!collapsed,
      pageIndex,
      widthMode,
    });
  }

  function applyOverlayTop(root) {
    if (!root) return;
    root.style.top = `${loadOverlayTop()}px`;
  }

  function applyUiState(ui, { renderBody = true } = {}) {
    if (!ui) return;
    suppressUiPersist = true;
    try {
      if (typeof ui.collapsed === 'boolean') collapsed = ui.collapsed;
      if (ui.widthMode === 'slim' || ui.widthMode === 'normal' || ui.widthMode === 'wide') {
        widthMode = ui.widthMode;
      }
      if (Number.isFinite(ui.pageIndex) && ui.pageIndex >= 0 && ui.pageIndex < PAGES.length) {
        pageIndex = ui.pageIndex;
      }
      const root = document.getElementById(ROOT_ID);
      if (root) {
        syncCollapsedUi(root);
        applyOverlayTop(root);
        if (renderBody) render();
      }
    } finally {
      suppressUiPersist = false;
    }
  }

  function bindCrossTabSync() {
    if (syncBound || typeof S.storage.subscribe !== 'function') return;
    syncBound = true;
    S.storage.subscribe(SYNC_KEYS, (key) => {
      if (key === UI_KEY) {
        applyUiState(loadUiState(), { renderBody: true });
        return;
      }
      if (key === TOP_KEY) {
        applyOverlayTop(document.getElementById(ROOT_ID));
        return;
      }
      // Hydrate / re-apply before refreshing the open panel.
      if (key === 'tbcc_fl_suite_flags_v1') {
        hooks.flags?.hydrate?.();
        hooks.onFlagsChange?.();
      }
      if (key === 'tbcc_fl_gender_filter_v1') FL.genderFilter?.apply?.();
      if (key === 'tbcc_fl_social_proof_v1') FL.socialProof?.apply?.();
      const root = document.getElementById(ROOT_ID);
      if (root && !collapsed) render();
    });
  }

  function bindChevronDrag(root, chevron) {
    let drag = null;
    const DRAG_THRESHOLD = 5;

    chevron.addEventListener('pointerdown', (e) => {
      if (e.button != null && e.button !== 0) return;
      drag = {
        pointerId: e.pointerId,
        startY: e.clientY,
        startTop: root.getBoundingClientRect().top,
        moved: false,
      };
      try {
        chevron.setPointerCapture(e.pointerId);
      } catch (_) { /* ignore */ }
      e.preventDefault();
    });

    chevron.addEventListener('pointermove', (e) => {
      if (!drag || e.pointerId !== drag.pointerId) return;
      const dy = e.clientY - drag.startY;
      if (!drag.moved && Math.abs(dy) < DRAG_THRESHOLD) return;
      drag.moved = true;
      const next = clampOverlayTop(drag.startTop + dy);
      root.style.top = `${next}px`;
      chevron.style.cursor = 'grabbing';
    });

    const endDrag = (e) => {
      if (!drag || (e && e.pointerId !== drag.pointerId)) return;
      const wasDrag = drag.moved;
      const top = root.getBoundingClientRect().top;
      if (wasDrag) saveOverlayTop(top);
      chevron.style.cursor = 'grab';
      try {
        if (e) chevron.releasePointerCapture(e.pointerId);
      } catch (_) { /* ignore */ }
      drag = null;
      if (wasDrag) {
        // Suppress the click that follows a drag so we don't toggle open/closed.
        chevron.dataset.suppressClick = '1';
        setTimeout(() => {
          delete chevron.dataset.suppressClick;
        }, 0);
      }
    };

    chevron.addEventListener('pointerup', endDrag);
    chevron.addEventListener('pointercancel', endDrag);
    chevron.addEventListener('lostpointercapture', () => {
      if (drag) {
        if (drag.moved) saveOverlayTop(root.getBoundingClientRect().top);
        drag = null;
        chevron.style.cursor = 'grab';
      }
    });
  }

  function syncCollapsedUi(root) {
    root.classList.toggle('collapsed', collapsed);
    root.classList.toggle('slim', widthMode === 'slim');
    root.classList.toggle('wide', widthMode === 'wide');
    const chevron = root.querySelector('.tbcc-chevron');
    if (chevron) chevron.textContent = collapsed ? 'FL ▸' : 'FL ◂';
    const Rail = global.TBCCSuiteRail;
    if (Rail) {
      Rail.syncJumpStack({
        stackId: JUMP_STACK_ID,
        overlayEl: root,
        visible: true,
        collapsed,
      });
    }
  }

  function loadKeywords() {
    const saved = S.storage.get(KW_KEY, null);
    if (saved && typeof saved === 'object') {
      return {
        titleInclude: String(saved.titleInclude || ''),
        titleExclude: String(saved.titleExclude || ''),
      };
    }
    return { titleInclude: '', titleExclude: '' };
  }

  function saveKeywords(kw) {
    S.storage.set(KW_KEY, {
      titleInclude: String(kw.titleInclude || ''),
      titleExclude: String(kw.titleExclude || ''),
    });
  }

  function keywordTargets() {
    const selectors = ['#stories-list > *', '#fl-masonry-wrap .fl-masonry-col > *', '#stories > *'];
    const found = new Set();
    for (const sel of selectors) {
      document.querySelectorAll(sel).forEach((el) => {
        if (el.classList?.contains('infinite-loading-container')) return;
        if ((el.textContent || '').trim().length < 20) return;
        if (el.closest(`#${ROOT_ID}`)) return;
        found.add(el);
      });
    }
    return [...found].filter((el) => ![...found].some((o) => o !== el && o.contains(el)));
  }

  function applyKeywordFilters() {
    const Rail = global.TBCCSuiteRail;
    const kw = loadKeywords();
    const match = Rail
      ? (hay) => Rail.matchesKeywords(hay, kw.titleInclude, kw.titleExclude)
      : (hay) => {
          const text = String(hay || '').toLowerCase();
          const ex = String(kw.titleExclude || '')
            .toLowerCase()
            .split(/[\s,]+/)
            .filter(Boolean);
          if (ex.some((k) => text.includes(k))) return false;
          const inc = String(kw.titleInclude || '')
            .toLowerCase()
            .split(/[\s,]+/)
            .filter(Boolean);
          if (!inc.length) return true;
          return inc.every((k) => text.includes(k));
        };
    keywordTargets().forEach((el) => {
      const ok = match(el.textContent || '');
      el.classList.toggle('tbcc-suite-kw-filtered', !ok);
    });
  }

  function mountKeywordBar() {
    const Rail = global.TBCCSuiteRail;
    if (!Rail) return;
    const kw = loadKeywords();
    Rail.mountKeywordBar({
      barId: 'tbcc-fl-kw-bar',
      hint: 'Refines feed/story text on this page (space/comma separated). Same fields as Keywords tab.',
      getInclude: () => loadKeywords().titleInclude,
      getExclude: () => loadKeywords().titleExclude,
      shouldMount: () => true,
      onChange: (inc, exc) => {
        saveKeywords({ titleInclude: inc, titleExclude: exc });
        applyKeywordFilters();
      },
    });
    void kw;
  }

  function ensureDom() {
    if (document.getElementById(ROOT_ID)) return;

    S.ensureStyle(
      ROOT_ID + '-css',
      `
      #${ROOT_ID} {
        position: fixed; z-index: 1000000; top: 72px; right: 0;
        display: flex; align-items: stretch; font: 13px/1.4 system-ui, sans-serif;
        color: #e8e8e8; pointer-events: none;
      }
      #${ROOT_ID} * { box-sizing: border-box; }
      #${ROOT_ID} .tbcc-chevron {
        pointer-events: auto; width: 28px; min-height: 120px;
        background: #141414; border: 1px solid #333; border-right: none;
        border-radius: 10px 0 0 10px; cursor: grab; color: #f43f5e;
        display: flex; align-items: center; justify-content: center;
        writing-mode: vertical-rl; text-orientation: mixed; letter-spacing: .08em;
        font-size: 11px; font-weight: 700; padding: 10px 0;
        touch-action: none; user-select: none;
      }
      #${ROOT_ID} .tbcc-chevron:active { cursor: grabbing; }
      #${ROOT_ID} .tbcc-panel {
        pointer-events: auto; width: min(300px, calc(100vw - 40px));
        max-height: min(72vh, 560px); background: #121212; border: 1px solid #333;
        border-right: none; border-radius: 12px 0 0 12px;
        box-shadow: -8px 0 28px rgba(0,0,0,.45); display: flex; flex-direction: column;
        overflow: hidden;
      }
      #${ROOT_ID}.collapsed .tbcc-panel { display: none; }
      #${ROOT_ID}.slim .tbcc-panel { width: min(240px, calc(100vw - 40px)); }
      #${ROOT_ID}.wide .tbcc-panel { width: min(360px, calc(100vw - 40px)); }
      #${ROOT_ID} .tbcc-head {
        display: flex; align-items: center; gap: 8px; padding: 10px 12px;
        background: #1a1a1a; border-bottom: 1px solid #2a2a2a;
      }
      #${ROOT_ID} .tbcc-head strong { flex: 1; font-size: 13px; }
      #${ROOT_ID} .tbcc-head button, #${ROOT_ID} .tbcc-foot button, #${ROOT_ID} .tbcc-body button.primary {
        background: #2a2a2a; color: #eee; border: 1px solid #444; border-radius: 6px;
        padding: 6px 10px; cursor: pointer;
      }
      #${ROOT_ID} .tbcc-head button:hover, #${ROOT_ID} .tbcc-foot button:hover {
        border-color: #f43f5e; color: #fff;
      }
      #${ROOT_ID} button.primary {
        background: #9f1239; border-color: #e11d48; width: 100%; margin-top: 8px; font-weight: 600;
      }
      #${ROOT_ID} button.primary.running { background: #3f1d1d; }
      #${ROOT_ID} .tbcc-tabs {
        display: flex; gap: 4px; padding: 8px; border-bottom: 1px solid #2a2a2a; overflow-x: auto;
      }
      #${ROOT_ID} .tbcc-tabs button {
        flex: 0 0 auto; background: transparent; border: 1px solid #333; color: #aaa;
        border-radius: 999px; padding: 4px 10px; cursor: pointer; font-size: 11px;
      }
      #${ROOT_ID} .tbcc-tabs button.active {
        background: #e11d48; border-color: #e11d48; color: #fff;
      }
      #${ROOT_ID} .tbcc-body { padding: 12px; overflow: auto; flex: 1; }
      #${ROOT_ID} .tbcc-foot {
        display: flex; gap: 8px; padding: 8px 12px; border-top: 1px solid #2a2a2a; background: #1a1a1a;
      }
      #${ROOT_ID} .tbcc-foot .page-ind { flex: 1; color: #888; font-size: 12px; align-self: center; }
      #${ROOT_ID} label.row {
        display: flex; gap: 8px; align-items: flex-start; padding: 6px 0; cursor: pointer;
      }
      #${ROOT_ID} .hint { color: #888; font-size: 12px; margin: 0 0 10px; }
      #${ROOT_ID} select, #${ROOT_ID} input[type="text"] {
        width: 100%; background: #1e1e1e; color: #eee; border: 1px solid #444;
        border-radius: 6px; padding: 6px 8px;
      }
      #${ROOT_ID} .field-row {
        display: flex; gap: 6px; align-items: stretch; margin-bottom: 4px;
      }
      #${ROOT_ID} .field-row input[type="text"] { flex: 1; min-width: 0; }
      #${ROOT_ID} button.clear-btn {
        flex: 0 0 auto; margin: 0; padding: 6px 10px; background: #2a2228; color: #eee;
        border: 1px solid #514049; border-radius: 6px; cursor: pointer; font-size: 12px;
      }
      #${ROOT_ID} button.clear-btn:hover { border-color: #f43f5e; }
      #${ROOT_ID} .stat { font-variant-numeric: tabular-nums; color: #fda4af; margin-top: 8px; }
      #${ROOT_ID} details.section {
        border: 1px solid #2a2a2a; border-radius: 8px; margin-bottom: 8px; padding: 0 8px;
      }
      #${ROOT_ID} details.section > summary {
        cursor: pointer; padding: 8px 4px; font-weight: 600; color: #ccc; list-style: none;
      }
      #${ROOT_ID} details.section > summary::-webkit-details-marker { display: none; }
      #${ROOT_ID} details.section > summary::before {
        content: '▸'; display: inline-block; margin-right: 6px; color: #f43f5e;
      }
      #${ROOT_ID} details.section[open] > summary::before { content: '▾'; }
    `
    );

    const root = document.createElement('div');
    root.id = ROOT_ID;
    root.innerHTML = `
      <button type="button" class="tbcc-chevron" title="TBCC FetLife Suite">FL ▸</button>
      <div class="tbcc-panel">
        <div class="tbcc-head">
          <strong>TBCC FetLife Suite</strong>
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
      </div>`;
    document.documentElement.appendChild(root);
    applyOverlayTop(root);
    syncCollapsedUi(root);
    global.TBCCSuiteRail?.ensureStyles?.();
    global.TBCCSuiteRail?.bindFootJumps?.(root);

    const tabs = root.querySelector('.tbcc-tabs');
    PAGES.forEach((p, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = p.title;
      b.dataset.page = p.id;
      b.addEventListener('click', () => {
        pageIndex = i;
        persistUiState();
        render();
      });
      tabs.appendChild(b);
    });

    const chevron = root.querySelector('.tbcc-chevron');
    bindChevronDrag(root, chevron);
    chevron.addEventListener('click', () => {
      if (chevron.dataset.suppressClick) return;
      collapsed = !collapsed;
      syncCollapsedUi(root);
      persistUiState();
    });
    root.querySelector('[data-act="collapse"]').addEventListener('click', () => {
      collapsed = true;
      syncCollapsedUi(root);
      persistUiState();
    });
    root.querySelector('[data-act="width"]')?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      widthMode = widthMode === 'slim' ? 'normal' : widthMode === 'normal' ? 'wide' : 'slim';
      syncCollapsedUi(root);
      persistUiState();
    });
    root.querySelector('[data-act="prev"]').addEventListener('click', () => {
      pageIndex = (pageIndex + PAGES.length - 1) % PAGES.length;
      persistUiState();
      render();
    });
    root.querySelector('[data-act="next"]').addEventListener('click', () => {
      pageIndex = (pageIndex + 1) % PAGES.length;
      persistUiState();
      render();
    });

    window.addEventListener(
      'resize',
      () => {
        applyOverlayTop(root);
      },
      { passive: true }
    );
  }

  function renderFeatures(body) {
    const flags = hooks.flags;
    const labels = hooks.labels || {};
    body.innerHTML = `<p class="hint">Toggle modules. Changes apply immediately.</p>`;
    Object.keys(flags.all()).forEach((key) => {
      const lab = document.createElement('label');
      lab.className = 'row';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = flags.get(key);
      cb.addEventListener('change', () => {
        flags.set(key, cb.checked);
        hooks.onFlagsChange?.(key, cb.checked);
      });
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(labels[key] || key));
      body.appendChild(lab);
    });
  }

  function renderAutoFollow(body) {
    const af = FL.autoFollow;
    const cfg = af?.loadCfg?.() || {};
    const placeCfg = FL.placeNav?.loadCfg?.() || {};
    const bm = FL.placeNav?.loadBookmark?.();
    const placeDisplay = FL.placeNav?.displayPlaceQuery?.() || placeCfg.lastQuery || '';
    const bmLabel = bm
      ? `Resume p.${bm.page}${bm.placeLabel ? ` · ${bm.placeLabel}` : ''}`
      : '';
    body.innerHTML = `
      <p class="hint">Clicks Follow on visible cards; infinite scroll fills the pool. Place opens /p/…/kinksters (navigation only — not the ASL vitals filter).</p>
      <label class="row">Place (city / area)</label>
      <div class="field-row">
        <input type="text" data-af="place" placeholder="e.g. Bangkok" />
        <button type="button" class="clear-btn" data-af="clear-place" title="Clear saved place">Clear</button>
      </div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button type="button" class="primary" data-af="go-place" style="margin-top:0;flex:1">Open kinksters</button>
        <button type="button" class="clear-btn" data-af="go-search" style="flex:0 0 auto">Search</button>
      </div>
      <p class="hint" data-af="place-hint" style="margin-top:6px">Default region for US slugs: California. Wrong slug? use Search.</p>
      <div style="display:flex;gap:8px;margin:8px 0;flex-wrap:wrap">
        <button type="button" class="clear-btn" data-af="resume" ${bm ? '' : 'disabled'} style="flex:1">${bm ? bmLabel : 'No bookmark yet'}</button>
        <button type="button" class="clear-btn" data-af="clear-bm" ${bm ? '' : 'disabled'}>Clear bookmark</button>
      </div>
      <label class="row">Speed</label>
      <select data-af="speed"></select>
      <label class="row"><input type="checkbox" data-af="skipMale" /> Respect ASL sex filters when following</label>
      <p class="hint" style="margin-top:0">When on: skip cards the ASL tab would remove (sex rules). ASL location needles do not apply on place kinksters pages.</p>
      <label class="row"><input type="checkbox" data-af="autoStartOnKinksters" /> Auto-start on /kinksters</label>
      <label class="row"><input type="checkbox" data-af="openOnSearch" /> Open this panel on /search</label>
      <div class="stat" data-af="stat">Followed: ${af?.getCount?.() || 0}</div>
      <button type="button" class="primary" data-af="toggle">Start auto-follow</button>
    `;
    const placeInput = body.querySelector('[data-af="place"]');
    placeInput.value = placeDisplay;
    const sel = body.querySelector('[data-af="speed"]');
    Object.entries(af?.SPEED_PRESETS || {}).forEach(([k, v]) => {
      const opt = document.createElement('option');
      opt.value = k;
      opt.textContent = v.label;
      if (k === (cfg.speed || 'fast')) opt.selected = true;
      sel.appendChild(opt);
    });
    body.querySelector('[data-af="skipMale"]').checked = cfg.skipMale !== false;
    body.querySelector('[data-af="autoStartOnKinksters"]').checked = cfg.autoStartOnKinksters !== false;
    body.querySelector('[data-af="openOnSearch"]').checked = cfg.openOnSearch !== false;

    const persist = () => {
      af.saveCfg({
        speed: sel.value,
        skipMale: body.querySelector('[data-af="skipMale"]').checked,
        autoStartOnKinksters: body.querySelector('[data-af="autoStartOnKinksters"]').checked,
        openOnSearch: body.querySelector('[data-af="openOnSearch"]').checked,
      });
    };
    sel.addEventListener('change', persist);
    body.querySelector('[data-af="skipMale"]').addEventListener('change', persist);
    body.querySelector('[data-af="autoStartOnKinksters"]').addEventListener('change', persist);
    body.querySelector('[data-af="openOnSearch"]').addEventListener('change', persist);

    const persistPlace = () => {
      FL.placeNav?.saveCfg?.({ lastQuery: placeInput.value.trim() });
    };
    placeInput.addEventListener('change', persistPlace);
    placeInput.addEventListener('blur', persistPlace);

    body.querySelector('[data-af="clear-place"]').addEventListener('click', () => {
      placeInput.value = '';
      FL.placeNav?.clearPlace?.();
      const hint = body.querySelector('[data-af="place-hint"]');
      if (hint) hint.textContent = 'Place cleared (saved). ASL location filter is unchanged — clear it on the ASL tab if needed.';
    });

    const go = (mode) => {
      const q = placeInput.value.trim();
      const hint = body.querySelector('[data-af="place-hint"]');
      if (!q) {
        if (hint) hint.textContent = 'Enter a place name first (e.g. Bangkok).';
        return;
      }
      // Navigation only — do not sync into ASL locationInclude.
      const r = FL.placeNav?.goPlace?.(q, { syncAsl: false, mode });
      if (hint && r?.url) hint.textContent = `Going: ${r.url}`;
    };
    body.querySelector('[data-af="go-place"]').addEventListener('click', () => go('kinksters'));
    body.querySelector('[data-af="go-search"]').addEventListener('click', () => go('search'));
    placeInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        go('kinksters');
      }
    });

    body.querySelector('[data-af="resume"]').addEventListener('click', () => {
      const url = FL.placeNav?.resumeBookmarkUrl?.();
      if (!url) return;
      location.assign(url);
    });
    body.querySelector('[data-af="clear-bm"]').addEventListener('click', () => {
      FL.placeNav?.clearBookmark?.();
      renderAutoFollow(body);
    });

    const btn = body.querySelector('[data-af="toggle"]');
    const syncBtn = () => {
      const running = af?.isRunning?.();
      btn.textContent = running ? `Stop (${af.getCount()} followed)` : 'Start auto-follow';
      btn.classList.toggle('running', !!running);
      body.querySelector('[data-af="stat"]').textContent = `Followed: ${af?.getCount?.() || 0}`;
    };
    btn.addEventListener('click', () => {
      if (af.isRunning()) af.stop();
      else {
        try {
          const path = location.pathname.replace(/\/+$/, '');
          if (/\/kinksters$/i.test(path)) {
            const page = Number(new URL(location.href).searchParams.get('page')) || 1;
            FL.placeNav?.saveBookmark?.({
              path,
              page,
              placeLabel: FL.placeNav.placeLabelFromPath?.(path) || placeInput.value.trim(),
            });
          }
        } catch (_) { /* ignore */ }
        af.start();
        const hint = body.querySelector('[data-af="place-hint"]');
        if (hint) hint.textContent = 'Bookmarking page progress — Resume later from this tab.';
      }
      syncBtn();
    });
    af.onProgress = () => syncBtn();
    af.onState = () => syncBtn();
    syncBtn();
  }

  function renderFlConsole(body) {
    const pc = FL.privacyConsole;
    const active = pc?.activeId?.() || 'lockdown';
    const levels = pc?.levels?.() || FL.privacyPresets?.levels || [];
    const status = pc?.getStatus?.() || '';
    body.innerHTML = `
      <p class="hint"><b>FLConsole</b> — one-tap FetLife <em>account</em> privacy tiers. These live on FetLife’s Settings page (not just this extension). Applying opens Settings and sets matching controls; review before you leave.</p>
      <div data-fc="levels"></div>
      <p class="hint" data-fc="status" style="margin-top:8px">${status || `Active preset: ${active}`}</p>
      <details class="section">
        <summary>Checklist for active preset</summary>
        <ul data-fc="check" style="margin:8px 0;padding-left:18px;color:#bbb;font-size:12px"></ul>
      </details>
      <details class="section">
        <summary>Gender catalog (reference)</summary>
        <p class="hint">From your FetLife gender list — for future ASL filters. Not applied automatically yet.</p>
        <p style="font-size:11px;color:#999;line-height:1.5" data-fc="genders"></p>
      </details>
    `;
    const wrap = body.querySelector('[data-fc="levels"]');
    levels.forEach((lv) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'primary';
      b.style.marginTop = '6px';
      b.textContent = lv.id === active ? `✓ ${lv.label}` : lv.label;
      b.title = lv.blurb || lv.short || '';
      const note = document.createElement('p');
      note.className = 'hint';
      note.style.margin = '2px 0 8px';
      note.textContent = lv.short || '';
      b.addEventListener('click', () => {
        pc?.applyPreset?.(lv.id);
        const st = body.querySelector('[data-fc="status"]');
        if (st) st.textContent = pc?.getStatus?.() || `Queued ${lv.label}`;
        renderFlConsole(body);
      });
      wrap.appendChild(b);
      wrap.appendChild(note);
    });
    const ul = body.querySelector('[data-fc="check"]');
    (pc?.checklist?.(active) || []).forEach((line) => {
      const li = document.createElement('li');
      li.textContent = line;
      ul.appendChild(li);
    });
    const gEl = body.querySelector('[data-fc="genders"]');
    if (gEl) gEl.textContent = (FL.genderCatalog || []).join(' · ');
    if (pc) {
      pc.onStatus = (msg) => {
        const st = body.querySelector('[data-fc="status"]');
        if (st) st.textContent = msg;
      };
    }
  }

  function renderKeywords(body) {
    const kw = loadKeywords();
    body.innerHTML = `
      <p class="hint">Include/Exclude for feed story text (same sticky bar). Include = all must match; exclude = hide if any. Space/comma separated.</p>
      <label class="row">Include (all must match)</label>
      <input type="text" data-kw-inc placeholder="e.g. rope bondage" autocomplete="off" />
      <label class="row">Exclude (hide if any)</label>
      <input type="text" data-kw-exc placeholder="e.g. cishet" autocomplete="off" />
      <div style="display:flex;gap:8px;margin-top:10px">
        <button type="button" class="primary" data-kw-apply>Apply</button>
        <button type="button" class="clear-btn" data-kw-clear>Clear</button>
      </div>
      <p class="hint" data-kw-status style="margin-top:8px">Ready</p>
    `;
    const inc = body.querySelector('[data-kw-inc]');
    const exc = body.querySelector('[data-kw-exc]');
    const status = body.querySelector('[data-kw-status]');
    inc.value = kw.titleInclude || '';
    exc.value = kw.titleExclude || '';
    const apply = () => {
      saveKeywords({ titleInclude: inc.value.trim(), titleExclude: exc.value.trim() });
      applyKeywordFilters();
      const bar = document.getElementById('tbcc-fl-kw-bar');
      if (bar) {
        const bi = bar.querySelector('[data-kw="inc"]');
        const be = bar.querySelector('[data-kw="exc"]');
        if (bi) bi.value = inc.value.trim();
        if (be) be.value = exc.value.trim();
      }
      if (status) status.textContent = 'Keywords applied';
    };
    body.querySelector('[data-kw-apply]')?.addEventListener('click', apply);
    body.querySelector('[data-kw-clear]')?.addEventListener('click', () => {
      inc.value = '';
      exc.value = '';
      apply();
    });
    inc.addEventListener('change', apply);
    exc.addEventListener('change', apply);
  }

  function renderGender(body) {
    const gf = FL.genderFilter;
    const cfg = gf?.loadCfg?.() || {};
    const onGeoKinksters = /\/p\/[^/]+\/[^/]+\/[^/]+\/kinksters/i.test(location.pathname);
    body.innerHTML = `
      <p class="hint">Client-side ASL filter. Matching cards are <b>removed</b> so the list reflows. Location needles apply on search/global lists — on place kinksters pages the URL is the geo scope (location text is ignored).</p>
      <label class="row"><input type="checkbox" data-g="hideMale" /> Hide Male (M)</label>
      <label class="row"><input type="checkbox" data-g="femaleOnly" /> Female only (hide non-F when sex known)</label>
      <label class="row"><input type="checkbox" data-g="hideFtM" /> Also hide FtM</label>
      <label class="row">Location must include (comma-separated)</label>
      <div class="field-row">
        <input type="text" data-g="location" placeholder="blank = any (vitals text match)" />
        <button type="button" class="clear-btn" data-g="clear-location" title="Clear location needles">Clear</button>
      </div>
      <p class="hint" data-g="status" style="margin-top:8px">${
        onGeoKinksters
          ? 'On a place kinksters list — location needles idle; Clear still wipes saved text for other pages.'
          : 'Persists on change. Clear writes blank immediately.'
      }</p>
      <button type="button" class="primary" data-g="apply">Re-apply filter</button>
    `;
    body.querySelector('[data-g="hideMale"]').checked = cfg.hideMale !== false;
    body.querySelector('[data-g="femaleOnly"]').checked = cfg.femaleOnly !== false;
    body.querySelector('[data-g="hideFtM"]').checked = !!cfg.hideFtM;
    const locInput = body.querySelector('[data-g="location"]');
    locInput.value = cfg.locationInclude != null ? cfg.locationInclude : '';
    const save = () => {
      gf.saveCfg({
        hideMale: body.querySelector('[data-g="hideMale"]').checked,
        femaleOnly: body.querySelector('[data-g="femaleOnly"]').checked,
        hideFtM: body.querySelector('[data-g="hideFtM"]').checked,
        locationInclude: locInput.value.trim(),
      });
      const result = gf.apply?.() || {};
      const hint = body.querySelector('[data-g="status"]');
      if (hint) {
        hint.textContent =
          result.skipped === 'profile'
            ? 'ASL skipped on member profiles (keeps Friend / Follow / Message).'
            : result.cards != null
              ? `Last apply: ${result.hidden || 0} removed / ${result.kept ?? '?'} kept`
              : 'Filter re-applied';
      }
    };
    body.querySelector('[data-g="hideMale"]').addEventListener('change', save);
    body.querySelector('[data-g="femaleOnly"]').addEventListener('change', save);
    body.querySelector('[data-g="hideFtM"]').addEventListener('change', save);
    locInput.addEventListener('change', save);
    locInput.addEventListener('blur', save);
    body.querySelector('[data-g="clear-location"]').addEventListener('click', () => {
      locInput.value = '';
      gf.saveCfg({
        hideMale: body.querySelector('[data-g="hideMale"]').checked,
        femaleOnly: body.querySelector('[data-g="femaleOnly"]').checked,
        hideFtM: body.querySelector('[data-g="hideFtM"]').checked,
        locationInclude: '',
      });
      gf.apply?.();
      const hint = body.querySelector('[data-g="status"]');
      if (hint) hint.textContent = 'Location needles cleared.';
    });
    body.querySelector('[data-g="apply"]').addEventListener('click', () => {
      save();
      gf.apply();
    });
  }

  function renderStories(body) {
    const sp = FL.socialProof;
    const cfg = sp?.loadCfg?.() || {};
    const pathNick = sp?.profileNicknameFromPath?.() || '';
    body.innerHTML = `
      <p class="hint"><b>Browser-only</b> social proof: pads Friends / Followers / Following on the profile you view in <em>this</em> browser (screenshots / screen-share). Other people without TBCC still see FetLife’s real counts — the site API cannot be faked from an extension.</p>
      <label class="row"><input type="checkbox" data-sp="enabled" /> Enable count padding</label>
      <label class="row">Profile nickname (lock to your profile)</label>
      <input type="text" data-sp="nickname" placeholder="e.g. freeUse-LongBoy" />
      <button type="button" data-sp="use-page" style="margin:6px 0 10px;width:100%">Use nickname from this page${pathNick ? ` (${pathNick})` : ''}</button>
      <label class="row">Friends</label>
      <input type="text" data-sp="friends" inputmode="numeric" placeholder="leave blank = no change" />
      <label class="row">Followers</label>
      <input type="text" data-sp="followers" inputmode="numeric" placeholder="e.g. 12000" />
      <label class="row">Following</label>
      <input type="text" data-sp="following" inputmode="numeric" placeholder="leave blank = no change" />
      <button type="button" class="primary" data-sp="apply">Apply counts on this page</button>
      <p class="hint" data-sp="status" style="margin-top:8px"></p>
      <hr style="border:none;border-top:1px solid #2a2a2a;margin:14px 0" />
      <strong style="display:block;margin-bottom:8px">Story types</strong>
      <div data-story-catalog></div>
    `;

    body.querySelector('[data-sp="enabled"]').checked = cfg.enabled !== false;
    body.querySelector('[data-sp="nickname"]').value = cfg.nickname || '';
    body.querySelector('[data-sp="friends"]').value = cfg.friends != null ? cfg.friends : '';
    body.querySelector('[data-sp="followers"]').value = cfg.followers != null ? cfg.followers : '';
    body.querySelector('[data-sp="following"]').value = cfg.following != null ? cfg.following : '';

    const persist = (andApply) => {
      const next = {
        enabled: body.querySelector('[data-sp="enabled"]').checked,
        nickname: body.querySelector('[data-sp="nickname"]').value.trim(),
        friends: body.querySelector('[data-sp="friends"]').value.trim(),
        followers: body.querySelector('[data-sp="followers"]').value.trim(),
        following: body.querySelector('[data-sp="following"]').value.trim(),
      };
      sp?.saveCfg?.(next);
      const status = body.querySelector('[data-sp="status"]');
      if (andApply) {
        const r = sp?.apply?.();
        if (status) {
          status.textContent = r?.ok
            ? `Applied — friends:${r.result?.friends ? '✓' : '—'} followers:${r.result?.followers ? '✓' : '—'} following:${r.result?.following ? '✓' : '—'}`
            : 'Saved. Open your profile About page to see padded counts.';
        }
      } else if (status) {
        status.textContent = 'Saved.';
      }
    };

    body.querySelector('[data-sp="enabled"]').addEventListener('change', () => persist(true));
    ['nickname', 'friends', 'followers', 'following'].forEach((k) => {
      body.querySelector(`[data-sp="${k}"]`).addEventListener('change', () => persist(true));
    });
    body.querySelector('[data-sp="apply"]').addEventListener('click', () => persist(true));
    body.querySelector('[data-sp="use-page"]').addEventListener('click', () => {
      const nick = sp?.profileNicknameFromPath?.() || '';
      if (nick) body.querySelector('[data-sp="nickname"]').value = nick;
      persist(true);
    });

    FL.storyFilter?.mountCatalog?.(body.querySelector('[data-story-catalog]'));
  }

  function renderMute(body) {
    body.innerHTML = `<p class="hint">Mute adds a (mute) link next to comment authors. List is stored in extension/local storage.</p>
      <p class="stat">Muted IDs: ${(S.storage.get('tbcc_fl_muted_users_v1', '') || '(none)')}</p>`;
  }

  function loadIntelMeta() {
    const saved = S.storage.get(INTEL_META_KEY, null);
    return {
      recordIntel: false, // opt-in — no media scrape; thin context only
      maxIntelRows: 2000,
      tbccApiUrl: 'http://127.0.0.1:8000/analytics/erome-browse-intel',
      ...(saved && typeof saved === 'object' ? saved : {}),
    };
  }

  function saveIntelMeta(meta) {
    S.storage.set(INTEL_META_KEY, meta || {});
  }

  function loadIntelRows() {
    const rows = S.storage.get(INTEL_ROWS_KEY, []);
    return Array.isArray(rows) ? rows : [];
  }

  function saveIntelRows(rows) {
    const meta = loadIntelMeta();
    const cap = Math.max(200, Number(meta.maxIntelRows) || 2000);
    S.storage.set(INTEL_ROWS_KEY, (rows || []).slice(-cap));
  }

  function scrapeFetlifeContextTags() {
    const tags = [];
    const push = (t) => {
      const s = String(t || '')
        .trim()
        .replace(/^#/, '')
        .toLowerCase();
      if (s && s.length >= 2 && s.length < 48) tags.push(s);
    };
    document
      .querySelectorAll(
        'a[href*="/hashtags/"], a[href*="/kinks/"], a[href*="/fetishes/"], .tag, [data-tag], a[href*="/groups/"]'
      )
      .forEach((a) => {
        const href = a.getAttribute('href') || '';
        const m =
          href.match(/\/(?:hashtags|kinks|fetishes)\/([^/?#]+)/i) ||
          href.match(/\/groups\/([^/?#]+)/i);
        if (m) push(decodeURIComponent(m[1]).replace(/[-_]+/g, ' '));
        else push(a.textContent);
      });
    const path = location.pathname || '';
    const place = path.match(/\/places?\/([^/?#]+)/i);
    if (place) push('place:' + decodeURIComponent(place[1]));
    const group = path.match(/\/groups\/([^/?#]+)/i);
    if (group) push('group:' + decodeURIComponent(group[1]).replace(/[-_]+/g, ' '));
    const disc = path.match(/\/discussions\/(\d+)/i);
    if (disc) push('discussion');
    return [...new Set(tags)].slice(0, 30);
  }

  function flContextEntityId() {
    const path = (location.pathname || '/').replace(/\/+$/, '') || '/';
    const day = new Date().toISOString().slice(0, 10);
    let hash = 0;
    const s = path + '|' + day;
    for (let i = 0; i < s.length; i++) hash = (hash * 31 + s.charCodeAt(i)) >>> 0;
    return 'flctx_' + hash.toString(16);
  }

  function scanFetlifeContextIntel() {
    const meta = loadIntelMeta();
    if (meta.recordIntel === false) return 0;
    const tags = scrapeFetlifeContextTags();
    if (!tags.length) return 0;
    const id = flContextEntityId();
    const url = location.href.split('#')[0];
    const row = {
      platform: 'fetlife',
      captured_at: new Date().toISOString(),
      album_url: url,
      album_id: id,
      entity_id: id,
      entity_url: url,
      title: (document.title || pathTitle()).slice(0, 200),
      tags,
      views: null,
      likes: null,
      videos: 0,
      images: 0,
      format_bucket: 'context_page',
      page_context: { path: location.pathname, kind: 'context_tags' },
      uploader: null,
    };
    const rows = loadIntelRows().filter((r) => String(r.album_id) !== id);
    rows.push(row);
    saveIntelRows(rows);
    return 1;
  }

  function pathTitle() {
    return (location.pathname || '/').split('/').filter(Boolean).slice(-2).join('/') || 'fetlife';
  }

  function exportFlIntelJsonl() {
    const rows = loadIntelRows();
    const name = `fetlife-context-intel-${new Date().toISOString().slice(0, 10)}.jsonl`;
    if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.exportJsonlSaveAs === 'function') {
      void globalThis.tbccBrowseIntel.exportJsonlSaveAs(rows, name);
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

  async function pushFlIntelToTbcc() {
    const meta = loadIntelMeta();
    const url = String(meta.tbccApiUrl || '').trim();
    if (!url) throw new Error('Set TBCC ingest URL');
    const rows = loadIntelRows();
    if (!rows.length) throw new Error('No intel rows');
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rows }),
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return rows.length;
  }

  function renderIntel(body) {
    const meta = loadIntelMeta();
    const rows = loadIntelRows();
    const preview = scrapeFetlifeContextTags().slice(0, 12);
    body.innerHTML = `
      <p class="hint"><b>Thin context only</b> — no media scrape. Records hashtags/kinks/group/place from the page you already opened. Default OFF. Push is manual.</p>
      <label class="row"><input type="checkbox" data-fl-intel="rec" /> Record context intel (opt-in)</label>
      <label class="field">TBCC ingest URL
        <input type="text" data-fl-intel="url" />
      </label>
      <div class="friend-grid" style="display:flex;flex-wrap:wrap;gap:6px;margin:8px 0">
        <button type="button" class="accent" data-fl-intel-act="scan">Scan this page</button>
        <button type="button" data-fl-intel-act="export">Export JSONL</button>
        <button type="button" data-fl-intel-act="push">Push to TBCC</button>
        <button type="button" data-fl-intel-act="clear">Clear</button>
      </div>
      <p class="stat">${rows.length} row(s) · visible tags: ${preview.length ? preview.join(', ') : '(none on this page)'}</p>
    `;
    body.querySelector('[data-fl-intel="rec"]').checked = !!meta.recordIntel;
    body.querySelector('[data-fl-intel="url"]').value = meta.tbccApiUrl || '';
    const persist = () => {
      saveIntelMeta({
        ...loadIntelMeta(),
        recordIntel: !!body.querySelector('[data-fl-intel="rec"]').checked,
        tbccApiUrl: body.querySelector('[data-fl-intel="url"]').value.trim(),
      });
    };
    body.querySelector('[data-fl-intel="rec"]').addEventListener('change', persist);
    body.querySelector('[data-fl-intel="url"]').addEventListener('change', persist);
    body.querySelector('[data-fl-intel-act="scan"]').addEventListener('click', () => {
      persist();
      if (!loadIntelMeta().recordIntel) {
        saveIntelMeta({ ...loadIntelMeta(), recordIntel: true });
      }
      const n = scanFetlifeContextIntel();
      body.querySelector('.stat').textContent = n
        ? `Recorded · ${loadIntelRows().length} row(s)`
        : 'No tags found on this page';
    });
    body.querySelector('[data-fl-intel-act="export"]').addEventListener('click', () => {
      exportFlIntelJsonl();
    });
    body.querySelector('[data-fl-intel-act="push"]').addEventListener('click', async () => {
      persist();
      try {
        const n = await pushFlIntelToTbcc();
        body.querySelector('.stat').textContent = `Pushed ${n} row(s)`;
      } catch (e) {
        body.querySelector('.stat').textContent = 'Push failed: ' + (e.message || e);
      }
    });
    body.querySelector('[data-fl-intel-act="clear"]').addEventListener('click', () => {
      if (!confirm('Clear FetLife context intel rows?')) return;
      saveIntelRows([]);
      render();
    });
  }

  function render() {
    ensureDom();
    const root = document.getElementById(ROOT_ID);
    const page = PAGES[pageIndex];
    root.querySelectorAll('.tbcc-tabs button').forEach((b) => {
      b.classList.toggle('active', b.dataset.page === page.id);
    });
    root.querySelector('.page-ind').textContent = `${pageIndex + 1} / ${PAGES.length} — ${page.title}`;
    const body = root.querySelector('.tbcc-body');
    if (page.id === 'features') renderFeatures(body);
    else if (page.id === 'autofollow') renderAutoFollow(body);
    else if (page.id === 'gender') renderGender(body);
    else if (page.id === 'keywords') renderKeywords(body);
    else if (page.id === 'flconsole') renderFlConsole(body);
    else if (page.id === 'stories') renderStories(body);
    else if (page.id === 'mute') renderMute(body);
    else if (page.id === 'intel') renderIntel(body);
  }

  FL.overlay = {
    mount(opts) {
      hooks = opts || {};
      const ui = loadUiState();
      pageIndex = ui.pageIndex;
      collapsed = ui.collapsed;
      widthMode = ui.widthMode || 'slim';
      ensureDom();
      syncCollapsedUi(document.getElementById(ROOT_ID));
      applyOverlayTop(document.getElementById(ROOT_ID));
      mountKeywordBar();
      applyKeywordFilters();
      render();
      bindCrossTabSync();
      if (!global.__tbccFlKwObs) {
        global.__tbccFlKwObs = new MutationObserver(() => {
          clearTimeout(global.__tbccFlKwT);
          global.__tbccFlKwT = setTimeout(applyKeywordFilters, 300);
        });
        try {
          global.__tbccFlKwObs.observe(document.body, { childList: true, subtree: true });
        } catch (_) {}
      }
      if (typeof GM_registerMenuCommand === 'function') {
        try {
          GM_registerMenuCommand('TBCC FetLife Suite: open overlay', () => FL.overlay.open());
        } catch (_) { /* ignore */ }
      }
    },
    open(pageId) {
      ensureDom();
      const root = document.getElementById(ROOT_ID);
      collapsed = false;
      if (pageId) {
        const i = PAGES.findIndex((p) => p.id === pageId);
        if (i >= 0) pageIndex = i;
      }
      syncCollapsedUi(root);
      applyOverlayTop(root);
      persistUiState();
      render();
    },
    collapse() {
      const root = document.getElementById(ROOT_ID);
      if (!root) return;
      collapsed = true;
      syncCollapsedUi(root);
      persistUiState();
    },
    refresh() {
      const root = document.getElementById(ROOT_ID);
      if (!root) return;
      applyUiState(loadUiState(), { renderBody: true });
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
