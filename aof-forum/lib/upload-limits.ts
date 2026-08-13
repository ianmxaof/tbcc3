/** Daily upload quotas (app-level; env overrides). */

/**
 * Daily file count. 0 or negative = unlimited (skip count check).
 * Default 0 removes the old hard 50/day wall for operator bulk gallery drops.
 */
export const UPLOAD_DAILY_FILE_LIMIT = Number.parseInt(
  process.env.UPLOAD_DAILY_FILE_LIMIT || "0",
  10
);

export const UPLOAD_DAILY_BYTE_LIMIT = Number.parseInt(
  process.env.UPLOAD_DAILY_BYTE_LIMIT || String(5 * 1024 * 1024 * 1024),
  10
);

export const UPLOAD_MAX_FILE_BYTES = Number.parseInt(
  process.env.UPLOAD_MAX_FILE_BYTES || String(500 * 1024 * 1024),
  10
);

export const UPLOAD_MAX_FILES_PER_BATCH = Number.parseInt(
  process.env.UPLOAD_MAX_FILES_PER_BATCH || "100",
  10
);

export type UploadQuotaUsage = {
  fileCount: number;
  byteTotal: number;
};

export type UploadQuotaCheck = {
  ok: boolean;
  reason?: string;
  usage: UploadQuotaUsage;
  limits: {
    dailyFiles: number;
    dailyBytes: number;
    maxFileBytes: number;
  };
};

export function checkUploadQuota(
  usage: UploadQuotaUsage,
  incomingFiles: number,
  incomingBytes: number
): UploadQuotaCheck {
  const limits = {
    dailyFiles: UPLOAD_DAILY_FILE_LIMIT,
    dailyBytes: UPLOAD_DAILY_BYTE_LIMIT,
    maxFileBytes: UPLOAD_MAX_FILE_BYTES,
  };

  if (incomingFiles > UPLOAD_MAX_FILES_PER_BATCH) {
    return {
      ok: false,
      reason: `Max ${UPLOAD_MAX_FILES_PER_BATCH} files per batch`,
      usage,
      limits,
    };
  }

  // 0 / negative = unlimited daily file count
  if (UPLOAD_DAILY_FILE_LIMIT > 0 && usage.fileCount + incomingFiles > UPLOAD_DAILY_FILE_LIMIT) {
    return {
      ok: false,
      reason: `Daily file limit (${UPLOAD_DAILY_FILE_LIMIT}) reached`,
      usage,
      limits,
    };
  }

  if (usage.byteTotal + incomingBytes > UPLOAD_DAILY_BYTE_LIMIT) {
    return {
      ok: false,
      reason: `Daily upload size limit reached`,
      usage,
      limits,
    };
  }

  return { ok: true, usage, limits };
}

export function isAllowedUploadMime(contentType: string): boolean {
  const ct = (contentType || "").toLowerCase().split(";")[0].trim();
  if (ct === "image/gif") return true;
  if (ct.startsWith("image/")) return true;
  if (ct.startsWith("video/")) return true;
  return false;
}
