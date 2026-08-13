/**
 * Index Storage Hub media that TBCC already exported to R2 (no Telegram re-download).
 *
 * Polls GET /media/export?origin=storage_hub&has_r2=true and inserts media_items
 * with the shared aof-media object_key.
 *
 *   npm run ingest:storage-hub:manifest
 *   npm run ingest:storage-hub:manifest -- --watch
 */
import { config } from "dotenv";
import path from "node:path";
import { createAdminClient } from "../lib/supabase/admin";
import { headObject } from "../lib/b2";
import { laneGroupForNetworkKey } from "../lib/storage-hub/lane-groups";
import {
  fetchTbccExportBatch,
  readTbccCursor,
  sleep,
  tbccItemAlreadyImported,
  writeTbccCursor,
  type TbccExportItem,
} from "../lib/tbcc-export";

const root = process.cwd();
config({ path: path.join(root, ".env.local") });
config({ path: path.join(root, ".env") });

const CURSOR_URL = "tbcc://storage-hub-r2-manifest-cursor";
const HUB = "storage_hub";

type R2ExportItem = TbccExportItem & {
  object_key?: string | null;
  direct_url?: string | null;
  has_r2?: boolean;
  byte_size?: number | null;
  content_type?: string | null;
};

function classifyMime(m: string): "image" | "video" | "gif" | null {
  const ct = (m || "").toLowerCase().split(";")[0].trim();
  if (ct === "image/gif") return "gif";
  if (ct.startsWith("image/")) return "image";
  if (ct.startsWith("video/")) return "video";
  return null;
}

function mimeFromItem(it: R2ExportItem): string {
  if (it.content_type) return it.content_type;
  const mt = (it.media_type || "").toLowerCase();
  if (mt === "video") return "video/mp4";
  if (mt === "gif") return "image/gif";
  return "image/jpeg";
}

async function ensureHubGroup(
  db: ReturnType<typeof createAdminClient>,
  networkKey: string | null | undefined,
  ownerId: string
): Promise<number> {
  const lane = laneGroupForNetworkKey(networkKey);
  const { data: existing } = await db.from("groups").select("id").eq("slug", lane.slug).maybeSingle();
  if (existing?.id) return existing.id as number;

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

async function indexOne(
  db: ReturnType<typeof createAdminClient>,
  it: R2ExportItem,
  ownerId: string,
  verifyHead: boolean
): Promise<"imported" | "skipped" | "failed"> {
  if (await tbccItemAlreadyImported(db, it.id)) return "skipped";

  const objectKey = (it.object_key || "").trim();
  if (!objectKey) return "failed";

  let byteSize = typeof it.byte_size === "number" ? it.byte_size : 0;
  let contentType = mimeFromItem(it);

  if (verifyHead) {
    try {
      const head = await headObject(objectKey);
      byteSize = head.contentLength || byteSize;
      contentType = head.contentType || contentType;
    } catch (e) {
      console.warn(`headObject failed tbcc=${it.id} key=${objectKey}: ${(e as Error).message}`);
      return "failed";
    }
  }

  const kind = classifyMime(contentType);
  if (!kind) {
    console.warn(`unsupported mime ${contentType} for tbcc=${it.id}`);
    return "failed";
  }

  const groupId = await ensureHubGroup(db, it.network_key, ownerId);
  const lane = laneGroupForNetworkKey(it.network_key);
  const title = it.network_key ? `hub/${it.network_key}/${it.id}` : `hub/${it.id}`;

  const ins = await db
    .from("media_items")
    .insert({
      kind,
      title,
      description: it.pool_name ? `Pool: ${it.pool_name}` : null,
      b2_key: objectKey,
      mime: contentType,
      byte_size: byteSize || null,
      source_kind: "telegram",
      source_url: it.direct_url || null,
      uploader_id: ownerId,
      is_public: true,
      is_nsfw: true,
    })
    .select("id")
    .single();

  if (ins.error || !ins.data) {
    // Unique b2_key — treat as already indexed
    if (ins.error?.code === "23505") {
      await db.from("ingest_jobs").insert({
        source_url: objectKey,
        source_kind: "telegram",
        status: "done",
        payload: { tbcc_id: it.id, hub: HUB, via: "r2_manifest", network_key: it.network_key },
      });
      return "skipped";
    }
    console.warn(`media insert failed tbcc=${it.id}: ${ins.error?.message}`);
    return "failed";
  }

  const mediaId = ins.data.id as number;
  await db.from("group_media").insert({
    group_id: groupId,
    media_id: mediaId,
    added_by: ownerId,
  });

  await db.from("ingest_jobs").insert({
    source_url: objectKey,
    source_kind: "telegram",
    status: "done",
    result_media_id: mediaId,
    destination_group_id: groupId,
    payload: {
      tbcc_id: it.id,
      hub: HUB,
      via: "r2_manifest",
      network_key: it.network_key,
      group_slug: lane.slug,
      object_key: objectKey,
    },
  });

  return "imported";
}

async function fetchR2Batch(opts: {
  apiUrl: string;
  apiKey: string | undefined;
  sinceId: number;
  batchLimit: number;
}): Promise<{ items: R2ExportItem[]; next: number } | null> {
  const url = new URL("/media/export", opts.apiUrl);
  url.searchParams.set("since_id", String(opts.sinceId));
  url.searchParams.set("limit", String(Math.max(1, Math.min(opts.batchLimit, 50))));
  url.searchParams.set("origin", "storage_hub");
  url.searchParams.set("has_r2", "true");

  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.apiKey) headers["X-TBCC-Internal-Key"] = opts.apiKey;
  const r = await fetch(url.toString(), { headers });
  if (!r.ok) {
    console.warn(`export has_r2 non-200: ${r.status}`);
    return null;
  }
  const j = (await r.json()) as { items?: R2ExportItem[]; next_since_id?: number };
  return { items: j.items ?? [], next: j.next_since_id ?? opts.sinceId };
}

