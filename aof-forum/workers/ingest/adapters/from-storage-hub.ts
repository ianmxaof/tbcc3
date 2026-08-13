import { mkdir, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { createAdminClient } from "../../../lib/supabase/admin";
import { laneGroupForNetworkKey } from "../../../lib/storage-hub/lane-groups";
import {
  classifyDownloadError,
  downloadTbccFileWithRetries,
  fetchTbccExportBatch,
  readTbccCursor,
  sleep,
  tbccItemAlreadyImported,
  writeTbccCursor,
  type TbccExportItem,
} from "../../../lib/tbcc-export";
import { logger } from "../../logger";
import { ingestOne } from "../pipeline";

export const STORAGE_HUB_CURSOR_URL = "tbcc://storage-hub-export-cursor";
const HUB_MARKER = "storage_hub";

export type ItemOutcome = "imported" | "skipped" | "failed_permanent" | "failed_retryable";

export type StorageHubPullResult = {
  itemsSeen: number;
  imported: number;
  skipped: number;
  failed: number;
  failedRetryable: number;
  failedPermanent: number;
  maxId: number;
  /** True when batch should pause before next tick (error-rate spike). */
  throttleSuggested: boolean;
};

async function ensureHubGroup(
  db: ReturnType<typeof createAdminClient>,
  networkKey: string | null | undefined,
  ownerId: string
): Promise<number> {
  const lane = laneGroupForNetworkKey(networkKey);
  const { data: existing } = await db.from("groups").select("id").eq("slug", lane.slug).maybeSingle();
  if (existing?.id) {
    return existing.id as number;
  }

  const { data, error } = await db
    .from("groups")
    .insert({
      slug: lane.slug,
      name: lane.name,
      description: lane.description,
      owner_id: ownerId,
      visibility: "public",
      is_nsfw: true,
    })
    .select("id")
    .single();

  if (error) {
    if (error.code === "23505") {
      const { data: row } = await db.from("groups").select("id").eq("slug", lane.slug).single();
      if (row?.id) return row.id as number;
    }
    throw new Error(`group insert ${lane.slug}: ${error.message}`);
  }
  return data.id as number;
}

async function recordJob(
  db: ReturnType<typeof createAdminClient>,
  opts: {
    apiUrl: string;
    it: TbccExportItem;
    status: "done" | "failed";
    mediaId?: number | null;
    groupId?: number | null;
    error?: string | null;
    retryable?: boolean;
    groupSlug?: string;
  }
): Promise<void> {
  await db.from("ingest_jobs").insert({
    source_url: `${opts.apiUrl}${opts.it.file_path}`,
    source_kind: "telegram",
    status: opts.status,
    result_media_id: opts.mediaId ?? null,
    destination_group_id: opts.groupId ?? null,
    error: opts.error ?? null,
    payload: {
      tbcc_id: opts.it.id,
      hub: HUB_MARKER,
      network_key: opts.it.network_key,
      pool_name: opts.it.pool_name,
      group_slug: opts.groupSlug,
      source_channel: opts.it.source_channel,
      retryable: opts.retryable ?? false,
    },
  });
}

/**
 * Ingest one export item. Exported for retry-failed script.
 */
export async function ingestStorageHubItem(
  db: ReturnType<typeof createAdminClient>,
  apiUrl: string,
  apiKey: string | undefined,
  it: TbccExportItem,
  ownerId: string,
  tmpDir: string
): Promise<ItemOutcome> {
  if (await tbccItemAlreadyImported(db, it.id)) {
    return "skipped";
  }

  const ext = it.media_type === "video" ? ".mp4" : it.media_type === "gif" ? ".gif" : ".jpg";
  const tmpPath = path.join(tmpDir, `tbcc-hub-${it.id}-${Date.now()}${ext}`);

  try {
    const buf = await downloadTbccFileWithRetries(apiUrl, it.file_path, apiKey);
    await writeFile(tmpPath, buf);
    const groupId = await ensureHubGroup(db, it.network_key, ownerId);
    const lane = laneGroupForNetworkKey(it.network_key);
    const title = it.network_key
      ? `hub/${it.network_key}/${it.id}`
      : it.source_channel
        ? `hub/${it.source_channel}/${it.id}`
        : `hub/${it.id}`;

    const r = await ingestOne({
      source: tmpPath,
      sourceKind: "telegram",
      title,
      description: it.pool_name ? `Pool: ${it.pool_name}` : undefined,
      uploaderId: ownerId,
      groupId,
    });

    if (r.status === "failed") {
      logger.warn({ tbccId: it.id, reason: r.reason }, "storage hub ingest failed");
      await recordJob(db, {
        apiUrl,
        it,
        status: "failed",
        mediaId: r.mediaId,
        groupId,
        error: r.reason ?? "ingest failed",
        retryable: true,
        groupSlug: lane.slug,
      });
      return "failed_retryable";
    }

    await recordJob(db, {
      apiUrl,
      it,
      status: "done",
      mediaId: r.mediaId,
      groupId,
      error: r.reason ?? null,
      retryable: false,
      groupSlug: lane.slug,
    });
    return r.status === "skipped_duplicate" ? "skipped" : "imported";
  } catch (e) {
    const { retryable, status } = classifyDownloadError(e);
    logger.warn(
      { tbccId: it.id, err: (e as Error).message, retryable, status },
      "storage hub item failed"
    );
    await recordJob(db, {
      apiUrl,
      it,
      status: "failed",
      error: (e as Error).message,
      retryable,
    });
    return retryable ? "failed_retryable" : "failed_permanent";
  } finally {
    await unlink(tmpPath).catch(() => undefined);
  }
}

/**
 * Pull Storage Hub + trusted AOF pool media from TBCC (origin=storage_hub) into forum groups.
 *
 * Cursor advances only through contiguous successes + permanent failures.
 * Retryable failures pin the cursor so the next batch retries from that id.
 */
export async function pullFromStorageHub(opts: {
  watch: boolean;
  ownerId?: string;
}): Promise<StorageHubPullResult> {
  const apiUrl = (process.env.TBCC_API_URL || "").replace(/\/$/, "");
  const apiKey = process.env.TBCC_INTERNAL_API_KEY;
  const ownerId = opts.ownerId || process.env.MOCK_SEED_USER_ID || process.env.STORAGE_HUB_OWNER_USER_ID || "";

  const empty = (maxId = 0): StorageHubPullResult => ({
    itemsSeen: 0,
    imported: 0,
    skipped: 0,
    failed: 0,
    failedRetryable: 0,
    failedPermanent: 0,
    maxId,
    throttleSuggested: false,
  });

  if (!apiUrl) {
    logger.warn("TBCC_API_URL not set - storage hub adapter disabled");
    return empty();
  }
  if (!ownerId) {
    logger.warn("MOCK_SEED_USER_ID or STORAGE_HUB_OWNER_USER_ID required for hub group owner");
    return empty();
  }

  const db = createAdminClient();
  const pollMs = Number.parseInt(process.env.INGEST_POLL_MS || "5000", 10) * 6;
  const batchLimit = Number.parseInt(process.env.TBCC_EXPORT_BATCH_LIMIT || "10", 10);
  const itemDelayMs = Number.parseInt(process.env.TBCC_EXPORT_ITEM_DELAY_MS || "3000", 10);
  const throttleMs = Number.parseInt(process.env.TBCC_EXPORT_THROTTLE_MS || "90000", 10);
  const tmpDir = path.join(process.env.INGEST_LOCAL_INBOX ?? ".", ".tmp", "tbcc-storage-hub");

  const tick = async (): Promise<StorageHubPullResult> => {
    const sinceId = await readTbccCursor(db, STORAGE_HUB_CURSOR_URL);
    const batch = await fetchTbccExportBatch({
      apiUrl,
      apiKey,
      sinceId,
      batchLimit,
      origin: "storage_hub",
    });

    if (!batch) {
      logger.warn("tbcc storage_hub export non-200 - check TBCC_API_URL and X-TBCC-Internal-Key");
      return empty(sinceId);
    }

    const items = batch.items ?? [];
    if (!items.length) {
      return empty(sinceId);
    }

    logger.info({ count: items.length, sinceId }, "storage hub export: new items");
    await mkdir(tmpDir, { recursive: true });

    let imported = 0;
    let skipped = 0;
    let failedRetryable = 0;
    let failedPermanent = 0;
    /** Contiguous advance: stop raising cursor at first retryable fail. */
    let cursor = sinceId;
    let blocked = false;

    for (const it of items) {
      const outcome = await ingestStorageHubItem(db, apiUrl, apiKey, it, ownerId, tmpDir);
      if (outcome === "imported") imported += 1;
      else if (outcome === "skipped") skipped += 1;
      else if (outcome === "failed_permanent") failedPermanent += 1;
      else failedRetryable += 1;

      if (!blocked) {
        if (outcome === "failed_retryable") {
          blocked = true;
          // Do not advance past this id — next export will include it again (since_id < id).
        } else {
          cursor = Math.max(cursor, it.id);
        }
      }

      if (itemDelayMs > 0) await sleep(itemDelayMs);
    }

    await writeTbccCursor(db, STORAGE_HUB_CURSOR_URL, cursor);

    const failed = failedRetryable + failedPermanent;
    const throttleSuggested = items.length > 0 && failedRetryable / items.length > 0.5;

    if (throttleSuggested && throttleMs > 0) {
      logger.warn(
        { failedRetryable, items: items.length, throttleMs },
        "storage hub: high retryable error rate — throttling"
      );
      await sleep(throttleMs);
    }

    return {
      itemsSeen: items.length,
      imported,
      skipped,
      failed,
      failedRetryable,
      failedPermanent,
      maxId: cursor,
      throttleSuggested,
    };
  };

  if (!opts.watch) {
    return await tick();
  }

  logger.info({ pollMs, apiUrl, batchLimit, itemDelayMs }, "storage hub export adapter running");
  while (true) {
    await tick();
    await sleep(pollMs);
  }
}
