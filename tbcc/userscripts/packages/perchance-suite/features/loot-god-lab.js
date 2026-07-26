/* Loot God Card Lab — compose border + quality primer + subject (+ local Δ). Extension FAB. */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const PC = (US.perchance = US.perchance || {});
  PC.features = PC.features || {};

  const PANEL_ID = 'tbcc-pc-loot-god-panel';
  const FAB_ID = 'tbcc-pc-loot-god-fab';
  const CHECK_KEY = 'tbcc_pc_loot_god_done_v1';
  const STATE_KEY = 'tbcc_pc_loot_god_state_v1';

  function lib() {
    return PC.lootGodLibrary || {};
  }

  function pick(arr) {
    if (!arr || !arr.length) return '';
    return arr[Math.floor(Math.random() * arr.length)];
  }

  function loadDone() {
    const raw = S.storage.get(CHECK_KEY, {}) || {};
    return typeof raw === 'object' ? raw : {};
  }

  function saveDone(map) {
    S.storage.set(CHECK_KEY, map);
  }

  function loadState() {
    return S.storage.get(STATE_KEY, null) || {};
  }

  function saveState(partial) {
    const next = { ...loadState(), ...partial };
    S.storage.set(STATE_KEY, next);
  }

  function tierMeta(n) {
    const t = lib().tiers && lib().tiers[String(n)];
    return t || { name: '?', world: '?', tagline: '', neon: '', mood: '' };
  }

  function tierPreset(n) {
    const L = lib();
    const p = (L.generatorPresets && L.generatorPresets[String(n)]) || {};
    const d = L.generatorDefaults || {};
    return {
      band: p.band || 'mid',
      label: p.label || `Tier ${n}`,
      note: p.note || '',
      howManyPics: p.howManyPics || d.howManyPics || '15',
      shape: p.shape || d.shape || 'Square',
      guidance: p.guidance || '10',
      imageSeed: p.imageSeed != null ? p.imageSeed : d.imageSeed || '',
      artStyle: p.artStyle || d.artStyle || 'NSFW - Realistic',
      persona: p.persona || d.persona || 'Default',
      ethnicity: p.ethnicity || d.ethnicity || 'Default',
      age: p.age || d.age || '32',
      hairColour: p.hairColour || d.hairColour || 'Default',
      hairStyle: p.hairStyle || d.hairStyle || 'Default',
      naughtyPose: p.naughtyPose || 'Filthy',
      expression: p.expression || 'Horny',
      extras1: p.extras1 || 'Default',
      extras2: p.extras2 || 'Default',
      extras3: p.extras3 || 'Default',
      extras4: p.extras4 || 'Default',
      extras5: p.extras5 || 'Default',
      location: p.location || 'Default',
      position: p.position || 'Default',
      view: p.view || 'Default',
      bodyType: p.bodyType || 'Default',
    };
  }

  function qualityPrimerForTier(n) {
    const L = lib();
    const band = tierPreset(n).band;
    const by = L.qualityPrimersByBand || {};
    return by[band] || L.qualityPrimerDefault || L.qualityPrimer || '';
  }

  function seedForTier(n) {
    const L = lib();
    const by = L.subjectSeedsByTier || {};
    const list = by[String(n)];
    if (list && list.length) return pick(list);
    return pick(L.subjectSeeds || []) || '';
  }

  function applyDelta(subject, level) {
    const banks = lib().deltaBanks || {};
    const base = (subject || '').trim();
    if (!base || level <= 0) return base;
    const bits = [base];
    if (level >= 1) {
      const L = pick(banks.lighting);
      if (L) bits.push(`lighting: ${L}`);
    }
    if (level >= 2) {
      const P = pick(banks.pose);
      const F = pick(banks.framing);
      if (P) bits.push(`pose: ${P}`);
      if (F) bits.push(`framing: ${F}`);
    }
    if (level >= 3) {
      const W = pick(banks.wardrobe);
      if (W) bits.push(`wardrobe accent: ${W}`);
    }
    return bits.join(', ');
  }

  function composePrompt(tier, subjectEffective) {
    const L = lib();
    const meta = tierMeta(tier);
    const preset = tierPreset(tier);
    const name = String(meta.name || '').toUpperCase();
    const world = meta.world || '';
    const tagline = meta.tagline || '';
    const neon = meta.neon || '';
    const mood = meta.mood || '';
    const primer = qualityPrimerForTier(tier);

    return [
      L.outputBlock || '',
      '',
      L.borderStyle || '',
      '',
      `TIER BLOCK (spell exactly when text is attempted; blank plate OK if typography fails — NO gibberish):`,
      `TOP-RIGHT = TIER ${tier} · ${world}`,
      `BOTTOM NAME = ${name}`,
      `TAGLINE = ${tagline}`,
      `NEON / FRAME ACCENT: ${neon}`,
      `MOOD CUE: ${mood}`,
      `LOOT VALUE BAND: ${preset.band} — ${preset.label}`,
      '',
      'PERCHANCE DROPDOWNS (set these on the page — Lab can auto-apply):',
      `How many Pics? = ${preset.howManyPics}`,
      `Shape of image(s) = ${preset.shape}`,
      `Guidance scale = ${preset.guidance}`,
      `Art Style = ${preset.artStyle}`,
      `Age? = ${preset.age}`,
      `Naughty Pose? = ${preset.naughtyPose}`,
      `Expression? = ${preset.expression}`,
      `Extras 1? = ${preset.extras1}`,
      `Extras 2? = ${preset.extras2}`,
      `Extras 3? = ${preset.extras3}`,
      `Extras 4? = ${preset.extras4}`,
      `Extras 5? = ${preset.extras5}`,
      `Location? = ${preset.location}`,
      `Position? = ${preset.position}`,
      `View? = ${preset.view}`,
      `Body type? = ${preset.bodyType}`,
      preset.note ? `PRESET NOTE: ${preset.note}` : '',
      '',
      primer,
      '',
      'SUBJECT (center window only — adult content allowed; keep chrome readable):',
      subjectEffective || '(describe the adult subject here)',
      '',
      'Generate now. ONE card only. Lock chrome. Match loot-value band. Prefer blank nameplate over gibberish. Put creative variation in the center window only.',
    ]
      .filter((line) => line !== '')
      .join('\n');
  }

  /** Set a page <select> whose nearby label matches labelRe to an option matching valueRe/text. */
  function setSelectByLabel(labelRe, wantText) {
    if (!wantText) return false;
    const want = String(wantText).trim().toLowerCase();
    const selects = Array.from(document.querySelectorAll('select'));
    for (const sel of selects) {
      const lab =
        sel.getAttribute('aria-label') ||
        sel.getAttribute('name') ||
        sel.previousElementSibling?.textContent ||
        sel.parentElement?.textContent ||
        '';
      if (!labelRe.test(lab)) continue;
      let matched = null;
      for (const opt of Array.from(sel.options)) {
        const t = (opt.textContent || opt.value || '').trim();
        if (t.toLowerCase() === want || t.toLowerCase().includes(want)) {
          matched = opt;
          break;
        }
      }
      // typo-tolerant: "Wet hair an body" vs "Wet hair and body"
      if (!matched && want.includes('wet hair')) {
        for (const opt of Array.from(sel.options)) {
          const t = (opt.textContent || '').toLowerCase();
          if (t.includes('wet hair')) {
            matched = opt;
            break;
          }
        }
      }
      if (!matched) continue;
      sel.value = matched.value;
      sel.dispatchEvent(new Event('input', { bubbles: true }));
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    }
    return false;
  }

  function applyGeneratorDropdowns(tier) {
    document.documentElement?.removeAttribute('data-tbcc-pc-border-only');
    const p = tierPreset(tier);
    const hits = [];
    const attempts = [
      [/how\s*many\s*pics/i, p.howManyPics],
      [/shape\s*of\s*image/i, p.shape],
      [/guidance/i, p.guidance],
      [/art\s*style/i, p.artStyle],
      [/\bage\b/i, p.age],
      [/naughty\s*pose/i, p.naughtyPose],
      [/expression/i, p.expression],
      [/extras\s*1/i, p.extras1],
      [/extras\s*2/i, p.extras2],
      [/extras\s*3/i, p.extras3],
      [/extras\s*4/i, p.extras4],
      [/extras\s*5/i, p.extras5],
      [/location/i, p.location],
      [/position/i, p.position],
      [/\bview\b/i, p.view],
      [/body\s*type/i, p.bodyType],
      [/persona/i, p.persona],
      [/ethnicity/i, p.ethnicity],
    ];
    for (const [re, val] of attempts) {
      if (val && setSelectByLabel(re, val)) hits.push(re.source);
    }
    return hits;
  }

  /** Force every page <select> that has a Default option onto Default. */
  function resetSelectsToDefault(opts) {
    const keepLabels = (opts && opts.keepLabels) || [];
    let cleared = 0;
    document.querySelectorAll('select').forEach((sel) => {
      const lab =
        sel.getAttribute('aria-label') ||
        sel.getAttribute('name') ||
        sel.previousElementSibling?.textContent ||
        sel.parentElement?.textContent ||
        '';
      if (keepLabels.some((re) => re.test(lab))) return;
      let def = null;
      for (const opt of Array.from(sel.options)) {
        const t = (opt.textContent || opt.value || '').trim();
        if (/^default$/i.test(t)) {
          def = opt;
          break;
        }
      }
      if (!def) return;
      if (sel.value !== def.value) {
        sel.value = def.value;
        sel.dispatchEvent(new Event('input', { bubbles: true }));
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      }
      cleared += 1;
    });
    return cleared;
  }

  /**
   * Full wipe: every Default-capable select → Default, prompt/negative blanked.
   * Closest thing to “no settings / factory clean” on this generator.
   */
  function clearAllGeneratorSettings() {
    document.documentElement?.removeAttribute('data-tbcc-pc-border-only');
    const cleared = resetSelectsToDefault({ keepLabels: [] });
    // Pics / shape / guidance often lack a literal “Default” — nudge to safe neutrals.
    const soft = [
      [/how\s*many\s*pics/i, '1'],
      [/shape\s*of\s*image/i, 'Square'],
      [/guidance/i, '7'],
    ];
    const softHits = [];
    for (const [re, val] of soft) {
      if (setSelectByLabel(re, val)) softHits.push(re.source);
    }
    if (PC.promptBridge && typeof PC.promptBridge.applyPrompt === 'function') {
      PC.promptBridge.applyPrompt('', '');
    }
    return { cleared, softHits };
  }

  /** Zero character plugins so they cannot override a frame-only prompt. */
  function applyBorderOnlyDropdowns() {
    document.documentElement?.setAttribute('data-tbcc-pc-border-only', '1');
    const L = lib();
    const cfg = L.borderOnlyDropdowns || {};
    const keepLabels = [/how\s*many\s*pics/i, /shape\s*of\s*image/i, /guidance/i, /image\s*seed/i];

    const cleared = resetSelectsToDefault({ keepLabels });
    const hits = [`cleared~${cleared}`];
    const attempts = [
      [/how\s*many\s*pics/i, cfg.howManyPics || '4'],
      [/shape\s*of\s*image/i, cfg.shape || 'Square'],
      [/guidance/i, cfg.guidance || '8'],
      [/art\s*style/i, cfg.artStyle || 'Default'],
      [/\bage\b/i, cfg.age || 'Default'],
      [/naughty\s*pose/i, cfg.naughtyPose || 'Default'],
      [/expression/i, cfg.expression || 'Default'],
      [/extras\s*1/i, cfg.extras1 || 'Default'],
      [/extras\s*2/i, cfg.extras2 || 'Default'],
      [/extras\s*3/i, cfg.extras3 || 'Default'],
      [/extras\s*4/i, cfg.extras4 || 'Default'],
      [/extras\s*5/i, cfg.extras5 || 'Default'],
      [/location/i, cfg.location || 'Default'],
      [/position/i, cfg.position || 'Default'],
      [/\bview\b/i, cfg.view || 'Default'],
      [/body\s*type/i, cfg.bodyType || 'Default'],
      [/persona/i, cfg.persona || 'Default'],
      [/ethnicity/i, cfg.ethnicity || 'Default'],
      [/lingerie/i, cfg.lingerie || 'Default'],
      [/cosplay/i, cfg.cosplay || 'Default'],
      [/underwear/i, cfg.underwear || 'Default'],
      [/\bdress\b/i, cfg.dress || 'Default'],
      [/skirts/i, cfg.skirts || 'Default'],
      [/hair\s*colou?r/i, cfg.hairColour || 'Default'],
      [/hair\s*style/i, cfg.hairStyle || 'Default'],
    ];
    for (const [re, val] of attempts) {
      if (val && setSelectByLabel(re, val)) hits.push(re.source);
    }
    return hits;
  }

  /** Empty chrome frame; optional per-tier neon + stamped plates for bulk border gens. */
  function composeBorderPrompt(tier) {
    const L = lib();
    const base = (L.borderOnlyPrompt || '').trim();
    if (!tier || tier < 1) return base;
    const meta = tierMeta(tier);
    const name = String(meta.name || '').toUpperCase();
    return [
      base,
      '',
      'TIER CHROME FOR THIS GEN (stamp readable text if the model can; else blank dark plates — NO gibberish):',
      `TOP-RIGHT = TIER ${tier} · ${meta.world || ''}`,
      `BOTTOM NAME = ${name}`,
      `TAGLINE = ${meta.tagline || ''}`,
      `NEON / FRAME ACCENT: ${meta.neon || 'hot-pink + cyan'}`,
      `MOOD CUE: ${meta.mood || ''}`,
      'CENTER WINDOW still fully transparent (or #00FF00 key). No subject.',
    ].join('\n');
  }

  function applyToPage(prompt, negative) {
    if (PC.promptBridge && typeof PC.promptBridge.applyPrompt === 'function') {
      return PC.promptBridge.applyPrompt(prompt, negative);
    }
    return false;
  }

  function mount() {
    if (document.getElementById(PANEL_ID)) return;
    const L = lib();

    S.ensureStyle(
      'tbcc-pc-loot-god-style',
      `
      #${PANEL_ID} {
        position: fixed; z-index: 999999; left: 12px; bottom: 12px;
        width: min(440px, calc(100vw - 24px)); max-height: min(82vh, 720px);
        overflow: auto; background: #121212; color: #ddd;
        border: 1px solid #3a3a3a; border-radius: 10px;
        box-shadow: 0 12px 36px rgba(0,0,0,.6);
        font: 12px/1.35 system-ui, sans-serif; display: none;
      }
      #${PANEL_ID}.open { display: flex; flex-direction: column; }
      #${PANEL_ID} header {
        position: sticky; top: 0; background: #1c1c1c; padding: 8px 10px;
        border-bottom: 1px solid #333; display: flex; gap: 6px; align-items: center;
      }
      #${PANEL_ID} header strong { flex: 1; font-size: 13px; }
      #${PANEL_ID} .body { padding: 10px; display: flex; flex-direction: column; gap: 8px; }
      #${PANEL_ID} label.row { display: flex; flex-direction: column; gap: 4px; }
      #${PANEL_ID} .inline { display: flex; gap: 8px; align-items: center; }
      #${PANEL_ID} .inline > * { flex: 1; }
      #${PANEL_ID} select, #${PANEL_ID} input, #${PANEL_ID} textarea, #${PANEL_ID} button {
        background: #2a2a2a; color: #eee; border: 1px solid #444; border-radius: 5px;
        padding: 6px 8px; font: inherit;
      }
      #${PANEL_ID} textarea { min-height: 72px; resize: vertical; width: 100%; box-sizing: border-box; }
      #${PANEL_ID} .preview {
        background: #1a1a1a; border: 1px dashed #444; border-radius: 6px;
        padding: 8px; color: #9a9a9a; max-height: 90px; overflow: auto; white-space: pre-wrap;
      }
      #${PANEL_ID} .chip {
        display: inline-block; background: #3a2210; color: #f0c090;
        border: 1px solid #6a4020; border-radius: 4px; padding: 3px 8px; font-size: 11px;
      }
      #${PANEL_ID} .actions { display: flex; flex-wrap: wrap; gap: 6px; }
      #${PANEL_ID} .actions button { flex: 1 1 40%; cursor: pointer; }
      #${PANEL_ID} .actions button.primary { background: #c45c26; border-color: #e07030; font-weight: 600; }
      #${PANEL_ID} .checklist { display: flex; flex-wrap: wrap; gap: 4px; }
      #${PANEL_ID} .checklist button {
        width: 28px; padding: 4px 0; cursor: pointer; font-size: 11px;
      }
      #${PANEL_ID} .checklist button.done { background: #2a4a2a; border-color: #4a6a4a; color: #b6e0b6; }
      #${PANEL_ID} .status.hint { min-height: 1.2em; }
      #${PANEL_ID} .toast-chip {
        display: none; align-self: flex-start;
        background: #1e3a1e; color: #c8f0c8; border: 1px solid #4a7a4a;
        border-radius: 999px; padding: 3px 9px; font-size: 11px;
      }
      #${PANEL_ID} .toast-chip.show { display: inline-block; }
      #${FAB_ID} {
        position: fixed; z-index: 999998; left: 12px; bottom: 56px;
        background: #8b2e1a; color: #fff; border: 0; border-radius: 6px;
        padding: 8px 12px; cursor: pointer; font: 12px system-ui, sans-serif;
        box-shadow: 0 4px 14px rgba(0,0,0,.45);
      }
      #${FAB_ID}:hover { background: #a83820; }
    `
    );

    const panel = document.createElement('div');
    panel.id = PANEL_ID;
    const tierOpts = Array.from({ length: 10 }, (_, i) => {
      const n = i + 1;
      const m = tierMeta(n);
      return `<option value="${n}">T${n} · ${m.name} · ${m.world}</option>`;
    }).join('');

    panel.innerHTML = `
      <header>
        <strong>Loot God Card Lab</strong>
        <button type="button" data-act="close">Close</button>
      </header>
      <div class="body">
        <div class="inline">
          <label class="row">Tier
            <select data-act="tier">${tierOpts}</select>
          </label>
          <label class="row">Δ variation
            <input type="range" data-act="delta" min="0" max="3" step="1" value="0" />
          </label>
        </div>
        <div class="chip" data-act="filechip">→ save as tier-1.png</div>
        <div class="chip" data-act="presetchip" style="margin-top:4px">band: trash · guidance 7</div>
        <div class="preview" data-act="tierpreview"></div>
        <details>
          <summary>Quality primer (tier band — locked)</summary>
          <div class="preview" data-act="primer"></div>
        </details>
        <div class="inline" style="align-items:flex-start">
          <label class="row" style="flex:1">Subject (your art)
            <textarea data-act="subject" placeholder="Adult subject / scene — border + quality are added for you"></textarea>
          </label>
          <label class="row" style="flex:0 0 72px; max-width:72px">Δ
            <input type="number" data-act="deltaNum" min="0" max="3" value="0" style="width:100%" />
          </label>
        </div>
        <div class="hint" data-act="deltahint">Δ 0 = verbatim subject. Higher = lighting / pose /wardrobe accents without rewriting your core.</div>
        <div class="inline">
          <label class="row">Instant preset
            <select data-act="instantPreset">
              <option value="clear">Clear · all Default</option>
              <option value="border">Border · blank chrome</option>
              <option value="border-tier">Border · this tier neon</option>
              ${Array.from({ length: 10 }, (_, i) => {
                const n = i + 1;
                const m = tierMeta(n);
                const p = tierPreset(n);
                return `<option value="t${n}">T${n} · ${m.name} · ${p.band}</option>`;
              }).join('')}
            </select>
          </label>
          <label class="row" style="flex:0 0 auto">
            <span style="opacity:0">&nbsp;</span>
            <button type="button" data-act="apply-preset" style="white-space:nowrap">Apply preset</button>
          </label>
        </div>
        <div class="actions">
          <button type="button" class="primary" data-act="compose">Compose + Apply</button>
          <button type="button" data-act="dropdowns">Apply page dropdowns</button>
          <button type="button" data-act="clear" title="All page selects → Default, blank prompts">Clear</button>
          <button type="button" data-act="reroll">Δ again</button>
          <button type="button" data-act="seed">Seed subject</button>
          <button type="button" data-act="copy">Copy prompt</button>
          <button type="button" data-act="copy-border">Border blank</button>
          <button type="button" data-act="border-tier">Border this tier</button>
          <button type="button" data-act="border-next">Border next →</button>
          <button type="button" data-act="mark">Mark tier done</button>
        </div>
        <div class="hint">Presets = instant dropdowns + prompt. Clear = every Default select + blank prompts. Borders: Clear → Border this tier → Generate → save frame-T{n}.png → Border next. Reload TBCC after suite build.</div>
        <div class="checklist" data-act="check"></div>
        <div class="toast-chip" data-act="toast"></div>
        <div class="status hint" data-act="status"></div>
      </div>
    `;
    document.documentElement.appendChild(panel);

    const fab = document.createElement('button');
    fab.id = FAB_ID;
    fab.type = 'button';
    fab.textContent = 'Loot Cards';
    fab.title = 'TBCC Loot God Card Lab';
    fab.addEventListener('click', () => {
      panel.classList.add('open');
      fab.style.display = 'none';
    });
    document.documentElement.appendChild(fab);

    const tierEl = panel.querySelector('[data-act="tier"]');
    const deltaEl = panel.querySelector('[data-act="delta"]');
    const deltaNum = panel.querySelector('[data-act="deltaNum"]');
    const subjectEl = panel.querySelector('[data-act="subject"]');
    const previewEl = panel.querySelector('[data-act="tierpreview"]');
    const primerEl = panel.querySelector('[data-act="primer"]');
    const fileChip = panel.querySelector('[data-act="filechip"]');
    const presetChip = panel.querySelector('[data-act="presetchip"]');
    const checkEl = panel.querySelector('[data-act="check"]');
    const statusEl = panel.querySelector('[data-act="status"]');
    const toastEl = panel.querySelector('[data-act="toast"]');
    const deltaHint = panel.querySelector('[data-act="deltahint"]');

    function chip(msg) {
      if (!toastEl) return;
      toastEl.textContent = msg;
      toastEl.classList.add('show');
      clearTimeout(toastEl._hide);
      toastEl._hide = setTimeout(() => toastEl.classList.remove('show'), 1400);
    }

    let lastPrompt = '';
    let lastNegative = L.negative || '';
    let lastSubjectVariant = '';

    const st = loadState();
    if (st.tier) tierEl.value = String(st.tier);
    if (st.subject) subjectEl.value = st.subject;
    if (typeof st.delta === 'number') {
      deltaEl.value = String(st.delta);
      deltaNum.value = String(st.delta);
    }

    function deltaLevel() {
      return Math.max(0, Math.min(3, parseInt(deltaEl.value, 10) || 0));
    }

    function syncDeltaUi() {
      const d = deltaLevel();
      deltaNum.value = String(d);
      const labels = [
        'Δ 0 — verbatim subject',
        'Δ 1 — + lighting/atmosphere',
        'Δ 2 — + pose/framing',
        'Δ 3 — + wardrobe accent',
      ];
      deltaHint.textContent = labels[d] || labels[0];
    }

    function refreshTierUi() {
      const n = parseInt(tierEl.value, 10) || 1;
      const m = tierMeta(n);
      const p = tierPreset(n);
      previewEl.textContent =
        `BORDER LOCK\nTIER ${n} · ${m.world} · ${m.name}\n"${m.tagline}"\nNeon: ${m.neon}\nMood: ${m.mood}\n\nPRESET: ${p.label}\n${p.note || ''}`;
      fileChip.textContent = `→ save as tier-${n}.png`;
      if (presetChip) {
        presetChip.textContent = `band: ${p.band} · guidance ${p.guidance} · ${p.extras5 !== 'Default' ? p.extras5 + ' · ' : ''}${p.label}`;
      }
      primerEl.textContent = qualityPrimerForTier(n);
      renderChecklist();
      saveState({ tier: n, subject: subjectEl.value, delta: deltaLevel() });
    }

    function renderChecklist() {
      const done = loadDone();
      checkEl.innerHTML = '';
      for (let n = 1; n <= 10; n++) {
        const b = document.createElement('button');
        b.type = 'button';
        b.textContent = String(n);
        if (done[String(n)]) b.classList.add('done');
        b.title = done[String(n)] ? `Tier ${n} marked done` : `Jump to tier ${n}`;
        b.addEventListener('click', () => {
          tierEl.value = String(n);
          refreshTierUi();
        });
        checkEl.appendChild(b);
      }
    }

    function buildAndApply(reroll) {
      const n = parseInt(tierEl.value, 10) || 1;
      const d = deltaLevel();
      const base = subjectEl.value.trim();
      const effective = applyDelta(base, d);
      lastSubjectVariant = effective;
      lastPrompt = composePrompt(n, effective);
      lastNegative = L.negative || '';
      const dropHits = applyGeneratorDropdowns(n);
      const ok = applyToPage(lastPrompt, lastNegative);
      if (PC.promptBridge && PC.promptBridge.publish) {
        PC.promptBridge.publish({
          jobId: `loot-god-tier-${n}`,
          lane: 'loot-god',
          label: `Loot God · T${n} · ${tierMeta(n).name}`,
          format: 'card-1x1',
          aspect: L.aspect || '1:1',
          shapeHint: L.shapeHint || 'Square = 512x512',
          prompt: lastPrompt,
          negative: lastNegative,
          subject: base,
          subjectVariant: effective,
          delta: d,
          band: tierPreset(n).band,
          source: reroll ? 'loot-god-delta' : 'loot-god-compose',
        });
      }
      const dropNote = dropHits.length ? ` · ${dropHits.length} dropdowns` : ' · dropdowns miss (set manually)';
      statusEl.textContent = ok
        ? `Applied T${n} ${tierPreset(n).band} (Δ${d})${effective !== base ? ' · subject varied' : ''}${dropNote}. Save as tier-${n}.png`
        : `Composed T${n} but could not find page prompt field — use Copy.${dropNote}`;
      saveState({ tier: n, subject: base, delta: d });
      return ok;
    }

    function applyBorderMode(opts) {
      const stampTier = !!(opts && opts.stampTier);
      const advance = !!(opts && opts.advance);
      let n = parseInt(tierEl.value, 10) || 1;
      if (advance) {
        n = n >= 10 ? 1 : n + 1;
        tierEl.value = String(n);
        refreshTierUi();
      }
      const text = stampTier ? composeBorderPrompt(n) : composeBorderPrompt(0);
      if (!text) {
        statusEl.textContent = 'No borderOnlyPrompt in library.';
        chip('Missing');
        return false;
      }
      const neg = (L.borderOnlyNegative || L.negative || '').trim();
      const dropHits = applyBorderOnlyDropdowns();
      lastPrompt = text;
      lastNegative = neg;
      const ok = applyToPage(text, neg);
      try {
        navigator.clipboard.writeText(text);
      } catch (_) {
        /* apply still counts */
      }
      const fname = stampTier ? `frame-T${n}.png` : 'frame.png';
      if (fileChip) fileChip.textContent = `→ save as ${fname}`;
      statusEl.textContent = ok
        ? `Border ${stampTier ? `T${n} neon` : 'blank'} applied · ${dropHits.length} dropdown resets. Generate → save ${fname}. Verify all character selects are Default.`
        : `Border prompt ready; ${dropHits.length} dropdown resets. Paste if needed. Save as ${fname}.`;
      chip(stampTier ? `Border T${n}` : 'Border blank');
      if (PC.promptBridge && PC.promptBridge.publish) {
        PC.promptBridge.publish({
          jobId: stampTier ? `loot-god-border-t${n}` : 'loot-god-border-only',
          lane: 'loot-god',
          label: stampTier
            ? `Loot God · border T${n} · ${tierMeta(n).name}`
            : 'Loot God · border-only frame',
          format: 'card-1x1-frame',
          aspect: L.aspect || '1:1',
          prompt: text,
          negative: neg,
          source: stampTier ? 'loot-god-border-tier' : 'loot-god-border-only',
        });
      }
      return ok;
    }

    function applyInstantPreset(key) {
      const k = String(key || '').trim();
      if (k === 'clear') {
        const r = clearAllGeneratorSettings();
        subjectEl.value = '';
        lastPrompt = '';
        lastNegative = '';
        saveState({ subject: '' });
        statusEl.textContent = `Cleared ${r.cleared} selects → Default${r.softHits.length ? ` · soft-set ${r.softHits.length}` : ''} · prompts blank.`;
        chip('Cleared');
        return;
      }
      if (k === 'border') {
        applyBorderMode({ stampTier: false });
        return;
      }
      if (k === 'border-tier') {
        applyBorderMode({ stampTier: true });
        return;
      }
      const tm = /^t(\d+)$/i.exec(k);
      if (tm) {
        const n = parseInt(tm[1], 10);
        tierEl.value = String(n);
        refreshTierUi();
        buildAndApply(false);
        chip(`Preset T${n}`);
        return;
      }
      statusEl.textContent = `Unknown preset: ${k}`;
      chip('Unknown');
    }

    panel.querySelector('[data-act="close"]').addEventListener('click', () => {
      panel.classList.remove('open');
      fab.style.display = '';
      chip('Closed');
    });
    tierEl.addEventListener('change', refreshTierUi);
    deltaEl.addEventListener('input', () => {
      syncDeltaUi();
      saveState({ delta: deltaLevel() });
    });
    deltaNum.addEventListener('change', () => {
      deltaEl.value = String(Math.max(0, Math.min(3, parseInt(deltaNum.value, 10) || 0)));
      syncDeltaUi();
    });
    subjectEl.addEventListener('change', () => saveState({ subject: subjectEl.value }));

    panel.querySelector('[data-act="compose"]').addEventListener('click', () => buildAndApply(false));
    panel.querySelector('[data-act="dropdowns"]').addEventListener('click', () => {
      const n = parseInt(tierEl.value, 10) || 1;
      const hits = applyGeneratorDropdowns(n);
      statusEl.textContent = hits.length
        ? `Applied ${hits.length} page dropdowns for T${n} (${tierPreset(n).band}).`
        : `No matching selects found — set Guidance/Extras manually for T${n}.`;
      chip(hits.length ? `${hits.length} dropdowns` : 'No selects');
    });
    panel.querySelector('[data-act="clear"]').addEventListener('click', () => {
      applyInstantPreset('clear');
    });
    panel.querySelector('[data-act="apply-preset"]').addEventListener('click', () => {
      const sel = panel.querySelector('[data-act="instantPreset"]');
      applyInstantPreset(sel ? sel.value : 'clear');
    });
    panel.querySelector('[data-act="reroll"]').addEventListener('click', () => {
      if (deltaLevel() === 0) {
        deltaEl.value = '1';
        syncDeltaUi();
      }
      buildAndApply(true);
    });
    panel.querySelector('[data-act="seed"]').addEventListener('click', () => {
      const n = parseInt(tierEl.value, 10) || 1;
      subjectEl.value = seedForTier(n) || subjectEl.value;
      saveState({ subject: subjectEl.value });
      statusEl.textContent = `Seeded T${n} ${tierPreset(n).band} subject — tweak then Compose + Apply.`;
      chip(`T${n} seed`);
    });
    panel.querySelector('[data-act="copy"]').addEventListener('click', async () => {
      if (!lastPrompt) buildAndApply(false);
      try {
        await navigator.clipboard.writeText(lastPrompt);
        statusEl.textContent = 'Prompt copied.';
        chip('Copied');
      } catch (_) {
        statusEl.textContent = 'Clipboard blocked — select from page field.';
        chip('Clipboard blocked');
      }
    });
    panel.querySelector('[data-act="copy-border"]').addEventListener('click', () => {
      applyBorderMode({ stampTier: false });
    });
    panel.querySelector('[data-act="border-tier"]').addEventListener('click', () => {
      applyBorderMode({ stampTier: true });
    });
    panel.querySelector('[data-act="border-next"]').addEventListener('click', () => {
      applyBorderMode({ stampTier: true, advance: true });
    });
    panel.querySelector('[data-act="mark"]').addEventListener('click', () => {
      const n = parseInt(tierEl.value, 10) || 1;
      const done = loadDone();
      done[String(n)] = true;
      saveDone(done);
      renderChecklist();
      statusEl.textContent = `Marked tier-${n}.png done. ${Object.keys(done).filter((k) => done[k]).length}/10`;
      chip(`T${n} done`);
    });

    syncDeltaUi();
    refreshTierUi();
  }

  PC.features.lootGodLab = {
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
