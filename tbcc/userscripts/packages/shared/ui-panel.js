/* Minimal floating settings shell */
(function (global) {
  'use strict';
  const S = global.__TBCC_US__.shared;

  S.ensureStyle = function ensureStyle(id, css) {
    if (document.getElementById(id)) return;
    const el = document.createElement('style');
    el.id = id;
    el.textContent = css;
    document.documentElement.appendChild(el);
  };

  S.mountFlagPanel = function mountFlagPanel(opts) {
    const { id, title, flags, labels, onChange } = opts;
    const panelId = id + '-panel';
    const fabId = id + '-fab';

    S.ensureStyle(
      id + '-style',
      `
      #${panelId} {
        position: fixed; z-index: 999999; right: 16px; bottom: 64px;
        width: min(360px, calc(100vw - 24px)); max-height: min(70vh, 560px);
        overflow: auto; background: #1a1a1a; color: #d4d4d4;
        border: 1px solid #333; border-radius: 8px; box-shadow: 0 8px 28px rgba(0,0,0,.55);
        font: 13px/1.35 system-ui, sans-serif; display: none;
      }
      #${panelId}.open { display: block; }
      #${panelId} header {
        position: sticky; top: 0; background: #222; padding: 10px 12px;
        border-bottom: 1px solid #333; display: flex; gap: 8px; align-items: center;
      }
      #${panelId} header strong { flex: 1; }
      #${panelId} header button, #${fabId} {
        background: #333; color: #eee; border: 1px solid #555; border-radius: 6px;
        padding: 6px 10px; cursor: pointer;
      }
      #${fabId} { position: fixed; z-index: 999998; right: 16px; bottom: 16px; }
      #${panelId} label { display: flex; gap: 8px; padding: 6px 12px; cursor: pointer; }
      #${panelId} .note { padding: 8px 12px 12px; color: #888; font-size: 12px; }
    `
    );

    if (!document.getElementById(panelId)) {
      const panel = document.createElement('div');
      panel.id = panelId;
      panel.innerHTML = `<header><strong>${title}</strong><button type="button" data-act="close">Close</button></header>
        <div class="note">Flags persist in extension localStorage (or TM if present). Reload if a feature looks stuck.</div>`;
      const all = flags.all();
      Object.keys(all).forEach((key) => {
        const lab = document.createElement('label');
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = all[key] !== false;
        cb.dataset.flag = key;
        cb.addEventListener('change', () => {
          flags.set(key, cb.checked);
          if (onChange) onChange(key, cb.checked);
        });
        lab.appendChild(cb);
        lab.appendChild(document.createTextNode(labels[key] || key));
        panel.appendChild(lab);
      });
      panel.querySelector('[data-act="close"]').addEventListener('click', () => panel.classList.remove('open'));
      document.documentElement.appendChild(panel);

      const fab = document.createElement('button');
      fab.id = fabId;
      fab.type = 'button';
      fab.textContent = opts.fabLabel || 'Suite';
      fab.addEventListener('click', () => panel.classList.toggle('open'));
      document.documentElement.appendChild(fab);
    }

    function open() {
      document.getElementById(panelId)?.classList.add('open');
    }

    if (typeof GM_registerMenuCommand === 'function') {
      try {
        GM_registerMenuCommand(opts.menuLabel || `${title}: settings`, open);
      } catch (_) { /* ignore */ }
    }

    return { open };
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
