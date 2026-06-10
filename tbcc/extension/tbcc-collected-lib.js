/**
 * Collected gallery staging store (chrome.storage.local tbcc_collected).
 * Shared by gallery.js and gallery-view.html.
 */
(function (global) {
  const STORAGE_COLLECTED = "tbcc_collected";
  const COLLECTED_CAP = 200;

  function collectedItemKey(it) {
    return String((it && it.url) || "").trim();
  }

  function parseTagsCsv(csv) {
    return String(csv || "")
      .split(/[,;]+/)
      .map((t) => t.trim().replace(/^#+/, ""))
      .filter((t) => t.length >= 2 && t.length <= 64);
  }

  function normalizeCollectedItem(raw) {
    const url = collectedItemKey(raw);
    if (!/^https?:\/\//i.test(url) && !String(url).startsWith("blob:") && !String(url).startsWith("data:"))
      return null;
    let sourceHost = "";
    try {
      if (/^https?:\/\//i.test(url)) sourceHost = new URL(url).hostname.replace(/^www\./, "");
    } catch (_) {}
    const tags = Array.isArray(raw && raw.tags)
      ? raw.tags.map((t) => String(t).trim()).filter(Boolean)
      : parseTagsCsv(raw && raw.tagsCsv);
    const mediaType =
      raw && raw.mediaType
        ? String(raw.mediaType)
        : /\.(mp4|webm|m3u8|mpd|mov|m4v)(\?|$)/i.test(url.toLowerCase())
          ? "video"
          : "image";
    return {
      url,
      thumbUrl: raw && raw.thumbUrl ? String(raw.thumbUrl) : "",
      mediaType,
      tagName: raw && raw.tagName ? String(raw.tagName) : mediaType === "video" ? "video" : "img",
      tabId: raw && raw.tabId != null && raw.tabId !== "" ? Number(raw.tabId) : null,
      tbccSourcePageUrl:
        raw && raw.tbccSourcePageUrl
          ? String(raw.tbccSourcePageUrl)
          : raw && raw.sourcePageUrl
            ? String(raw.sourcePageUrl)
            : "",
      detailPageUrl: raw && raw.detailPageUrl ? String(raw.detailPageUrl) : "",
      name: raw && raw.name ? String(raw.name) : "",
      sourceHost: raw && raw.sourceHost ? String(raw.sourceHost) : sourceHost,
      tags,
      tagsCsv: tags.join(", "),
      note: raw && raw.note ? String(raw.note).slice(0, 400) : "",
      collectionId: raw && raw.collectionId ? String(raw.collectionId) : "",
      collectionLabel: raw && raw.collectionLabel ? String(raw.collectionLabel).slice(0, 80) : "",
      addedAt: Number(raw && raw.addedAt ? raw.addedAt : Date.now()) || Date.now(),
      staged: !!(raw && raw.staged),
      fromSend: !!(raw && raw.fromSend),
      media_id: raw && raw.media_id != null ? raw.media_id : null,
      to_saved: !!(raw && raw.to_saved),
    };
  }

  function fromGalleryItem(it, extras) {
    const e = extras || {};
    const url = collectedItemKey(it);
    if (!url) return null;
    let sourceHost = "";
    try {
      if (/^https?:\/\//i.test(url)) sourceHost = new URL(url).hostname.replace(/^www\./, "");
    } catch (_) {}
    const mediaType =
      (it && (it.mediaType || it.tagName || "")).toLowerCase() === "video" ||
      String(it && it.tagName || "").toLowerCase() === "video"
        ? "video"
        : "image";
    return normalizeCollectedItem({
      url,
      thumbUrl: (it && it.thumbUrl) || "",
      mediaType,
      tagName: (it && it.tagName) || "",
      tabId: it && it.tabId != null ? it.tabId : null,
      tbccSourcePageUrl: (it && it.tbccSourcePageUrl) || "",
      detailPageUrl: (it && it.detailPageUrl) || "",
      name: (it && it.name) || "",
      sourceHost,
      tags: e.tags || [],
      tagsCsv: e.tagsCsv || "",
      note: e.note || "",
      collectionId: e.collectionId || "",
      collectionLabel: e.collectionLabel || "",
      addedAt: Date.now(),
      staged: true,
      fromSend: false,
    });
  }

  async function getItems() {
    const raw = await new Promise((resolve) =>
      chrome.storage.local.get(STORAGE_COLLECTED, (o) => resolve(o[STORAGE_COLLECTED]))
    );
    const arr = Array.isArray(raw) ? raw : [];
    return arr.map(normalizeCollectedItem).filter(Boolean);
  }

  async function setItems(items) {
    const norm = items.map(normalizeCollectedItem).filter(Boolean).slice(0, COLLECTED_CAP);
    await new Promise((resolve) => chrome.storage.local.set({ [STORAGE_COLLECTED]: norm }, resolve));
    return norm;
  }

  /** Append items; skip duplicate URLs (newer metadata wins on same url). */
  async function appendItems(newItems) {
    const incoming = newItems.map(normalizeCollectedItem).filter(Boolean);
    if (!incoming.length) return { added: 0, total: 0 };
    const existing = await getItems();
    const byUrl = new Map();
    for (const it of existing) byUrl.set(collectedItemKey(it), it);
    let added = 0;
    for (const it of incoming) {
      const k = collectedItemKey(it);
      if (!k) continue;
      const had = byUrl.has(k);
      const prev = byUrl.get(k);
      const merged = prev
        ? normalizeCollectedItem({
            ...prev,
            ...it,
            tags: [...new Set([...(prev.tags || []), ...(it.tags || [])])],
            addedAt: it.addedAt || prev.addedAt,
          })
        : it;
      byUrl.set(k, merged);
      if (!had) added++;
    }
    const merged = [...byUrl.values()].sort((a, b) => b.addedAt - a.addedAt).slice(0, COLLECTED_CAP);
    await setItems(merged);
    return { added, total: merged.length };
  }

  async function removeKeys(keys) {
    const drop = new Set(keys);
    const kept = (await getItems()).filter((it) => !drop.has(collectedItemKey(it)));
    await setItems(kept);
    return kept.length;
  }

  function listCollectionLabels(items) {
    const map = new Map();
    for (const it of items) {
      const id = it.collectionId || "";
      const label = it.collectionLabel || (id ? id.replace(/^batch_/, "Batch ") : "");
      if (!id && !label) continue;
      const key = id || label;
      if (!map.has(key)) map.set(key, { id, label: label || id, count: 0 });
      map.get(key).count++;
    }
    return [...map.values()].sort((a, b) => b.count - a.count);
  }

  global.TbccCollected = {
    STORAGE_COLLECTED,
    COLLECTED_CAP,
    collectedItemKey,
    normalizeCollectedItem,
    fromGalleryItem,
    parseTagsCsv,
    getItems,
    setItems,
    appendItems,
    removeKeys,
    listCollectionLabels,
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
