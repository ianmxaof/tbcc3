/**
 * Bulk drain: Storage Hub + AOF network pool media → AOF Forum groups.
 *
 * Loops until TBCC /media/export?origin=storage_hub returns empty
 * (or cursor is pinned on a retryable failure with no forward progress —
 * in that case keep looping; worker retries with backoff).
 *
 *   npm run ingest:storage-hub
 *   npm run ingest:storage-hub -- --reset-cursor
 */
import { config } from "dotenv";
import path from "node:path";
import { createAdminClient } from "../lib/supabase/admin";
import {
  STORAGE_HUB_CURSOR_URL,
  pullFromStorageHub,
} from "../workers/ingest/adapters/from-storage-hub";

const root = process.cwd();
config({ path: path.join(root, ".env.local") });
config({ path: path.join(root, ".env") });

async function resetCursor(): Promise<void> {
  const db = createAdminClient();
  const { data } = await db
    .from("ingest_jobs")
    .select("id")
    .eq("source_kind", "telegram")
    .eq("source_url", STORAGE_HUB_CURSOR_URL)
    .maybeSingle();
  if (data?.id) {
    await db.from("ingest_jobs").delete().eq("id", data.id);
    console.log("Reset storage hub export cursor.");
  }
}

async function main(): Promise<void> {
  if (process.argv.includes("--reset-cursor")) {
    await resetCursor();
  }

  const ownerId = process.env.MOCK_SEED_USER_ID || process.env.STORAGE_HUB_OWNER_USER_ID;
  if (!ownerId) {
    console.error("Set MOCK_SEED_USER_ID or STORAGE_HUB_OWNER_USER_ID in .env.local");
    process.exit(1);
  }

  let totalImported = 0;
  let totalSkipped = 0;
  let totalFailed = 0;
  let batches = 0;
  const maxBatches = Number.parseInt(process.env.TBCC_INGEST_MAX_BATCHES || "0", 10);
  let idleEmpty = 0;
  let lastCursor = -1;
  let stuckBatches = 0;

  console.log("Draining Storage Hub export into AOF Forum groups…");
  console.log(`TBCC_API_URL=${process.env.TBCC_API_URL || "(unset)"}`);
  console.log(`Owner=${ownerId}`);

  while (true) {
    const result = await pullFromStorageHub({ watch: false, ownerId });
    batches += 1;
    totalImported += result.imported;
    totalSkipped += result.skipped;
    totalFailed += result.failed;

    console.log(
      `batch ${batches}: seen=${result.itemsSeen} imported=${result.imported} skipped=${result.skipped} ` +
        `failed=${result.failed} (retryable=${result.failedRetryable} permanent=${result.failedPermanent}) ` +
        `cursor=${result.maxId}`
    );

    if (!result.itemsSeen) {
      idleEmpty += 1;
      if (idleEmpty >= 2) break;
      continue;
    }
    idleEmpty = 0;

    if (result.maxId === lastCursor && result.failedRetryable > 0 && result.imported === 0) {
      stuckBatches += 1;
      // Keep retrying pinned cursor; after many no-progress loops exit so operator can investigate.
      if (stuckBatches >= 10) {
        console.log(
          `Pinned on retryable failures at cursor=${result.maxId} after ${stuckBatches} no-progress batches — stopping. Run retry-failed later.`
        );
        process.exitCode = 1;
        break;
      }
    } else {
      stuckBatches = 0;
    }
    lastCursor = result.maxId;

    if (maxBatches > 0 && batches >= maxBatches) {
      console.log(`Stopped after ${maxBatches} batch(es) (TBCC_INGEST_MAX_BATCHES).`);
      break;
    }
  }

  console.log(
    `Done. imported=${totalImported} skipped=${totalSkipped} failed=${totalFailed} batches=${batches}`
  );
  if (totalFailed > 0 && process.exitCode !== 1) {
    process.exitCode = 1;
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
