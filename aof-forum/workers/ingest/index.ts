import { config as loadEnv } from "dotenv";
loadEnv({ path: process.env.DOTENV_PATH ?? ".env.local" });
loadEnv({ path: ".env", override: false });

import { startLocalFolderWatcher } from "./adapters/from-local-folder";
import { startJobQueueWorker } from "./adapters/from-job-queue";
import { pullFromStorageHub } from "./adapters/from-storage-hub";
import { pullFromTelegram } from "./adapters/from-telegram";
import { logger } from "../logger";

/**
 * Combined ingest worker. Runs three adapters in parallel:
 *   1. local-folder: drag-and-drop into INGEST_LOCAL_INBOX
 *   2. job-queue:    rows in `ingest_jobs` table (created by the api/ingest UI)
 *   3. telegram:     poll tbcc for new captured media
 *   4. storage-hub:  poll tbcc origin=storage_hub → lane groups (INGEST_STORAGE_HUB=1)
 *
 * Usage:
 *   tsx workers/ingest/index.ts            # one-shot drain
 *   tsx workers/ingest/index.ts --watch    # long-running poller
 */
async function main(): Promise<void> {
  const watch = process.argv.includes("--watch");
  const storageHubFlag = (process.env.INGEST_STORAGE_HUB || "0").trim().toLowerCase();
  const storageHubEnabled = !["0", "false", "no", "off"].includes(storageHubFlag);
  logger.info({ watch, storageHubEnabled }, "ingest worker starting");

  const tasks: Promise<unknown>[] = [
    startLocalFolderWatcher({ watch }),
    startJobQueueWorker({ watch }),
    pullFromTelegram({ watch }),
  ];
  if (storageHubEnabled) {
    tasks.push(pullFromStorageHub({ watch }));
  }

  if (watch) {
    // Keep process alive; adapters loop internally.
    await Promise.all(tasks);
  } else {
    await Promise.all(tasks);
    logger.info("one-shot drain complete");
  }
}

main().catch((e) => {
  logger.fatal({ err: (e as Error).message, stack: (e as Error).stack }, "ingest worker crashed");
  process.exit(1);
});
