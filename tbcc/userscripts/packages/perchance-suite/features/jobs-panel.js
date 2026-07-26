/* Gemini-parity job preset bar — fills prompt/negative from jobs-data.js */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const PC = (US.perchance = US.perchance || {});
  PC.features = PC.features || {};

  const PANEL_ID = 'tbcc-pc-jobs-panel';
  const FAB_ID = 'tbcc-pc-jobs-fab';
  const TOAST_ID = 'tbcc-pc-jobs-toast';
  const PUSH_VAR = '--tbcc-pc-jobs-push';

  function jobs() {
    const data = PC.jobsData || { jobs: [] };
    return Array.isArray(data.jobs) ? data.jobs : [];
  }

  function toast(msg) {
    let el = document.getElementById(TOAST_ID);
    if (!el) {
      el = document.createElement('div');
      el.id = TOAST_ID;
      document.documentElement.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(el._hide);
    el._hide = setTimeout(() => el.classList.remove('show'), 1400);
  }

  function flashBtn(btn, ok) {
    if (!btn) return;
    const prev = btn.style.outline;
    btn.style.outline = ok ? '2px solid #6d6' : '2px solid #d66';
    btn.style.background = ok ? '#2a4a2a' : '#4a2a2a';
    setTimeout(() => {
      btn.style.outline = prev || '';
      btn.style.background = '';
    }, 700);
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
      #${TOAST_ID} {
        position: fixed; z-index: 1000001; left: 12px; top: 56px;
        background: #1e3a1e; color: #c8f0c8; border: 1px solid #4a7a4a;
        border-radius: 999px; padding: 4px 10px; font: 11px system-ui, sans-serif;
        opacity: 0; pointer-events: none; transition: opacity .15s ease;
        box-shadow: 0 4px 12px rgba(0,0,0,.35);
      }
      #${TOAST_ID}.show { opacity: 1; }
      html.tbcc-pc-jobs-open {
        scroll-padding-top: var(${PUSH_VAR}, 0px);
      }
      html.tbcc-pc-jobs-open textarea[data-tbcc-pc-pushed="1"] {
        outline: 1px dashed #555;
      }
    `
    );

    const panel = document.createElement('div');
    panel.id = PANEL_ID;
    panel.innerHTML = `
      <header>
        <strong>TBCC jobs (loot first)</strong>
        <button type="button" data-act="copy">Copy</button>
        <button type="button" data-act="close">Close</button>
      </header>
      <div class="filters">
        <select data-act="lane">
          <option value="loot" selected>Loot</option>
          <option value="all">All lanes</option>
          <option value="promo">Promo (martyrs etc)</option>
        </select>
        <input type="search" data-act="q" placeholder="Filter…" style="flex:1" />
      </div>
      <div class="list" data-act="list"></div>
      <div class="hint">
        Default = <b>Loot</b> only. Prefer <b>Loot Cards</b> FAB for explicit God Lab.
        Hover off this panel to auto-close. Copy shows a tiny chip toast.
        Apply pushes the page prompt field below this panel so it stays visible.
      </div>
    `;
    document.documentElement.appendChild(panel);

    const fab = document.createElement('button');
    fab.id = FAB_ID;
    fab.type = 'button';
    fab.textContent = 'TBCC Jobs';
    document.documentElement.appendChild(fab);

    const listEl = panel.querySelector('[data-act="list"]');
    const laneEl = panel.querySelector('[data-act="lane"]');
    const qEl = panel.querySelector('[data-act="q"]');
    const copyBtn = panel.querySelector('[data-act="copy"]');
    const closeBtn = panel.querySelector('[data-act="close"]');
    let selected = null;
    let leaveTimer = null;
    let pushedEl = null;

    function clearPush() {
      document.documentElement.classList.remove('tbcc-pc-jobs-open');
      document.documentElement.style.removeProperty(PUSH_VAR);
      if (pushedEl) {
        pushedEl.style.marginTop = pushedEl.dataset.tbccPrevMargin || '';
        delete pushedEl.dataset.tbccPrevMargin;
        delete pushedEl.dataset.tbccPcPushed;
        pushedEl = null;
      }
    }

    function applyPush() {
      const h = Math.ceil(panel.getBoundingClientRect().height || 420);
      const pad = h + 20;
      document.documentElement.style.setProperty(PUSH_VAR, `${pad}px`);
      document.documentElement.classList.add('tbcc-pc-jobs-open');
      const ta =
        (PC.promptBridge && typeof PC.promptBridge.findPromptTextarea === 'function'
          ? PC.promptBridge.findPromptTextarea()
          : null) || document.querySelector('textarea');
      if (ta) {
        if (pushedEl && pushedEl !== ta) clearPush();
        pushedEl = ta;
        if (ta.dataset.tbccPrevMargin == null) {
          ta.dataset.tbccPrevMargin = ta.style.marginTop || '';
        }
        ta.dataset.tbccPcPushed = '1';
        ta.style.marginTop = `${pad}px`;
        try {
          ta.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        } catch (_) { /* ignore */ }
      }
    }

    function openPanel() {
      panel.classList.add('open');
      fab.style.display = 'none';
      requestAnimationFrame(() => applyPush());
    }

    function closePanel() {
      panel.classList.remove('open');
      fab.style.display = '';
      clearPush();
      flashBtn(closeBtn, true);
      toast('Closed');
    }

    fab.addEventListener('click', openPanel);
    closeBtn.addEventListener('click', closePanel);

    panel.addEventListener('mouseleave', () => {
      clearTimeout(leaveTimer);
      leaveTimer = setTimeout(() => {
        if (panel.classList.contains('open')) closePanel();
      }, 450);
    });
    panel.addEventListener('mouseenter', () => clearTimeout(leaveTimer));

    function render() {
      const lane = laneEl.value;
      const q = (qEl.value || '').trim().toLowerCase();
      listEl.innerHTML = '';
      for (const job of jobs()) {
        if (lane !== 'all' && job.lane !== lane) continue;
        // Hide martyrs unless promo/all explicitly selected
        if (lane === 'loot' && /martyr/i.test(`${job.id} ${job.label} ${job.preset || ''}`)) continue;
        const blob = `${job.label} ${job.id} ${job.format || ''}`.toLowerCase();
        if (q && !blob.includes(q)) continue;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'job';
        btn.innerHTML = `<div>${job.label}</div><small>${job.id} · ${job.format} · ${job.aspect} · ${job.shapeHint || ''}</small>`;
        btn.addEventListener('click', () => {
          selected = job;
          const ok = fillJob(job);
          flashBtn(btn, ok);
          toast(ok ? 'Applied to prompt' : 'Applied (field missing?)');
          applyPush();
        });
        listEl.appendChild(btn);
      }
    }

    laneEl.addEventListener('change', render);
    qEl.addEventListener('input', render);
    copyBtn.addEventListener('click', async () => {
      const job = selected || (global.__tbccPerchanceLastPrompt && global.__tbccPerchanceLastPrompt.prompt
        ? global.__tbccPerchanceLastPrompt
        : null);
      const text = job && job.prompt ? job.prompt : '';
      if (!text) {
        flashBtn(copyBtn, false);
        toast('Nothing to copy');
        return;
      }
      try {
        await navigator.clipboard.writeText(text);
        flashBtn(copyBtn, true);
        toast('Copied');
      } catch (_) {
        flashBtn(copyBtn, false);
        toast('Clipboard blocked');
      }
    });

    render();

    if (typeof GM_registerMenuCommand === 'function') {
      try {
        GM_registerMenuCommand('TBCC Perchance: jobs', openPanel);
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
      document.getElementById(TOAST_ID)?.remove();
      document.documentElement.classList.remove('tbcc-pc-jobs-open');
      document.documentElement.style.removeProperty(PUSH_VAR);
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
