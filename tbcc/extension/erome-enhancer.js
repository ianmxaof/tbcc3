/* TBCC extension port — Erome Enhancer (from erome-enhancer.user.js v4.2) */
tbccWaitForModule('erome_enhancer', function () {(function () {
  'use strict';
 
  // Constants
  const STORAGE_KEY = 'eromeEnhancerSettings';
  const VIEWED_KEY = 'eromeViewedAlbums';
  const DEFAULTS = {
    filterMode: 'videos',
    autoScroll: true,
    hideViewed: false,
    minVideoSeconds: 0,
    showLikes: true,
    enableSorting: true,
    titleInclude: '',
    titleExclude: '',
    /** Like + Repost controls on explore/search thumbnails (no album open). */
    gridLikeRepost: true,
    /** Album page: surface video source URLs + one-click → ThisVid direct-link upload. */
    videoThisVidBridge: true,
  };
  const INTEL_KEY = 'eromeBrowseIntelRows';
  const INTEL_META_KEY = 'eromeBrowseIntelMeta';

  function loadIntelMeta() {
    try {
      return Object.assign(
        {
          recordIntel: true,
          maxIntelRows: 5000,
          tbccApiUrl: 'http://127.0.0.1:8000/analytics/erome-browse-intel',
          showTransportOverlay: true,
          showIntelLivePanel: true,
        },
        JSON.parse(localStorage.getItem(INTEL_META_KEY) || '{}')
      );
    } catch {
      return {
        recordIntel: true,
        maxIntelRows: 5000,
        tbccApiUrl: 'http://127.0.0.1:8000/analytics/erome-browse-intel',
        showTransportOverlay: true,
        showIntelLivePanel: true,
      };
    }
  }
  function saveIntelMeta(meta) {
    localStorage.setItem(INTEL_META_KEY, JSON.stringify(meta));
  }
  let intelMeta = loadIntelMeta();

  function loadIntelRows() {
    try {
      return JSON.parse(localStorage.getItem(INTEL_KEY) || '[]');
    } catch {
      return [];
    }
  }
  function saveIntelRows(rows, opts) {
    const o = opts || {};
    if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.saveWithCapAndMaybePush === 'function') {
      globalThis.tbccBrowseIntel.saveWithCapAndMaybePush({
        rows,
        meta: intelMeta,
        skipAutoPush: !!o.skipAutoPush,
        applyTrimmed: (stored) => {
          try {
            localStorage.setItem(INTEL_KEY, JSON.stringify(stored));
          } catch (_) {}
        },
        toast: (msg) => {
          try {
            showEeToast(msg);
          } catch (_) {}
        },
      });
      return;
    }
    const cap = Math.max(500, intelMeta.maxIntelRows || 5000);
    localStorage.setItem(INTEL_KEY, JSON.stringify(rows.slice(-cap)));
  }

  let lastIntelBadgeCount = 0;

  function updateIntelCountBadge(opts = {}) {
    const el = document.getElementById('eeIntelCountNum');
    const wrap = document.getElementById('eeIntelCountWrap');
    if (!el) return;
    const count = loadIntelRows().length;
    el.textContent = String(count);
    if (wrap) {
      wrap.style.opacity = intelMeta.recordIntel !== false ? '1' : '0.4';
      wrap.title = intelMeta.recordIntel !== false
        ? `Browse intel: ${count} rows saved (one per album per day)`
        : 'Browse intel recording is off — enable in Enhancer settings';
    }
    if (opts.pulse && count > lastIntelBadgeCount) {
      el.style.transition = 'color 0.2s ease, transform 0.2s ease';
      el.style.color = '#ffffff';
      el.style.transform = 'scale(1.3)';
      setTimeout(() => {
        el.style.color = '#7ec8e3';
        el.style.transform = '';
      }, 450);
    }
    lastIntelBadgeCount = count;
  }

  function albumIdFromUrl(url) {
    const m = (url || '').match(/\/a\/([^/?#]+)/i);
    return m ? m[1].toLowerCase() : '';
  }

  function pageContext() {
    const path = location.pathname;
    const ctx = { path, page_num: currentPage };
    if (path.startsWith('/search')) {
      const q = new URLSearchParams(location.search).get('q');
      if (q) ctx.search_query = q;
    }
    return ctx;
  }

  function formatBucket(videos, images) {
    const v = Number(videos) || 0;
    const i = Number(images) || 0;
    if (v >= 1 && i >= 1) return 'mixed_album';
    if (v === 1 && !i) return 'single_video';
    if (v > 1 && !i) return 'multi_video';
    if (i && !v) return 'photo_album';
    return 'unknown';
  }

  function extractTitleFromDoc(doc) {
    const h1 = doc.querySelector('h1');
    return h1 ? h1.textContent.trim().slice(0, 200) : '';
  }

  function extractTagsFromDoc(doc) {
    const tags = [];
    doc.querySelectorAll('a[href*="/search?q="], .album-tags a, .tags a').forEach((a) => {
      const t = (a.textContent || '').trim().replace(/^#/, '');
      if (t && t.length < 40) tags.push(t.toLowerCase());
    });
    return [...new Set(tags)].slice(0, 30);
  }

  function parseRelativeAgeDays(text) {
    if (!text) return null;
    const s = String(text).trim().toLowerCase();
    const m = s.match(/(\d+)\s*(second|minute|hour|day|week|month|year)s?\s*ago/);
    if (!m) return null;
    const n = parseInt(m[1], 10);
    const unit = m[2];
    const perDay = { second: 1 / 86400, minute: 1 / 1440, hour: 1 / 24, day: 1, week: 7, month: 30, year: 365 };
    return Math.max(0.04, n * (perDay[unit] || 1));
  }

  function extractUploadedAgeDaysFromDoc(doc) {
    const candidates = doc.querySelectorAll(
      '.album-created, .album-date, time[datetime], [class*="created"], [class*="uploaded"]'
    );
    for (const el of candidates) {
      const dt = el.getAttribute('datetime');
      if (dt) {
        const ms = Date.parse(dt);
        if (!Number.isNaN(ms)) return Math.max(0.04, (Date.now() - ms) / 86400000);
      }
      const days = parseRelativeAgeDays(el.textContent);
      if (days != null) return days;
    }
    const bodyText = doc.body?.textContent || '';
    const inline = bodyText.match(/(\d+\s*(?:second|minute|hour|day|week|month|year)s?\s*ago)/i);
    return inline ? parseRelativeAgeDays(inline[1]) : null;
  }

  function extractUploaderFromDoc(doc) {
    const skip = /^\/user\/(login|register|feed|liked|saved|disclaimer|logout|settings)/i;
    for (const a of doc.querySelectorAll('a[href*="/user/"]')) {
      const href = a.getAttribute('href') || '';
      if (skip.test(href)) continue;
      const m = href.match(/\/user\/([^/?#]+)/i);
      if (m) return decodeURIComponent(m[1]).slice(0, 80);
    }
    return null;
  }

  function extractIsVerifiedFromDoc(doc) {
    const skip = /^\/user\/(login|register|feed|liked|saved|disclaimer|logout|settings)/i;
    for (const a of doc.querySelectorAll('a[href*="/user/"]')) {
      const href = a.getAttribute('href') || '';
      if (skip.test(href)) continue;
      const block = a.closest('.user-info, .album-user, .username, .profile, .media-group-info') || a.parentElement;
      if (block?.querySelector('.fa-check, .fa-check-circle, .verified, [title*="Verified"], [title*="verified"]')) {
        return true;
      }
    }
    return !!doc.querySelector('.fa-check-circle, .verified-badge, .verified');
  }

  function extractMediaSequenceFromDoc(doc) {
    const seq = [];
    const groups = doc.querySelectorAll('#medias .media-group, #medias > div[class*="media"]');
    if (groups.length) {
      groups.forEach((el) => {
        if (el.querySelector('video')) seq.push('video');
        else if (el.querySelector('img')) seq.push('image');
      });
    } else {
      doc.querySelectorAll('#medias video').forEach(() => seq.push('video'));
      doc.querySelectorAll('#medias img[src*="erome.com/i/"], #medias img[src*="/i/"]').forEach(() => seq.push('image'));
    }
    return seq.slice(0, 30);
  }

  function recordBrowseSnapshot(albumEl, doc, metrics) {
    if (!intelMeta.recordIntel) return;
    const link = albumEl.querySelector(SELECTORS.albumLink);
    if (!link?.href) return;
    const albumId = albumIdFromUrl(link.href);
    if (!albumId) return;
    const day = new Date().toISOString().slice(0, 10);
    const dedupeKey = albumId + ':' + day;
    const rows = loadIntelRows();
    if (rows.some((r) => (r.album_id + ':' + String(r.captured_at || '').slice(0, 10)) === dedupeKey)) return;

    const views = metrics.views ?? extractViews(albumEl);
    const likes = metrics.likes ?? extractLikes(albumEl);
    const videos = metrics.videos ?? extractVideos(albumEl);
    const images = metrics.images ?? extractImages(albumEl);
    let engagement_bps = 0;
    if (views && likes) engagement_bps = Math.round((likes / views) * 100000);

    const uploaded_at_approx_days_ago =
      metrics.uploaded_at_approx_days_ago ?? extractUploadedAgeDaysFromDoc(doc);
    const views_per_day_proxy =
      metrics.views_per_day_proxy ??
      (views && uploaded_at_approx_days_ago ? Math.round((views / uploaded_at_approx_days_ago) * 10) / 10 : null);
    const uploader = metrics.uploader ?? extractUploaderFromDoc(doc);
    const is_uploader_verified =
      metrics.is_uploader_verified ?? (uploader ? extractIsVerifiedFromDoc(doc) : null);
    const media_sequence = metrics.media_sequence ?? extractMediaSequenceFromDoc(doc);

    const row = {
      platform: 'erome',
      captured_at: new Date().toISOString(),
      album_url: link.href,
      album_id: albumId,
      entity_id: albumId,
      entity_url: link.href,
      page_context: pageContext(),
      views,
      likes,
      videos,
      images,
      total_duration_sec: metrics.total_duration_sec || extractDuration(albumEl),
      avg_duration_sec: metrics.avg_duration_sec || extractAvgDuration(albumEl),
      longest_clip_sec: metrics.longest_clip_sec || extractLongestClip(albumEl),
      title: metrics.title || extractTitleFromDoc(doc),
      tags: metrics.tags || extractTagsFromDoc(doc),
      format_bucket: formatBucket(videos, images),
      engagement_bps,
      uploaded_at_approx_days_ago,
      views_per_day_proxy,
      uploader,
      is_uploader_verified,
      media_sequence,
    };
    // Duration-band tags help AOF pool mapping without inventing new schema fields.
    const longest = Number(row.longest_clip_sec) || Number(row.total_duration_sec) || 0;
    const tagList = Array.isArray(row.tags) ? row.tags : [];
    if (longest > 0) {
      let band = 'dur_20m_plus';
      if (longest < 180) band = 'dur_0_3m';
      else if (longest < 600) band = 'dur_3_10m';
      else if (longest < 1200) band = 'dur_10_20m';
      if (!tagList.includes(band)) row.tags = [...tagList, band].slice(0, 30);
    } else {
      row.tags = tagList;
    }
    rows.push(row);
    saveIntelRows(rows);
    updateIntelCountBadge({ pulse: true });
    try {
      window.dispatchEvent(new CustomEvent("tbcc-erome-intel-row", { detail: { row, count: rows.length } }));
    } catch (_) {}
  }

  function exportIntelJsonl() {
    const rows = loadIntelRows();
    const name = `erome-browse-intel-${new Date().toISOString().slice(0, 10)}.jsonl`;
    if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.exportJsonlSaveAs === 'function') {
      void globalThis.tbccBrowseIntel.exportJsonlSaveAs(rows, name).then((r) => {
        showEeToast(r && r.ok !== false ? `Save As · ${name}` : 'Export failed');
      });
      return;
    }
    const blob = new Blob([rows.map((r) => JSON.stringify(r)).join('\n') + (rows.length ? '\n' : '')], { type: 'application/jsonl' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function pushIntelToTbcc() {
    const rows = loadIntelRows();
    if (!rows.length) {
      alert('No intel rows to push.');
      return;
    }
    const url = (intelMeta.tbccApiUrl || '').trim().replace(/\/$/, '');
    try {
      if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.postIntelRows === 'function') {
        const resp = await globalThis.tbccBrowseIntel.postIntelRows(url, rows);
        const keep = Math.max(100, Math.floor(Math.max(500, intelMeta.maxIntelRows || 5000) * 0.2));
        saveIntelRows(rows.slice(-keep), { skipAutoPush: true });
        updateIntelCountBadge();
        alert(
          `Pushed ${resp.appended ?? rows.length} rows` +
            (resp.url ? ` via ${resp.url}` : '') +
            ` · kept ${Math.min(rows.length, keep)} local`
        );
        return;
      }
      if (!url) {
        alert('Set TBCC API URL in Intel settings (or Options → API base)');
        return;
      }
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows }),
      });
      const data = await res.json();
      alert(res.ok ? `Pushed ${data.appended ?? 0} rows (scanned ${data.scanned ?? rows.length})` : `Push failed: ${res.status}`);
    } catch (e) {
      alert('Push failed: ' + e.message);
    }
  }

  function clearIntelRows() {
    if (!confirm('Clear all browse intel rows?')) return;
    saveIntelRows([], { skipAutoPush: true });
    updateIntelCountBadge();
    alert('Browse intel cleared.');
  }

  function intelSummaryText() {
    const rows = loadIntelRows();
    const tagBuckets = {};
    const vpdBuckets = {};
    rows.forEach((r) => {
      (r.tags || []).forEach((t) => {
        if (r.views) {
          if (!tagBuckets[t]) tagBuckets[t] = [];
          tagBuckets[t].push(r.views);
        }
        if (r.views_per_day_proxy) {
          if (!vpdBuckets[t]) vpdBuckets[t] = [];
          vpdBuckets[t].push(r.views_per_day_proxy);
        }
      });
    });
    const median = (vals) => {
      vals.sort((a, b) => a - b);
      return vals[Math.floor(vals.length / 2)] || 0;
    };
    const rankedViews = Object.entries(tagBuckets)
      .map(([tag, vals]) => [tag, median(vals)])
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
    const rankedVpd = Object.entries(vpdBuckets)
      .map(([tag, vals]) => [tag, median(vals)])
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
    let out = `Rows: ${rows.length}\nTop tags (median views):\n`;
    out += rankedViews.map(([t, v]) => `  ${t}: ${v}`).join('\n') || '  (none yet)';
    out += '\n\nTop tags (median views/day proxy):\n';
    out += rankedVpd.map(([t, v]) => `  ${t}: ${v}`).join('\n') || '  (need age data — browse album pages)';
    return out;
  }


  const SELECTORS = {
    albums: '#albums',
    albumLink: '.album-link, a[href*="/a/"]',
    albumThumbnail: '.album-thumbnail-container',
    albumBottomRight: '.album-bottom-right',
    albumVideos: '.album-videos',
    albumImages: '.album-images',
    albumViews: '.album-bottom-views',
    tabs: '#tabs',
    page: '#page',
  };

  // State
  let settings = loadSettings();
  let viewedAlbums = loadViewed();
  let currentPage = 1;
  let loading = false;
  const MAX_PAGES = 100;
  let lastSort = null;
  let pendingFetches = 0;
  let processingQueue = false;

  // Inject CSS once
  const CSS = `
    .ee-duration-badge, .ee-watched-badge, .ee-deleted-overlay {
      position: absolute;
      pointer-events: none;
    }
    .ee-duration-badge {
      top: 8px;
      right: 8px;
      background: rgba(0, 0, 0, 0.85);
      color: white;
      padding: 4px 8px;
      border-radius: 4px;
      font-weight: 600;
      z-index: 12;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4);
      line-height: 1.2;
      font-size: 11px;
    }
    .ee-watched-overlay {
      top: 0; left: 0; right: 0; bottom: 0;
      width: 100%; height: 100%;
      background: rgba(0, 0, 0, 0.5);
      z-index: 10;
    }
    .ee-watched-badge {
      top: 8px;
      left: 8px;
      background: rgba(235, 99, 149, 0.9);
      color: white;
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.5px;
      z-index: 11;
      box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    .ee-album-actions {
      position: absolute;
      left: 8px;
      bottom: 8px;
      z-index: 20;
      display: flex;
      gap: 6px;
      pointer-events: auto;
    }
    .ee-album-actions .ee-act {
      border: none;
      border-radius: 999px;
      min-width: 36px;
      height: 36px;
      cursor: pointer;
      background: rgba(0,0,0,.72);
      color: #fff;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 2px 8px rgba(0,0,0,.45);
      font-size: 14px;
      line-height: 1;
      padding: 0 8px;
      gap: 3px;
    }
    .ee-album-actions .ee-act:hover { background: rgba(235,99,149,.95); }
    .ee-album-actions .ee-act.on { background: #eb6395; }
    .ee-album-actions .ee-act:disabled { opacity: .55; cursor: wait; }
    .ee-album-actions .ee-act .ee-act-n {
      font-size: 10px; font-weight: 700; max-width: 32px; overflow: hidden;
    }
    .ee-toast {
      position: fixed; z-index: 1000001; left: 50%; bottom: 24px; transform: translateX(-50%);
      background: rgba(20,20,20,.94); color: #eee; border: 1px solid #444; border-radius: 8px;
      padding: 10px 14px; font: 13px/1.3 system-ui, sans-serif; pointer-events: none;
      box-shadow: 0 8px 24px rgba(0,0,0,.4);
    }
    .ee-vid-bridge {
      margin: 8px 0 12px; padding: 8px 10px; background: #2a2a2a; border: 1px solid #444;
      border-radius: 8px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
      font: 12px/1.3 system-ui, sans-serif; color: #ddd;
    }
    .ee-vid-bridge a.ee-vid-src {
      color: #7ec8e3; word-break: break-all; max-width: 100%;
    }
    .ee-vid-bridge .ee-vid-actions { display: flex; flex-wrap: wrap; gap: 6px; }
    .ee-vid-bridge button {
      background: #333; color: #eee; border: 1px solid #555; border-radius: 6px;
      padding: 5px 10px; cursor: pointer; font-weight: 600;
    }
    .ee-vid-bridge button.ee-tv { background: #eb6395; border-color: #eb6395; color: #fff; }
    .ee-vid-bridge button:hover { filter: brightness(1.08); }
    #ee-title-filter-bar {
      position: fixed; z-index: 99990; left: 12px; bottom: 16px;
      display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
      max-width: min(520px, calc(100vw - 24px));
      padding: 10px 12px; background: rgba(30,30,30,.94); color: #ddd;
      border: 1px solid #444; border-radius: 10px;
      box-shadow: 0 8px 24px rgba(0,0,0,.45); font: 12px/1.3 system-ui, sans-serif;
    }
    #ee-title-filter-bar label { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 140px; color: #aaa; }
    #ee-title-filter-bar input {
      background: #222; border: 1px solid #555; color: #eee; border-radius: 6px;
      padding: 6px 8px; width: 100%;
    }
    #ee-title-filter-bar .ee-tf-hint { width: 100%; color: #777; font-size: 11px; }
    #ee-title-filter-bar button {
      background: #333; color: #eee; border: 1px solid #555; border-radius: 6px;
      padding: 6px 10px; cursor: pointer; align-self: flex-end;
    }
    .album.ee-title-filtered { display: none !important; }
    .ee-deleted-overlay {
      top: 0; left: 0; right: 0; bottom: 0;
      width: 100%; height: 100%;
      background: rgba(0, 0, 0, 0.7);
      z-index: 15;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: opacity 0.3s ease;
    }
    .ee-page-separator {
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 30px 0;
      height: 40px;
      width: 100%;
      clear: both;
      grid-column: 1 / -1;
    }
    #eromeSortControls {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 8px;
      margin: 16px 0;
      max-width: 900px;
    }
    #eromeSortControls button {
      padding: 8px 12px;
      font-size: 14px;
      font-weight: 600;
      border: 1px solid #d0d0d0;
      border-radius: 6px;
      cursor: pointer;
      background: #fff;
      color: #333;
      transition: all 0.2s ease;
      white-space: nowrap;
      min-width: 120px;
      text-align: center;
    }
    #eromeSortControls button:hover {
      background: #f6f6f6;
      transform: translateY(-1px);
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .settings-section { margin-bottom: 25px; }
    .section-header {
      font-weight: 600; color: #eb6395; font-size: 15px;
      margin-bottom: 15px; padding-bottom: 8px;
      border-bottom: 2px solid #444; display: flex; align-items: center;
    }
    .section-content { padding-left: 10px; }
    .form-group { margin-bottom: 20px; }
    .control-label {
      display: block; margin-bottom: 8px;
      font-size: 14px; font-weight: 500; color: #ddd;
    }
    .form-control {
      background: #444; border: 1px solid #555; color: #fff;
      border-radius: 6px; font-size: 14px; transition: all 0.3s ease;
    }
    .form-control:focus {
      border-color: #eb6395;
      box-shadow: 0 0 0 3px rgba(235, 99, 149, 0.2);
      background: #444; color: #fff; outline: none;
    }
    .checkbox { margin-bottom: 12px; }
    .checkbox label {
      display: flex; align-items: center; font-size: 14px;
      color: #ddd; cursor: pointer; transition: color 0.2s ease;
    }
    .checkbox label:hover { color: #fff; }
    .checkbox input[type="checkbox"] {
      margin-right: 10px; transform: scale(1.2); accent-color: #eb6395;
    }
    .btn {
      border-radius: 6px; font-size: 13px; padding: 10px 18px;
      transition: all 0.3s ease; border: none; cursor: pointer; font-weight: 500;
    }
    .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.4); }
    .ee-action-buttons {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 10px; margin-top: 20px; padding-top: 15px; border-top: 1px solid #444;
    }
    .ee-action-btn { width: 100%; white-space: nowrap; }
    #clearViewed { background: #555 !important; border-color: #666 !important; color: #ccc !important; }
    #clearViewed:hover { background: #666 !important; border-color: #777 !important; }
    #resetDurationFilter { border: 1px solid #eb6395 !important; color: #eb6395 !important; background: transparent !important; }
    #resetDurationFilter:hover { background: rgba(235, 99, 149, 0.15) !important; box-shadow: 0 4px 12px rgba(235, 99, 149, 0.2) !important; }
    #saveEnhancer:hover { background: #d85585 !important; border-color: #d85585 !important; box-shadow: 0 6px 16px rgba(235, 99, 149, 0.4) !important; }
    .modal-content { border-radius: 4px; box-shadow: 0 15px 40px rgba(0,0,0,0.6); border: 1px solid #444; }
    .modal-header { background: linear-gradient(135deg, #2b2b2b 0%, #333 100%); }
    .modal-body { background: linear-gradient(135deg, #2b2b2b 0%, #2f2f2f 100%); }
    /* Keep settings scrollable so Summary never clips under the footer */
    #enhancerModal .modal-dialog { margin: 24px auto; max-width: 640px; }
    #enhancerModal .modal-content { max-height: calc(100vh - 48px); display: flex; flex-direction: column; }
    #enhancerModal .modal-body {
      overflow-y: auto; max-height: none; flex: 1 1 auto;
      -webkit-overflow-scrolling: touch;
    }
    #enhancerModal .modal-footer { flex-shrink: 0; }
    #intelSummaryBox {
      display: none; margin-top: 12px; padding: 12px 14px;
      max-height: min(220px, 28vh); overflow: auto;
      background: #1a1a1a !important; color: #f0f0f0 !important;
      border: 1px solid #555; border-left: 3px solid #eb6395;
      border-radius: 6px; font: 12px/1.45 Consolas, Menlo, Monaco, monospace;
      white-space: pre-wrap; word-break: break-word;
      box-shadow: inset 0 0 0 1px rgba(0,0,0,.35);
    }
    #intelSummaryBox::-webkit-scrollbar { width: 8px; height: 8px; }
    #intelSummaryBox::-webkit-scrollbar-thumb { background: #555; border-radius: 4px; }
    #intelSummaryBox::-webkit-scrollbar-track { background: #222; }
  `;

  // Inject CSS
  const styleEl = document.createElement('style');
  styleEl.textContent = CSS;
  document.head.appendChild(styleEl);

  /* ---------- Storage ---------- */
  function loadSettings() {
    try {
      return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'));
    } catch {
      return Object.assign({}, DEFAULTS);
    }
  }
  function saveSettings() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  }
  function loadViewed() {
    try {
      return JSON.parse(localStorage.getItem(VIEWED_KEY) || '[]');
    } catch {
      return [];
    }
  }
  function saveViewed() {
    localStorage.setItem(VIEWED_KEY, JSON.stringify(viewedAlbums));
  }
  function clearViewed() {
    viewedAlbums = [];
    saveViewed();
    alert('Viewed albums cleared!');
    location.reload();
  }

  /* ---------- Utilities ---------- */
  function parseDurationText(text) {
    if (!text) return 0;
    const parts = text.trim().split(':').map(Number);
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    return Number(parts[0]) || 0;
  }

  function fixLazyImages(root = document) {
    root.querySelectorAll('img').forEach(img => {
      if (img.dataset.src) img.src = img.dataset.src;
      if (img.dataset.srcset) img.srcset = img.dataset.srcset;
      if (img.getAttribute('data-src')) img.src = img.getAttribute('data-src');
      if (img.getAttribute('data-srcset')) img.srcset = img.getAttribute('data-srcset');
      img.classList.remove('lazy', 'lazyload', 'lozad');
    });
  }

  function parseAbbrevNumber(text) {
    // Shared helper: comma-as-decimal with K/M ("4,7M" ≠ "47M").
    if (typeof globalThis.tbccParseAbbrevNumber === 'function') {
      return globalThis.tbccParseAbbrevNumber(text);
    }
    if (!text) return 0;
    const t = String(text).replace(/\s+/g, ' ').trim();
    const m = t.match(/(\d[\d.,]*)(\s*[KMB])?/i);
    if (!m) return 0;
    let raw = m[1];
    const unit = (m[2] || '').trim().toUpperCase();
    if (unit) {
      raw = raw.replace(/,/g, '.');
      const parts = raw.split('.');
      if (parts.length > 2) raw = parts[0] + '.' + parts.slice(1).join('');
    } else {
      raw = raw.replace(/,/g, '');
      if (/^\d{1,3}(\.\d{3})+$/.test(raw)) raw = raw.replace(/\./g, '');
      else raw = raw.replace(/\.(?=.*\.)/g, '');
    }
    const num = parseFloat(raw);
    if (!isFinite(num)) return 0;
    if (unit === 'K') return Math.round(num * 1e3);
    if (unit === 'M') return Math.round(num * 1e6);
    if (unit === 'B') return Math.round(num * 1e9);
    return Math.round(num);
  }

  function formatDuration(seconds) {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hrs > 0) return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  /* ---------- Extraction Functions (Consolidated) ---------- */
  function extractMetric(album, metricName, extractFn) {
    const cacheKey = `_${metricName}Parsed`;
    if (album.dataset[cacheKey]) return +album.dataset[cacheKey];
    const value = extractFn(album);
    album.dataset[cacheKey] = String(value);
    return value;
  }

  function extractViews(album) {
    return extractMetric(album, 'views', (a) => {
      const viewsEl = a.querySelector(SELECTORS.albumViews);
      if (viewsEl) {
        const text = viewsEl.textContent.replace(/\s*views?\s*/i, '').trim();
        const v = parseAbbrevNumber(text);
        if (v) return v;
      }
      const dataEl = a.querySelector('[data-views],[data-view],[data-count-views]');
      if (dataEl) {
        const val = dataEl.getAttribute('data-views') || dataEl.getAttribute('data-view') || dataEl.getAttribute('data-count-views');
        return parseAbbrevNumber(val);
      }
      const icon = a.querySelector('.fa-eye:not(.fa-eye-slash)');
      if (icon?.parentElement?.classList.contains('album-bottom-views')) {
        return parseAbbrevNumber(icon.parentElement.textContent.replace(/\s*views?\s*/i, '').trim());
      }
      return 0;
    });
  }

  function extractVideos(album) {
    return extractMetric(album, 'videos', (a) => {
      const videoSpan = a.querySelector(SELECTORS.albumVideos);
      if (videoSpan) {
        const clone = videoSpan.cloneNode(true);
        clone.querySelectorAll('.fa-heart, .pink').forEach(el => {
          if (el.classList.contains('fa-heart')) {
            el.previousElementSibling?.remove();
            el.remove();
          }
        });
        const match = clone.textContent.trim().match(/(\d+)/);
        if (match) return parseInt(match[1]);
      }
      const dataEl = a.querySelector('[data-videos],[data-video-count],[data-count-videos]');
      if (dataEl) {
        const val = dataEl.getAttribute('data-videos') || dataEl.getAttribute('data-video-count') || dataEl.getAttribute('data-count-videos');
        return parseAbbrevNumber(val);
      }
      const icon = a.querySelector('.fa-video,.fa-film');
      if (icon?.parentElement?.classList.contains('album-videos')) {
        const match = icon.parentElement.textContent.trim().match(/(\d+)/);
        if (match) return parseInt(match[1]);
      }
      return 0;
    });
  }

  function extractDuration(album) {
    return extractMetric(album, 'duration', (a) => {
      const totalDuration = a.dataset.totalVideoDuration;
      return totalDuration ? parseInt(totalDuration) : 0;
    });
  }

  function extractImages(album) {
    return extractMetric(album, 'images', (a) => {
      const imageSpan = a.querySelector(SELECTORS.albumImages);
      if (imageSpan) {
        const match = imageSpan.textContent.trim().match(/(\d+)/);
        if (match) return parseInt(match[1]);
      }
      const dataEl = a.querySelector('[data-images],[data-image-count],[data-count-images]');
      if (dataEl) {
        const val = dataEl.getAttribute('data-images') || dataEl.getAttribute('data-image-count') || dataEl.getAttribute('data-count-images');
        return parseAbbrevNumber(val);
      }
      return 0;
    });
  }

  function extractTotalItems(album) {
    return extractMetric(album, 'totalItems', (a) => extractVideos(a) + extractImages(a));
  }

  function extractLikes(album) {
    return extractMetric(album, 'likes', (a) => {
      const cached = a.dataset.likeCount;
      if (cached) return parseInt(cached) || 0;
      const likeEl = a.querySelector('.album-likes-display span:last-child');
      if (likeEl) return parseInt(likeEl.textContent.trim()) || 0;
      return 0;
    });
  }

  function extractAvgDuration(album) {
    return extractMetric(album, 'avgDuration', (a) => {
      const avg = a.dataset.avgVideoDuration;
      return avg ? parseInt(avg) : 0;
    });
  }

  function extractLongestClip(album) {
    return extractMetric(album, 'longestClip', (a) => {
      try {
        const durations = JSON.parse(a.dataset.videoDurations || '[]');
        return durations.length ? Math.max(...durations) : 0;
      } catch {
        return 0;
      }
    });
  }

  function extractEngagement(album) {
    return extractMetric(album, 'engagement', (a) => {
      const views = extractViews(a);
      const likes = extractLikes(a);
      if (!views || !likes) return 0;
      return Math.round((likes / views) * 100000);
    });
  }

  function extractUnwatched(album) {
    return extractMetric(album, 'unwatched', (a) => {
      const link = a.querySelector(SELECTORS.albumLink);
      if (!link?.href) return 0;
      return viewedAlbums.includes(link.href) ? 0 : 1;
    });
  }

  const SORT_HANDLERS = {
    views: extractViews,
    videos: extractVideos,
    images: extractImages,
    items: extractTotalItems,
    duration: extractDuration,
    avgDuration: extractAvgDuration,
    longest: extractLongestClip,
    likes: extractLikes,
    engagement: extractEngagement,
    unwatched: extractUnwatched,
  };

  function reapplyLastSort() {
    const fn = lastSort && SORT_HANDLERS[lastSort];
    if (fn) sortAlbums(fn);
    else resetAlbums();
  }

  /* ---------- Album Sorting (Consolidated) ---------- */
  function tagOriginalOrder(albums) {
    albums.forEach((a, i) => {
      if (!a.hasAttribute('data-original-index')) {
        a.setAttribute('data-original-index', String(i));
      }
    });
  }

  function sortOrResetAlbums(sortFn = null) {
    const container = document.querySelector(SELECTORS.albums);
    if (!container) return;
    
    const allChildren = Array.from(container.children);
    const albums = [];
    const separatorMap = new Map();
    
    allChildren.forEach((child, index) => {
      if (child.classList.contains('ee-page-separator')) {
        separatorMap.set(index, child);
      } else if (child.classList.contains('album')) {
        albums.push(child);
      }
    });
    
    if (!albums.length) return;
    tagOriginalOrder(albums);

    const sorted = sortFn ? [...albums].sort((a, b) => {
      const kb = sortFn(b), ka = sortFn(a);
      if (kb !== ka) return kb - ka;
      return (parseInt(a.getAttribute('data-original-index')) || 0) - (parseInt(b.getAttribute('data-original-index')) || 0);
    }) : [...albums].sort((a, b) => 
      (parseInt(a.getAttribute('data-original-index')) || 0) - (parseInt(b.getAttribute('data-original-index')) || 0)
    );

    container.innerHTML = '';
    let albumIndex = 0;
    for (let i = 0; i < allChildren.length; i++) {
      if (separatorMap.has(i)) {
        container.appendChild(separatorMap.get(i));
      } else if (albumIndex < sorted.length) {
        container.appendChild(sorted[albumIndex++]);
      }
    }
  }

  function sortAlbums(keyFnDesc) { sortOrResetAlbums(keyFnDesc); }
  function resetAlbums() { sortOrResetAlbums(); }

  function albumFormatBucket(albumEl) {
    const v = extractVideos(albumEl);
    const i = extractImages(albumEl);
    return formatBucket(v, i);
  }

  function isMixedAlbum(albumEl) {
    return albumFormatBucket(albumEl) === 'mixed_album';
  }

  function filterAlbumsByFormat(bucket) {
    const container = document.querySelector(SELECTORS.albums);
    if (!container) return 0;
    let shown = 0;
    container.querySelectorAll('.album').forEach((a) => {
      const match = !bucket || albumFormatBucket(a) === bucket;
      a.style.display = match ? '' : 'none';
      if (match) shown += 1;
    });
    return shown;
  }

  function clearAlbumFormatFilter() {
    const container = document.querySelector(SELECTORS.albums);
    if (!container) return;
    container.querySelectorAll('.album').forEach((a) => {
      a.style.display = '';
    });
  }

  /** Intel-driven action: keep mixed albums only, sort by likes (DOM on current search). */
  function applyShowMostLikedMixed() {
    const n = filterAlbumsByFormat('mixed_album');
    lastSort = 'likes_mixed';
    sortAlbums(extractLikes);
    return n;
  }

  let lastIntelDiscovery = null;

  function intelSummaryUrl() {
    try {
      const meta = JSON.parse(localStorage.getItem('eromeBrowseIntelMeta') || '{}');
      const base = String(meta.tbccApiUrl || 'http://127.0.0.1:8000/analytics/erome-browse-intel').trim();
      return base.replace(/\/?$/, '') + '/summary?days=30';
    } catch (_) {
      return 'http://127.0.0.1:8000/analytics/erome-browse-intel/summary?days=30';
    }
  }

  function renderIntelDiscoveryBanner(discovery) {
    const existing = document.getElementById('eromeIntelDiscovery');
    if (existing) existing.remove();
    if (!discovery || !Array.isArray(discovery.suite_actions) || !discovery.suite_actions.length) return;
    const action = discovery.suite_actions.find((a) => a && a.id === 'show_most_liked_mixed')
      || discovery.suite_actions[0];
    if (!action) return;
    const bar = document.getElementById('eromeSortControls');
    if (!bar || !bar.parentElement) return;
    const wrap = document.createElement('div');
    wrap.id = 'eromeIntelDiscovery';
    wrap.style.cssText =
      'margin:8px 0 4px;padding:10px 12px;border-radius:8px;background:#2a1520;border:1px solid #eb6395;' +
      'color:#fce7f3;font-size:13px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;';
    const ev = action.evidence || {};
    const lift = ev.lift_vs_runner_up != null ? ` · ${Math.round((ev.lift_vs_runner_up - 1) * 100)}% lift` : '';
    const n = ev.n != null ? ` · n=${ev.n}` : '';
    wrap.innerHTML =
      `<span style="flex:1;min-width:180px"><b>Intel discovery</b> — ${String(action.label || '').replace(/</g, '')}` +
      `<span style="opacity:.75;font-size:11px">${lift}${n} · ${String(discovery.preferred_metric || '')}</span></span>`;
    const go = document.createElement('button');
    go.type = 'button';
    go.textContent = 'Apply on this page';
    go.style.cssText =
      'background:#eb6395;color:#fff;border:0;border-radius:6px;padding:6px 12px;cursor:pointer;font-weight:600;';
    go.addEventListener('click', (e) => {
      e.preventDefault();
      const shown = applyShowMostLikedMixed();
      go.textContent = `Showing ${shown} mixed ♥`;
      const mixedBtn = document.getElementById('eromeSortByMixedLikes');
      if (mixedBtn) mixedBtn.style.outline = '2px solid #fff';
    });
    wrap.appendChild(go);
    bar.parentElement.insertBefore(wrap, bar);
  }

  async function refreshIntelDiscoveries() {
    if (location.pathname.startsWith('/a/')) return;
    try {
      let data = null;
      try {
        const meta = JSON.parse(localStorage.getItem('eromeBrowseIntelMeta') || '{}');
        const hint = String(meta.tbccApiUrl || '').trim();
        if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.fetchIntelSummary === 'function') {
          data = await globalThis.tbccBrowseIntel.fetchIntelSummary(hint, 30);
        }
      } catch (_) {}
      if (!data) return;
      lastIntelDiscovery = data.discoveries || data;
      renderIntelDiscoveryBanner(lastIntelDiscovery);
      const mixedBtn = document.getElementById('eromeSortByMixedLikes');
      if (mixedBtn && (data.preferred_format_bucket === 'mixed_album' ||
          (lastIntelDiscovery && lastIntelDiscovery.preferred_format_bucket === 'mixed_album'))) {
        mixedBtn.style.background = '#eb6395';
        mixedBtn.style.color = '#fff';
        mixedBtn.title = 'Ledger says mixed albums lead — tap to filter + sort by likes';
      }
    } catch (_) {
      /* API down — Mixed button still works from DOM */
    }
  }

  function addSortingControls() {
    if (!settings.enableSorting || location.pathname.startsWith('/a/')) return;
    const tabsContainer = document.querySelector(SELECTORS.tabs);
    if (!tabsContainer || document.getElementById('eromeSortControls')) return;

    const bar = document.createElement('div');
    bar.id = 'eromeSortControls';
    
    const buttons = [
      ['♥ Mixed', 'eromeSortByMixedLikes', () => {
        lastSort = 'likes_mixed';
        const n = applyShowMostLikedMixed();
        const btn = document.getElementById('eromeSortByMixedLikes');
        if (btn) btn.textContent = `♥ Mixed (${n})`;
      }],
      ['↓ Views', 'eromeSortByViews', () => { lastSort = 'views'; clearAlbumFormatFilter(); sortAlbums(extractViews); }],
      ['↓ Likes', 'eromeSortByLikes', () => { lastSort = 'likes'; clearAlbumFormatFilter(); sortAlbums(extractLikes); }],
      ['♥ Rate', 'eromeSortByEngagement', () => { lastSort = 'engagement'; clearAlbumFormatFilter(); sortAlbums(extractEngagement); }],
      ['↓ Videos', 'eromeSortByVideos', () => { lastSort = 'videos'; clearAlbumFormatFilter(); sortAlbums(extractVideos); }],
      ['↓ Images', 'eromeSortByImages', () => { lastSort = 'images'; clearAlbumFormatFilter(); sortAlbums(extractImages); }],
      ['↓ Items', 'eromeSortByItems', () => { lastSort = 'items'; clearAlbumFormatFilter(); sortAlbums(extractTotalItems); }],
      ['↓ Duration', 'eromeSortByDuration', () => { lastSort = 'duration'; clearAlbumFormatFilter(); sortAlbums(extractDuration); }],
      ['↓ Avg', 'eromeSortByAvgDuration', () => { lastSort = 'avgDuration'; clearAlbumFormatFilter(); sortAlbums(extractAvgDuration); }],
      ['↓ Longest', 'eromeSortByLongest', () => { lastSort = 'longest'; clearAlbumFormatFilter(); sortAlbums(extractLongestClip); }],
      ['★ New', 'eromeSortByUnwatched', () => { lastSort = 'unwatched'; clearAlbumFormatFilter(); sortAlbums(extractUnwatched); }],
      ['↺ Reset', 'eromeSortReset', () => {
        lastSort = null;
        clearAlbumFormatFilter();
        const mixedBtn = document.getElementById('eromeSortByMixedLikes');
        if (mixedBtn) mixedBtn.textContent = '♥ Mixed';
        resetAlbums();
      }],
    ];

    buttons.forEach(([text, id, handler]) => {
      const btn = document.createElement('button');
      btn.id = id;
      btn.textContent = text;
      btn.addEventListener('click', (e) => { e.preventDefault(); handler(); });
      bar.appendChild(btn);
    });

    tabsContainer.parentElement.insertBefore(bar, tabsContainer.nextSibling);
    setTimeout(() => refreshIntelDiscoveries(), 800);
  }

  /* ---------- Like Count & Duration Display ---------- */
  async function addLikeCount(albumEl) {
    if (albumEl.dataset.likesProcessed || location.pathname.startsWith('/a/') || !settings.showLikes) return;
    const link = albumEl.querySelector(SELECTORS.albumLink);
    if (!link) return;

    albumEl.dataset.likesProcessed = 'true';
    pendingFetches++;
    const albumIndex = pendingFetches;
    updateLoadingCount(pendingFetches);

    try {
      const response = await fetchWithRetry(link.href, albumIndex);
      const html = await response.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');

      if (doc.querySelector('h1')?.textContent.includes('Album deleted')) {
        markAsDeleted(albumEl);
        return;
      }

      let count = 0;
      try {
        const likeCountEl = doc.querySelector('#like_count');
        if (likeCountEl?.textContent) {
          count = likeCountEl.textContent.trim();
        } else {
          const heartIcon = doc.querySelector('.far.fa-heart.fa-lg');
          if (heartIcon?.nextElementSibling?.firstChild) {
            count = heartIcon.nextElementSibling.firstChild.textContent.trim();
          }
        }
        count = parseInt(count) || 0;
      } catch (likeErr) {
        count = 0;
      }
      albumEl.dataset.likeCount = String(count);
      delete albumEl.dataset._likesParsed;

      const videoDurations = [];
      doc.querySelectorAll('.duration').forEach(durEl => {
        const seconds = parseDurationText(durEl.textContent.trim());
        if (seconds > 0) videoDurations.push(seconds);
      });
      
      if (videoDurations.length > 0) {
        const totalSeconds = videoDurations.reduce((sum, dur) => sum + dur, 0);
        const avgSeconds = Math.round(totalSeconds / videoDurations.length);
        albumEl.dataset.videoDurations = JSON.stringify(videoDurations);
        albumEl.dataset.avgVideoDuration = avgSeconds;
        albumEl.dataset.totalVideoDuration = totalSeconds;
        
        addDurationDisplay(albumEl, totalSeconds, avgSeconds, videoDurations.length);
        
        if (settings.minVideoSeconds > 0 && avgSeconds < settings.minVideoSeconds) {
          albumEl.remove();
          return;
        }
      }


      recordBrowseSnapshot(albumEl, doc, {
        likes: count,
        videos: videoDurations.length,
        total_duration_sec: videoDurations.reduce((s, d) => s + d, 0),
        avg_duration_sec: videoDurations.length ? Math.round(videoDurations.reduce((s, d) => s + d, 0) / videoDurations.length) : 0,
        longest_clip_sec: videoDurations.length ? Math.max(...videoDurations) : 0,
        title: extractTitleFromDoc(doc),
        tags: extractTagsFromDoc(doc),
      });

      if (count > 0) {
        const bottomRight = albumEl.querySelector(SELECTORS.albumBottomRight);
        if (bottomRight) {
          const likeDisplay = document.createElement('span');
          likeDisplay.className = 'album-likes-display';
          likeDisplay.style.cssText = 'position:relative;display:inline-block;margin-left:4px;';
          likeDisplay.innerHTML = `<i class="fas fa-heart fa-lg" style="color:#eb6395;margin-right:4px;"></i><span style="font-weight:600;">${count}</span>`;
          bottomRight.appendChild(likeDisplay);
        }
        const nEl = albumEl.querySelector('.ee-like-n');
        if (nEl) nEl.textContent = String(count);
      }
    } catch (err) {
      if (err.message === 'ALBUM_DELETED') markAsDeleted(albumEl);
    } finally {
      pendingFetches--;
      updateLoadingCount(pendingFetches);
      if (pendingFetches === 0) {
        hideLoadingIndicator();
        processingQueue = false;
        if (lastSort && ['likes', 'engagement', 'duration', 'avgDuration', 'longest'].includes(lastSort)) {
          reapplyLastSort();
        }
      }
    }
  }

  function addDurationDisplay(albumEl, totalSeconds, avgSeconds, videoCount) {
    const container = albumEl.querySelector(SELECTORS.albumThumbnail);
    if (!container || container.querySelector('.ee-duration-badge')) return;
    if (!container.style.position || container.style.position === 'static') {
      container.style.position = 'relative';
    }
    const badge = document.createElement('div');
    badge.className = 'ee-duration-badge';
    badge.title = `${videoCount} video${videoCount > 1 ? 's' : ''}\nTotal: ${formatDuration(totalSeconds)}\nAverage: ${formatDuration(avgSeconds)}`;
    badge.innerHTML = `<div style="opacity: 0.9;"><i class="fa fa-clock" style="margin-right: 3px;"></i>${formatDuration(totalSeconds)}</div>${videoCount > 1 ? `<div style="font-size: 9px; opacity: 0.7; margin-top: 2px;">${videoCount} videos</div>` : ''}`;
    container.appendChild(badge);
  }

  function processLikesForAlbums(container = document) {
    if (location.pathname.startsWith('/a/') || !settings.showLikes) return;
    const albums = container.querySelectorAll('.album');
    if (albums.length === 0) return;
    
    showLoadingIndicator();
    processingQueue = true;
    albums.forEach((album, index) => {
      if (!album.dataset.likesProcessed) {
        setTimeout(() => addLikeCount(album), index * 100);
      }
    });
  }

  /* ---------- Grid Like / Repost (no album open) ---------- */
  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
  }

  function albumIdFromEl(albumEl) {
    const href =
      albumEl.querySelector(SELECTORS.albumLink)?.href ||
      albumEl.querySelector('a[href*="/a/"]')?.href ||
      '';
    return albumIdFromUrl(href);
  }

  function showEeToast(msg) {
    document.querySelectorAll('.ee-toast').forEach((el) => el.remove());
    const el = document.createElement('div');
    el.className = 'ee-toast';
    el.textContent = msg;
    document.documentElement.appendChild(el);
    setTimeout(() => el.remove(), 2800);
  }

  async function postAlbumLike(albumId) {
    const token = csrfToken();
    const res = await fetch(`/album/like/${encodeURIComponent(albumId)}`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRF-TOKEN': token,
      },
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  }

  async function postAlbumRepost(albumId) {
    const token = csrfToken();
    const res = await fetch('/album/repost', {
      method: 'POST',
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRF-TOKEN': token,
      },
      body: `id=${encodeURIComponent(albumId)}`,
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok || data.status === 'success', status: res.status, data };
  }

  function addAlbumActionButtons(albumEl) {
    if (!settings.gridLikeRepost || location.pathname.startsWith('/a/')) return;
    if (albumEl.dataset.eeActionsMounted) return;
    const thumb = albumEl.querySelector(SELECTORS.albumThumbnail);
    const albumId = albumIdFromEl(albumEl);
    if (!thumb || !albumId) return;
    albumEl.dataset.eeActionsMounted = '1';
    if (!thumb.style.position || thumb.style.position === 'static') {
      thumb.style.position = 'relative';
    }

    const wrap = document.createElement('div');
    wrap.className = 'ee-album-actions';
    wrap.innerHTML = `
      <button type="button" class="ee-act ee-like" title="Like" aria-label="Like">
        <i class="fas fa-heart"></i><span class="ee-act-n ee-like-n"></span>
      </button>
      <button type="button" class="ee-act ee-repost" title="Repost" aria-label="Repost">
        <i class="fas fa-retweet"></i><span class="ee-act-n ee-repost-n"></span>
      </button>
    `;

    const stop = (e) => {
      e.preventDefault();
      e.stopPropagation();
    };
    wrap.addEventListener('click', stop);
    wrap.addEventListener('mousedown', stop);

    const likeBtn = wrap.querySelector('.ee-like');
    const repostBtn = wrap.querySelector('.ee-repost');
    const likeN = wrap.querySelector('.ee-like-n');
    const repostN = wrap.querySelector('.ee-repost-n');

    // Seed count from existing display / dataset when available
    const seedLikes = albumEl.dataset.likeCount || albumEl.querySelector('.album-likes-display span:last-child')?.textContent;
    if (seedLikes && String(seedLikes).trim() !== '0') likeN.textContent = String(seedLikes).trim();

    likeBtn.addEventListener('click', async (e) => {
      stop(e);
      if (likeBtn.disabled) return;
      likeBtn.disabled = true;
      try {
        const { ok, status, data } = await postAlbumLike(albumId);
        if (status === 401 || data?.error === 'Unauthenticated.' || /login/i.test(data?.msg || '')) {
          showEeToast('Sign in to Erome to like albums');
          return;
        }
        if (!ok && data?.error) {
          showEeToast(String(data.error));
          return;
        }
        likeBtn.classList.add('on');
        const next =
          data?.likes ??
          data?.count ??
          data?.like_count ??
          (parseInt(likeN.textContent || albumEl.dataset.likeCount || '0', 10) || 0) + 1;
        likeN.textContent = String(next);
        albumEl.dataset.likeCount = String(next);
        const disp = albumEl.querySelector('.album-likes-display span:last-child');
        if (disp) disp.textContent = String(next);
        showEeToast(data?.msg || 'Liked');
      } catch (err) {
        showEeToast('Like failed');
        console.warn('[EE] like failed', err);
      } finally {
        likeBtn.disabled = false;
      }
    });

    repostBtn.addEventListener('click', async (e) => {
      stop(e);
      if (repostBtn.disabled) return;
      repostBtn.disabled = true;
      try {
        const { ok, data } = await postAlbumRepost(albumId);
        if (data?.status === 'error' || /login|register/i.test(data?.msg || '')) {
          showEeToast(data?.msg || 'Sign in to Erome to repost');
          return;
        }
        if (!ok && data?.status !== 'success') {
          showEeToast(data?.msg || 'Repost failed');
          return;
        }
        repostBtn.classList.add('on');
        const n = parseInt(repostN.textContent || '0', 10) || 0;
        repostN.textContent = String(n + 1);
        showEeToast(data?.msg || 'Reposted');
      } catch (err) {
        showEeToast('Repost failed');
        console.warn('[EE] repost failed', err);
      } finally {
        repostBtn.disabled = false;
      }
    });

    thumb.appendChild(wrap);
  }

  function processAlbumActions(container = document) {
    if (location.pathname.startsWith('/a/') || settings.gridLikeRepost === false) return;
    container.querySelectorAll('.album').forEach((album) => addAlbumActionButtons(album));
  }

  /* ---------- Rate Limit Handling ---------- */
  async function fetchWithRetry(url, albumIndex, maxRetries = 5, initialDelay = 2000) {
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const response = await fetch(url);
        if (response.status === 404 || response.status === 410) throw new Error('ALBUM_DELETED');
        if (response.status === 429) {
          await new Promise(resolve => setTimeout(resolve, initialDelay * Math.pow(2, attempt)));
          continue;
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        return response;
      } catch (err) {
        if (err.message === 'ALBUM_DELETED' || attempt === maxRetries - 1) throw err;
        await new Promise(resolve => setTimeout(resolve, initialDelay * Math.pow(2, attempt)));
      }
    }
  }

  function showLoadingIndicator() {
    if (document.getElementById('ee-loading-indicator')) return;
    const indicator = document.createElement('div');
    indicator.id = 'ee-loading-indicator';
    indicator.innerHTML = `<div style="position: fixed;bottom: 20px;right: 20px;background: rgba(235, 99, 149, 0.95);color: white;padding: 12px 20px;border-radius: 8px;box-shadow: 0 4px 12px rgba(0,0,0,0.3);z-index: 9999;display: flex;align-items: center;gap: 12px;font-weight: 600;font-size: 14px;"><div style="width: 20px;height: 20px;border: 3px solid rgba(255,255,255,0.3);border-top-color: white;border-radius: 50%;animation: spin 0.8s linear infinite;"></div><span>Loading album data...</span><span id="ee-loading-count" style="background: rgba(255,255,255,0.2);padding: 2px 8px;border-radius: 4px;font-size: 12px;">0</span></div>`;
    document.body.appendChild(indicator);
  }

  function updateLoadingCount(count) {
    const countEl = document.getElementById('ee-loading-count');
    if (countEl) countEl.textContent = count;
  }

  function hideLoadingIndicator() {
    document.getElementById('ee-loading-indicator')?.remove();
  }

  /* ---------- Overlay Creation (Consolidated) ---------- */
  function createOverlay(type, albumEl) {
    const container = albumEl.querySelector(SELECTORS.albumThumbnail);
    if (!container || container.querySelector(`.ee-${type}-overlay`)) return;
    if (!container.style.position || container.style.position === 'static') {
      container.style.position = 'relative';
    }

    const overlay = document.createElement('div');
    overlay.className = `ee-${type}-overlay`;
    
    if (type === 'watched') {
      const badge = document.createElement('div');
      badge.className = 'ee-watched-badge';
      badge.textContent = 'WATCHED';
      container.appendChild(overlay);
      container.appendChild(badge);
    } else if (type === 'deleted') {
      const link = container.querySelector('a');
      if (link) {
        link.addEventListener('click', (e) => e.preventDefault());
        link.style.cursor = 'default';
      }
      const message = document.createElement('div');
      message.style.cssText = 'background: rgba(235, 99, 149, 0.95);color: white;padding: 12px 20px;border-radius: 8px;font-size: 14px;font-weight: 700;letter-spacing: 0.5px;box-shadow: 0 4px 12px rgba(0,0,0,0.5);text-align: center;line-height: 1.4;';
      message.innerHTML = `<i class="fa fa-trash" style="display: block; font-size: 24px; margin-bottom: 8px;"></i>ALBUM DELETED`;
      overlay.appendChild(message);
      container.appendChild(overlay);
      container.addEventListener('mouseenter', () => overlay.style.opacity = '0');
      container.addEventListener('mouseleave', () => overlay.style.opacity = '1');
      const thumbnail = container.querySelector('img');
      if (thumbnail) thumbnail.style.filter = 'grayscale(50%) brightness(0.7)';
    }
  }

  function markAsViewed(albumEl) { createOverlay('watched', albumEl); }
  function markAsDeleted(albumEl) { createOverlay('deleted', albumEl); }

  /* ---------- Grid Filtering ---------- */
  function parseTitleKeywords(raw) {
    return String(raw || '')
      .toLowerCase()
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function albumTitleText(albumEl) {
    const link = albumEl.querySelector(SELECTORS.albumLink) || albumEl.querySelector('a');
    const bits = [
      link?.getAttribute('title'),
      albumEl.querySelector('.album-title, .album-bottom-title, .title')?.textContent,
      albumEl.querySelector('img')?.getAttribute('alt'),
      link?.textContent,
    ];
    return bits
      .map((b) => String(b || '').trim())
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
  }

  function matchesTitleKeywords(albumEl) {
    const title = albumTitleText(albumEl);
    const exclude = parseTitleKeywords(settings.titleExclude);
    if (exclude.some((k) => title.includes(k))) return false;
    const include = parseTitleKeywords(settings.titleInclude);
    if (include.length && !include.every((k) => title.includes(k))) return false;
    return true;
  }

  function matchesFilter(albumEl) {
    const videoSpan = albumEl.querySelector(SELECTORS.albumVideos);
    const imageSpan = albumEl.querySelector(SELECTORS.albumImages);
    const vCount = videoSpan ? Number((videoSpan.textContent.match(/(\d+)/) || [0])[0]) : 0;
    const iCount = imageSpan ? Number((imageSpan.textContent.match(/(\d+)/) || [0])[0]) : 0;
    const anchor = albumEl.querySelector('a');
    const url = anchor?.href;

    if (settings.hideViewed && url && viewedAlbums.includes(url)) return false;
    if (!matchesTitleKeywords(albumEl)) return false;

    switch (settings.filterMode) {
      case 'videos':
        return vCount > 0;
      case 'images':
        return iCount > 0 && vCount === 0;
      default:
        return true;
    }
  }

  function applyTitleKeywordVisibility() {
    const container = document.querySelector(SELECTORS.albums);
    if (!container) return;
    container.querySelectorAll('.album').forEach((album) => {
      const ok = matchesFilter(album);
      album.classList.toggle('ee-title-filtered', !ok);
      if (ok) {
        fixLazyImages(album);
        markAlbumClick(album);
      }
    });
  }
  window.__tbccEromeApplyTitleKeywords = applyTitleKeywordVisibility;

  function markAlbumClick(albumEl) {
    const link = albumEl.querySelector('a');
    if (!link || link.dataset.eeBound) return;
    link.dataset.eeBound = '1';

    if (viewedAlbums.includes(link.href)) markAsViewed(albumEl);

    link.addEventListener('mousedown', (event) => {
      if (event.button === 0 || event.button === 1) {
        if (!viewedAlbums.includes(link.href)) {
          viewedAlbums.push(link.href);
          saveViewed();
          markAsViewed(albumEl);
        }
      }
    });
  }

  function applyInitialFilter() {
    const container = document.querySelector(SELECTORS.albums);
    if (!container) return;
    const albums = Array.from(container.querySelectorAll('.album'));
    tagOriginalOrder(albums);
    albums.forEach((album) => {
      if (!matchesFilter(album)) {
        album.classList.add('ee-title-filtered');
      } else {
        album.classList.remove('ee-title-filtered');
        fixLazyImages(album);
        markAlbumClick(album);
      }
    });
  }

  function mountTitleFilterBar() {
    if (location.pathname.startsWith('/a/') || document.getElementById('ee-title-filter-bar')) return;
    if (!document.querySelector(SELECTORS.albums)) return;

    const bar = document.createElement('div');
    bar.id = 'ee-title-filter-bar';
    bar.innerHTML = `
      <label>Include (all must match)<input type="text" id="eeTitleInclude" placeholder="e.g. milf blonde" autocomplete="off"></label>
      <label>Exclude (hide if any)<input type="text" id="eeTitleExclude" placeholder="e.g. gay" autocomplete="off"></label>
      <button type="button" id="eeTitleFilterClear">Clear</button>
      <div class="ee-tf-hint">Refines album titles on this grid (space/comma separated). Does not change Erome’s search URL.</div>
    `;
    document.body.appendChild(bar);

    const includeEl = bar.querySelector('#eeTitleInclude');
    const excludeEl = bar.querySelector('#eeTitleExclude');
    includeEl.value = settings.titleInclude || '';
    excludeEl.value = settings.titleExclude || '';

    let t = null;
    const applyLive = () => {
      settings.titleInclude = includeEl.value.trim();
      settings.titleExclude = excludeEl.value.trim();
      saveSettings();
      applyTitleKeywordVisibility();
    };
    const onInput = () => {
      clearTimeout(t);
      t = setTimeout(applyLive, 250);
    };
    includeEl.addEventListener('input', onInput);
    excludeEl.addEventListener('input', onInput);
    bar.querySelector('#eeTitleFilterClear').addEventListener('click', () => {
      includeEl.value = '';
      excludeEl.value = '';
      applyLive();
    });
  }

  /* ---------- Infinite Scroll ---------- */
  function createPageSeparator(pageNum) {
    const separator = document.createElement('div');
    separator.className = 'ee-page-separator';
    separator.dataset.pageNumber = pageNum;
    separator.innerHTML = `<div style="flex: 1;height: 2px;background: linear-gradient(to right, transparent, #444, #444, transparent);"></div><div style="padding: 8px 20px;background: #2b2b2b;border: 2px solid #444;border-radius: 20px;margin: 0 15px;font-weight: 600;color: #eb6395;font-size: 14px;white-space: nowrap;"><i class="fa fa-arrow-down" style="margin-right: 8px;"></i>Page ${pageNum}<i class="fa fa-arrow-down" style="margin-left: 8px;"></i></div><div style="flex: 1;height: 2px;background: linear-gradient(to left, transparent, #444, #444, transparent);"></div>`;
    return separator;
  }

  function setupInfiniteScroll() {
    disableNativeInfiniteScroll();
    let scrollLocked = false;
    window.addEventListener('scroll', () => {
      if (!settings.autoScroll || scrollLocked || processingQueue || pendingFetches > 0) return;
      if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 500) {
        scrollLocked = true;
        loadNextPage().finally(() => setTimeout(() => scrollLocked = false, 1000));
      }
    });
  }

  function disableNativeInfiniteScroll() {
    if (typeof $ === 'function') {
      const $page = $(SELECTORS.page);
      try {
        if ($page.data('infiniteScroll')) $page.infiniteScroll('destroy');
      } catch (e) {}
      $page.off('append.infiniteScroll load.infiniteScroll request.infiniteScroll last.infiniteScroll error.infiniteScroll append');
    }
    if (typeof window.InfiniteScroll !== 'undefined') {
      window.InfiniteScroll = function() {
        return { destroy: () => {}, on: () => {}, off: () => {}, loadNextPage: () => {} };
      };
    }
    if (typeof $ === 'function' && $.fn) {
      $.fn.infiniteScroll = function() { return this; };
    }
    setTimeout(() => {
      const infiniteScrollScript = Array.from(document.querySelectorAll('script')).find(script => 
        script.textContent.includes('infiniteScroll') || script.textContent.includes('infinite-scroll') || script.textContent.includes('.infiniteScroll(')
      );
      if (infiniteScrollScript) infiniteScrollScript.remove();
    }, 100);
  }

  async function loadNextPage() {
    if (loading || currentPage >= MAX_PAGES || processingQueue || pendingFetches > 0) return;
    
    loading = true;
    const nextPage = currentPage + 1;
    const path = location.pathname;
    let url = `?page=${nextPage}`;
    if (path.startsWith('/explore')) url = `/explore?page=${nextPage}`;
    else if (path.startsWith('/search')) {
      const p = new URLSearchParams(location.search);
      p.set('page', nextPage);
      url = `/search?${p.toString()}`;
    } else if (path.startsWith('/user/feed')) url = `/user/feed?page=${nextPage}`;
    else if (path.startsWith('/user/liked')) url = `/user/liked?page=${nextPage}`;
    else if (path.startsWith('/user/saved')) url = `/user/saved?page=${nextPage}`;
    else if (/^\/[^/]+$/.test(path)) url = `${path}?page=${nextPage}`;

    try {
      const res = await fetchWithRetry(url, `Page${nextPage}`);
      const html = await res.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      fixLazyImages(doc);
      doc.querySelectorAll('.suggested-users, .col-sm-12:has(h2)').forEach(el => el.remove());
      
      const newAlbums = doc.querySelectorAll('.album');
      const container = document.querySelector(SELECTORS.albums);
      
      if (container && newAlbums.length > 0) {
        const frag = document.createDocumentFragment();
        frag.appendChild(createPageSeparator(nextPage));
        
        let addedCount = 0;
        newAlbums.forEach(n => {
          const clone = document.importNode(n, true);
          if (matchesFilter(clone)) {
            fixLazyImages(clone);
            clone.setAttribute('data-original-index', String(container.querySelectorAll('.album').length));
            frag.appendChild(clone);
            addedCount++;
          }
        });
        
        container.appendChild(frag);
        
        setTimeout(() => {
          document.querySelectorAll('.separator .bubble-mobile').forEach(bubble => {
            if (bubble.href?.includes('/o/')) bubble.closest('.separator')?.remove();
          });
          document.querySelectorAll('.suggested-users').forEach(el => el.remove());
        }, 100);
        
        const addedAlbums = Array.from(container.querySelectorAll('.album')).slice(-addedCount);
        addedAlbums.forEach(album => markAlbumClick(album));
        processAlbumActions(container);
        
        showLoadingIndicator();
        processingQueue = true;
        addedAlbums.forEach((album, index) => setTimeout(() => addLikeCount(album), index * 100));
        
        return new Promise((resolve) => {
          const waitForProcessing = setInterval(() => {
            if (!processingQueue && pendingFetches === 0) {
              clearInterval(waitForProcessing);
              reapplyLastSort();
              currentPage = nextPage;
              loading = false;
              resolve();
            }
          }, 500);
        });
      } else {
        currentPage = nextPage;
        loading = false;
      }
    } catch (err) {
      loading = false;
    }
  }

  /* ---------- Album Pages ---------- */
  function getMediaGroups() {
    return Array.from(document.querySelectorAll('.media-group, .album-media, [class*="media"]'));
  }

  function isVideoGroup(g) {
    return !!(g.querySelector('.duration, video, [class*="video"], .fa-video'));
  }

  function getGroupDurationSeconds(g) {
    let durationText = '';
    const durationEl = g.querySelector('.duration');
    if (durationEl) durationText = durationEl.textContent || durationEl.innerText || '';
    if (!durationText && g.dataset.duration) durationText = g.dataset.duration;
    if (!durationText && g.getAttribute('data-duration')) durationText = g.getAttribute('data-duration');
    if (!durationText) {
      const durationMatch = g.innerHTML.match(/(\d{1,2}):(\d{2})(?::(\d{2}))?/);
      if (durationMatch) durationText = durationMatch[0];
    }
    return parseDurationText(durationText.trim());
  }

  function updateHiddenCounter(n) {
    const num = document.getElementById('eeCountNum');
    if (num) num.textContent = String(n);
  }

  function applyAlbumEnhancements() {
    if (!location.pathname.startsWith('/a/')) return;
    const groups = getMediaGroups();
    if (!groups.length) {
      updateHiddenCounter(0);
      publishAlbumVideoUrls();
      return;
    }
    let hidden = 0;
    groups.forEach(g => {
      if (isVideoGroup(g)) {
        const secs = getGroupDurationSeconds(g);
        if (settings.minVideoSeconds > 0 && secs > 0 && secs < settings.minVideoSeconds) {
          g.style.display = 'none';
          hidden++;
        } else {
          g.style.display = '';
        }
      } else {
        g.style.display = '';
      }
    });
    updateHiddenCounter(hidden);
    publishAlbumVideoUrls();
  }

  /* ---------- Album video sources → R2 host → ThisVid my_video_upload ---------- */
  const THISVID_PENDING_KEY = 'tbccThisVidPendingUpload';
  const THISVID_UPLOAD_URL = 'https://thisvid.com/my_video_upload/';

  function collectVideoSources(videoEl) {
    const sources = Array.from(videoEl.querySelectorAll('source')).filter((s) => s && s.src);
    if (!sources.length && videoEl.src && !/^blob:/i.test(videoEl.src)) {
      return [{ src: videoEl.src, label: '' }];
    }
    return sources.map((s) => ({
      src: s.src,
      label: String(s.getAttribute('label') || s.getAttribute('data-quality') || '').trim(),
    }));
  }

  function pickBestVideoSrc(entries) {
    if (!entries || !entries.length) return '';
    const hd = entries.find((e) => /hd|1080|720/i.test(e.label));
    if (hd) return hd.src;
    const mp4 = entries.find((e) => /\.mp4(\?|#|$)/i.test(e.src));
    return (mp4 || entries[0]).src;
  }

  function albumTitleHint() {
    const h =
      document.querySelector('h1')?.textContent ||
      document.querySelector('.album-title')?.textContent ||
      document.title ||
      '';
    return String(h).replace(/\s+/g, ' ').trim().slice(0, 120);
  }

  function storePendingThisVid(payload, thenOpen) {
    const openUpload = () => {
      window.open(THISVID_UPLOAD_URL, '_blank');
      if (typeof thenOpen === 'function') thenOpen();
    };
    try {
      if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        chrome.storage.local.set({ [THISVID_PENDING_KEY]: payload }, openUpload);
        return;
      }
    } catch (_) {}
    try {
      localStorage.setItem(THISVID_PENDING_KEY, JSON.stringify(payload));
    } catch (_) {}
    openUpload();
  }

  /** After TBCC reload/update, album tabs keep old content scripts — runtime.id is gone. */
  function isExtensionContextAlive() {
    try {
      return !!(typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.id);
    } catch (_) {
      return false;
    }
  }

  function isContextInvalidatedError(err) {
    const msg = String((err && err.message) || err || '');
    return /extension context invalidated|context invalidated/i.test(msg);
  }

  async function hostEromeUrlToR2(srcUrl) {
    if (!isExtensionContextAlive() || !chrome.runtime.sendMessage) {
      throw new Error('Extension context invalidated — reload this Erome tab, then retry → ThisVid');
    }
    const resp = await new Promise((resolve, reject) => {
      try {
        chrome.runtime.sendMessage(
          {
            action: 'tbcc-watermark-upload-r2',
            url: srcUrl,
            destination: 'library',
            refererPageUrl: location.href.split('#')[0],
            preferFull: true,
          },
          (r) => {
            if (chrome.runtime.lastError) {
              const m = chrome.runtime.lastError.message || 'runtime error';
              if (/context invalidated/i.test(m)) {
                reject(
                  new Error('Extension context invalidated — reload this Erome tab, then retry → ThisVid')
                );
                return;
              }
              reject(new Error(m));
              return;
            }
            resolve(r || {});
          }
        );
      } catch (e) {
        if (isContextInvalidatedError(e)) {
          reject(
            new Error('Extension context invalidated — reload this Erome tab, then retry → ThisVid')
          );
          return;
        }
        reject(e);
      }
    });
    if (!resp || !resp.ok || !resp.directUrl) {
      throw new Error((resp && resp.error) || 'R2 upload returned no URL');
    }
    return resp;
  }

  function sendVideoToThisVid(srcUrl) {
    const raw = String(srcUrl || '').trim();
    if (!raw) {
      showEeToast('No video URL');
      return;
    }
    const title = albumTitleHint();
    const albumUrl = location.href.split('#')[0];
    // Stale tab after extension reload — R2 + chrome.storage both dead until refresh.
    if (!isExtensionContextAlive()) {
      try {
        navigator.clipboard.writeText(raw);
      } catch (_) {}
      showEeToast('TBCC was reloaded — refresh this tab, then retry → ThisVid (URL copied)');
      return;
    }
    // Already hosted on our CDN — skip re-upload.
    if (/media\.powercore\.app|\.r2\.dev/i.test(raw)) {
      storePendingThisVid(
        { url: raw, title, albumUrl, ts: Date.now(), hosted: 'r2' },
        () => showEeToast('Opening ThisVid upload — R2 URL will auto-fill')
      );
      return;
    }
    showEeToast('Hosting to R2…');
    hostEromeUrlToR2(raw)
      .then((result) => {
        storePendingThisVid(
          {
            url: result.directUrl,
            title,
            albumUrl,
            ts: Date.now(),
            hosted: 'r2',
            sourceUrl: raw,
            watermarked: !!result.watermarked,
          },
          () =>
            showEeToast(
              `R2 ready${result.watermarked ? ' · watermarked' : ''} — opening ThisVid upload`
            )
        );
      })
      .catch((e) => {
        const err = (e && e.message) || String(e);
        try {
          navigator.clipboard.writeText(raw);
        } catch (_) {}
        if (isContextInvalidatedError(e)) {
          showEeToast('TBCC was reloaded — refresh this tab, then retry → ThisVid (URL copied)');
          return;
        }
        showEeToast(`R2 host failed: ${err}`);
      });
  }

  function publishAlbumVideoUrls() {
    if (!location.pathname.startsWith('/a/') || settings.videoThisVidBridge === false) {
      window.__tbccEromeAlbumVideos = [];
      return;
    }
    const list = [];
    document.querySelectorAll('video').forEach((videoEl, i) => {
      const entries = collectVideoSources(videoEl);
      const best = pickBestVideoSrc(entries);
      if (!best) return;
      list.push({
        index: list.length + 1,
        url: best,
        sources: entries.map((e) => e.src).filter(Boolean),
        title: albumTitleHint(),
      });
    });
    window.__tbccEromeAlbumVideos = list;
    window.__tbccEromeSendToThisVid = sendVideoToThisVid;
    try {
      window.dispatchEvent(new CustomEvent('tbcc-erome-album-videos', { detail: { videos: list } }));
    } catch (_) {}
    // Remove any leftover inline bars from earlier builds (insertBefore used to crash).
    document.querySelectorAll('.ee-vid-bridge').forEach((el) => el.remove());
  }

  function observeAlbumChanges() {
    if (!location.pathname.startsWith('/a/')) return;
    const container = document.body;
    if (!container) return;
    const mo = new MutationObserver(() => {
      clearTimeout(window.__ee_album_timeout);
      window.__ee_album_timeout = setTimeout(() => applyAlbumEnhancements(), 500);
    });
    mo.observe(container, { childList: true, subtree: true });
  }

  /* ---------- UI ---------- */
  function ensureEnhancerNav() {
    const navContainer = document.querySelector('.navbar .container .col-sm-12');
    if (!navContainer) return null;
    if (document.getElementById('enhancerNavItem')) {
      updateIntelCountBadge();
      return document.getElementById('enhancerBtn');
    }
    const div = document.createElement('div');
    div.className = 'sp';
    div.id = 'enhancerNavItem';
    div.innerHTML = `<a href="#" id="enhancerBtn" style="display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap;"><i class="fa fa-sliders"></i><span>Enhancer</span><span style="display:inline-flex;align-items:center;gap:4px;color:#eb6395;margin-left:8px;font-weight:600;font-size:13px;"><i class="fa fa-eye-slash"></i><span id="eeCountNum">0</span></span><span id="eeIntelCountWrap" style="display:inline-flex;align-items:center;gap:4px;color:#7ec8e3;margin-left:6px;font-weight:600;font-size:13px;"><i class="fa fa-bar-chart"></i><span id="eeIntelCountNum">0</span></span></a>`;
    const orientationDropdown = navContainer.querySelector('.sp.dropdown.sign-in');
    if (orientationDropdown) {
      orientationDropdown.insertAdjacentElement('afterend', div);
    } else {
      navContainer.insertBefore(div, navContainer.querySelector('.navbar-header'));
    }
    updateIntelCountBadge();
    return document.getElementById('enhancerBtn');
  }

  function addSettingsUI() {
    const anchor = ensureEnhancerNav();
    if (!anchor || document.getElementById('enhancerModal')) return;
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.id = 'enhancerModal';
    modal.innerHTML = `<div class="modal-dialog"><div class="modal-content" style="background:#2b2b2b;color:#fff;"><div class="modal-header" style="border-bottom:1px solid #444;padding:20px 25px 15px;"><button type="button" class="close" data-dismiss="modal" style="color:#fff;opacity:0.8;font-size:24px;margin-top:-5px;">×</button><h4 class="modal-title" style="font-weight:600;font-size:18px;"><i class="fa fa-sliders" style="margin-right:10px;color:#eb6395;"></i>Erome Enhancer Settings</h4></div><div class="modal-body" style="padding:25px;"><div class="settings-section"><div class="section-header"><i class="fa fa-th-large" style="margin-right:8px;"></i>Grid View Filters</div><div class="section-content"><div class="form-group"><label class="control-label">Content Filter</label><select id="filterMode" class="form-control"><option value="all">Show All Albums</option><option value="videos">Videos Only</option><option value="images">Images Only (No Videos)</option></select></div><div class="form-group"><label class="control-label">Title include (all must match)</label><input type="text" id="titleInclude" class="form-control" placeholder="e.g. milf blonde"></div><div class="form-group"><label class="control-label">Title exclude (hide if any match)</label><input type="text" id="titleExclude" class="form-control" placeholder="e.g. gay"></div><div class="form-group"><div class="checkbox"><label><input type="checkbox" id="autoScroll"> Auto-load pages (infinite scroll)</label></div></div><div class="form-group"><div class="checkbox"><label><input type="checkbox" id="hideViewed"> Hide viewed albums</label></div></div><div class="form-group"><div class="checkbox"><label><input type="checkbox" id="showLikes"> Show like counts on albums</label></div></div><div class="form-group"><div class="checkbox"><label><input type="checkbox" id="gridLikeRepost"> Like + Repost on gallery thumbnails</label></div></div><div class="form-group"><div class="checkbox"><label><input type="checkbox" id="videoThisVidBridge"> Album: publish video URLs to FAB Videos tab</label></div></div><div class="form-group"><div class="checkbox"><label><input type="checkbox" id="enableSorting"> Enable album sorting controls</label></div></div></div></div>
<div class="settings-section"><div class="section-header"><i class="fa fa-bar-chart" style="margin-right:8px;"></i>Browse Intel (v4)</div><div class="section-content" style="background:#333;padding:20px;border-radius:8px;border:1px solid #444;"><div class="form-group"><div class="checkbox"><label><input type="checkbox" id="recordIntel"> Record browse intel while loading likes</label></div></div><div class="form-group"><div class="checkbox"><label><input type="checkbox" id="showTransportOverlay"> Show right-edge Erome tab (ER ▸ — live intel + Playwright)</label></div></div><div class="form-group"><label class="control-label">Max intel rows (localStorage)</label><input type="number" id="maxIntelRows" class="form-control" min="500" max="50000" value="5000"></div><div class="form-group"><label class="control-label">TBCC ingest URL (optional)</label><input type="text" id="tbccApiUrl" class="form-control" placeholder="http://127.0.0.1:8000/analytics/erome-browse-intel"></div><div class="ee-action-buttons"><button type="button" id="exportIntel" class="btn btn-default ee-action-btn"><i class="fa fa-download"></i> Export JSONL</button><button type="button" id="pushIntelTbcc" class="btn btn-default ee-action-btn"><i class="fa fa-upload"></i> Push to TBCC</button><button type="button" id="showIntelSummary" class="btn btn-default ee-action-btn"><i class="fa fa-list"></i> Summary</button><button type="button" id="clearIntel" class="btn btn-default ee-action-btn"><i class="fa fa-trash"></i> Clear Intel</button></div><pre id="intelSummaryBox" class="ee-intel-summary" hidden></pre></div></div><hr style="border-color:#444;margin:25px 0;">
<div class="settings-section"><div class="section-header"><i class="fa fa-clock-o" style="margin-right:8px;"></i>Video Duration Filter</div><div class="section-content" style="background:#333;padding:20px;border-radius:8px;margin-top:12px;border:1px solid #444;"><div class="form-group" style="margin-bottom:20px;"><label class="control-label" style="font-size:14px;color:#ddd;font-weight:500;"><i class="fa fa-filter" style="margin-right:6px;"></i>Minimum Average Video Duration</label><div style="display:flex;align-items:center;gap:12px;margin-top:8px;"><input type="number" id="minVideoSeconds" class="form-control" min="0" placeholder="0 = disabled" style="flex:1;background:#444;border:1px solid #555;color:#fff;"><span style="color:#888;font-size:13px;white-space:nowrap;font-weight:500;">seconds</span></div><div style="font-size:12px;color:#777;margin-top:8px;line-height:1.4;"><i class="fa fa-info-circle" style="margin-right:5px;"></i>Hide albums where the average video duration is shorter than this</div></div><div style="background:#3a3a3a;padding:12px 15px;border-radius:6px;margin-top:15px;border-left:3px solid #eb6395;"><div style="font-size:12px;color:#999;display:flex;align-items:center;"><i class="fa fa-exclamation-circle" style="margin-right:8px;font-size:14px;"></i><span>Applies to both grid pages and individual album pages</span></div></div><div class="ee-action-buttons"><button id="clearViewed" class="btn btn-default ee-action-btn"><i class="fa fa-trash" style="margin-right:6px;"></i>Clear Viewed</button><button id="resetDurationFilter" class="btn btn-default ee-action-btn"><i class="fa fa-refresh" style="margin-right:6px;"></i>Reset Duration</button></div></div></div></div><div class="modal-footer" style="border-top:1px solid #444;padding:20px 25px;"><button id="saveEnhancer" class="btn btn-primary" style="background:#eb6395 !important;border-color:#eb6395 !important;color:#fff !important;font-weight:600;padding:10px 20px;width:100%;"><i class="fa fa-check" style="margin-right:8px;"></i>Apply Settings</button></div></div></div>`;
    document.body.appendChild(modal);

    anchor.addEventListener('click', e => {
      e.preventDefault();
      document.getElementById('filterMode').value = settings.filterMode;
      document.getElementById('titleInclude').value = settings.titleInclude || '';
      document.getElementById('titleExclude').value = settings.titleExclude || '';
      document.getElementById('autoScroll').checked = settings.autoScroll;
      document.getElementById('hideViewed').checked = settings.hideViewed;
      document.getElementById('showLikes').checked = settings.showLikes;
      document.getElementById('gridLikeRepost').checked = settings.gridLikeRepost !== false;
      document.getElementById('videoThisVidBridge').checked = settings.videoThisVidBridge !== false;
      document.getElementById('enableSorting').checked = settings.enableSorting;
      document.getElementById('minVideoSeconds').value = settings.minVideoSeconds || 0;
      document.getElementById('recordIntel').checked = intelMeta.recordIntel !== false;
      document.getElementById('showTransportOverlay').checked = !!intelMeta.showTransportOverlay;
      document.getElementById('maxIntelRows').value = intelMeta.maxIntelRows || 5000;
      document.getElementById('tbccApiUrl').value = intelMeta.tbccApiUrl || '';

      if (typeof $ === 'function') {
        $('#enhancerModal').modal({ show: true, backdrop: true });
      } else {
        modal.style.display = 'block';
        modal.classList.add('show');
      }
    });

    modal.querySelector('#saveEnhancer').addEventListener('click', () => {
      settings.filterMode = document.getElementById('filterMode').value;
      settings.titleInclude = (document.getElementById('titleInclude').value || '').trim();
      settings.titleExclude = (document.getElementById('titleExclude').value || '').trim();
      settings.autoScroll = document.getElementById('autoScroll').checked;
      settings.hideViewed = document.getElementById('hideViewed').checked;
      settings.showLikes = document.getElementById('showLikes').checked;
      settings.gridLikeRepost = document.getElementById('gridLikeRepost').checked;
      settings.videoThisVidBridge = document.getElementById('videoThisVidBridge').checked;
      settings.enableSorting = document.getElementById('enableSorting').checked;
      settings.minVideoSeconds = parseInt(document.getElementById('minVideoSeconds').value) || 0;
      saveSettings();
      intelMeta.recordIntel = document.getElementById('recordIntel').checked;
      intelMeta.showTransportOverlay = document.getElementById('showTransportOverlay').checked;
      intelMeta.maxIntelRows = parseInt(document.getElementById('maxIntelRows').value) || 5000;
      intelMeta.tbccApiUrl = document.getElementById('tbccApiUrl').value.trim();
      saveIntelMeta(intelMeta);
      try {
        window.dispatchEvent(
          new CustomEvent('tbcc-erome-transport-toggle', {
            detail: { open: !!intelMeta.showTransportOverlay },
          })
        );
      } catch (_) {}

      if (typeof $ === 'function') {
        $('#enhancerModal').modal('hide');
      } else {
        modal.style.display = 'none';
        modal.classList.remove('show');
      }
      setTimeout(() => {
        if (location.pathname.startsWith('/a/')) {
          applyAlbumEnhancements();
        } else {
          const barInc = document.getElementById('eeTitleInclude');
          const barExc = document.getElementById('eeTitleExclude');
          if (barInc) barInc.value = settings.titleInclude || '';
          if (barExc) barExc.value = settings.titleExclude || '';
          applyTitleKeywordVisibility();
          document.querySelectorAll('.ee-album-actions').forEach((el) => el.remove());
          document.querySelectorAll('.album').forEach((a) => {
            delete a.dataset.eeActionsMounted;
          });
          if (settings.gridLikeRepost) processAlbumActions();
        }
      }, 200);
    });

    modal.querySelector('#clearViewed').addEventListener('click', clearViewed);

    modal.querySelector('#exportIntel')?.addEventListener('click', exportIntelJsonl);
    modal.querySelector('#pushIntelTbcc')?.addEventListener('click', pushIntelToTbcc);
    modal.querySelector('#clearIntel')?.addEventListener('click', clearIntelRows);
    modal.querySelector('#showIntelSummary')?.addEventListener('click', () => {
      const box = document.getElementById('intelSummaryBox');
      if (!box) return;
      box.hidden = false;
      box.style.display = 'block';
      box.textContent = intelSummaryText();
      // Keep summary in view inside the scrollable modal body
      try {
        box.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      } catch (_) {}
    });

    modal.querySelector('#resetDurationFilter').addEventListener('click', () => {
      settings.minVideoSeconds = 0;
      saveSettings();
      document.getElementById('minVideoSeconds').value = 0;
      location.pathname.startsWith('/a/') ? applyAlbumEnhancements() : location.reload();
    });

    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        if (typeof $ === 'function') {
          $('#enhancerModal').modal('hide');
        } else {
          modal.style.display = 'none';
          modal.classList.remove('show');
        }
      }
    });
  }

  /* ---------- Cleanup ---------- */
  function disableDisclaimer() {
    const disclaimer = document.getElementById('disclaimer');
    if (!disclaimer) return;
    if (typeof $ === 'function') {
      $.ajax({ type: 'POST', url: '/user/disclaimer', async: true });
      $('#disclaimer').remove();
      $('body').css('overflow', 'visible');
    } else {
      fetch('/user/disclaimer', { method: 'POST' }).catch(() => {});
      disclaimer.remove();
      document.body.style.overflow = 'visible';
    }
  }

  function cleanNavbar() {
    const navContainer = document.querySelector('.navbar .container .col-sm-12');
    if (navContainer) {
      navContainer.querySelectorAll('.sp').forEach(div => {
        const link = div.querySelector('a');
        if (link?.href?.includes('/o/menu-')) div.remove();
      });
    }
    document.querySelector('.sp-mob.hidden-sm.hidden-md.hidden-lg')?.remove();
    document.querySelectorAll('.separator .bubble-mobile').forEach(bubble => {
      if (bubble.href?.includes('/o/')) bubble.closest('.separator')?.remove();
    });
    const navbar = document.querySelector('.navbar.navbar-inverse.navbar-static-top');
    if (navbar && !document.getElementById('ee-navbar-fix')) {
      const style = document.createElement('style');
      style.id = 'ee-navbar-fix';
      style.textContent = `.navbar.navbar-inverse.navbar-static-top { top: 0 !important; }`;
      document.head.appendChild(style);
    }
  }

  /* ---------- Init ---------- */
  function init() {
    disableDisclaimer();
    cleanNavbar();
    fixLazyImages();
    
    const albumsContainer = document.querySelector(SELECTORS.albums);
    if (albumsContainer && !location.pathname.startsWith('/a/')) {
      albumsContainer.style.minHeight = '600px';
    }
    
    if (location.pathname.startsWith('/a/')) {
      setTimeout(() => {
        applyAlbumEnhancements();
        observeAlbumChanges();
      }, 2000);
    } else {
      applyInitialFilter();
      mountTitleFilterBar();
      addSortingControls();
      setTimeout(() => setupInfiniteScroll(), 1000);
      setTimeout(() => processLikesForAlbums(), 500);
      setTimeout(() => processAlbumActions(), 300);
    }
    addSettingsUI();
    updateIntelCountBadge();
    // Already at max from a prior session — flush without waiting for a new album save.
    try {
      if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.flushIfAtCap === 'function') {
        globalThis.tbccBrowseIntel.flushIfAtCap({
          rows: loadIntelRows(),
          meta: intelMeta,
          applyTrimmed: (stored) => {
            try {
              localStorage.setItem(INTEL_KEY, JSON.stringify(stored));
            } catch (_) {}
            updateIntelCountBadge();
          },
          toast: (msg) => {
            try {
              showEeToast(msg);
            } catch (_) {
              try {
                console.info('[TBCC intel]', msg);
              } catch (__) {}
            }
          },
        });
      }
    } catch (_) {}
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
});
