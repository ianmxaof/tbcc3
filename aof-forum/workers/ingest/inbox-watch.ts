/**
 * Watch INGEST_LOCAL_INBOX only; process existing + new drops; idle-exit (default 5 min).
 * Used by `npm run ingest:inbox:watch` and `! AOF INGEST.cmd`.
 */
import { config as loadEnv } from "dotenv";
loadEnv({ path: process.env.DOTENV_PATH ?? ".env.local" });
loadEnv({ path: ".env", override: false });

import { DEFAULT_INBOX_IDLE_MS, startLocalFolderWatcher } from "./adapters/from-local-folder";
import { logger } from "../logger";

async function main(): Promise<void> {
  const inbox = process.env.INGEST_LOCAL_INBOX || "(unset)";
  const idleMs =
    process.env.INGEST_INBOX_IDLE_MS !== undefined && process.env.INGEST_INBOX_IDLE_MS !== ""
      ? Math.max(0, parseInt(process.env.INGEST_INBOX_IDLE_MS, 10) || 0)
      : DEFAULT_INBOX_IDLE_MS;
  logger.info({ inbox, idleMs }, "inbox-only watch starting");
  await startLocalFolderWatcher({ watch: true, idleMs });
}

main().catch((e) => {
  logger.fatal({ err: (e as Error).message, stack: (e as Error).stack }, "inbox-only watch crashed");
  process.exit(1);
});
