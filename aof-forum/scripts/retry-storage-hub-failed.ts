/**
 * Re-attempt Storage Hub ingest_jobs that failed with retryable errors
 * (502/524/timeout) after the cursor already advanced past them.
 *
 *   npm run ingest:storage-hub:retry-failed
 *   npm run ingest:storage-hub:retry-failed -- --limit 50
 */
import { config } from "dotenv";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { createAdminClient } from "../lib/supabase/admin";
import type { TbccExportItem } from "../lib/tbcc-export";
import { ingestStorageHubItem } from "../workers/ingest/adapters/from-storage-hub";

const root = process.cwd();
config({ path: path.join(root, ".env.local") });
config({ path: path.join(root, ".env") });

const HUB = "storage_hub";

type JobRow = {
  id: number;
  source_url: string | null;
  error: string | null;
  payload: {
    tbcc_id?: number;
    hub?: string;
    retryable?: boolean;
    network_key?: string | null;
    pool_name?: string | null;
    source_channel?: string | null;
    media_type?: string | null;
  } | null;
};

function parseLimit(): number {
  const idx = process.argv.indexOf("--limit");
  if (idx >= 0 && process.argv[idx + 1]) {
    return Math.max(1, Number.parseInt(process.argv[idx + 1], 10) || 100);
  }
  return Number.parseInt(process.env.TBCC_RETRY_FAILED_LIMIT || "100", 10);
}

function looksRetryable(row: JobRow): boolean {
  const p = row.payload || {};
  if (p.retryable === false) return false;
  if (p.retryable === true) return true;
  // Legacy jobs (pre-harden) without retryable flag: treat gateway/timeouts as retryable.
  const err = row.error || "";
  if (/404|410 Not Found/i.test(err)) return false;
  return /502|503|504|524|timeout|network|ECONNRESET|ETIMEDOUT/i.test(err);
}

function toExportItem(row: JobRow, apiUrl: string): TbccExportItem | null {
  const tbccId = row.payload?.tbcc_id;
  if (typeof tbccId !== "number" || tbccId <= 0) return null;
  let filePath = `/media/${tbccId}/file`;
  if (row.source_url?.includes("/media/")) {
    try {
      const u = new URL(row.source_url);
      filePath = u.pathname;
    } catch {
      const m = row.source_url.match(/(\/media\/\d+\/file)/);
      if (m) filePath = m[1];
    }
  }
  return {
    id: tbccId,
    file_path: filePath.startsWith("/") ? filePath : `/${filePath}`,
    network_key: row.payload?.network_key,
    pool_name: row.payload?.pool_name,
    source_channel: row.payload?.source_channel,
    media_type: row.payload?.media_type ?? (filePath.endsWith(".mp4") ? "video" : "photo"),
  };
}

async function main(): Promise<void> {
  const apiUrl = (process.env.TBCC_API_URL || "").replace(/\/$/, "");
  const apiKey = process.env.TBCC_INTERNAL_API_KEY;
  const ownerId = process.env.MOCK_SEED_USER_ID || process.env.STORAGE_HUB_OWNER_USER_ID;
  const limit = parseLimit();

  if (!apiUrl) {
    console.error("TBCC_API_URL required");
    process.exit(1);
  }
  if (!ownerId) {
    console.error("MOCK_SEED_USER_ID or STORAGE_HUB_OWNER_USER_ID required");
    process.exit(1);
  }

  const db = createAdminClient();
  // Fetch recent failed hub jobs; filter retryable in JS (jsonb filter quirks).
  const { data, error } = await db
    .from("ingest_jobs")
    .select("id, source_url, error, payload")
    .eq("source_kind", "telegram")
    .eq("status", "failed")
    .contains("payload", { hub: HUB })
    .order("id", { ascending: false })
    .limit(Math.min(limit * 5, 2000));

  if (error) {
    console.error("query failed:", error.message);
    process.exit(1);
  }

  const rows = ((data || []) as JobRow[]).filter(looksRetryable);
  // Dedupe by tbcc_id (keep newest job row).
  const byTbcc = new Map<number, JobRow>();
  for (const row of rows) {
    const id = row.payload?.tbcc_id;
    if (typeof id !== "number") continue;
    if (!byTbcc.has(id)) byTbcc.set(id, row);
  }
  const unique = [...byTbcc.values()].slice(0, limit);

  console.log(`Retrying up to ${unique.length} failed storage_hub jobs (limit=${limit})…`);
  console.log(`TBCC_API_URL=${apiUrl}`);

  const tmpDir = path.join(process.env.INGEST_LOCAL_INBOX ?? ".", ".tmp", "tbcc-storage-hub-retry");
  await mkdir(tmpDir, { recursive: true });

  let imported = 0;
  let skipped = 0;
  let failed = 0;

  for (const row of unique) {
    const it = toExportItem(row, apiUrl);
    if (!it) {
      failed += 1;
      continue;
    }
    const outcome = await ingestStorageHubItem(db, apiUrl, apiKey, it, ownerId, tmpDir);
    console.log(`tbcc_id=${it.id} job=${row.id} → ${outcome}`);
    if (outcome === "imported") imported += 1;
    else if (outcome === "skipped") skipped += 1;
    else failed += 1;
  }

  console.log(`Done. imported=${imported} skipped=${skipped} failed=${failed}`);
  if (failed > 0) process.exitCode = 1;
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
