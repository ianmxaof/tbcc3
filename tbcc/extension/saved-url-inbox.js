/**
 * Shared saved-URL inbox storage (chrome.storage.local).
 * Keep STORAGE_SAVED_VIDEO_URLS in sync with background.js.
 */
(function (global) {
  const STORAGE_SAVED_VIDEO_URLS = "tbccSavedVideoUrls";
  const SAVED_VIDEO_URLS_CAP = 600;

  function normalizeRow(raw) {
    const url = String((raw && raw.url) || "").trim();
    if (!url) return null;
    const poolId =
      raw && raw.poolId != null && raw.poolId !== ""
        ? parseInt(raw.poolId, 10)
        : raw && raw.targetPoolId != null && raw.targetPoolId !== ""
          ? parseInt(raw.targetPoolId, 10)
          : null;
    const destType =
      raw && raw.destType === "loot_modifier"
        ? "loot_modifier"
        : raw && raw.destType === "archive"
          ? "archive"
          : "pool";
    let modifierId =
      raw && raw.modifierId != null && raw.modifierId !== ""
        ? parseInt(raw.modifierId, 10)
        : null;
    if (!Number.isFinite(modifierId) || modifierId < 1) modifierId = null;
    return {
      url,
      addedAt: Number(raw && raw.addedAt ? raw.addedAt : Date.now()) || Date.now(),
      ref: raw && raw.ref ? String(raw.ref).trim() : "",
      destType,
      poolId: destType === "pool" && Number.isFinite(poolId) && poolId > 0 ? poolId : null,
      tagsCsv: raw && raw.tagsCsv ? String(raw.tagsCsv).trim() : "",
      autoTag: raw && raw.autoTag === false ? false : true,
      includeZipPromo:
        raw && raw.includeZipPromo === false
          ? false
          : raw && raw.includeZipPromo === true
            ? true
            : null,
      lootZipPack: raw && raw.lootZipPack === true,
      lootRandomHighTier: raw && raw.lootRandomHighTier !== false,
      note: raw && raw.note ? String(raw.note).trim() : "",
      status:
        raw && raw.status === "imported"
          ? "imported"
          : raw && raw.status === "importing"
            ? "importing"
            : "queued",
      mediaId:
        raw && raw.mediaId != null && raw.mediaId !== ""
          ? parseInt(raw.mediaId, 10)
          : null,
      modifierId,
      lastError: raw && raw.lastError ? String(raw.lastError).slice(0, 400) : "",
    };
  }

  function rowKey(row) {
    return String(row.url) + "|" + String(row.addedAt);
  }

  async function getRows() {
    const data = await new Promise((resolve) =>
      chrome.storage.local.get([STORAGE_SAVED_VIDEO_URLS], resolve)
    );
    const arr = Array.isArray(data[STORAGE_SAVED_VIDEO_URLS]) ? data[STORAGE_SAVED_VIDEO_URLS] : [];
    return arr.map(normalizeRow).filter(Boolean);
  }

  async function setRows(rows) {
    const capped = rows
      .map(normalizeRow)
      .filter(Boolean)
      .slice(0, SAVED_VIDEO_URLS_CAP);
    await new Promise((resolve) =>
      chrome.storage.local.set({ [STORAGE_SAVED_VIDEO_URLS]: capped }, resolve)
    );
    const arch = global.TbccMasterArchive;
    if (arch && arch.mirrorInboxRows) await arch.mirrorInboxRows(capped);
    return capped;
  }

  async function appendToArchive(url, opts) {
    const clean = String(url || "").trim();
    if (!/^https?:\/\//i.test(clean)) return { ok: false, error: "Need an http(s) URL." };
    const arch = global.TbccMasterArchive;
    if (!arch || !arch.recordUrl) return { ok: false, error: "Master archive module not loaded." };
    const tagsCsv = opts && opts.tagsCsv ? String(opts.tagsCsv).trim() : "";
    const note = opts && opts.note ? String(opts.note).trim() : "";
    await arch.recordUrl(clean, {
      source: (opts && opts.source) || "inbox",
      ref: opts && opts.ref ? String(opts.ref) : "",
      note,
      tags: tagsCsv,
    });
    return { ok: true, duplicate: false, archived: true };
  }

  async function appendUrl(url, opts) {
    const clean = String(url || "").trim();
    if (!/^https?:\/\//i.test(clean)) return { ok: false, error: "Need an http(s) URL." };
    const destType =
      opts && opts.destType === "loot_modifier"
        ? "loot_modifier"
        : opts && opts.destType === "archive"
          ? "archive"
          : "pool";
    if (destType === "archive") {
      return appendToArchive(clean, opts);
    }
    const rows = await getRows();
    const dup = rows.some((x) => x.url === clean);
    if (dup) return { ok: true, duplicate: true };
    const poolId =
      opts && opts.poolId != null && opts.poolId !== ""
        ? parseInt(opts.poolId, 10)
        : null;
    rows.unshift(
      normalizeRow({
        url: clean,
        addedAt: Date.now(),
        ref: opts && opts.ref ? String(opts.ref) : "",
        destType,
        poolId: Number.isFinite(poolId) && poolId > 0 ? poolId : null,
        tagsCsv: opts && opts.tagsCsv ? String(opts.tagsCsv) : "",
        note: opts && opts.note ? String(opts.note) : "",
        status: "queued",
      })
    );
    await setRows(rows);
    const arch = global.TbccMasterArchive;
    if (arch && arch.recordUrl) {
      void arch.recordUrl(clean, {
        source: "inbox",
        ref: opts && opts.ref ? String(opts.ref) : "",
      });
    }
    return { ok: true, duplicate: false };
  }

  global.TbccSavedUrlInbox = {
    STORAGE_SAVED_VIDEO_URLS,
    SAVED_VIDEO_URLS_CAP,
    normalizeRow,
    rowKey,
    getRows,
    setRows,
    appendToArchive,
    appendUrl,
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
