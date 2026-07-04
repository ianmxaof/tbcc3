/**
 * Fast import pipeline: POST /import/bytes returns job_id immediately; poll until Telegram finishes.
 * Background alarms (chrome.alarms) re-poll after service worker restarts — see background.js.
 */
const TBCC_API_IMPORT_BYTES = "http://localhost:8000/import/bytes";
const TBCC_API_IMPORT_JOBS = "http://localhost:8000/import/jobs";
const TBCC_IMPORT_POLL_MS = 700;
const TBCC_IMPORT_POLL_MAX_MS = 900000;
const TBCC_STORAGE_IMPORT_QUEUE_PAUSED = "tbccImportQueuePaused";
const TBCC_IMPORT_TERMINAL_STATUSES = new Set(["done", "failed", "skipped", "cancelled"]);

const TBCC_IMPORT_STAGE_LABELS = {
  stored: "Staged on server",
  queued: "Queued for Telegram",
  telegram: "Uploading to Telegram…",
  processing: "Uploading to Telegram…",
  enrich: "Auto-tag…",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

function tbccImportStageLabel(stage, status) {
  if (status === "failed") return TBCC_IMPORT_STAGE_LABELS.failed;
  if (status === "cancelled") return TBCC_IMPORT_STAGE_LABELS.cancelled;
  return TBCC_IMPORT_STAGE_LABELS[stage] || stage || status || "Working…";
}

function tbccIsImportTerminal(status) {
  return TBCC_IMPORT_TERMINAL_STATUSES.has(String(status || "").toLowerCase());
}

async function tbccGetImportQueuePaused() {
  try {
    const data = await chrome.storage.local.get(TBCC_STORAGE_IMPORT_QUEUE_PAUSED);
    return !!data[TBCC_STORAGE_IMPORT_QUEUE_PAUSED];
  } catch (_) {
    return false;
  }
}

async function tbccSetImportQueuePaused(paused) {
  await chrome.storage.local.set({ [TBCC_STORAGE_IMPORT_QUEUE_PAUSED]: !!paused });
}

async function tbccParseImportHttpResponse(r) {
  const text = await r.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (_) {
    data = { error: text ? text.slice(0, 200) : `HTTP ${r.status}` };
  }
  if (!r.ok && !data.error) data.error = text ? text.slice(0, 200) : `HTTP ${r.status}`;
  return data;
}

async function tbccNotifyGalleryJobUpdate(galleryJobId, payload) {
  if (!galleryJobId) return;
  try {
    await chrome.runtime.sendMessage({
      action: "tbcc-gallery-job-update",
      id: galleryJobId,
      stage: payload.stage,
      status: payload.status,
      backendJobId: payload.job_id || payload.backendJobId,
      error: payload.error,
      label: tbccImportStageLabel(payload.stage, payload.status),
    });
  } catch (_) {}
}

function tbccArmImportPollAlarm(galleryJobId, backendJobId) {
  if (!galleryJobId || !backendJobId) return;
  try {
    chrome.runtime.sendMessage({
      action: "tbcc-import-poll-arm",
      galleryJobId,
      backendJobId,
    });
  } catch (_) {}
}

async function tbccPollImportJob(jobId, galleryJobId, onTick) {
  if (galleryJobId) tbccArmImportPollAlarm(galleryJobId, jobId);
  const start = Date.now();
  while (Date.now() - start < TBCC_IMPORT_POLL_MAX_MS) {
    let data = {};
    try {
      const r = await fetch(`${TBCC_API_IMPORT_JOBS}/${encodeURIComponent(jobId)}`);
      data = await tbccParseImportHttpResponse(r);
    } catch (e) {
      return { error: String(e && e.message ? e.message : e), job_id: jobId };
    }
    if (onTick) onTick(data);
    void tbccNotifyGalleryJobUpdate(galleryJobId, data);
    if (data.status === "cancelled") {
      return { error: data.error || "Cancelled", job_id: jobId, status: "cancelled" };
    }
    if (data.status === "done") {
      const res = data.result || {};
      if (res.status === "saved_only") {
        return {
          status: "saved_only",
          job_id: jobId,
          telegram_message_id: res.telegram_message_id,
          message: "Saved to Telegram Saved Messages",
        };
      }
      if (res.status === "imported" || data.media_id) {
        return { status: "imported", media_id: data.media_id || res.media_id, job_id: jobId };
      }
      if (res.status === "skipped") {
        return { status: "skipped", media_id: data.media_id || res.media_id, job_id: jobId };
      }
      return { status: "done", job_id: jobId, ...data };
    }
    if (data.status === "failed") {
      return { error: data.error || "Import failed", job_id: jobId, ...data };
    }
    await new Promise((res) => setTimeout(res, TBCC_IMPORT_POLL_MS));
  }
  return { error: "Import timed out waiting for Telegram upload", job_id: jobId };
}

/**
 * POST multipart form to /import/bytes; poll when job_id returned.
 */
async function tbccPostImportForm(form, galleryJobId) {
  if (await tbccGetImportQueuePaused()) {
    return { error: "Import queue paused — tap Resume in Running tasks" };
  }
  const headers = {};
  if (galleryJobId) headers["X-TBCC-Extension-Job-Id"] = galleryJobId;
  const r = await fetch(TBCC_API_IMPORT_BYTES, { method: "POST", body: form, headers });
  const data = await tbccParseImportHttpResponse(r);
  if (data.error) return data;
  if (data.job_id) {
    void tbccNotifyGalleryJobUpdate(galleryJobId, { ...data, stage: data.stage || "queued" });
    tbccArmImportPollAlarm(galleryJobId, data.job_id);
    return tbccPollImportJob(data.job_id, galleryJobId);
  }
  return data;
}

async function tbccCancelBackendImportJob(backendJobId) {
  if (!backendJobId) return { ok: false, error: "no_job_id" };
  try {
    const r = await fetch(`${TBCC_API_IMPORT_JOBS}/${encodeURIComponent(backendJobId)}/cancel`, {
      method: "POST",
    });
    return tbccParseImportHttpResponse(r);
  } catch (e) {
    return { ok: false, error: String(e && e.message ? e.message : e) };
  }
}

