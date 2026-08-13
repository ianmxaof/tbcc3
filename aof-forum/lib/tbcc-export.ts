import { createAdminClient } from "./supabase/admin";

export type TbccExportItem = {
  id: number;
  source_channel?: string | null;
  media_type?: string | null;
  file_path: string;
  network_key?: string | null;
  pool_name?: string | null;
  tags?: string | null;
  object_key?: string | null;
  direct_url?: string | null;
  has_r2?: boolean;
  byte_size?: number | null;
  content_type?: string | null;
};

export type TbccExportResponse = {
  items?: TbccExportItem[];
  next_since_id?: number;
  count?: number;
  origin?: string | null;
};

export class TbccDownloadError extends Error {
  status: number;
  retryable: boolean;

  constructor(status: number, message: string, retryable: boolean) {
    super(message);
    this.name = "TbccDownloadError";
    this.status = status;
    this.retryable = retryable;
  }
}

/** Permanent skips (dead Telegram pointers). */
export function isPermanentDownloadStatus(status: number): boolean {
  return status === 404 || status === 410 || status === 400;
}

/** Transient tunnel / Telethon / gateway failures. */
export function isRetryableDownloadStatus(status: number): boolean {
  return status === 502 || status === 503 || status === 504 || status === 524 || status === 408 || status === 429;
}

export function classifyDownloadError(err: unknown): { retryable: boolean; status: number | null } {
  if (err instanceof TbccDownloadError) {
    return { retryable: err.retryable, status: err.status };
  }
  const msg = (err as Error)?.message || String(err);
  const m = msg.match(/tbcc file download (\d+)/i);
  if (m) {
    const status = Number.parseInt(m[1], 10);
    if (isPermanentDownloadStatus(status)) return { retryable: false, status };
    if (isRetryableDownloadStatus(status)) return { retryable: true, status };
    return { retryable: status >= 500, status };
  }
  // Network / abort / fetch failures
  if (/abort|timeout|network|ECONNRESET|ETIMEDOUT|fetch failed/i.test(msg)) {
    return { retryable: true, status: null };
  }
  return { retryable: true, status: null };
}

export function tbccHeaders(apiKey: string | undefined): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (apiKey) headers["X-TBCC-Internal-Key"] = apiKey;
  return headers;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function readTbccCursor(
  db: ReturnType<typeof createAdminClient>,
  cursorUrl: string
): Promise<number> {
  const { data } = await db
    .from("ingest_jobs")
    .select("payload")
    .eq("source_kind", "telegram")
    .eq("source_url", cursorUrl)
    .maybeSingle();
  const id = (data?.payload as { tbcc_id?: number } | undefined)?.tbcc_id;
  return typeof id === "number" && id > 0 ? id : 0;
}

export async function writeTbccCursor(
  db: ReturnType<typeof createAdminClient>,
  cursorUrl: string,
  tbccId: number
): Promise<void> {
  const { data: existing } = await db
    .from("ingest_jobs")
    .select("id")
    .eq("source_kind", "telegram")
    .eq("source_url", cursorUrl)
    .maybeSingle();

  const payload = { tbcc_id: tbccId };
  if (existing?.id) {
    await db
      .from("ingest_jobs")
      .update({ payload, status: "done", error: null })
      .eq("id", existing.id);
    return;
  }
  await db.from("ingest_jobs").insert({
    source_url: cursorUrl,
    source_kind: "telegram",
    status: "done",
    payload,
  });
}

/**
 * Download bytes from TBCC /media/{id}/file.
 * Default timeout 15 minutes for large Telethon pulls through Cloudflare.
 */
export async function downloadTbccFile(
  apiUrl: string,
  filePath: string,
  apiKey: string | undefined,
  opts?: { timeoutMs?: number }
): Promise<Buffer> {
  const timeoutMs = opts?.timeoutMs ?? Number.parseInt(process.env.TBCC_DOWNLOAD_TIMEOUT_MS || "900000", 10);
  const url = new URL(filePath, apiUrl);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const r = await fetch(url.toString(), {
      headers: tbccHeaders(apiKey),
      signal: controller.signal,
    });
    if (!r.ok) {
      const permanent = isPermanentDownloadStatus(r.status);
      const retryable = !permanent && (isRetryableDownloadStatus(r.status) || r.status >= 500);
      throw new TbccDownloadError(
        r.status,
        `tbcc file download ${r.status} ${r.statusText} for ${url.pathname}`,
        retryable
      );
    }
    return Buffer.from(await r.arrayBuffer());
  } catch (e) {
    if (e instanceof TbccDownloadError) throw e;
    const msg = (e as Error)?.message || String(e);
    if (/abort/i.test(msg)) {
      throw new TbccDownloadError(408, `tbcc file download timeout after ${timeoutMs}ms for ${url.pathname}`, true);
    }
    throw new TbccDownloadError(0, `tbcc file download network error for ${url.pathname}: ${msg}`, true);
  } finally {
    clearTimeout(timer);
  }
}

export async function downloadTbccFileWithRetries(
  apiUrl: string,
  filePath: string,
  apiKey: string | undefined,
  opts?: { attempts?: number; timeoutsMs?: number }
): Promise<Buffer> {
  const attempts = opts?.attempts ?? Number.parseInt(process.env.TBCC_DOWNLOAD_RETRIES || "3", 10);
  const backoffs = [5_000, 20_000, 60_000];
  let lastErr: unknown;
  for (let i = 0; i < Math.max(1, attempts); i++) {
    try {
      return await downloadTbccFile(apiUrl, filePath, apiKey, { timeoutMs: opts?.timeoutsMs });
    } catch (e) {
      lastErr = e;
      const { retryable } = classifyDownloadError(e);
      if (!retryable || i >= attempts - 1) throw e;
      const wait = backoffs[Math.min(i, backoffs.length - 1)] ?? 60_000;
      await sleep(wait);
    }
  }
  throw lastErr;
}

export async function fetchTbccExportBatch(opts: {
  apiUrl: string;
  apiKey: string | undefined;
  sinceId: number;
  batchLimit: number;
  origin?: string;
  hasR2?: boolean;
}): Promise<TbccExportResponse | null> {
  const url = new URL("/media/export", opts.apiUrl);
  url.searchParams.set("since_id", String(opts.sinceId));
  url.searchParams.set("limit", String(Math.max(1, Math.min(opts.batchLimit, 50))));
  if (opts.origin) {
    url.searchParams.set("origin", opts.origin);
  }
  if (opts.hasR2 === true) {
    url.searchParams.set("has_r2", "true");
  } else if (opts.hasR2 === false) {
    url.searchParams.set("has_r2", "false");
  }

  const r = await fetch(url.toString(), { headers: tbccHeaders(opts.apiKey) });
  if (!r.ok) {
    return null;
  }
  return (await r.json()) as TbccExportResponse;
}

export async function tbccItemAlreadyImported(
  db: ReturnType<typeof createAdminClient>,
  tbccId: number
): Promise<boolean> {
  const { data } = await db
    .from("ingest_jobs")
    .select("id")
    .eq("source_kind", "telegram")
    .eq("status", "done")
    .contains("payload", { tbcc_id: tbccId, hub: "storage_hub" })
    .limit(1)
    .maybeSingle();
  return !!data?.id;
}
