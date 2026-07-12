/* Expose last prompt for TBCC extension capture metadata + generate hook */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const PC = (US.perchance = US.perchance || {});
  PC.features = PC.features || {};

  const HIST_KEY = 'tbcc_pc_prompt_history_v1';
  const MAX_HIST = 80;

  function findPromptTextarea() {
    const areas = Array.from(document.querySelectorAll('textarea'));
    if (!areas.length) return null;
    // Prefer labeled prompt / largest textarea
    const scored = areas.map((el) => {
      const lab = (el.getAttribute('aria-label') || el.placeholder || el.name || '').toLowerCase();
      const promptish = /prompt/.test(lab) && !/negative/.test(lab) ? 10 : 0;
      return { el, score: promptish + Math.min(5, (el.value || '').length / 200) };
    });
    scored.sort((a, b) => b.score - a.score);
    return scored[0].el;
  }

  function findNegativeTextarea() {
    const areas = Array.from(document.querySelectorAll('textarea'));
    for (const el of areas) {
      const lab = (el.getAttribute('aria-label') || el.placeholder || el.name || '').toLowerCase();
      if (/negative/.test(lab)) return el;
    }
    return null;
  }

  function publish(meta) {
    const payload = {
      ...meta,
      updatedAt: Date.now(),
      href: location.href,
    };
    global.__tbccPerchanceLastPrompt = payload;
    try {
      document.documentElement.dataset.tbccPerchancePrompt = JSON.stringify({
        id: payload.jobId || null,
        lane: payload.lane || null,
        format: payload.format || null,
        aspect: payload.aspect || null,
        updatedAt: payload.updatedAt,
      });
    } catch (_) { /* ignore */ }
  }

  function pushHistory(entry) {
    const list = S.storage.get(HIST_KEY, []) || [];
    const next = [entry, ...list.filter((x) => x && x.prompt !== entry.prompt)].slice(0, MAX_HIST);
    S.storage.set(HIST_KEY, next);
  }

  PC.promptBridge = {
    publish,
    pushHistory,
    findPromptTextarea,
    findNegativeTextarea,
    getHistory() {
      return S.storage.get(HIST_KEY, []) || [];
    },
    applyPrompt(prompt, negative) {
      const p = findPromptTextarea();
      const n = findNegativeTextarea();
      if (p) {
        p.value = prompt || '';
        p.dispatchEvent(new Event('input', { bubbles: true }));
        p.dispatchEvent(new Event('change', { bubbles: true }));
      }
      if (n && negative != null) {
        n.value = negative;
        n.dispatchEvent(new Event('input', { bubbles: true }));
        n.dispatchEvent(new Event('change', { bubbles: true }));
      }
      publish({
        prompt: prompt || '',
        negative: negative || '',
        source: 'apply',
      });
      pushHistory({
        prompt: prompt || '',
        negative: negative || '',
        at: Date.now(),
      });
      return !!(p);
    },
  };

  function hookGenerate() {
    const buttons = Array.from(document.querySelectorAll('button, [role="button"], input[type="button"]'));
    for (const btn of buttons) {
      const t = (btn.textContent || btn.value || '').trim().toLowerCase();
      if (t === 'generate' || t.startsWith('generate')) {
        if (btn.dataset.tbccPcHooked) continue;
        btn.dataset.tbccPcHooked = '1';
        btn.addEventListener(
          'click',
          () => {
            const p = findPromptTextarea();
            const n = findNegativeTextarea();
            const prompt = p ? p.value : '';
            const negative = n ? n.value : '';
            const prev = global.__tbccPerchanceLastPrompt || {};
            publish({
              ...prev,
              prompt,
              negative,
              source: 'generate',
            });
            if (prompt) pushHistory({ prompt, negative, at: Date.now(), jobId: prev.jobId });
          },
          true
        );
      }
    }
  }

  let scanTimer = null;
  PC.features.promptBridge = {
    start() {
      hookGenerate();
      scanTimer = setInterval(hookGenerate, 2000);
    },
    stop() {
      if (scanTimer) clearInterval(scanTimer);
      scanTimer = null;
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
