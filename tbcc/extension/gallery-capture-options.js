/* global chrome */
/** Sync gallery capture settings (same storage as gallery.js `tbcc_gallery_settings`). */
(function () {
  const STORAGE_SETTINGS = "tbcc_gallery_settings";
  const STORAGE_COLLECTED = "tbcc_collected";
  const STORAGE_PAGE_MEDIA_MENU = "tbccPageMediaMenuEnabled";

  const elFormat = document.getElementById("captureSettingFormat");
  const elAuto = document.getElementById("captureSettingAutoRefresh");
  const elHard = document.getElementById("captureSettingHardRefresh");
  const elRt = document.getElementById("captureSettingResourceTiming");
  const elLazy = document.getElementById("captureSettingLazyDelay");
  const elPageMediaMenu = document.getElementById("captureSettingPageMediaMenu");
  const elClearSelOnOpen = document.getElementById("captureSettingClearSelectionOnOpen");
  const elNotifySystem = document.getElementById("captureSettingNotifySystem");
  const elNotifyZip = document.getElementById("captureSettingNotifyZip");
  const elZipPromo = document.getElementById("captureSettingZipPromo");
  const elNotifySendTbcc = document.getElementById("captureSettingNotifySendTbcc");
  const elNotifySendSaved = document.getElementById("captureSettingNotifySendSaved");
  const elNotifySendChannel = document.getElementById("captureSettingNotifySendChannel");
  const elNotificationStyle = document.getElementById("captureSettingNotificationStyle");
  const elDownloadMode = document.getElementById("captureSettingDownloadMode");
  const elWmEnabled = document.getElementById("captureSettingPromoWatermarkEnabled");
  const elWmText = document.getElementById("captureSettingWmText");
  const elWmText2 = document.getElementById("captureSettingWmText2");
  const elWmText3 = document.getElementById("captureSettingWmText3");
  const elWmOpacity = document.getElementById("captureSettingWmOpacity");
  const elWmOpacityVal = document.getElementById("captureSettingWmOpacityVal");
  const elWmSizeRatio = document.getElementById("captureSettingWmSizeRatio");
  const elWmColor = document.getElementById("captureSettingWmColor");
  const elWmColorHex = document.getElementById("captureSettingWmColorHex");
  const elWmPosition = document.getElementById("captureSettingWmPosition");
  const elWmMode = document.getElementById("captureSettingWmMode");
  const elWmStripPrevious = document.getElementById("captureSettingWmStripPrevious");
  const elZipHeuristic = document.getElementById("captureSettingZipHeuristic");
  const elZipBundleTemplate = document.getElementById("captureSettingZipBundleTemplate");
  const elZipEntryTemplate = document.getElementById("captureSettingZipEntryTemplate");
  const btnClear = document.getElementById("captureSettingClearCache");
  const apiStatus = document.getElementById("tbccApiStatus");

  function mergeSave(partial) {
    return new Promise((resolve) => {
      chrome.storage.local.get(STORAGE_SETTINGS, (o) => {
        const cur = (o[STORAGE_SETTINGS] && typeof o[STORAGE_SETTINGS] === "object") ? o[STORAGE_SETTINGS] : {};
        const next = { ...cur, ...partial };
        chrome.storage.local.set({ [STORAGE_SETTINGS]: next }, resolve);
      });
    });
  }

  function normalizeWmFromStorage(s) {
    const PW = typeof TbccPromoWatermark !== "undefined" ? TbccPromoWatermark : null;
    const raw = (s && s.promoWatermark) || {};
    let wm = PW ? PW.normalizePromoWatermark(raw) : raw;
    if (s && s.skipPromoWatermark === true) wm = { ...wm, enabled: false };
    return wm;
  }

  function readWmFromForm() {
    const opacity = elWmOpacity ? Number(elWmOpacity.value) : 0.58;
    const sizePct = elWmSizeRatio ? Number(elWmSizeRatio.value) : 4.5;
    const color = (elWmColorHex && elWmColorHex.value.trim()) || (elWmColor && elWmColor.value) || "#ffffff";
    return {
      enabled: elWmEnabled ? !!elWmEnabled.checked : true,
      text: (elWmText && elWmText.value.trim()) || "telegram.me/aofmainhub",
      textSecondary: (elWmText2 && elWmText2.value.trim()) || "",
      textTertiary: (elWmText3 && elWmText3.value.trim()) || "",
      opacity: Number.isFinite(opacity) ? opacity : 0.58,
      color,
      position: (elWmPosition && elWmPosition.value) || "bottom_right",
      mode: (elWmMode && elWmMode.value) || "rotate",
      sizeRatio: Number.isFinite(sizePct) ? Math.max(1.2, Math.min(8, sizePct)) / 100 : 0.045,
      stripPrevious: !!(elWmStripPrevious && elWmStripPrevious.checked),
    };
  }

  function applyWmToForm(wm) {
    const w = typeof TbccPromoWatermark !== "undefined" ? TbccPromoWatermark.normalizePromoWatermark(wm) : wm;
    if (elWmEnabled) elWmEnabled.checked = w.enabled !== false;
    if (elWmText) elWmText.value = w.text || "";
    if (elWmText2) elWmText2.value = w.textSecondary || "";
    if (elWmText3) elWmText3.value = w.textTertiary || "";
    if (elWmOpacity) elWmOpacity.value = String(w.opacity != null ? w.opacity : 0.58);
    if (elWmOpacityVal) elWmOpacityVal.textContent = Number(w.opacity != null ? w.opacity : 0.58).toFixed(2);
    if (elWmSizeRatio) elWmSizeRatio.value = String(((w.sizeRatio != null ? w.sizeRatio : 0.045) * 100).toFixed(1));
    const col = w.color || "#ffffff";
    if (elWmColor) elWmColor.value = col.startsWith("#") ? col : "#ffffff";
    if (elWmColorHex) elWmColorHex.value = col;
    if (elWmPosition) elWmPosition.value = w.position || "bottom_right";
    if (elWmMode) elWmMode.value = w.mode === "fixed" ? "fixed" : "rotate";
    if (elWmStripPrevious) elWmStripPrevious.checked = !!w.stripPrevious;
  }

  async function savePromoWatermark() {
    const promoWatermark =
      typeof TbccPromoWatermark !== "undefined"
        ? TbccPromoWatermark.normalizePromoWatermark(readWmFromForm())
        : readWmFromForm();
    await mergeSave({
      promoWatermark,
      skipPromoWatermark: !promoWatermark.enabled,
    });
    if (typeof tbccFetchApi === "function" && typeof TbccPromoWatermark !== "undefined") {
      try {
        const payload = TbccPromoWatermark.configToApiPayload(promoWatermark);
        await tbccFetchApi("/watermark-settings", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            enabled: payload.enabled,
            text_primary: payload.text,
            text_secondary: payload.text_secondary,
            text_tertiary: payload.text_tertiary,
            opacity: payload.opacity,
            color: payload.color,
            strip_previous: payload.strip_previous,
          }),
        });
      } catch (_) {}
    }
  }

  async function load() {
    const o = await new Promise((r) => chrome.storage.local.get([STORAGE_SETTINGS, STORAGE_PAGE_MEDIA_MENU], r));
    const s = o[STORAGE_SETTINGS] || {};
    if (elFormat) elFormat.value = s.format === "jpeg" ? "jpeg" : "original";
    if (elAuto) elAuto.checked = s.autoRefresh !== false;
    if (elHard) elHard.checked = s.refreshHard !== false;
    if (elRt) elRt.checked = s.resourceTimingAllImages === true;
    if (elClearSelOnOpen) elClearSelOnOpen.checked = s.clearSelectionOnOpen === true;
    if (elNotifySystem) elNotifySystem.checked = s.notifyUseSystem !== false;
    if (elNotifyZip) elNotifyZip.checked = s.notifyOnZipComplete !== false;
    const zipPromo = await new Promise((r) => chrome.storage.local.get(["tbccZipPromoInGallery"], r));
    if (elZipPromo) elZipPromo.checked = zipPromo.tbccZipPromoInGallery !== false;
    if (elNotifySendTbcc) elNotifySendTbcc.checked = s.notifyOnSendTbccComplete !== false;
    if (elNotifySendSaved) elNotifySendSaved.checked = s.notifyOnSendSavedComplete !== false;
    if (elNotifySendChannel) elNotifySendChannel.checked = s.notifyOnSendChannelComplete !== false;
    if (elNotificationStyle) elNotificationStyle.value = s.notificationStyle || "full";
    if (elDownloadMode) elDownloadMode.value = s.downloadMode === "direct" ? "direct" : "buffered";
    applyWmToForm(normalizeWmFromStorage(s));
    if (elZipHeuristic) elZipHeuristic.checked = s.zipHeuristicNaming !== false;
    if (elZipBundleTemplate) elZipBundleTemplate.value = s.zipBundleTemplate || "";
    if (elZipEntryTemplate) elZipEntryTemplate.value = s.zipEntryTemplate || "";
    if (elPageMediaMenu) elPageMediaMenu.checked = o[STORAGE_PAGE_MEDIA_MENU] !== false;
    if (elLazy) {
      const d = parseInt(String(s.captureLazyDelayMs || 0), 10);
      elLazy.value = String(isNaN(d) ? 0 : Math.max(0, Math.min(3000, d)));
    }
  }

  if (elFormat)
    elFormat.addEventListener("change", () => mergeSave({ format: elFormat.value }));
  if (elAuto)
    elAuto.addEventListener("change", () => mergeSave({ autoRefresh: !!elAuto.checked }));
  if (elHard)
    elHard.addEventListener("change", () => mergeSave({ refreshHard: !!elHard.checked }));
  if (elRt)
    elRt.addEventListener("change", () => mergeSave({ resourceTimingAllImages: !!elRt.checked }));
  if (elClearSelOnOpen)
    elClearSelOnOpen.addEventListener("change", () => mergeSave({ clearSelectionOnOpen: !!elClearSelOnOpen.checked }));
  if (elNotifySystem)
    elNotifySystem.addEventListener("change", () => mergeSave({ notifyUseSystem: !!elNotifySystem.checked }));
  if (elNotifyZip)
    elNotifyZip.addEventListener("change", () => mergeSave({ notifyOnZipComplete: !!elNotifyZip.checked }));
  if (elZipPromo)
    elZipPromo.addEventListener("change", () =>
      chrome.storage.local.set({ tbccZipPromoInGallery: !!elZipPromo.checked })
    );
  if (elNotifySendTbcc)
    elNotifySendTbcc.addEventListener("change", () => mergeSave({ notifyOnSendTbccComplete: !!elNotifySendTbcc.checked }));
  if (elNotifySendSaved)
    elNotifySendSaved.addEventListener("change", () => mergeSave({ notifyOnSendSavedComplete: !!elNotifySendSaved.checked }));
  if (elNotifySendChannel)
    elNotifySendChannel.addEventListener("change", () => mergeSave({ notifyOnSendChannelComplete: !!elNotifySendChannel.checked }));
  if (elNotificationStyle)
    elNotificationStyle.addEventListener("change", () => mergeSave({ notificationStyle: elNotificationStyle.value || "full" }));
  if (elDownloadMode)
    elDownloadMode.addEventListener("change", () =>
      mergeSave({ downloadMode: elDownloadMode.value === "direct" ? "direct" : "buffered" })
    );
  if (elWmEnabled) elWmEnabled.addEventListener("change", () => void savePromoWatermark());
  if (elWmText) elWmText.addEventListener("change", () => void savePromoWatermark());
  if (elWmText2) elWmText2.addEventListener("change", () => void savePromoWatermark());
  if (elWmText3) elWmText3.addEventListener("change", () => void savePromoWatermark());
  if (elWmOpacity)
    elWmOpacity.addEventListener("input", () => {
      if (elWmOpacityVal) elWmOpacityVal.textContent = Number(elWmOpacity.value).toFixed(2);
    });
  if (elWmOpacity) elWmOpacity.addEventListener("change", () => void savePromoWatermark());
  if (elWmSizeRatio) elWmSizeRatio.addEventListener("change", () => void savePromoWatermark());
  if (elWmColor)
    elWmColor.addEventListener("input", () => {
      if (elWmColorHex) elWmColorHex.value = elWmColor.value;
    });
  if (elWmColor) elWmColor.addEventListener("change", () => void savePromoWatermark());
  if (elWmColorHex)
    elWmColorHex.addEventListener("change", () => {
      if (elWmColor && /^#[0-9a-f]{3,6}$/i.test(elWmColorHex.value.trim())) {
        elWmColor.value = elWmColorHex.value.trim();
      }
      void savePromoWatermark();
    });
  if (elWmPosition) elWmPosition.addEventListener("change", () => void savePromoWatermark());
  if (elWmMode) elWmMode.addEventListener("change", () => void savePromoWatermark());
  if (elWmStripPrevious) elWmStripPrevious.addEventListener("change", () => void savePromoWatermark());
  if (elZipHeuristic)
    elZipHeuristic.addEventListener("change", () =>
      mergeSave({ zipHeuristicNaming: !!elZipHeuristic.checked })
    );
  if (elZipBundleTemplate)
    elZipBundleTemplate.addEventListener("change", () =>
      mergeSave({ zipBundleTemplate: (elZipBundleTemplate.value || "").trim() })
    );
  if (elZipEntryTemplate)
    elZipEntryTemplate.addEventListener("change", () =>
      mergeSave({ zipEntryTemplate: (elZipEntryTemplate.value || "").trim() })
    );
  if (elLazy)
    elLazy.addEventListener("change", () => {
      let d = parseInt(elLazy.value, 10);
      if (isNaN(d)) d = 0;
      mergeSave({ captureLazyDelayMs: Math.max(0, Math.min(3000, d)) });
    });
  if (elPageMediaMenu)
    elPageMediaMenu.addEventListener("change", () =>
      chrome.storage.local.set({ [STORAGE_PAGE_MEDIA_MENU]: !!elPageMediaMenu.checked })
    );
  if (btnClear)
    btnClear.addEventListener("click", async () => {
      if (!confirm("Clear collected media cache in the gallery?")) return;
      await new Promise((r) => chrome.storage.local.remove(STORAGE_COLLECTED, r));
      btnClear.textContent = "Cleared";
      setTimeout(() => {
        btnClear.textContent = "Clear gallery cache";
      }, 2000);
    });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    if (changes[STORAGE_SETTINGS] || changes[STORAGE_PAGE_MEDIA_MENU]) load();
  });

  async function pingApi() {
    if (!apiStatus) return;
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 4000);
    try {
      const r = await fetch("http://localhost:8000/health", { method: "GET", signal: ac.signal });
      clearTimeout(t);
      if (r.ok) {
        apiStatus.textContent = "● API reachable (localhost:8000)";
        apiStatus.style.color = "#a6e3a1";
      } else {
        apiStatus.textContent = "○ API returned " + r.status;
        apiStatus.style.color = "#fab387";
      }
    } catch (_) {
      clearTimeout(t);
      apiStatus.textContent = "○ API offline — start TBCC backend";
      apiStatus.style.color = "#6c7086";
    }
  }

  async function loadWatermarkFromApiIfNeeded() {
    if (typeof tbccFetchApi !== "function" || typeof TbccPromoWatermark === "undefined") return;
    const o = await new Promise((r) => chrome.storage.local.get(STORAGE_SETTINGS, r));
    const s = o[STORAGE_SETTINGS] || {};
    if (s.promoWatermark && Object.keys(s.promoWatermark).length > 1) return;
    try {
      const data = await tbccFetchApiJson("/import/watermark-config");
      const wm = TbccPromoWatermark.effectiveFromApiResponse(data);
      applyWmToForm(wm);
      await mergeSave({ promoWatermark: wm, skipPromoWatermark: !wm.enabled });
    } catch (_) {}
  }

  load();
  void loadWatermarkFromApiIfNeeded();
  pingApi();
  setInterval(pingApi, 30000);
})();
