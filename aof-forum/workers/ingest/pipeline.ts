import { randomUUID } from "node:crypto";
import { createReadStream, statSync } from "node:fs";
import { readFile, copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import mime from "mime-types";
import sharp from "sharp";
import { buildMediaKey, putStream } from "../../lib/b2";
import { createAdminClient } from "../../lib/supabase/admin";
import { logger } from "../logger";

export type MediaKind = "image" | "video" | "gif";
export type SourceKind = "upload" | "telegram" | "web_pull" | "stash_import" | "local_inbox";

export interface IngestInput {
  /** Absolute path to a file on disk OR remote URL (will be downloaded first). */
  source: string;
  sourceKind: SourceKind;
  /** Optional user-supplied metadata. */
  title?: string;
  description?: string;
  uploaderId?: string | null;
  /** Optional drop target: group/gallery to attach the resulting media to. */
  groupId?: number | null;
  galleryId?: number | null;
  /** Pre-existing local filename hint (for URL ingest). */
  filenameHint?: string;
}

export interface IngestResult {
  status: "done" | "skipped_duplicate" | "failed";
  mediaId?: number;
  b2Key?: string;
  reason?: string;
}

// =============================================================================
// Helpers
// =============================================================================

function classifyMime(m: string): MediaKind | null {
  if (m === "image/gif") return "gif";
  if (m.startsWith("image/")) return "image";
  if (m.startsWith("video/")) return "video";
  return null;
}

/**
 * Difference hash (dHash) on a 9x8 grayscale resize. Returns 64 bits as 8 bytes.
 * Cheap, robust to small edits, good for first-pass dedupe.
 */
async function dhash(buf: Buffer): Promise<Buffer> {
  const raw = await sharp(buf, { failOn: "none" })
    .grayscale()
    .resize(9, 8, { fit: "fill" })
    .raw()
    .toBuffer();
  const out = Buffer.alloc(8);
  for (let row = 0; row < 8; row++) {
    let byte = 0;
    for (let col = 0; col < 8; col++) {
      const left = raw[row * 9 + col];
      const right = raw[row * 9 + col + 1];
      if (right > left) byte |= 1 << (7 - col);
    }
    out[row] = byte;
  }
  return out;
}

/**
 * Extract a representative video frame at ~30% of duration as JPEG buffer.
 * Returns null if ffmpeg isn't available or the file can't be probed.
 */
async function extractVideoFrame(localPath: string, durationSec: number | null): Promise<Buffer | null> {
  const at = Math.max(1, Math.floor((durationSec ?? 5) * 0.3));
  try {
    const { execa } = await import("execa");
    const { stdout } = await execa(
      "ffmpeg",
      ["-hide_banner", "-loglevel", "error", "-ss", String(at), "-i", localPath, "-frames:v", "1", "-f", "image2", "-vcodec", "mjpeg", "pipe:1"],
      { buffer: true, timeout: 30_000 }
    );
    return Buffer.isBuffer(stdout) ? stdout : Buffer.from(stdout as unknown as string);
  } catch (e) {
    logger.warn({ err: (e as Error).message, localPath }, "ffmpeg frame extract failed - install ffmpeg for video phash");
    return null;
  }
}

interface ProbeResult {
  width?: number;
  height?: number;
  duration?: number;
  mime?: string;
}

async function ffprobeFile(localPath: string): Promise<ProbeResult> {
  try {
    const { execa } = await import("execa");
    const { stdout } = await execa(
      "ffprobe",
      [
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        localPath,
      ],
      { timeout: 30_000 }
    );
    const j = JSON.parse(stdout) as {
      streams?: Array<{ codec_type?: string; width?: number; height?: number }>;
      format?: { duration?: string };
    };
    const v = j.streams?.find((s) => s.codec_type === "video");
    return {
      width: v?.width,
      height: v?.height,
      duration: j.format?.duration ? Number.parseFloat(j.format.duration) : undefined,
    };
  } catch (e) {
    logger.warn({ err: (e as Error).message, localPath }, "ffprobe failed - skipping size/duration");
    return {};
  }
}

async function downloadToBuffer(url: string): Promise<{ buf: Buffer; contentType: string; filename: string }> {
  const r = await fetch(url, { redirect: "follow" });
  if (!r.ok) throw new Error(`download failed: ${r.status} ${r.statusText} for ${url}`);
  const contentType = r.headers.get("content-type") ?? "application/octet-stream";
  const ab = await r.arrayBuffer();
  const u = new URL(url);
  const filename = path.basename(u.pathname) || `download-${Date.now()}`;
  return { buf: Buffer.from(ab), contentType, filename };
}

async function copyToStashInbox(srcPath: string, baseName: string): Promise<void> {
  const inbox = process.env.STASH_INBOX_DIR;
  if (!inbox) return;
  try {
    await mkdir(inbox, { recursive: true });
    const dest = path.join(inbox, baseName);
    await copyFile(srcPath, dest);
    logger.debug({ dest }, "copied to stash inbox");
  } catch (e) {
    logger.warn({ err: (e as Error).message }, "copy to stash inbox failed");
  }
}

// =============================================================================
// Main entrypoint
// =============================================================================

export async function ingestOne(input: IngestInput): Promise<IngestResult> {
  const db = createAdminClient();
  const log = logger.child({ source: input.source.slice(0, 200), kind: input.sourceKind });

  let localPath: string;
  let cleanupLocal = false;
  let fileBuf: Buffer;
  let contentType: string;
  let filename: string;

  // Resolve source -> local buffer + path.
  if (/^https?:\/\//i.test(input.source)) {
    const dl = await downloadToBuffer(input.source);
    fileBuf = dl.buf;
    contentType = dl.contentType;
    filename = input.filenameHint ?? dl.filename;
    // Stage to a temp file so ffprobe / ffmpeg can read it.
    const tmpDir = path.join(process.env.INGEST_LOCAL_INBOX ?? ".", ".tmp");
    await mkdir(tmpDir, { recursive: true });
    localPath = path.join(tmpDir, `${randomUUID()}-${filename}`);
    await import("node:fs/promises").then((m) => m.writeFile(localPath, fileBuf));
    cleanupLocal = true;
  } else {
    localPath = input.source;
    const stat = statSync(localPath);
    if (!stat.isFile()) {
      return { status: "failed", reason: `not a file: ${localPath}` };
    }
    fileBuf = await readFile(localPath);
    contentType = (mime.lookup(localPath) || "application/octet-stream") as string;
    filename = path.basename(localPath);
  }

  const kind = classifyMime(contentType);
  if (!kind) {
    log.info({ contentType }, "skipping non-media");
    return { status: "failed", reason: `unsupported content-type: ${contentType}` };
  }

  // Probe + hash.
  const probe = kind === "video" ? await ffprobeFile(localPath) : {};
  let hashSource = fileBuf;
  if (kind === "video") {
    const frame = await extractVideoFrame(localPath, probe.duration ?? null);
    if (frame) hashSource = frame;
  }
  let hash: Buffer | null = null;
  try {
    hash = await dhash(hashSource);
  } catch (e) {
    log.warn({ err: (e as Error).message }, "dhash failed - continuing without dedupe hash");
  }

  // Dedupe by hash.
  if (hash) {
    const dup = await db
      .from("media_items")
      .select("id")
      .eq("phash", `\\x${hash.toString("hex")}`)
      .limit(1)
      .maybeSingle();
    if (dup.data?.id) {
      log.info({ existingId: dup.data.id }, "duplicate by phash - skipping");
      return { status: "skipped_duplicate", mediaId: dup.data.id, reason: "phash match" };
    }
  }

  // Upload to B2.
  const ext = (mime.extension(contentType) || filename.split(".").pop() || "bin").toString();
  const b2Key = buildMediaKey(randomUUID(), ext);
  await putStream({
    key: b2Key,
    body: createReadStream(localPath),
    contentType,
    contentLength: statSync(localPath).size,
  });
  log.info({ b2Key, bytes: statSync(localPath).size }, "uploaded to B2");

  // Insert row.
  const ins = await db
    .from("media_items")
    .insert({
      kind,
      title: input.title ?? filename,
      description: input.description ?? null,
      b2_key: b2Key,
      mime: contentType,
      byte_size: statSync(localPath).size,
      width: probe.width ?? null,
      height: probe.height ?? null,
      duration_seconds: probe.duration ?? null,
      phash: hash ? `\\x${hash.toString("hex")}` : null,
      source_url: /^https?:\/\//i.test(input.source) ? input.source : null,
      source_kind: input.sourceKind,
      uploader_id: input.uploaderId ?? null,
    })
    .select("id")
    .single();

  if (ins.error || !ins.data) {
    log.error({ err: ins.error?.message }, "media_items insert failed");
    return { status: "failed", reason: ins.error?.message ?? "insert failed" };
  }
  const mediaId = ins.data.id as number;

  // Optional: attach to a group / gallery.
  if (input.groupId) {
    await db.from("group_media").insert({
      group_id: input.groupId,
      media_id: mediaId,
      added_by: input.uploaderId ?? null,
    });
  }
  if (input.galleryId) {
    await db.from("gallery_items").insert({
      gallery_id: input.galleryId,
      media_id: mediaId,
    });
  }

  // Hand off to Stash for auto-tagging (community plugins do the work).
  await copyToStashInbox(localPath, filename);

  if (cleanupLocal) {
    await import("node:fs/promises").then((m) => m.unlink(localPath).catch(() => {}));
  }

  return { status: "done", mediaId, b2Key };
}
