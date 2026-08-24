/* FetLife context intel — operator build only (omitted from community). */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const INTEL_ROWS_KEY = 'tbcc_fl_intel_rows_v1';
  const INTEL_META_KEY = 'tbcc_fl_intel_meta_v1';

  function loadIntelMeta() {
    const saved = S.storage.get(INTEL_META_KEY, null);
    return {
      recordIntel: false,
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

  function pathTitle() {
    return (location.pathname || '/').split('/').filter(Boolean).slice(-2).join('/') || 'fetlife';
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

  FL.overlayIntel = {
    render(body, rerender) {
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
        rerender?.();
      });
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
