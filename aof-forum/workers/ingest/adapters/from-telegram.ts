import { mkdir, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { createAdminClient } from "../../../lib/supabase/admin";
import {
  downloadTbccFile,
  fetchTbccExportBatch,
  readTbccCursor,
  sleep,
  writeTbccCursor,
  type TbccExportItem,
} from "../../../lib/tbcc-export";
import { logger } from "../../logger";
import { ingestOne } from "../pipeline";

const CURSOR_URL = "tbcc://export-cursor";

/**
 * Pull approved media from TBCC into the forum via GET /media/export.
 *
 * Contract (P2):
 *   GET  {TBCC_API_URL}/media/export?since_id=<n>&limit=<batch>
 *   -> { items: [{ id, file_path, source_channel, media_type, ... }], next_since_id }
 *
 * Bytes are fetched from each item's file_path (GET /media/{id}/file) with the same
 * internal key. Batches are throttled to avoid starving TBCC's serialized Telegram I/O lock.
 */
export async function pullFromTelegram(opts: { watch: boolean }): Promise<void> {
  const apiUrl = (process.env.TBCC_API_URL || "").replace(/\/$/, "");
  const apiKey = process.env.TBCC_INTERNAL_API_KEY;
  if (!apiUrl) {
    logger.warn("TBCC_API_URL not set - telegram adapter disabled");
    return;
  }

  const db = createAdminClient();
  const pollMs = Number.parseInt(process.env.INGEST_POLL_MS || "5000", 10) * 6;
  const batchLimit = Number.parseInt(process.env.TBCC_EXPORT_BATCH_LIMIT || "10", 10);
  const itemDelayMs = Number.parseInt(process.env.TBCC_EXPORT_ITEM_DELAY_MS || "3000", 10);
  const tmpDir = path.join(process.env.INGEST_LOCAL_INBOX ?? ".", ".tmp", "tbcc-export");

  const tick = async () => {
    const sinceId = await readTbccCursor(db, CURSOR_URL);
    const j = await fetchTbccExportBatch({
      apiUrl,
      apiKey,
      sinceId,
      batchLimit,
    });
    if (!j) {
      logger.warn(
        "tbcc export non-200 - check TBCC_API_URL, /media/export, and X-TBCC-Internal-Key"
      );
      return;
    }
    const items: TbccExportItem[] = j.items ?? [];
    if (!items.length) return;

    logger.info({ count: items.length, sinceId }, "telegram export: new items");
    await mkdir(tmpDir, { recursive: true });

    let maxId = sinceId;
    for (const it of items) {
      maxId = Math.max(maxId, it.id);
      const ext =
        it.media_type === "video" ? ".mp4" : it.media_type === "gif" ? ".gif" : ".jpg";
      const tmpPath = path.join(tmpDir, `tbcc-${it.id}-${Date.now()}${ext}`);

      try {
        const buf = await downloadTbccFile(apiUrl, it.file_path, apiKey);
        await writeFile(tmpPath, buf);
        const title = it.source_channel
          ? `tg/${it.source_channel}/${it.id}`
          : `tg/${it.id}`;
        const r = await ingestOne({
          source: tmpPath,
          sourceKind: "telegram",
          title,
        });
        await db.from("ingest_jobs").insert({
          source_url: `${apiUrl}${it.file_path}`,
          source_kind: "telegram",
          status: r.status,
          result_media_id: r.mediaId ?? null,
          error: r.reason ?? null,
          payload: { tbcc_id: it.id, source_channel: it.source_channel },
        });
        if (r.status === "failed") {
          logger.warn({ tbccId: it.id, reason: r.reason }, "telegram export ingest failed");
        }
      } catch (e) {
        logger.warn({ tbccId: it.id, err: (e as Error).message }, "telegram export item failed");
        await db.from("ingest_jobs").insert({
          source_url: `${apiUrl}${it.file_path}`,
          source_kind: "telegram",
          status: "failed",
          error: (e as Error).message,
          payload: { tbcc_id: it.id, source_channel: it.source_channel },
        });
      } finally {
        await unlink(tmpPath).catch(() => undefined);
        if (itemDelayMs > 0) await sleep(itemDelayMs);
      }
    }

    await writeTbccCursor(db, CURSOR_URL, maxId);
  };

  if (!opts.watch) {
    await tick();
    return;
  }
  logger.info({ pollMs, apiUrl, batchLimit, itemDelayMs }, "telegram export adapter running");
  while (true) {
    await tick();
    await sleep(pollMs);
  }
}
