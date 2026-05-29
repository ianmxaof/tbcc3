/**
 * Gallery batch send-promo: tail image on Saved Messages / channel album sends.
 * Settings: GET /gallery-send-promo/extension-payload
 */
(function (global) {
  const API_BASE = "http://localhost:8000";
  const STORAGE_SHOW = "tbccShowSendPromoStrip";
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

  function renderStrip() {
    const wrap = $("sendPromoStripWrap");
    const strip = $("sendPromoStrip");
    if (!wrap || !strip) return;
    const p = payloadCache || { enabled: false, images: [] };
    strip.innerHTML = "";
    if (!p.enabled || !p.images || !p.images.length) {
      const empty = document.createElement("p");
      empty.className = "send-promo-strip-empty";
      empty.textContent = "Upload a promo tile (logo, profile card) — appended last on each batch send.";
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

    if (toggle) {
      toggle.addEventListener("click", () => {
        chrome.storage.local.get([STORAGE_SHOW], (local) => {
          const next = local[STORAGE_SHOW] !== true;
          chrome.storage.local.set({ [STORAGE_SHOW]: next }, () => {
            const wrap = $("sendPromoStripWrap");
            if (wrap) wrap.hidden = !next;
            toggle.classList.toggle("is-active", next);
            if (next) void refresh(true);
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
        if (global.showToast) global.showToast("Send promo tile appended.", "info");
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
    sendSavedTail,
    importMediaId,
    bindUi,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindUi);
  } else {
    bindUi();
  }
})(typeof window !== "undefined" ? window : globalThis);
