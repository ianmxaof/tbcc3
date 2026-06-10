/**
 * Persistent master list of URLs and usernames (chrome.storage.local).
 * Survives inbox clears and extension updates via backup mirror key.
 */
(function (global) {
  const STORAGE_MASTER = "tbccMasterArchiveV1";
  const STORAGE_MASTER_BACKUP = "tbccMasterArchiveBackupV1";
  const STORAGE_INBOX_MIRROR = "tbccSavedVideoUrls_mirror";
  const MASTER_CAP = 12000;
  const PAGE_SIZE = 100;
  const ARCHIVE_API_BULK = "http://127.0.0.1:8000/archive/entries/bulk";
  const ARCHIVE_API_SYNC = "http://127.0.0.1:8000/archive/entries/sync-bundle";
  const STORAGE_EXPORT_CHECKPOINT = "tbccMasterArchiveExportCheckpointV1";
  const AUTO_EXPORT_EVERY = 100;

  function normalizeEntry(raw) {
    const kind = raw && raw.kind === "username" ? "username" : "url";
    let value =
      kind === "username"
        ? String((raw && raw.value) || "")
            .trim()
            .replace(/^@+/, "")
        : String((raw && raw.value) || "").trim();
    if (kind === "username" && typeof TbccUsernameFilter !== "undefined") {
      value = TbccUsernameFilter.normalizeUsernameCandidate(value) || "";
    }
    if (!value) return null;
    if (kind === "username" && !/^[a-zA-Z0-9._-]{2,64}$/.test(value)) return null;
    if (kind === "url" && !/^https?:\/\//i.test(value)) return null;
    return {
      kind,
      value,
      addedAt: Number(raw && raw.addedAt ? raw.addedAt : Date.now()) || Date.now(),
      source: raw && raw.source ? String(raw.source).slice(0, 80) : "",
      ref: raw && raw.ref ? String(raw.ref).slice(0, 500) : "",
      note: raw && raw.note ? String(raw.note).slice(0, 400) : "",
      description: raw && raw.description ? String(raw.description).slice(0, 400) : "",
      tags: raw && raw.tags ? String(raw.tags).slice(0, 500) : raw && raw.tagsCsv ? String(raw.tagsCsv).slice(0, 500) : "",
    };
  }

  function entryKey(e) {
    return e.kind + "|" + e.value.toLowerCase();
  }

  function formatEntryWhen(addedAt) {
    try {
      return new Date(addedAt).toLocaleString();
    } catch (_) {
      return "";
    }
  }

  function formatEntryMeta(e) {
    const parts = [];
    if (e.source) parts.push(e.source);
    if (e.ref) parts.push("ref: " + String(e.ref).slice(0, 120));
    const when = formatEntryWhen(e.addedAt);
    if (when) parts.push(when);
    if (e.tags) parts.push("tags: " + String(e.tags).slice(0, 80));
    if (e.note) parts.push(e.note);
    return parts.join(" · ");
  }

  const SORT_FIELDS = ["addedAt", "value", "host", "source", "kind", "summary", "tags"];

  function entryHost(e) {
    if (!e || e.kind !== "url") return "";
    try {
      const h = new URL(e.value).hostname.replace(/^www\./i, "");
      return h.toLowerCase();
    } catch (_) {
      return "";
    }
  }

  function sortFieldValue(e, field) {
    const f = SORT_FIELDS.includes(field) ? field : "addedAt";
    if (f === "addedAt") return Number(e.addedAt || 0);
    if (f === "kind") return e.kind === "username" ? 1 : 0;
    if (f === "host") return entryHost(e);
    if (f === "summary") {
      const s =
        (e.description && String(e.description).trim()) ||
        (e.summary && String(e.summary).trim()) ||
        (e.note && !String(e.note).startsWith("ref:") ? String(e.note).trim() : "");
      return s.toLowerCase();
    }
    if (f === "source") return String(e.source || "").toLowerCase();
    if (f === "tags") return String(e.tags || "").toLowerCase();
    return String(e.value || "").toLowerCase();
  }

  function compareEntries(a, b, field, dir) {
    const av = sortFieldValue(a, field);
    const bv = sortFieldValue(b, field);
    const asc = String(dir || "desc").toLowerCase() === "asc";
    if (av < bv) return asc ? -1 : 1;
    if (av > bv) return asc ? 1 : -1;
    return 0;
  }

  /** Multi-key sort (primary, optional secondary, value tiebreaker). */
  function sortEntries(entries, opts) {
    const rows = (entries || []).slice();
    const sortBy = (opts && opts.sortBy) || "addedAt";
    const sortDir = (opts && opts.sortDir) || "desc";
    const sortBy2 = opts && opts.sortBy2 ? String(opts.sortBy2).trim() : "";
    const sortDir2 = (opts && opts.sortDir2) || "asc";
    rows.sort((a, b) => {
      let c = compareEntries(a, b, sortBy, sortDir);
      if (c !== 0) return c;
      if (sortBy2 && SORT_FIELDS.includes(sortBy2)) {
        c = compareEntries(a, b, sortBy2, sortDir2);
        if (c !== 0) return c;
      }
      return compareEntries(a, b, "value", "asc");
    });
    return rows;
  }

  /** Filter then sort. */
  function filterEntries(entries, opts) {
    const q = opts && opts.q ? String(opts.q).trim().toLowerCase() : "";
    const kind = opts && opts.kind ? String(opts.kind).trim() : "";
    const tagsFilter = opts && opts.tags ? String(opts.tags).trim().toLowerCase() : "";
    let rows = (entries || []).map(normalizeEntry).filter(Boolean);
    if (kind) rows = rows.filter((e) => e.kind === kind);
    if (tagsFilter) {
      const tokens = tagsFilter.split(",").map((t) => t.trim()).filter(Boolean);
      if (tokens.length) {
        rows = rows.filter((e) => {
          const hay = String(e.tags || "").toLowerCase();
          return tokens.every((t) => hay.includes(t));
        });
      }
    }
    if (q) {
      rows = rows.filter(
        (e) =>
          e.value.toLowerCase().includes(q) ||
          (e.source || "").toLowerCase().includes(q) ||
          (e.ref || "").toLowerCase().includes(q) ||
          (e.note || "").toLowerCase().includes(q) ||
          (e.tags || "").toLowerCase().includes(q) ||
          entryHost(e).includes(q)
      );
    }
    return sortEntries(rows, opts);
  }

  function paginateEntries(entries, pageIndex, pageSize) {
    const size = pageSize > 0 ? pageSize : PAGE_SIZE;
    const total = entries.length;
    const totalPages = Math.max(1, Math.ceil(total / size) || 1);
    const page = Math.min(Math.max(0, pageIndex || 0), totalPages - 1);
    const start = page * size;
    return {
      page,
      pageSize: size,
      total,
      totalPages,
      slice: entries.slice(start, start + size),
    };
  }

  function entriesToUrlLines(entries, selectedKeys) {
    const keys = selectedKeys instanceof Set ? selectedKeys : null;
    const out = [];
    for (const e of entries || []) {
      if (e.kind !== "url") continue;
      const k = entryKey(e);
      if (keys && !keys.has(k)) continue;
      out.push(e.value);
    }
    return out;
  }

  function voidSyncEntriesToServer(entries) {
    const list = (entries || []).map(normalizeEntry).filter(Boolean);
    if (!list.length || typeof fetch === "undefined") return;
    try {
      void fetch(ARCHIVE_API_BULK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          entries: list.map((e) => ({
            kind: e.kind,
            value: e.value,
            source: e.source,
            ref: e.ref,
            note: e.note,
            tags: e.tags,
            added_at: e.addedAt,
            origin: "extension",
          })),
          merge: true,
        }),
      }).catch(() => {});
    } catch (_) {}
  }

  function voidSyncEntryToServer(e) {
    voidSyncEntriesToServer([e]);
  }

  async function maybeAutoExportCheckpoint(entries) {
    const n = (entries || []).length;
    if (n < AUTO_EXPORT_EVERY) return;
    const bucket = Math.floor(n / AUTO_EXPORT_EVERY);
    if (bucket < 1) return;
    const data = await new Promise((resolve) =>
      chrome.storage.local.get([STORAGE_EXPORT_CHECKPOINT], resolve)
    );
    const prev = Number(data[STORAGE_EXPORT_CHECKPOINT]) || 0;
    if (bucket <= prev) return;
    await new Promise((resolve) =>
      chrome.storage.local.set({ [STORAGE_EXPORT_CHECKPOINT]: bucket }, resolve)
    );
    const stamp = new Date().toISOString().slice(0, 10);
    downloadText(
      `tbcc-master-archive-${bucket * AUTO_EXPORT_EVERY}-${stamp}.json`,
      exportJson(entries),
      "application/json"
    );
  }

  /** Pull server table into local master archive (merge by kind|value, newest addedAt wins). */
  async function syncFromServer() {
    if (typeof fetch === "undefined") return { ok: false, error: "fetch unavailable" };
    try {
      const resp = await fetch(ARCHIVE_API_SYNC, { method: "GET" });
      const text = await resp.text();
      let data = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch (_) {}
      if (!resp.ok) {
        return { ok: false, error: (data.detail || text || "HTTP " + resp.status).toString().slice(0, 200) };
      }
      const incoming = (data.entries || []).map((raw) =>
        normalizeEntry({
          kind: raw.kind,
          value: raw.value,
          source: raw.source,
          ref: raw.ref,
          note: raw.note,
          description: raw.description,
          tags: raw.tags,
          summary: raw.summary,
          addedAt: raw.addedAt || raw.added_at,
        })
      );
      if (!incoming.length) return { ok: true, merged: 0, total: (await getEntries()).length };
      const local = await getEntries();
      const byKey = new Map(local.map((e) => [entryKey(e), e]));
      let merged = 0;
      for (const e of incoming) {
        const k = entryKey(e);
        const cur = byKey.get(k);
        if (!cur) {
          byKey.set(k, e);
          merged++;
        } else if ((e.addedAt || 0) >= (cur.addedAt || 0)) {
          byKey.set(k, { ...cur, ...e });
          merged++;
        }
      }
      const combined = [...byKey.values()].sort((a, b) => (b.addedAt || 0) - (a.addedAt || 0));
      await writeEntries(combined);
      return { ok: true, merged, total: combined.length, pulled: incoming.length };
    } catch (e) {
      return { ok: false, error: String(e.message || e) };
    }
  }

  async function getEntries() {
    const data = await new Promise((resolve) =>
      chrome.storage.local.get([STORAGE_MASTER], resolve)
    );
    const arr = Array.isArray(data[STORAGE_MASTER]) ? data[STORAGE_MASTER] : [];
    return arr.map(normalizeEntry).filter(Boolean);
  }

  async function writeEntries(entries) {
    const capped = entries
      .map(normalizeEntry)
      .filter(Boolean)
      .slice(0, MASTER_CAP);
    await new Promise((resolve) =>
      chrome.storage.local.set(
        {
          [STORAGE_MASTER]: capped,
          [STORAGE_MASTER_BACKUP]: capped,
        },
        resolve
      )
    );
    return capped;
  }

  async function restoreFromBackupIfEmpty() {
    const data = await new Promise((resolve) =>
      chrome.storage.local.get([STORAGE_MASTER, STORAGE_MASTER_BACKUP], resolve)
    );
    const cur = Array.isArray(data[STORAGE_MASTER]) ? data[STORAGE_MASTER] : [];
    const backup = Array.isArray(data[STORAGE_MASTER_BACKUP]) ? data[STORAGE_MASTER_BACKUP] : [];
    if (!cur.length && backup.length) {
      await writeEntries(backup.map(normalizeEntry).filter(Boolean));
      return { restored: true, count: backup.length };
    }
    if (cur.length && !backup.length) {
      await new Promise((resolve) =>
        chrome.storage.local.set({ [STORAGE_MASTER_BACKUP]: cur }, resolve)
      );
    }
    return { restored: false, count: cur.length };
  }

  async function recordEntry(kind, value, opts) {
    const e = normalizeEntry({
      kind,
      value,
      addedAt: Date.now(),
      source: opts && opts.source,
      ref: opts && opts.ref,
      note: opts && opts.note,
      tags: opts && (opts.tags || opts.tagsCsv),
    });
    if (!e) return { ok: false };
    const rows = await getEntries();
    const key = entryKey(e);
    const without = rows.filter((r) => entryKey(r) !== key);
    without.unshift(e);
    await writeEntries(without);
    voidSyncEntryToServer(e);
    void maybeAutoExportCheckpoint(without);
    return { ok: true, duplicate: false };
  }

  async function recordUrl(url, opts) {
    return recordEntry("url", url, opts);
  }

  async function recordUsername(username, opts) {
    return recordEntry("username", username, opts);
  }

  async function mirrorInboxRows(rows) {
    const normalized = Array.isArray(rows) ? rows : [];
    await new Promise((resolve) =>
      chrome.storage.local.set({ [STORAGE_INBOX_MIRROR]: normalized }, resolve)
    );
  }

  async function restoreInboxFromMirrorIfEmpty(getInboxRows, setInboxRows) {
    const cur = await getInboxRows();
    if (cur.length) return { restored: false, count: 0 };
    const data = await new Promise((resolve) =>
      chrome.storage.local.get([STORAGE_INBOX_MIRROR], resolve)
    );
    const mirror = Array.isArray(data[STORAGE_INBOX_MIRROR]) ? data[STORAGE_INBOX_MIRROR] : [];
    if (!mirror.length) return { restored: false, count: 0 };
    await setInboxRows(mirror);
    return { restored: true, count: mirror.length };
  }

  function exportJson(entries) {
    return JSON.stringify(entries, null, 2);
  }

  function exportCsv(entries) {
    const lines = ["kind,value,addedAt,source,ref,note,tags"];
    for (const e of entries) {
      const esc = (s) => '"' + String(s || "").replace(/"/g, '""') + '"';
      lines.push(
        [e.kind, e.value, e.addedAt, e.source, e.ref, e.note, e.tags].map(esc).join(",")
      );
    }
    return lines.join("\n");
  }

  function exportText(entries, filterKind) {
    const rows = filterKind ? entries.filter((e) => e.kind === filterKind) : entries;
    return rows.map((e) => e.value).join("\n");
  }

  function parseImportText(text, defaultKind) {
    const raw = String(text || "").trim();
    if (!raw) return [];
    if (raw.startsWith("[") || raw.startsWith("{")) {
      try {
        const parsed = JSON.parse(raw);
        const arr = Array.isArray(parsed) ? parsed : parsed.entries || parsed.items || [];
        return arr
          .map((x) => {
            if (typeof x === "string") return normalizeEntry({ kind: defaultKind || "url", value: x });
            return normalizeEntry({
              kind: x.kind || x.type || defaultKind || "url",
              value: x.value || x.url || x.username,
              source: x.source,
              ref: x.ref,
              note: x.note,
            });
          })
          .filter(Boolean);
      } catch (_) {}
    }
    const out = [];
    const lines = raw.split(/\r?\n/);
    const looksCsv = lines[0] && /^kind\s*,/i.test(lines[0]);
    for (let i = 0; i < lines.length; i++) {
      let line = lines[i].trim();
      if (!line || line.startsWith("#")) continue;
      if (looksCsv && i === 0) continue;
      if (looksCsv) {
        const parts = line.match(/("([^"]|"")*"|[^,]*)(,|$)/g);
        if (parts && parts.length >= 2) {
          const cells = parts.map((p) =>
            p
              .replace(/,$/, "")
              .replace(/^"|"$/g, "")
              .replace(/""/g, '"')
              .trim()
          );
          const e = normalizeEntry({
            kind: cells[0] || defaultKind || "url",
            value: cells[1],
            source: cells[3],
            ref: cells[4],
            note: cells[5],
          });
          if (e) out.push(e);
          continue;
        }
      }
      if (line.includes(",")) {
        const [first, ...rest] = line.split(",");
        const e = normalizeEntry({
          kind: /^[a-zA-Z0-9._-]{2,64}$/.test(first.trim()) && !/^https?:/i.test(first)
            ? "username"
            : defaultKind || "url",
          value: first.trim(),
          note: rest.join(",").trim(),
        });
        if (e) out.push(e);
        continue;
      }
      const kind =
        /^[a-zA-Z0-9._-]{2,64}$/.test(line) && !/^https?:/i.test(line)
          ? "username"
          : defaultKind || "url";
      const e = normalizeEntry({ kind, value: line });
      if (e) out.push(e);
    }
    return out;
  }

  async function importEntries(parsed, merge) {
    const incoming = (parsed || []).map(normalizeEntry).filter(Boolean);
    if (!incoming.length) return { ok: false, error: "No valid entries.", added: 0 };
    let rows = merge ? await getEntries() : [];
    const keys = new Set(rows.map(entryKey));
    let added = 0;
    for (const e of incoming) {
      const k = entryKey(e);
      if (keys.has(k)) continue;
      keys.add(k);
      rows.unshift(e);
      added++;
    }
    await writeEntries(rows);
    voidSyncEntriesToServer(incoming);
    void maybeAutoExportCheckpoint(rows);
    return { ok: true, added, total: rows.length };
  }

  async function clearArchive() {
    await new Promise((resolve) =>
      chrome.storage.local.set({ [STORAGE_MASTER]: [], [STORAGE_MASTER_BACKUP]: [] }, resolve)
    );
  }

  function downloadText(filename, text, mime) {
    const blob = new Blob([text], { type: mime || "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  /** @param {string} [idSuffix] '' for gallery sheet, 'Opts' for extension options page */
  function readSortOptsFromDom(idSuffix) {
    const sfx = idSuffix || "";
    const sortBy = document.getElementById("masterArchiveSort1" + sfx);
    const sortDir = document.getElementById("masterArchiveSort1Dir" + sfx);
    const sortBy2 = document.getElementById("masterArchiveSort2" + sfx);
    const sortDir2 = document.getElementById("masterArchiveSort2Dir" + sfx);
    return {
      sortBy: (sortBy && sortBy.value) || "addedAt",
      sortDir: (sortDir && sortDir.value) || "desc",
      sortBy2: (sortBy2 && sortBy2.value) || "",
      sortDir2: (sortDir2 && sortDir2.value) || "asc",
    };
  }

  global.TbccMasterArchive = {
    STORAGE_MASTER,
    STORAGE_MASTER_BACKUP,
    STORAGE_INBOX_MIRROR,
    MASTER_CAP,
    PAGE_SIZE,
    ARCHIVE_API_BULK,
    ARCHIVE_API_SYNC,
    AUTO_EXPORT_EVERY,
    syncFromServer,
    voidSyncEntriesToServer,
    maybeAutoExportCheckpoint,
    normalizeEntry,
    entryKey,
    formatEntryMeta,
    formatEntryWhen,
    SORT_FIELDS,
    readSortOptsFromDom,
    entryHost,
    sortEntries,
    filterEntries,
    paginateEntries,
    entriesToUrlLines,
    getEntries,
    writeEntries,
    restoreFromBackupIfEmpty,
    recordEntry,
    recordUrl,
    recordUsername,
    mirrorInboxRows,
    restoreInboxFromMirrorIfEmpty,
    exportJson,
    exportCsv,
    exportText,
    parseImportText,
    importEntries,
    clearArchive,
    downloadText,
  };
})(typeof globalThis !== "undefined" ? globalThis : self);