async function tick(opts: {
  apiUrl: string;
  apiKey: string | undefined;
  ownerId: string;
  batchLimit: number;
  verifyHead: boolean;
}): Promise<{ seen: number; imported: number; skipped: number; failed: number; cursor: number }> {
  const db = createAdminClient();
  const sinceId = await readTbccCursor(db, CURSOR_URL);
  const batch = await fetchR2Batch({
    apiUrl: opts.apiUrl,
    apiKey: opts.apiKey,
    sinceId,
    batchLimit: opts.batchLimit,
  });
  if (!batch) {
    return { seen: 0, imported: 0, skipped: 0, failed: 0, cursor: sinceId };
  }
  if (!batch.items.length) {
    return { seen: 0, imported: 0, skipped: 0, failed: 0, cursor: sinceId };
  }

  let imported = 0;
  let skipped = 0;
  let failed = 0;
  let cursor = sinceId;

  for (const it of batch.items) {
    const outcome = await indexOne(db, it, opts.ownerId, opts.verifyHead);
    if (outcome === "imported") imported += 1;
    else if (outcome === "skipped") skipped += 1;
    else failed += 1;
    cursor = Math.max(cursor, it.id);
  }

  await writeTbccCursor(db, CURSOR_URL, cursor);
  return { seen: batch.items.length, imported, skipped, failed, cursor };
}

async function main(): Promise<void> {
  const watch = process.argv.includes("--watch");
  const apiUrl = (process.env.TBCC_API_URL || "").replace(/\/$/, "");
  const apiKey = process.env.TBCC_INTERNAL_API_KEY;
  const ownerId = process.env.MOCK_SEED_USER_ID || process.env.STORAGE_HUB_OWNER_USER_ID || "";
  const batchLimit = Number.parseInt(process.env.TBCC_EXPORT_BATCH_LIMIT || "20", 10);
  const verifyHead = (process.env.TBCC_MANIFEST_VERIFY_HEAD || "1").trim() !== "0";
  const pollMs = Number.parseInt(process.env.INGEST_POLL_MS || "5000", 10) * 6;

  if (!apiUrl || !ownerId) {
    console.error("TBCC_API_URL and MOCK_SEED_USER_ID (or STORAGE_HUB_OWNER_USER_ID) required");
    process.exit(1);
  }

  console.log(`Manifest ingest from ${apiUrl} (has_r2=true) verifyHead=${verifyHead}`);

  let batches = 0;
  while (true) {
    const r = await tick({ apiUrl, apiKey, ownerId, batchLimit, verifyHead });
    batches += 1;
    console.log(
      `batch ${batches}: seen=${r.seen} imported=${r.imported} skipped=${r.skipped} failed=${r.failed} cursor=${r.cursor}`
    );
    if (!watch) {
      if (!r.seen) break;
      // one-shot drain loop
      continue;
    }
    await sleep(pollMs);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
