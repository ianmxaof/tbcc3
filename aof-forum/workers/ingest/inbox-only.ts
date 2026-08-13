/**
 * One-shot drain of INGEST_LOCAL_INBOX only (no Telegram / storage-hub / job queue).
 * Used by `npm run ingest:inbox` (one-shot). Launcher uses `ingest:inbox:watch`.
 */
import { config as loadEnv } from "dotenv";
loadEnv({ path: process.env.DOTENV_PATH ?? ".env.local" });
loadEnv({ path: ".env", override: false });

import { startLocalFolderWatcher } from "./adapters/from-local-folder";
import { logger } from "../logger";

async function main(): Promise<void> {
  const inbox = process.env.INGEST_LOCAL_INBOX || "(unset)";
  logger.info({ inbox }, "inbox-only drain starting");
  await startLocalFolderWatcher({ watch: false });
  logger.info("inbox-only drain complete");
}

main().catch((e) => {
  logger.fatal({ err: (e as Error).message, stack: (e as Error).stack }, "inbox-only crashed");
  process.exit(1);
});
