/**
 * Shared browse-intel helpers for Erome / ThisVid / Motherless overlays.
 * Auto-push to TBCC master ledger when local rows hit max; Pareto + Live feed HTML.
 * Push goes through the extension service worker (avoids HTTPS→HTTP mixed-content block).
 */
(function (global) {
  "use strict";

  const DEBOUNCE_MS = 60_000;

  function median(vals) {
    if (!vals.length) return 0;
    const a = vals.slice().sort((x, y) => x - y);
    return a[Math.floor(a.length / 2)] || 0;
  }

  function fmtNum(n) {
    if (typeof global.tbccFormatAbbrevNumber === "function") {
      return global.tbccFormatAbbrevNumber(n);
    }
    const v = Number(n);
    if (!Number.isFinite(v)) return "?";
    if (v >= 1e6) return `${(v / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
    if (v >= 1e3) return `${(v / 1e3).toFixed(1).replace(/\.0$/, "")}K`;
    return String(Math.round(v));
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /** Pareto-style ranking: tags by median views/day (fallback median views). */
  function isNoiseIntelTag(tag) {
    const t = String(tag || "")
      .trim()
      .toLowerCase();
    if (!t || t.length < 2) return true;
    if (
      /^(image|images|video|videos|photo|photos|galleries|gallery|term|gi|gv|gm|g|u|m|f|s)$/i.test(t)
    ) {
      return true;
    }
    if (/^[a-f0-9]{6,12}$/i.test(t)) return true;
    if (/^g[a-f0-9]{5,12}$/i.test(t)) return true;
    return false;
  }

  function paretoTagRanks(rows) {
    const buckets = {};
    (rows || []).forEach((r) => {
      (r.tags || []).forEach((t) => {
        const tag = String(t || "")
          .trim()
          .toLowerCase();
        if (isNoiseIntelTag(tag)) return;
        if (!buckets[tag]) buckets[tag] = { views: [], vpd: [] };
        if (r.views != null && Number(r.views) > 0) buckets[tag].views.push(Number(r.views));
        if (r.views_per_day_proxy != null && Number(r.views_per_day_proxy) > 0) {
          buckets[tag].vpd.push(Number(r.views_per_day_proxy));
        }
      });
    });
    const ranked = Object.keys(buckets)
      .map((tag) => {
        const b = buckets[tag];
        const useVpd = b.vpd.length >= 2;
        const score = useVpd ? median(b.vpd) : median(b.views);
        return { tag, score, metric: useVpd ? "vpd" : "views", n: b.views.length + b.vpd.length };
      })
      .filter((r) => r.score > 0)
      .sort((a, b) => b.score - a.score);
    const paretoCut = Math.max(1, Math.ceil(ranked.length * 0.2));
    return { ranked, paretoCut, pareto: ranked.slice(0, paretoCut) };
  }

  /**
   * HTML block: Pareto top tags + Live captures (last 12).
   * @param {object[]} rows
   * @param {{ topN?: number, feedN?: number }} [opts]
   */
  function renderParetoLiveHtml(rows, opts) {
    const o = opts || {};
    const topN = o.topN || 12;
    const feedN = o.feedN || 12;
    const list = Array.isArray(rows) ? rows : [];
    const { ranked, paretoCut } = paretoTagRanks(list);
    const maxScore = ranked[0]?.score || 1;
    const recent = list.slice(-feedN).reverse();
    const topHtml = ranked
      .slice(0, topN)
      .map((r, i) => {
        const pct = Math.round((r.score / maxScore) * 100);
        const isPareto = i < paretoCut;
        return `<div class="tbcc-intel-pareto-row${isPareto ? " top" : ""}" style="display:flex;align-items:center;gap:6px;font-size:11px;padding:2px 0">
          <span style="width:18px;color:#666">${i + 1}</span>
          <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(r.tag)}</span>
          <div style="height:6px;border-radius:3px;background:#eb6395;width:${Math.max(8, pct * 0.9)}px"></div>
          <span style="width:64px;text-align:right;font-variant-numeric:tabular-nums;color:#aaa">${fmtNum(r.score)}${r.metric === "vpd" ? "/d" : ""}</span>
        </div>`;
      })
      .join("");
    const feedHtml = recent
      .map(
        (r) =>
          `<div class="tbcc-intel-feed-item" style="font-size:11px;color:#aaa;padding:3px 0;border-bottom:1px solid #2a2a2a">
            <strong style="color:#ddd">${escapeHtml((r.title || r.album_id || "").slice(0, 40))}</strong>
            · ${r.views != null ? fmtNum(r.views) : "?"} views · ${(r.tags || []).slice(0, 3).map(escapeHtml).join(", ")}
          </div>`
      )
      .join("");
    return `
      <div class="tbcc-intel-live" style="margin-top:10px">
        <div style="color:#888;font-size:10px;margin-bottom:4px">Pareto tags · ${ranked.length} · rows ${list.length}</div>
        ${
          topHtml ||
          (list.length
            ? '<div style="color:#666;font-size:11px">Rows stored — waiting for view counts on thumbs (Pareto ranks by median views / views-per-day).</div>'
            : '<div style="color:#666;font-size:11px">No intel yet — browse with Record on.</div>')
        }
        <div style="margin-top:8px;border-top:1px solid #333;padding-top:8px;max-height:160px;overflow:auto">
          <div style="color:#888;font-size:10px;margin:0 0 4px">Live captures</div>
          ${feedHtml || '<div style="color:#666;font-size:11px">Waiting for captures…</div>'}
        </div>
      </div>`;
  }

  /**
   * POST rows via service worker (preferred) or page fetch fallback.
   * @returns {Promise<{ ok: boolean, appended?: number, error?: string, url?: string }>}
   */
  function postIntelRows(apiUrl, rows) {
    const list = Array.isArray(rows) ? rows : [];
    const hint = String(apiUrl || "").trim();
    return new Promise((resolve, reject) => {
      try {
        if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
          chrome.runtime.sendMessage(
            { action: "tbcc-browse-intel-push", url: hint, rows: list },
            (resp) => {
              if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message || "runtime error"));
                return;
              }
              if (!resp || !resp.ok) {
                reject(new Error((resp && resp.error) || "Push failed"));
                return;
              }
              resolve(resp);
            }
          );
          return;
        }
      } catch (e) {
        /* fall through to page fetch */
      }
      void (async () => {
        try {
          if (!hint) throw new Error("No TBCC ingest URL");
          const res = await fetch(hint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rows: list }),
          });
          let data = {};
          try {
            data = await res.json();
          } catch (_) {}
          if (!res.ok) throw new Error(data.detail || data.error || `HTTP ${res.status}`);
          resolve({
            ok: true,
            appended: data.appended != null ? data.appended : list.length,
            scanned: data.scanned,
            url: hint,
            data,
          });
        } catch (err) {
          reject(err);
        }
      })();
    });
  }

  /**
   * GET /summary via service worker (avoids page→localhost permission prompts on Brave).
   * @returns {Promise<object|null>}
   */
  function fetchIntelSummary(apiUrl, days) {
    const hint = String(apiUrl || "").trim();
    return new Promise((resolve) => {
      try {
        if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
          chrome.runtime.sendMessage(
            { action: "tbcc-browse-intel-summary", url: hint, days: days || 30 },
            (resp) => {
              if (chrome.runtime.lastError || !resp || !resp.ok) {
                resolve(null);
                return;
              }
              resolve(resp.data || null);
            }
          );
          return;
        }
      } catch (_) {}
      resolve(null);
    });
  }

  function schedulePush(toPush, apiUrl, keep, applyTrimmed, toast) {
    const g = global;
    if (g.__tbccIntelPushBusy) return false;
    if (Date.now() - Number(g.__tbccIntelPushAt || 0) < DEBOUNCE_MS) return false;

    g.__tbccIntelPushBusy = true;
    g.__tbccIntelPushAt = Date.now();
    void postIntelRows(apiUrl, toPush)
      .then((resp) => {
        const appended = resp.appended != null ? resp.appended : toPush.length;
        const trimmed = toPush.slice(-keep);
        applyTrimmed(trimmed);
        toast(`Pushed ${appended} → TBCC intel · kept ${trimmed.length} local`);
      })
      .catch((e) => {
        toast(`Intel auto-push failed: ${(e && e.message) || e}`);
      })
      .finally(() => {
        g.__tbccIntelPushBusy = false;
      });
    return true;
  }

  /**
   * When rows.length >= maxIntelRows, POST to tbccApiUrl then keep last 20%.
   * Debounced: one in-flight; skip if last attempt < 60s ago.
   *
   * @param {{ rows: object[], meta: object, applyTrimmed: (rows: object[]) => void, toast?: (msg: string) => void, skipAutoPush?: boolean, force?: boolean }} opts
   * @returns {{ stored: object[], scheduled: boolean }}
   */
  function saveWithCapAndMaybePush(opts) {
    const rows = Array.isArray(opts.rows) ? opts.rows : [];
    const meta = opts.meta || {};
    const cap = Math.max(500, Number(meta.maxIntelRows) || 5000);
    const keep = Math.max(100, Math.floor(cap * 0.2));
    const applyTrimmed = typeof opts.applyTrimmed === "function" ? opts.applyTrimmed : () => {};
    const toast = typeof opts.toast === "function" ? opts.toast : () => {};
    const apiUrl = String(meta.tbccApiUrl || "").trim().replace(/\/$/, "");
    const atCap = rows.length >= cap;

    if (opts.skipAutoPush || (!atCap && !opts.force)) {
      const stored = rows.slice(-cap);
      applyTrimmed(stored);
      return { stored, scheduled: false };
    }

    if (!atCap && opts.force) {
      applyTrimmed(rows.slice(-cap));
      return { stored: rows.slice(-cap), scheduled: false };
    }

    // Cap immediately so localStorage never grows unbounded while push runs.
    const capped = rows.slice(-cap);
    applyTrimmed(capped);

    if (!apiUrl && !opts.force) {
      toast("Intel at max — set TBCC ingest URL (or Options API base) to auto-push");
      return { stored: capped, scheduled: false };
    }

    const toPush = rows.slice();
    const scheduled = schedulePush(toPush, apiUrl, keep, applyTrimmed, toast);
    if (!scheduled && opts.force) {
      toast("Intel push already in flight — wait a minute, or Export JSONL");
    }
    return { stored: capped, scheduled };
  }

  /**
   * Call on page boot when already sitting at max (no new save to trigger auto-push).
   */
  function flushIfAtCap(opts) {
    const rows = Array.isArray(opts.rows) ? opts.rows : [];
    const meta = opts.meta || {};
    const cap = Math.max(500, Number(meta.maxIntelRows) || 5000);
    if (rows.length < cap) return { scheduled: false };
    return saveWithCapAndMaybePush({ ...opts, rows, meta, force: true });
  }

  /**
   * Export JSONL via chrome.downloads with Save As dialog (file explorer).
   * Falls back to anchor download if SW unavailable.
   * @param {object[]} rows
   * @param {string} [filename]
   * @returns {Promise<{ ok: boolean, downloadId?: number, error?: string }>}
   */
  function exportJsonlSaveAs(rows, filename) {
    const list = Array.isArray(rows) ? rows : [];
    const text = list.map((r) => JSON.stringify(r)).join("\n") + (list.length ? "\n" : "");
    const name = String(filename || "browse-intel.jsonl")
      .replace(/[<>:"/\\|?*\x00-\x1f]/g, "_")
      .slice(0, 180);
    return new Promise((resolve) => {
      try {
        if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
          chrome.runtime.sendMessage(
            { action: "tbcc-intel-export-jsonl", filename: name, text },
            (resp) => {
              if (chrome.runtime.lastError) {
                legacyAnchorDownload(text, name);
                resolve({ ok: true, via: "anchor", error: chrome.runtime.lastError.message });
                return;
              }
              if (!resp || !resp.ok) {
                legacyAnchorDownload(text, name);
                resolve({ ok: true, via: "anchor", error: (resp && resp.error) || "download failed" });
                return;
              }
              resolve(resp);
            }
          );
          return;
        }
      } catch (_) {}
      legacyAnchorDownload(text, name);
      resolve({ ok: true, via: "anchor" });
    });
  }

  function legacyAnchorDownload(text, name) {
    try {
      const blob = new Blob([text], { type: "application/x-ndjson" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (_) {}
  }

  global.tbccBrowseIntel = {
    median,
    fmtNum,
    escapeHtml,
    paretoTagRanks,
    isNoiseIntelTag,
    renderParetoLiveHtml,
    postIntelRows,
    fetchIntelSummary,
    saveWithCapAndMaybePush,
    flushIfAtCap,
    exportJsonlSaveAs,
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
