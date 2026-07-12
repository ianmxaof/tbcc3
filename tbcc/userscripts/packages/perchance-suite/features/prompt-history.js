/* Lightweight prompt history (GM storage) — full IndexedDB upstream lives in inbox */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const PC = (US.perchance = US.perchance || {});
  PC.features = PC.features || {};

  const PANEL_ID = 'tbcc-pc-hist-panel';
  const FAB_ID = 'tbcc-pc-hist-fab';

  function mount() {
    if (document.getElementById(PANEL_ID)) return;
    S.ensureStyle(
      'tbcc-pc-hist-style',
      `
      #${PANEL_ID} {
        position: fixed; z-index: 999999; right: 12px; bottom: 56px;
        width: min(380px, calc(100vw - 24px)); max-height: min(60vh, 480px);
        overflow: auto; background: #141414; color: #ddd;
        border: 1px solid #333; border-radius: 8px; display: none;
        font: 12px/1.35 system-ui, sans-serif;
      }
      #${PANEL_ID}.open { display: block; }
      #${PANEL_ID} header {
        position: sticky; top: 0; background: #1c1c1c; padding: 8px 10px;
        border-bottom: 1px solid #333; display: flex; gap: 6px;
      }
      #${PANEL_ID} header strong { flex: 1; }
      #${PANEL_ID} button, #${FAB_ID} {
        background: #2a2a2a; color: #eee; border: 1px solid #444; border-radius: 5px;
        padding: 5px 8px; cursor: pointer; font: inherit;
      }
      #${FAB_ID} { position: fixed; z-index: 999998; right: 12px; bottom: 12px; }
      #${PANEL_ID} .row {
        display: block; width: calc(100% - 12px); margin: 6px; text-align: left;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
    `
    );

    const panel = document.createElement('div');
    panel.id = PANEL_ID;
    panel.innerHTML = `<header><strong>Prompt history</strong><button type="button" data-act="refresh">Refresh</button><button type="button" data-act="close">Close</button></header><div data-act="list"></div>`;
    document.documentElement.appendChild(panel);

    const fab = document.createElement('button');
    fab.id = FAB_ID;
    fab.type = 'button';
    fab.textContent = 'PC Hist';
    fab.addEventListener('click', () => {
      panel.classList.toggle('open');
      render();
    });
    document.documentElement.appendChild(fab);

    const list = panel.querySelector('[data-act="list"]');
    function render() {
      const items = (PC.promptBridge && PC.promptBridge.getHistory()) || [];
      list.innerHTML = '';
      if (!items.length) {
        list.innerHTML = '<div style="padding:10px;color:#888">No history yet. Apply a job or click generate.</div>';
        return;
      }
      items.forEach((item, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'row';
        const preview = (item.prompt || '').slice(0, 120).replace(/\s+/g, ' ');
        btn.textContent = `${idx + 1}. ${preview}`;
        btn.title = item.prompt || '';
        btn.addEventListener('click', () => {
          PC.promptBridge.applyPrompt(item.prompt || '', item.negative || '');
          if (item.jobId) {
            PC.promptBridge.publish({
              ...(global.__tbccPerchanceLastPrompt || {}),
              jobId: item.jobId,
              prompt: item.prompt,
              negative: item.negative,
              source: 'history',
            });
          }
        });
        list.appendChild(btn);
      });
    }

    panel.querySelector('[data-act="close"]').addEventListener('click', () => panel.classList.remove('open'));
    panel.querySelector('[data-act="refresh"]').addEventListener('click', render);
  }

  PC.features.promptHistory = {
    start() {
      const go = () => mount();
      if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go);
      else go();
    },
    stop() {
      document.getElementById(PANEL_ID)?.remove();
      document.getElementById(FAB_ID)?.remove();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
