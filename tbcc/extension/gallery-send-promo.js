/**
 * Gallery batch send-promo: tail image on Saved Messages / channel album sends.
 * Settings: GET /gallery-send-promo/extension-payload
 */
(function (global) {
  const API_BASE = "http://localhost:8000";
  const STORAGE_SHOW = "tbccShowSendPromoStrip";
  const STORAGE_BODY_EXPANDED = "tbccSendPromoStripBodyExpanded";
  const STORAGE_ON_SEND = "tbccSendPromoOnSend";
  const STORAGE_ACTIVE = "tbccSendPromoActiveId";

  let payloadCache = null;
  let payloadAt = 0;

  function $(id) {
    return document.getElementById(id);
  }

  async function fetchPayload(force) {
    const now = Date.now();
    if (!force && payloadCache && now - payloadAt < 15000) return payloadCache;
    try {
      const r = await fetch(API_BASE + "/gallery-send-promo/extension-payload", { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      payloadCache = await r.json();
      payloadAt = now;
      return payloadCache;
    } catch (_) {
      return { enabled: false, images: [], active_image: null };
    }
  }

  async function getActiveImage() {
    const p = await fetchPayload(false);
    if (!p || !p.enabled) return null;
    const local = await chrome.storage.local.get([STORAGE_ACTIVE]);
    const override = (local[STORAGE_ACTIVE] || "").trim();
    const images = Array.isArray(p.images) ? p.images : [];
    if (override) {
      const hit = images.find((i) => i.id === override);
      if (hit) return hit;
    }
    if (p.active_image && p.active_image.url) return p.active_image;
    return images[0] || null;
  }

  async function shouldAppendTail() {
    try {
      const local = await chrome.storage.local.get([STORAGE_ON_SEND]);
      if (local[STORAGE_ON_SEND] === false) return false;
    } catch (_) {}
    const img = await getActiveImage();
    return !!(img && img.url);
  }

  async function fetchActiveBlob() {
    const img = await getActiveImage();
    if (!img || !img.url) return null;
    try {
      const r = await fetch(img.url, { cache: "no-store" });
      if (!r.ok) return null;
      const blob = await r.blob();
      if (!blob || !blob.size) return null;
      const name = (img.filename || "tbcc_send_promo.jpg").split("/").pop();
      return { blob, name: name || "tbcc_send_promo.jpg", label: img.label || "" };
    } catch (_) {
      return null;
    }
  }

  function applyStripBodyExpanded(expanded) {
    const wrap = $("sendPromoStripWrap");
    const body = $("sendPromoStripBody");
    const chevron = $("btnSendPromoStripExpand");
    if (!wrap || !body) return;
    const on = !!expanded;
    wrap.classList.toggle("is-body-expanded", on);
    body.hidden = !on;
    if (chevron) {
      chevron.setAttribute("aria-expanded", on ? "true" : "false");
      chevron.title = on ? "Hide promo image tiles" : "Show promo image tiles";
    }
  }

  function updateStripCountBadge() {
    const el = $("sendPromoStripCount");
    if (!el) return;
    const p = payloadCache || { images: [] };
    const n = Array.isArray(p.images) ? p.images.length : 0;
    if (n > 0) {
      el.hidden = false;
      el.textContent = n + (n === 1 ? " image" : " images");
    } else {
      el.hidden = true;
      el.textContent = "";
    }
  }

  async function loadStripBodyExpanded() {
    try {
      const local = await chrome.storage.local.get([STORAGE_BODY_EXPANDED]);
      return local[STORAGE_BODY_EXPANDED] === true;
    } catch (_) {
      return false;
    }
  }

  function setStripBodyExpanded(expanded, persist) {
    applyStripBodyExpanded(expanded);
    if (persist !== false) {
      try {
        chrome.storage.local.set({ [STORAGE_BODY_EXPANDED]: !!expanded });
      } catch (_) {}
    }
  }

  function renderStrip() {
    const wrap = $("sendPromoStripWrap");
    const strip = $("sendPromoStrip");
    if (!wrap || !strip) return;
    const p = payloadCache || { enabled: false, images: [] };
    updateStripCountBadge();
    strip.innerHTML = "";
    if (!p.enabled || !p.images || !p.images.length) {
      const empty = document.createElement("p");
      empty.className = "send-promo-strip-empty";
      empty.textContent =
        "Upload promo tiles (logo, profile card) — pick one for the batch send tail.";
      strip.appendChild(empty);
      return;
    }
    chrome.storage.local.get([STORAGE_ACTIVE], (local) => {
      const activeId = (local[STORAGE_ACTIVE] || p.active_image_id || "").trim();
      p.images.forEach((img) => {
        const tile = document.createElement("button");
        tile.type = "button";
        tile.className = "send-promo-tile" + (img.id === activeId ? " is-active" : "");
        tile.title = (img.label || "Promo") + " — click to use on send";
        const el = document.createElement("img");
        el.src = img.url;
        el.alt = img.label || "Promo";
        tile.appendChild(el);
        if (img.label) {
          const cap = document.createElement("span");
          cap.className = "send-promo-tile__label";
          cap.textContent = img.label;
          tile.appendChild(cap);
        }
        tile.addEventListener("click", () => {
          chrome.storage.local.set({ [STORAGE_ACTIVE]: img.id }, () => {
            payloadCache = { ...p, active_image_id: img.id, active_image: img };
            renderStrip();
          });
        });
        const del = document.createElement("button");
        del.type = "button";
        del.className = "send-promo-tile__del";
        del.title = "Remove";
        del.textContent = "×";
        del.addEventListener("click", (e) => {
          e.stopPropagation();
          void deleteImage(img.id);
        });
        tile.appendChild(del);
        strip.appendChild(tile);
      });
    });
  }

  async function refresh(force) {
    payloadCache = await fetchPayload(!!force);
    const wrap = $("sendPromoStripWrap");
    if (!wrap) return payloadCache;
    try {
      const local = await chrome.storage.local.get([STORAGE_SHOW]);
      wrap.hidden = local[STORAGE_SHOW] !== true;
    } catch (_) {
      wrap.hidden = true;
    }
    renderStrip();
    if (!wrap.hidden) {
      const expanded = await loadStripBodyExpanded();
      applyStripBodyExpanded(expanded);
    }
    syncCheckboxes();
    return payloadCache;
  }

  function syncCheckboxes() {
    const on = payloadCache && payloadCache.enabled;
    ["sendPromoOnSend", "sendPromoOnSendSheet"].forEach((id) => {
      const el = $(id);
      if (!el) return;
      chrome.storage.local.get([STORAGE_ON_SEND], (local) => {
        el.checked = local[STORAGE_ON_SEND] !== false && on !== false;
        el.disabled = !on;
      });
    });
  }

  function bindUi() {
    const toggle = $("btnToggleSendPromoStrip");
    const uploadBtn = $("btnSendPromoUpload");
    const fileInput = $("sendPromoFileInput");
    const bindOnSend = (id) => {
      const el = $(id);
      if (!el) return;
      el.addEventListener("change", () => {
        chrome.storage.local.set({ [STORAGE_ON_SEND]: !!el.checked });
      });
    };
    bindOnSend("sendPromoOnSend");
    bindOnSend("sendPromoOnSendSheet");

    const chevron = $("btnSendPromoStripExpand");
    if (chevron) {
      chevron.addEventListener("click", () => {
        const wrap = $("sendPromoStripWrap");
        const expanded = !!(wrap && wrap.classList.contains("is-body-expanded"));
        setStripBodyExpanded(!expanded);
      });
    }

    if (toggle) {
      toggle.addEventListener("click", () => {
        chrome.storage.local.get([STORAGE_SHOW], (local) => {
          const next = local[STORAGE_SHOW] !== true;
          chrome.storage.local.set({ [STORAGE_SHOW]: next }, () => {
            const wrap = $("sendPromoStripWrap");
            if (wrap) wrap.hidden = !next;
            toggle.classList.toggle("is-active", next);
            if (next) {
              void refresh(true).then(async () => {
                const expanded = await loadStripBodyExpanded();
                applyStripBodyExpanded(expanded);
              });
            } else {
              applyStripBodyExpanded(false);
            }
          });
        });
      });
    }
    if (uploadBtn && fileInput) {
      uploadBtn.addEventListener("click", () => fileInput.click());
      fileInput.addEventListener("change", () => {
        const f = fileInput.files && fileInput.files[0];
        fileInput.value = "";
        if (f) void uploadImage(f);
      });
    }
  }

  async function uploadImage(file) {
    const form = new FormData();
    form.append("file", file, file.name || "promo.jpg");
    try {
      const r = await fetch(API_BASE + "/gallery-send-promo/images", { method: "POST", body: form });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || r.statusText);
      payloadCache = data.settings;
      payloadAt = Date.now();
      if (data.image && data.image.id) {
        chrome.storage.local.set({ [STORAGE_ACTIVE]: data.image.id });
      }
      renderStrip();
      setStripBodyExpanded(true);
      if (global.showToast) global.showToast("Promo image uploaded.", "info");
    } catch (e) {
      if (global.showToast) global.showToast((e && e.message) || "Upload failed", "error");
    }
  }

  async function deleteImage(imageId) {
    try {
      const r = await fetch(API_BASE + "/gallery-send-promo/images/" + encodeURIComponent(imageId), {
        method: "DELETE",
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || r.statusText);
      payloadCache = data.settings;
      payloadAt = Date.now();
      renderStrip();
    } catch (e) {
      if (global.showToast) global.showToast((e && e.message) || "Delete failed", "error");
    }
  }

  const TELEGRAM_ALBUM_MAX = 10;

  function planAlbumBatchSizes(batchCount, includePromoTail, maxSize) {
    const n = Math.max(0, Number(batchCount) || 0);
    const max = Math.max(1, Number(maxSize) || TELEGRAM_ALBUM_MAX);
    if (!includePromoTail) {
      if (n === 0) return [];
      const sizes = [];
      for (let i = 0; i < n; i += max) sizes.push(Math.min(max, n - i));
      return sizes;
    }
    if (n === 0) return [0];
    const k = Math.ceil((n + 1) / max);
    const sizes = [];
    let i = 0;
    for (let albumIdx = 0; albumIdx < k; albumIdx++) {
      const isLast = albumIdx === k - 1;
      if (isLast) {
        sizes.push(n - i);
      } else {
        let take = max;
        const prefixFull = (k - 1) * max;
        const remainder = n - prefixFull;
        if (albumIdx === k - 2 && remainder === 0) take = max - 1;
        sizes.push(take);
        i += take;
      }
    }
    return sizes;
  }

  class AlbumSendPlanner {
    constructor(batchCount, includePromo, maxSize) {
      this.includePromo = !!includePromo;
      this.maxSize = maxSize || TELEGRAM_ALBUM_MAX;
      if (!this.includePromo) {
        this.sizes = planAlbumBatchSizes(batchCount, false, this.maxSize);
      } else {
        this.sizes = planAlbumBatchSizes(batchCount, true, this.maxSize);
      }
      this.idx = 0;
      this.pos = 0;
    }

    take(available) {
      const left = Math.max(0, Number(available) || 0);
      if (!left) return 0;
      if (!this.sizes.length) return Math.min(this.maxSize, left);
      if (this.idx >= this.sizes.length) return Math.min(this.maxSize, left);
      const need = this.sizes[this.idx] - this.pos;
      return Math.min(need, left);
    }

    appendPromoAfterChunk(take) {
      if (!this.includePromo || this.idx >= this.sizes.length) return false;
      const isLast = this.idx === this.sizes.length - 1;
      const completes = this.pos + take >= this.sizes[this.idx];
      return isLast && completes;
    }

    advance(take) {
      if (!this.sizes.length) return;
      this.pos += take;
      if (this.pos >= this.sizes[this.idx]) {
        this.idx += 1;
        this.pos = 0;
      }
    }

    needsPromoOnlySend() {
      return this.includePromo && this.sizes.length === 1 && this.sizes[0] === 0;
    }
  }

  function sliceNextAlbumChunk(items, start, planner) {
    const take = planner.take(items.length - start);
    if (take <= 0) return { chunk: [], next: start, appendPromo: false };
    const chunk = items.slice(start, start + take);
    const appendPromo = planner.appendPromoAfterChunk(take);
    planner.advance(take);
    return { chunk, next: start + take, appendPromo };
  }

  async function prepareAlbumTail() {
    if (!(await shouldAppendTail())) return { pack: null, pending: false, planner: null };
    const pack = await fetchActiveBlob();
    return {
      pack,
      pending: !!pack,
      planner: null,
    };
  }

  function createAlbumSendPlanner(batchCount, includePromo) {
    return new AlbumSendPlanner(batchCount, includePromo, TELEGRAM_ALBUM_MAX);
  }

  async function sendSavedTail(poolId, appendCaptionToForm, appendErr, bump) {
    if (!(await shouldAppendTail())) return false;
    const pack = await fetchActiveBlob();
    if (!pack) return false;
    const form = new FormData();
    form.append("files", pack.blob, pack.name);
    if (typeof appendCaptionToForm === "function") appendCaptionToForm(form, "");
    try {
      const r = await fetch(API_BASE + "/import/saved-batch", { method: "POST", body: form });
      const text = await r.text();
      let data = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch (_) {}
      if (data.status === "saved_only" && !data.error) {
        if (typeof bump === "function") bump();
        if (global.showToast) global.showToast("Send promo tile sent.", "info");
        return true;
      }
      if (appendErr) appendErr(data.error || "Send promo tail failed");
    } catch (e) {
      if (appendErr) appendErr((e && e.message) || "Send promo tail failed");
    }
    return false;
  }

  async function importMediaId(poolId) {
    if (!(await shouldAppendTail())) return null;
    const pack = await fetchActiveBlob();
    if (!pack) return null;
    const form = new FormData();
    form.append("file", pack.blob, pack.name);
    form.append("pool_id", String(poolId));
    form.append("saved_only", "false");
    form.append("source", "extension:send-promo");
    try {
      const r = await fetch(API_BASE + "/import/bytes", { method: "POST", body: form });
      const text = await r.text();
      let data = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch (_) {}
      if (data.media_id) return data.media_id;
    } catch (_) {}
    return null;
  }

  global.TbccSendPromo = {
    refresh,
    shouldAppend: shouldAppendTail,
    prepareAlbumTail,
    createAlbumSendPlanner,
    sliceNextAlbumChunk,
    planAlbumBatchSizes,
    sendSavedTail,
    importMediaId,
    bindUi,
    TELEGRAM_ALBUM_MAX,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindUi);
  } else {
    bindUi();
  }
})(typeof window !== "undefined" ? window : globalThis);
