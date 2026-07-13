/* Gemini-parity job preset bar — fills prompt/negative from jobs-data.js */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const PC = (US.perchance = US.perchance || {});
  PC.features = PC.features || {};

  const PANEL_ID = 'tbcc-pc-jobs-panel';
  const FAB_ID = 'tbcc-pc-jobs-fab';

  function jobs() {
    const data = PC.jobsData || { jobs: [] };
    return Array.isArray(data.jobs) ? data.jobs : [];
  }

  function fillJob(job) {
    if (!job || !PC.promptBridge) return false;
    const ok = PC.promptBridge.applyPrompt(job.prompt, job.negative);
    PC.promptBridge.publish({
      jobId: job.id,
      lane: job.lane,
      label: job.label,
      format: job.format,
      aspect: job.aspect,
      shapeHint: job.shapeHint,
      prompt: job.prompt,
      negative: job.negative,
      source: 'job-preset',
    });
    return ok;
  }

  function mount() {
    if (document.getElementById(PANEL_ID)) return;

    S.ensureStyle(
      'tbcc-pc-jobs-style',
      `
      #${PANEL_ID} {
        position: fixed; z-index: 999999; left: 12px; top: 12px;
        width: min(420px, calc(100vw - 24px)); max-height: min(78vh, 640px);
        overflow: auto; background: #141414; color: #ddd;
        border: 1px solid #333; border-radius: 8px; box-shadow: 0 10px 32px rgba(0,0,0,.55);
        font: 12px/1.35 system-ui, sans-serif; display: none;
      }
      #${PANEL_ID}.open { display: flex; flex-direction: column; }
      #${PANEL_ID} header {
        position: sticky; top: 0; background: #1c1c1c; padding: 8px 10px;
        border-bottom: 1px solid #333; display: flex; gap: 6px; align-items: center;
      }
      #${PANEL_ID} header strong { flex: 1; font-size: 13px; }
      #${PANEL_ID} .filters { display: flex; gap: 6px; padding: 8px 10px; border-bottom: 1px solid #2a2a2a; }
      #${PANEL_ID} select, #${PANEL_ID} input, #${PANEL_ID} button {
        background: #2a2a2a; color: #eee; border: 1px solid #444; border-radius: 5px;
        padding: 5px 8px; font: inherit;
      }
      #${PANEL_ID} .list { padding: 6px; display: flex; flex-direction: column; gap: 4px; }
      #${PANEL_ID} .job {
        text-align: left; cursor: pointer; padding: 7px 8px;
      }
      #${PANEL_ID} .job:hover { background: #2f2f2f; }
      #${PANEL_ID} .job small { display: block; color: #888; margin-top: 2px; }
      #${PANEL_ID} .hint { padding: 8px 10px 10px; color: #888; font-size: 11px; }
      #${FAB_ID} {
        position: fixed; z-index: 999998; left: 12px; top: 12px;
        background: #c45c26; color: #fff; border: 0; border-radius: 6px;
        padding: 8px 12px; cursor: pointer; font: 12px system-ui, sans-serif;
        box-shadow: 0 4px 14px rgba(0,0,0,.4);
      }
    `
    );

    const panel = document.createElement('div');
    panel.id = PANEL_ID;
    panel.innerHTML = `
      <header>
        <strong>TBCC jobs (Gemini parity)</strong>
        <button type="button" data-act="copy">Copy</button>
        <button type="button" data-act="close">Close</button>
      </header>
      <div class="filters">
        <select data-act="lane">
          <option value="all">All lanes</option>
          <option value="promo">Promo</option>
          <option value="loot">Loot</option>
        </select>
        <input type="search" data-act="q" placeholder="Filter…" style="flex:1" />
      </div>
      <div class="list" data-act="list"></div>
      <div class="hint">
        Apply fills the page prompt + negative and sets <code>window.__tbccPerchanceLastPrompt</code>
        for TBCC capture. Gemini CLI fallback if QR/HUD text fails.
        Shape hint is advisory (Perchance resolution ≠ Gemini aspect enum).
      </div>
    `;
    document.documentElement.appendChild(panel);

    const fab = document.createElement('button');
    fab.id = FAB_ID;
    fab.type = 'button';
    fab.textContent = 'TBCC Jobs';
    fab.addEventListener('click', () => {
      panel.classList.add('open');
      fab.style.display = 'none';
    });
    document.documentElement.appendChild(fab);

    panel.querySelector('[data-act="close"]').addEventListener('click', () => {
      panel.classList.remove('open');
      fab.style.display = '';
    });

    const listEl = panel.querySelector('[data-act="list"]');
    const laneEl = panel.querySelector('[data-act="lane"]');
    const qEl = panel.querySelector('[data-act="q"]');
    let selected = null;

    function render() {
      const lane = laneEl.value;
      const q = (qEl.value || '').trim().toLowerCase();
      listEl.innerHTML = '';
      for (const job of jobs()) {
        if (lane !== 'all' && job.lane !== lane) continue;
        const blob = `${job.label} ${job.id} ${job.format || ''}`.toLowerCase();
        if (q && !blob.includes(q)) continue;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'job';
        btn.innerHTML = `<div>${job.label}</div><small>${job.id} · ${job.format} · ${job.aspect} · ${job.shapeHint || ''}</small>`;
        btn.addEventListener('click', () => {
          selected = job;
          const ok = fillJob(job);
          btn.style.outline = ok ? '1px solid #6a6' : '1px solid #a66';
          setTimeout(() => {
            btn.style.outline = '';
          }, 800);
        });
        listEl.appendChild(btn);
      }
    }

    laneEl.addEventListener('change', render);
    qEl.addEventListener('input', render);
    // close handler wired above with fab restore
    panel.querySelector('[data-act="copy"]').addEventListener('click', async () => {
      const job = selected || (global.__tbccPerchanceLastPrompt && global.__tbccPerchanceLastPrompt.prompt
        ? global.__tbccPerchanceLastPrompt
        : null);
      const text = job && job.prompt ? job.prompt : '';
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
      } catch (_) { /* ignore */ }
    });

    render();

    if (typeof GM_registerMenuCommand === 'function') {
      try {
        GM_registerMenuCommand('TBCC Perchance: jobs', () => panel.classList.add('open'));
      } catch (_) { /* ignore */ }
    }
  }

  PC.features.jobsPanel = {
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
