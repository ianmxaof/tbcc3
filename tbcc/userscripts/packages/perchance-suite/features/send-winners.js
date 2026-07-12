/* Send winners → TBCC: select canvases/images and dispatch capture hint */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const PC = (US.perchance = US.perchance || {});
  PC.features = PC.features || {};

  const BAR_ID = 'tbcc-pc-send-bar';

  function mount() {
    if (document.getElementById(BAR_ID)) return;
    S.ensureStyle(
      'tbcc-pc-send-style',
      `
      #${BAR_ID} {
        position: fixed; z-index: 999997; left: 50%; transform: translateX(-50%);
        bottom: 12px; display: flex; gap: 8px; align-items: center;
        background: #1a1a1a; border: 1px solid #444; border-radius: 8px;
        padding: 8px 10px; font: 12px system-ui, sans-serif; color: #ddd;
      }
      #${BAR_ID} button {
        background: #2d6a4f; color: #fff; border: 0; border-radius: 5px;
        padding: 6px 10px; cursor: pointer; font: inherit;
      }
      #${BAR_ID} button.secondary { background: #333; }
      #${BAR_ID} .meta { color: #888; max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    `
    );
    const bar = document.createElement('div');
    bar.id = BAR_ID;
    bar.innerHTML = `
      <span class="meta" data-act="meta">TBCC capture bridge</span>
      <button type="button" data-act="tag">Tag selection</button>
      <button type="button" class="secondary" data-act="copy-meta">Copy meta JSON</button>
    `;
    document.documentElement.appendChild(bar);

    const metaEl = bar.querySelector('[data-act="meta"]');
    function refreshMeta() {
      const p = global.__tbccPerchanceLastPrompt;
      metaEl.textContent = p
        ? `${p.lane || '?'} · ${p.jobId || p.source || 'prompt'} · ${p.format || ''}`
        : 'No job applied yet';
    }
    setInterval(refreshMeta, 1500);
    refreshMeta();

    bar.querySelector('[data-act="tag"]').addEventListener('click', () => {
      let nodes = document.querySelectorAll('canvas.tbcc-pc-pick, img.tbcc-pc-pick');
      if (!nodes.length) {
        metaEl.textContent = 'Alt-click canvases/images to pick, then Tag';
        return;
      }
      let n = 0;
      nodes.forEach((el) => {
        el.dataset.tbccPerchanceJob =
          (global.__tbccPerchanceLastPrompt && global.__tbccPerchanceLastPrompt.jobId) || '';
        n++;
      });
      metaEl.textContent = `Tagged ${n} pick(s) for TBCC capture`;
      try {
        global.dispatchEvent(
          new CustomEvent('tbcc-perchance-send-winners', {
            detail: { count: n, meta: global.__tbccPerchanceLastPrompt || null },
          })
        );
      } catch (_) { /* ignore */ }
    });

    bar.querySelector('[data-act="copy-meta"]').addEventListener('click', async () => {
      const raw = JSON.stringify(global.__tbccPerchanceLastPrompt || {}, null, 2);
      try {
        await navigator.clipboard.writeText(raw);
        metaEl.textContent = 'Meta copied';
      } catch (_) {
        metaEl.textContent = 'Clipboard blocked';
      }
    });

    // Click to toggle pick on canvases
    document.addEventListener(
      'click',
      (e) => {
        const t = e.target;
        if (!t || !t.tagName) return;
        if (t.tagName === 'CANVAS' || t.tagName === 'IMG') {
          if (e.altKey) {
            t.classList.toggle('tbcc-pc-pick');
            e.preventDefault();
          }
        }
      },
      true
    );
  }

  PC.features.sendWinners = {
    start() {
      const go = () => mount();
      if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go);
      else go();
    },
    stop() {
      document.getElementById(BAR_ID)?.remove();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
