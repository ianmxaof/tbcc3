/* TBCC-style chevron overlay: collapsible + paginated suite control */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const ROOT_ID = 'tbcc-fl-overlay';
  const PAGES = [
    { id: 'features', title: 'Features' },
    { id: 'autofollow', title: 'Auto-follow' },
    { id: 'gender', title: 'Gender filter' },
    { id: 'stories', title: 'Story types' },
    { id: 'mute', title: 'Mute' },
  ];

  let pageIndex = 0;
  let collapsed = false;
  let hooks = {};

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
        border-radius: 10px 0 0 10px; cursor: pointer; color: #f43f5e;
        display: flex; align-items: center; justify-content: center;
        writing-mode: vertical-rl; text-orientation: mixed; letter-spacing: .08em;
        font-size: 11px; font-weight: 700; padding: 10px 0;
      }
      #${ROOT_ID} .tbcc-panel {
        pointer-events: auto; width: min(380px, calc(100vw - 40px));
        max-height: min(78vh, 640px); background: #121212; border: 1px solid #333;
        border-right: none; border-radius: 12px 0 0 12px;
        box-shadow: -8px 0 28px rgba(0,0,0,.45); display: flex; flex-direction: column;
        overflow: hidden;
      }
      #${ROOT_ID}.collapsed .tbcc-panel { display: none; }
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
          <button type="button" data-act="collapse">Hide</button>
        </div>
        <div class="tbcc-tabs"></div>
        <div class="tbcc-body"></div>
        <div class="tbcc-foot">
          <button type="button" data-act="prev">Prev</button>
          <span class="page-ind"></span>
          <button type="button" data-act="next">Next</button>
        </div>
      </div>`;
    document.documentElement.appendChild(root);

    const tabs = root.querySelector('.tbcc-tabs');
    PAGES.forEach((p, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = p.title;
      b.dataset.page = p.id;
      b.addEventListener('click', () => {
        pageIndex = i;
        render();
      });
      tabs.appendChild(b);
    });

    root.querySelector('.tbcc-chevron').addEventListener('click', () => {
      collapsed = !collapsed;
      root.classList.toggle('collapsed', collapsed);
      root.querySelector('.tbcc-chevron').textContent = collapsed ? 'FL ▸' : 'FL ◂';
    });
    root.querySelector('[data-act="collapse"]').addEventListener('click', () => {
      collapsed = true;
      root.classList.add('collapsed');
      root.querySelector('.tbcc-chevron').textContent = 'FL ▸';
    });
    root.querySelector('[data-act="prev"]').addEventListener('click', () => {
      pageIndex = (pageIndex + PAGES.length - 1) % PAGES.length;
      render();
    });
    root.querySelector('[data-act="next"]').addEventListener('click', () => {
      pageIndex = (pageIndex + 1) % PAGES.length;
      render();
    });
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
    body.innerHTML = `
      <p class="hint">Clicks Follow on visible cards, scrolls for more, skips males when gender filter is on.</p>
      <label class="row">Speed</label>
      <select data-af="speed"></select>
      <label class="row"><input type="checkbox" data-af="skipMale" /> Skip male profiles</label>
      <label class="row"><input type="checkbox" data-af="autoStartOnKinksters" /> Open this panel on /kinksters</label>
      <div class="stat" data-af="stat">Followed: ${af?.getCount?.() || 0}</div>
      <button type="button" class="primary" data-af="toggle">Start auto-follow</button>
    `;
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

    const persist = () => {
      af.saveCfg({
        speed: sel.value,
        skipMale: body.querySelector('[data-af="skipMale"]').checked,
        autoStartOnKinksters: body.querySelector('[data-af="autoStartOnKinksters"]').checked,
      });
    };
    sel.addEventListener('change', persist);
    body.querySelector('[data-af="skipMale"]').addEventListener('change', persist);
    body.querySelector('[data-af="autoStartOnKinksters"]').addEventListener('change', persist);

    const btn = body.querySelector('[data-af="toggle"]');
    const syncBtn = () => {
      const running = af?.isRunning?.();
      btn.textContent = running ? `Stop (${af.getCount()} followed)` : 'Start auto-follow';
      btn.classList.toggle('running', !!running);
      body.querySelector('[data-af="stat"]').textContent = `Followed: ${af?.getCount?.() || 0}`;
    };
    btn.addEventListener('click', () => {
      if (af.isRunning()) af.stop();
      else af.start();
      syncBtn();
    });
    af.onProgress = () => syncBtn();
    af.onState = () => syncBtn();
    syncBtn();
  }

  function renderGender(body) {
    const gf = FL.genderFilter;
    const cfg = gf?.loadCfg?.() || {};
    body.innerHTML = `
      <p class="hint">Hides list cards whose vitals parse as male (ASL-style, e.g. 32M). Does not call FetLife APIs.</p>
      <label class="row"><input type="checkbox" data-g="hideMale" /> Hide Male (M)</label>
      <label class="row"><input type="checkbox" data-g="hideFtM" /> Also hide FtM</label>
      <button type="button" class="primary" data-g="apply">Re-apply filter</button>
    `;
    body.querySelector('[data-g="hideMale"]').checked = cfg.hideMale !== false;
    body.querySelector('[data-g="hideFtM"]').checked = !!cfg.hideFtM;
    const save = () => {
      gf.saveCfg({
        hideMale: body.querySelector('[data-g="hideMale"]').checked,
        hideFtM: body.querySelector('[data-g="hideFtM"]').checked,
      });
      gf.apply();
    };
    body.querySelector('[data-g="hideMale"]').addEventListener('change', save);
    body.querySelector('[data-g="hideFtM"]').addEventListener('change', save);
    body.querySelector('[data-g="apply"]').addEventListener('click', () => gf.apply());
  }

  function renderStories(body) {
    body.innerHTML = `<p class="hint">Use the floating <b>Story types</b> button for the full catalog, or open Activity Feed settings (local-only toggles).</p>
      <button type="button" class="primary" data-s="open">Open story types panel</button>`;
    body.querySelector('[data-s="open"]').addEventListener('click', () => {
      document.getElementById('tbcc-fl-story-panel')?.classList.add('open');
    });
  }

  function renderMute(body) {
    body.innerHTML = `<p class="hint">Mute adds a (mute) link next to comment authors. List is stored in Tampermonkey.</p>
      <p class="stat">Muted IDs: ${(S.storage.get('tbcc_fl_muted_users_v1', '') || '(none)')}</p>`;
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
    else if (page.id === 'stories') renderStories(body);
    else if (page.id === 'mute') renderMute(body);
  }

  FL.overlay = {
    mount(opts) {
      hooks = opts || {};
      ensureDom();
      render();
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
      root.classList.remove('collapsed');
      root.querySelector('.tbcc-chevron').textContent = 'FL ◂';
      if (pageId) {
        const i = PAGES.findIndex((p) => p.id === pageId);
        if (i >= 0) pageIndex = i;
      }
      render();
    },
    collapse() {
      const root = document.getElementById(ROOT_ID);
      if (!root) return;
      collapsed = true;
      root.classList.add('collapsed');
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
