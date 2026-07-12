/* global chrome, TbccXProfileLooms */
/** Extension options — X profile overlay Comic Looms settings (mirrors CONF threads / timeout). */
(function () {
  if (!window.TbccXProfileLooms) return;

  var elIdle = document.getElementById("loomsIdleThreads");
  var elBrowse = document.getElementById("loomsBrowseThreads");
  var elDownload = document.getElementById("loomsDownloadThreads");
  var elTimeout = document.getElementById("loomsTimeoutSec");
  var elIncludeVideo = document.getElementById("loomsIncludeVideo");
  var elFetchOriginal = document.getElementById("loomsFetchOriginal");
  var elMaxItems = document.getElementById("loomsMaxItems");
  var elZipNameTemplate = document.getElementById("loomsZipNameTemplate");
  var elZipSkipWatermark = document.getElementById("loomsZipSkipWatermark");
  var elReset = document.getElementById("loomsResetDefaults");
  var statusEl = document.getElementById("loomsSettingsStatus");

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || "";
  }

  function readForm() {
    return TbccXProfileLooms.clampLoomsSettings({
      idleThreads: elIdle ? elIdle.value : undefined,
      browseThreads: elBrowse ? elBrowse.value : undefined,
      downloadThreads: elDownload ? elDownload.value : undefined,
      timeoutSec: elTimeout ? elTimeout.value : undefined,
      includeVideo: elIncludeVideo ? elIncludeVideo.checked : undefined,
      fetchOriginal: elFetchOriginal ? elFetchOriginal.checked : undefined,
      maxItems: elMaxItems ? elMaxItems.value : undefined,
      zipNameTemplate: elZipNameTemplate ? elZipNameTemplate.value : undefined,
      zipSkipWatermark: elZipSkipWatermark ? elZipSkipWatermark.checked : undefined,
    });
  }

  function fillForm(s) {
    if (elIdle) elIdle.value = String(s.idleThreads);
    if (elBrowse) elBrowse.value = String(s.browseThreads);
    if (elDownload) elDownload.value = String(s.downloadThreads);
    if (elTimeout) elTimeout.value = String(s.timeoutSec);
    if (elIncludeVideo) elIncludeVideo.checked = !!s.includeVideo;
    if (elFetchOriginal) elFetchOriginal.checked = !!s.fetchOriginal;
    if (elMaxItems) elMaxItems.value = String(s.maxItems);
    if (elZipNameTemplate) elZipNameTemplate.value = s.zipNameTemplate || "";
    if (elZipSkipWatermark) elZipSkipWatermark.checked = s.zipSkipWatermark !== false;
  }

  function bindStepper(inputId, key, delta) {
    var input = document.getElementById(inputId);
    if (!input) return;
    var wrap = input.closest(".tbcc-looms-stepper");
    if (!wrap) return;
    var minus = wrap.querySelector('[data-step="-1"]');
    var plus = wrap.querySelector('[data-step="1"]');
    function bump(d) {
      var s = readForm();
      var cur = s[key];
      var next = TbccXProfileLooms.clampLoomsSettings(Object.assign({}, s, { [key]: cur + d }));
      input.value = String(next[key]);
      void persist();
    }
    if (minus) minus.addEventListener("click", function () { bump(-1); });
    if (plus) plus.addEventListener("click", function () { bump(1); });
    input.addEventListener("change", function () { void persist(); });
  }

  function persist() {
    return TbccXProfileLooms.saveLoomsSettings(readForm()).then(function (s) {
      fillForm(s);
      setStatus("Saved — idle " + s.idleThreads + ", browse " + s.browseThreads + ", download " + s.downloadThreads + ", timeout " + s.timeoutSec + "s");
    });
  }

  bindStepper("loomsIdleThreads", "idleThreads");
  bindStepper("loomsBrowseThreads", "browseThreads");
  bindStepper("loomsDownloadThreads", "downloadThreads");
  bindStepper("loomsTimeoutSec", "timeoutSec");

  if (elIncludeVideo) elIncludeVideo.addEventListener("change", function () { void persist(); });
  if (elFetchOriginal) elFetchOriginal.addEventListener("change", function () { void persist(); });
  if (elMaxItems) elMaxItems.addEventListener("change", function () { void persist(); });
  if (elZipNameTemplate) elZipNameTemplate.addEventListener("change", function () { void persist(); });
  if (elZipSkipWatermark) elZipSkipWatermark.addEventListener("change", function () { void persist(); });

  if (elReset) {
    elReset.addEventListener("click", function () {
      fillForm(TbccXProfileLooms.LOOMS_DEFAULTS);
      void persist();
    });
  }

  TbccXProfileLooms.loadLoomsSettings().then(function (s) {
    fillForm(s);
    setStatus("Defaults: idle 2 · browse 4 · download 4 · timeout 9s (Comic Looms X profile)");
  });
})();
