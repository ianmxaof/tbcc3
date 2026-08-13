import path from "node:path";
import { mkdir, unlink, readdir, stat } from "node:fs/promises";
import chokidar from "chokidar";
import { ingestOne } from "../pipeline";
import { logger } from "../../logger";

/** Operator launcher / notes that live in the inbox — never ingest these. */
const INBOX_SKIP_NAMES = new Set([
  "! aof ingest.cmd",
  "!aof ingest.cmd",
  "desktop.ini",
  "thumbs.db",
]);

const INBOX_SKIP_EXT = new Set([
  ".cmd",
  ".bat",
  ".ps1",
  ".md",
  ".txt",
  ".url",
  ".lnk",
  ".ini",
  ".tmp",
  ".partial",
  ".crdownload",
]);

/** Default idle exit for watch mode (5 minutes). Override with INGEST_INBOX_IDLE_MS. */
export const DEFAULT_INBOX_IDLE_MS = 5 * 60 * 1000;

function shouldSkipInboxFile(filePath: string): boolean {
  if (filePath.includes(`${path.sep}.tmp${path.sep}`)) return true;
  const base = path.basename(filePath);
  if (base.startsWith(".")) return true;
  if (INBOX_SKIP_NAMES.has(base.toLowerCase())) return true;
  const ext = path.extname(base).toLowerCase();
  if (INBOX_SKIP_EXT.has(ext)) return true;
  return false;
}

async function deleteInboxFile(filePath: string): Promise<void> {
  try {
    await unlink(filePath);
    logger.info({ filePath }, "inbox: deleted after success");
  } catch (e) {
    logger.error(
      { err: (e as Error).message, filePath },
      "inbox: could not delete after success — delete manually"
    );
  }
}

export interface LocalFolderWatcherOpts {
  watch: boolean;
  /**
   * When `watch` is true: exit the process after this many ms with no media
   * activity (no new file start/end). Default 5 minutes. Set 0 to never idle-exit.
   */
  idleMs?: number;
}

/**
 * Watch / drain the inbox folder. On success (or duplicate skip), permanently
 * deletes the source file. Failures stay in place for retry.
 *
 * Watch mode with idleMs > 0 auto-exits so the launcher does not sit on CPU/RAM.
 */
export async function startLocalFolderWatcher(opts: LocalFolderWatcherOpts): Promise<void> {
  const inbox = process.env.INGEST_LOCAL_INBOX;
  if (!inbox) {
    logger.warn("INGEST_LOCAL_INBOX not set - local-folder adapter disabled");
    return;
  }
  await mkdir(inbox, { recursive: true });

  const envIdle = process.env.INGEST_INBOX_IDLE_MS;
  // Idle-exit only when explicitly requested (inbox:watch / INGEST_INBOX_IDLE_MS).
  // Full `npm run ingest:watch` must not die after 5 minutes of quiet inbox.
  const idleMs =
    opts.idleMs !== undefined
      ? opts.idleMs
      : envIdle !== undefined && envIdle !== ""
        ? Math.max(0, parseInt(envIdle, 10) || 0)
        : 0;

  let inFlight = 0;
  let idleTimer: ReturnType<typeof setTimeout> | null = null;
  let shuttingDown = false;
  // Assigned below before any idle tick can fire; typed for close().
  let watcher: { close: () => Promise<void> } | null = null;

  const clearIdle = () => {
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
  };

  const scheduleIdleExit = () => {
    if (!opts.watch || idleMs <= 0 || shuttingDown) return;
    clearIdle();
    idleTimer = setTimeout(() => {
      void (async () => {
        if (shuttingDown) return;
        if (inFlight > 0) {
          scheduleIdleExit();
          return;
        }
        shuttingDown = true;
        logger.info({ idleMs }, "inbox: idle — shutting down watcher");
        clearIdle();
        try {
          await watcher?.close();
        } catch {
          /* ignore */
        }
        process.exit(0);
      })();
    }, idleMs);
  };

  const bumpActivity = () => {
    if (!opts.watch || idleMs <= 0) return;
    scheduleIdleExit();
  };

  const handle = async (filePath: string) => {
    if (shouldSkipInboxFile(filePath)) return;
    if (shuttingDown) return;
    inFlight += 1;
    bumpActivity();
    logger.info({ filePath }, "inbox: ingesting");
    try {
      const r = await ingestOne({ source: filePath, sourceKind: "local_inbox" });
      logger.info({ filePath, ...r }, "inbox: done");
      if (r.status === "done" || r.status === "skipped_duplicate") {
        await deleteInboxFile(filePath);
      }
    } catch (e) {
      logger.error({ err: (e as Error).message, filePath }, "inbox: failed");
    } finally {
      inFlight = Math.max(0, inFlight - 1);
      bumpActivity();
    }
  };

  if (!opts.watch) {
    const entries = await readdir(inbox).catch(() => []);
    for (const name of entries) {
      const full = path.join(inbox, name);
      const st = await stat(full).catch(() => null);
      if (st?.isFile()) await handle(full);
    }
    return;
  }

  const chokidarWatcher = chokidar.watch(inbox, {
    ignoreInitial: false,
    awaitWriteFinish: { stabilityThreshold: 1500, pollInterval: 500 },
    depth: 0,
  });
  watcher = chokidarWatcher;
  chokidarWatcher
    .on("add", (p) => void handle(p))
    .on("error", (e) => logger.error({ err: (e as Error).message }, "watcher error"));
  logger.info({ inbox, idleMs }, "watching local inbox");
  bumpActivity();

  // Keep the promise pending until idle exit or process signal.
  await new Promise<void>(() => {
    /* resolved only via process.exit on idle */
  });
}
