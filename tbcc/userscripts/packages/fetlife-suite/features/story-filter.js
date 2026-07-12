/* FetLife story filter — DOM layer (client-side only) */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const core = US.fetlife.storyFilterCore;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const STORAGE_KEY = 'tbcc_fl_story_enabled_v1';
  const HIDDEN_ATTR = 'data-fl-fsf-hidden';
  const TYPE_ATTR = 'data-fl-fsf-type';
  const PANEL_ID = 'tbcc-fl-story-panel';

  function loadEnabled() {
    const saved = S.storage.get(STORAGE_KEY, null);
    const base = core.defaultEnabledMap();
    if (!saved || typeof saved !== 'object') return base;
    return { ...base, ...saved };
  }

  let enabled = loadEnabled();

  function storyNodes() {
    const selectors = ['#stories-list > *', '#fl-masonry-wrap .fl-masonry-col > *', '#stories > *'];
    const found = new Set();
    for (const sel of selectors) {
      document.querySelectorAll(sel).forEach((el) => {
        if (el.classList?.contains('infinite-loading-container')) return;
        if ((el.textContent || '').trim().length < 20) return;
        if (el.closest(`#${PANEL_ID}`)) return;
        found.add(el);
      });
    }
    return [...found].filter((el) => ![...found].some((o) => o !== el && o.contains(el)));
  }

  function applyFeedFilter() {
    const nodes = storyNodes();
    let hidden = 0;
    for (const el of nodes) {
      const text = el.innerText || el.textContent || '';
      const type =
        el.getAttribute('data-feed-event') ||
        el.getAttribute('data-story-type') ||
        el.getAttribute('data-type') ||
        core.classifyStoryText(text);
      if (type) el.setAttribute(TYPE_ATTR, type);
      const show = !type || enabled[type] !== false;
      if (show) el.removeAttribute(HIDDEN_ATTR);
      else {
        el.setAttribute(HIDDEN_ATTR, '1');
        hidden += 1;
      }
    }
    if (hidden) console.debug(`[FL suite] storyFilter hidden=${hidden}/${nodes.length}`);
  }

  function unlockSettingsPage() {
    const form = document.getElementById('update_feed_settings_form');
    if (!form) return;
    if (!document.getElementById('tbcc-fl-fsf-banner')) {
      const h2 = [...form.querySelectorAll('h2')].find((h) => /Hide\/Show Feed Stories/i.test(h.textContent || ''));
      const banner = document.createElement('div');
      banner.id = 'tbcc-fl-fsf-banner';
      banner.style.cssText =
        'margin:8px 0 12px;padding:8px 10px;background:#2a1f14;border:1px solid #664;border-radius:6px;color:#e8c48a;font-size:13px;';
      banner.textContent =
        'TBCC FetLife Suite: toggles save locally and filter your browser feed. Not sent to FetLife Supporter APIs.';
      (h2?.parentElement || form).insertBefore(banner, h2?.nextSibling || form.firstChild);
    }
    form.querySelectorAll('input[name="feed[story_types][]"]').forEach((input) => {
      if (!input.value) return;
      input.disabled = false;
      input.checked = enabled[input.value] !== false;
      const label = input.closest('label');
      if (label) {
        label.style.opacity = '1';
        label.style.cursor = 'pointer';
        label.style.pointerEvents = 'auto';
      }
      if (input.dataset.tbccBound) return;
      input.dataset.tbccBound = '1';
      input.addEventListener('change', (ev) => {
        ev.stopPropagation();
        enabled = { ...enabled, [input.value]: input.checked };
        S.storage.set(STORAGE_KEY, enabled);
        applyFeedFilter();
      });
    });
    if (!form.dataset.tbccSubmitBlocked) {
      form.dataset.tbccSubmitBlocked = '1';
      form.addEventListener(
        'submit',
        (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          S.storage.set(STORAGE_KEY, enabled);
        },
        true
      );
    }
  }

  function buildTypePanel() {
    if (document.getElementById(PANEL_ID)) return;
    S.ensureStyle(
      'tbcc-fl-fsf-style',
      `[${HIDDEN_ATTR}="1"]{display:none!important}
       #${PANEL_ID}{position:fixed;z-index:999999;right:16px;bottom:110px;width:min(420px,calc(100vw - 24px));max-height:min(65vh,560px);overflow:auto;background:#1a1a1a;color:#d4d4d4;border:1px solid #333;border-radius:8px;display:none;font:13px/1.35 system-ui,sans-serif}
       #${PANEL_ID}.open{display:block}
       #${PANEL_ID} header{position:sticky;top:0;background:#222;padding:10px 12px;display:flex;gap:8px;align-items:center;border-bottom:1px solid #333}
       #${PANEL_ID} header strong{flex:1}
       #${PANEL_ID} button{background:#333;color:#eee;border:1px solid #555;border-radius:6px;padding:6px 10px;cursor:pointer}
       #${PANEL_ID} .cat{padding:8px 12px 4px;font-weight:700;color:#bbb}
       #${PANEL_ID} label{display:flex;gap:8px;padding:4px 12px 4px 16px;cursor:pointer}
       #tbcc-fl-story-fab{position:fixed;z-index:999998;right:16px;bottom:60px;background:#333;color:#eee;border:1px solid #555;border-radius:6px;padding:6px 10px;cursor:pointer}`
    );
    const panel = document.createElement('div');
    panel.id = PANEL_ID;
    panel.innerHTML = `<header><strong>Story types</strong>
      <button type="button" data-act="all-on">All on</button>
      <button type="button" data-act="all-off">All off</button>
      <button type="button" data-act="close">Close</button></header>
      <div style="padding:8px 12px;color:#888;font-size:12px">Unchecked = hidden in browser only.</div>`;
    for (const cat of core.CATALOG) {
      const h = document.createElement('div');
      h.className = 'cat';
      h.textContent = cat.category;
      panel.appendChild(h);
      for (const item of cat.items) {
        const lab = document.createElement('label');
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = enabled[item.id] !== false;
        cb.addEventListener('change', () => {
          enabled = { ...enabled, [item.id]: cb.checked };
          S.storage.set(STORAGE_KEY, enabled);
          unlockSettingsPage();
          applyFeedFilter();
        });
        lab.appendChild(cb);
        lab.appendChild(document.createTextNode(item.label));
        panel.appendChild(lab);
      }
    }
    panel.querySelector('[data-act="close"]').onclick = () => panel.classList.remove('open');
    panel.querySelector('[data-act="all-on"]').onclick = () => {
      Object.keys(enabled).forEach((k) => (enabled[k] = true));
      S.storage.set(STORAGE_KEY, enabled);
      panel.querySelectorAll('input[type=checkbox]').forEach((cb) => (cb.checked = true));
      applyFeedFilter();
    };
    panel.querySelector('[data-act="all-off"]').onclick = () => {
      Object.keys(enabled).forEach((k) => (enabled[k] = false));
      S.storage.set(STORAGE_KEY, enabled);
      panel.querySelectorAll('input[type=checkbox]').forEach((cb) => (cb.checked = false));
      applyFeedFilter();
    };
    document.documentElement.appendChild(panel);
    const fab = document.createElement('button');
    fab.id = 'tbcc-fl-story-fab';
    fab.type = 'button';
    fab.textContent = 'Story types';
    fab.onclick = () => panel.classList.toggle('open');
    document.documentElement.appendChild(fab);
  }

  FL.features = FL.features || {};
  FL.features.storyFilter = {
    start() {
      unlockSettingsPage();
      buildTypePanel();
      applyFeedFilter();
      this._unsubObs = S.observer.subscribe(() => {
        unlockSettingsPage();
        applyFeedFilter();
      });
      this._unsubSpa = S.spa.onChange(() => setTimeout(applyFeedFilter, 300));
    },
    stop() {
      this._unsubObs?.();
      this._unsubSpa?.();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
