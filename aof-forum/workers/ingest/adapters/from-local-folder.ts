import path from "node:path";
import { mkdir } from "node:fs/promises";
import chokidar from "chokidar";
import { ingestOne } from "../pipeline";
import { logger } from "../../logger";

/**
 * Watch the inbox folder. On a new file (after it finishes writing), run the
 * ingest pipeline and move/delete the source.
 */
export async function startLocalFolderWatcher(opts: { watch: boolean }): Promise<void> {
  const inbox = process.env.INGEST_LOCAL_INBOX;
  if (!inbox) {
    logger.warn("INGEST_LOCAL_INBOX not set - local-folder adapter disabled");
    return;
  }
  await mkdir(inbox, { recursive: true });

  const handle = async (filePath: string) => {
    // Ignore our own .tmp downloads.
    if (filePath.includes(`${path.sep}.tmp${path.sep}`)) return;
    const base = path.basename(filePath);
    if (base.startsWith(".")) return;
    logger.info({ filePath }, "inbox: ingesting");
    try {
      const r = await ingestOne({ source: filePath, sourceKind: "local_inbox" });
      logger.info({ filePath, ...r }, "inbox: done");
      if (r.status === "done" || r.status === "skipped_duplicate") {
        // Leave the file in place - users can clean inbox manually, or we add a
        // .processed/ subfolder later. Skipping move for now to avoid surprises.
      }
    } catch (e) {
      logger.error({ err: (e as Error).message, filePath }, "inbox: failed");
    }
  };

  if (!opts.watch) {
    // One-shot drain.
    const fs = await import("node:fs/promises");
    const entries = await fs.readdir(inbox).catch(() => []);
    for (const name of entries) {
      const full = path.join(inbox, name);
      const st = await fs.stat(full).catch(() => null);
      if (st?.isFile()) await handle(full);
    }
    return;
  }

  const watcher = chokidar.watch(inbox, {
    ignoreInitial: false,
    awaitWriteFinish: { stabilityThreshold: 1500, pollInterval: 500 },
    depth: 0,
  });
  watcher
    .on("add", (p) => void handle(p))
    .on("error", (e) => logger.error({ err: (e as Error).message }, "watcher error"));
  logger.info({ inbox }, "watching local inbox");
}
