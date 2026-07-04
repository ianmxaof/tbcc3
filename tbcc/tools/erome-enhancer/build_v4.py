#!/usr/bin/env python3
"""Assemble erome-enhancer.user.js v4 from v3.3 base + intel patch markers."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "erome-enhancer.user.js"

HEADER = r"""// ==UserScript==
// @name         Erome Enhancer — Extended Sorts + Browse Intel
// @namespace    https://github.com/powercore-repo/telegram_bot2
// @version      4.0.0
// @license      MIT
// @author       LisaTurtlesCuck + TBCC fork
// @description  Erome grid sorts (views/likes/engagement/duration), infinite scroll, filters, browse-intel JSONL export for TBCC pool ranking.
// Privacy: @grant none — settings, viewed history, and browse intel stay in localStorage only; fetches go to erome.com.
// @match        https://www.erome.com/*
// @grant        none
// ==/UserScript==
"""

# Intel + settings patch inserted after DEFAULTS block in source
INTEL_BLOCK = r"""
  const INTEL_KEY = 'eromeBrowseIntelRows';
  const INTEL_META_KEY = 'eromeBrowseIntelMeta';

  function loadIntelMeta() {
    try {
      return Object.assign({ recordIntel: true, maxIntelRows: 5000, tbccApiUrl: '' }, JSON.parse(localStorage.getItem(INTEL_META_KEY) || '{}'));
    } catch {
      return { recordIntel: true, maxIntelRows: 5000, tbccApiUrl: '' };
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
  function saveIntelRows(rows) {
    const cap = Math.max(500, intelMeta.maxIntelRows || 5000);
    localStorage.setItem(INTEL_KEY, JSON.stringify(rows.slice(-cap)));
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

    const row = {
      captured_at: new Date().toISOString(),
      album_url: link.href,
      album_id: albumId,
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
    };
    rows.push(row);
    saveIntelRows(rows);
  }

  function exportIntelJsonl() {
    const rows = loadIntelRows();
    const blob = new Blob([rows.map((r) => JSON.stringify(r)).join('\n') + (rows.length ? '\n' : '')], { type: 'application/jsonl' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'browse-intel-drop.jsonl';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function pushIntelToTbcc() {
    const url = (intelMeta.tbccApiUrl || '').trim().replace(/\/$/, '');
    if (!url) {
      alert('Set TBCC API URL in Intel settings (e.g. http://127.0.0.1:8000/analytics/erome-browse-intel)');
      return;
    }
    const rows = loadIntelRows();
    if (!rows.length) {
      alert('No intel rows to push.');
      return;
    }
    try {
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
    saveIntelRows([]);
    alert('Browse intel cleared.');
  }

  function intelSummaryText() {
    const rows = loadIntelRows();
    const tagBuckets = {};
    rows.forEach((r) => {
      if (!r.views) return;
      (r.tags || []).forEach((t) => {
        if (!tagBuckets[t]) tagBuckets[t] = [];
        tagBuckets[t].push(r.views);
      });
    });
    const ranked = Object.entries(tagBuckets)
      .map(([tag, vals]) => {
        vals.sort((a, b) => a - b);
        return [tag, vals[Math.floor(vals.length / 2)] || 0];
      })
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12);
    return `Rows: ${rows.length}\nTop tags (median views):\n` + ranked.map(([t, v]) => `  ${t}: ${v}`).join('\n');
  }
"""

ADD_LIKE_COUNT_PATCH = """
      recordBrowseSnapshot(albumEl, doc, {
        likes: count,
        videos: videoDurations.length,
        total_duration_sec: videoDurations.reduce((s, d) => s + d, 0),
        avg_duration_sec: videoDurations.length ? Math.round(videoDurations.reduce((s, d) => s + d, 0) / videoDurations.length) : 0,
        longest_clip_sec: videoDurations.length ? Math.max(...videoDurations) : 0,
        title: extractTitleFromDoc(doc),
        tags: extractTagsFromDoc(doc),
      });
"""

SETTINGS_HTML_PATCH = """
<div class="settings-section"><div class="section-header"><i class="fa fa-bar-chart" style="margin-right:8px;"></i>Browse Intel (v4)</div><div class="section-content" style="background:#333;padding:20px;border-radius:8px;border:1px solid #444;"><div class="form-group"><div class="checkbox"><label><input type="checkbox" id="recordIntel"> Record browse intel while loading likes</label></div></div><div class="form-group"><label class="control-label">Max intel rows (localStorage)</label><input type="number" id="maxIntelRows" class="form-control" min="500" max="50000" value="5000"></div><div class="form-group"><label class="control-label">TBCC ingest URL (optional)</label><input type="text" id="tbccApiUrl" class="form-control" placeholder="http://127.0.0.1:8000/analytics/erome-browse-intel"></div><div class="ee-action-buttons"><button type="button" id="exportIntel" class="btn btn-default ee-action-btn"><i class="fa fa-download"></i> Export JSONL</button><button type="button" id="pushIntelTbcc" class="btn btn-default ee-action-btn"><i class="fa fa-upload"></i> Push to TBCC</button><button type="button" id="showIntelSummary" class="btn btn-default ee-action-btn"><i class="fa fa-list"></i> Summary</button><button type="button" id="clearIntel" class="btn btn-default ee-action-btn"><i class="fa fa-trash"></i> Clear Intel</button></div><pre id="intelSummaryBox" style="display:none;margin-top:12px;font-size:11px;color:#aaa;max-height:160px;overflow:auto;"></pre></div></div><hr style="border-color:#444;margin:25px 0;">
"""

def main() -> None:
    base_path = ROOT / "erome-enhancer-v3.3-base.user.js"
    if not base_path.is_file():
        raise SystemExit(f"Missing base file: {base_path}")

    src = base_path.read_text(encoding="utf-8")
    # Strip old header through ==/UserScript==
    idx = src.find("// ==/UserScript==")
    if idx < 0:
        raise SystemExit("Invalid base userscript")
    body = src[idx + len("// ==/UserScript==") :].lstrip("\n")

    body = body.replace(
        "  const DEFAULTS = {\n    filterMode: 'videos',\n    autoScroll: true,\n    hideViewed: false,\n    minVideoSeconds: 0,\n    showLikes: true,\n    enableSorting: true,\n  };",
        "  const DEFAULTS = {\n    filterMode: 'videos',\n    autoScroll: true,\n    hideViewed: false,\n    minVideoSeconds: 0,\n    showLikes: true,\n    enableSorting: true,\n  };" + INTEL_BLOCK,
        1,
    )

    if ADD_LIKE_COUNT_PATCH.strip() not in body:
        needle = "      if (count > 0) {\n        const bottomRight = albumEl.querySelector(SELECTORS.albumBottomRight);"
        if needle not in body:
            raise SystemExit("addLikeCount patch anchor not found")
        body = body.replace(needle, ADD_LIKE_COUNT_PATCH + "\n" + needle, 1)

    if "Browse Intel (v4)" not in body:
        body = body.replace(
            '<hr style="border-color:#444;margin:25px 0;"><div class="settings-section"><div class="section-header"><i class="fa fa-clock-o"',
            SETTINGS_HTML_PATCH + '<div class="settings-section"><div class="section-header"><i class="fa fa-clock-o"',
            1,
        )

    # Settings binders
    bind_patch = """
      document.getElementById('recordIntel').checked = intelMeta.recordIntel !== false;
      document.getElementById('maxIntelRows').value = intelMeta.maxIntelRows || 5000;
      document.getElementById('tbccApiUrl').value = intelMeta.tbccApiUrl || '';
"""
    body = body.replace(
        "      document.getElementById('minVideoSeconds').value = settings.minVideoSeconds || 0;",
        "      document.getElementById('minVideoSeconds').value = settings.minVideoSeconds || 0;" + bind_patch,
        1,
    )

    save_patch = """
      intelMeta.recordIntel = document.getElementById('recordIntel').checked;
      intelMeta.maxIntelRows = parseInt(document.getElementById('maxIntelRows').value) || 5000;
      intelMeta.tbccApiUrl = document.getElementById('tbccApiUrl').value.trim();
      saveIntelMeta(intelMeta);
"""
    body = body.replace(
        "      settings.minVideoSeconds = parseInt(document.getElementById('minVideoSeconds').value) || 0;\n      saveSettings();",
        "      settings.minVideoSeconds = parseInt(document.getElementById('minVideoSeconds').value) || 0;\n      saveSettings();" + save_patch,
        1,
    )

    action_patch = """
    modal.querySelector('#exportIntel')?.addEventListener('click', exportIntelJsonl);
    modal.querySelector('#pushIntelTbcc')?.addEventListener('click', pushIntelToTbcc);
    modal.querySelector('#clearIntel')?.addEventListener('click', clearIntelRows);
    modal.querySelector('#showIntelSummary')?.addEventListener('click', () => {
      const box = document.getElementById('intelSummaryBox');
      if (!box) return;
      box.style.display = 'block';
      box.textContent = intelSummaryText();
    });
"""
    body = body.replace(
        "    modal.querySelector('#resetDurationFilter').addEventListener('click', () => {",
        action_patch + "\n    modal.querySelector('#resetDurationFilter').addEventListener('click', () => {",
        1,
    )

    OUT.write_text(HEADER + "\n" + body, encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
