import { randomUUID } from "node:crypto";
import { mkdir, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { execa } from "execa";
import sharp from "sharp";
import { deleteKey, getObjectBuffer, headObject } from "@/lib/b2";
import { createAdminClient } from "@/lib/supabase/admin";

export type MediaKind = "image" | "video" | "gif";

export type FinalizeUploadInput = {
  b2Key: string;
  filename: string;
  contentType: string;
  byteSize: number;
  uploaderId: string;
  galleryId?: number | null;
};

export type FinalizeUploadResult =
  | { status: "done"; mediaId: number }
  | { status: "skipped_duplicate"; mediaId: number; reason: string }
  | { status: "failed"; reason: string };

function classifyMime(m: string): MediaKind | null {
  if (m === "image/gif") return "gif";
  if (m.startsWith("image/")) return "image";
  if (m.startsWith("video/")) return "video";
  return null;
}

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

async function ffprobeFile(localPath: string): Promise<{
  width?: number;
  height?: number;
  duration?: number;
}> {
  try {
    const { stdout } = await execa(
      "ffprobe",
      ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", localPath],
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
  } catch {
    return {};
  }
}

async function extractVideoFrame(localPath: string, durationSec: number | null): Promise<Buffer | null> {
  const at = Math.max(1, Math.floor((durationSec ?? 5) * 0.3));
  try {
    const { stdout } = await execa(
      "ffmpeg",
      [
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        String(at),
        "-i",
        localPath,
        "-frames:v",
        "1",
        "-f",
        "image2",
        "-vcodec",
        "mjpeg",
        "pipe:1",
      ],
      { encoding: null as unknown as undefined, timeout: 30_000 }
    );
    return Buffer.isBuffer(stdout) ? (stdout as unknown as Buffer) : Buffer.from(stdout as unknown as string);
  } catch {
    return null;
  }
}

export async function finalizeB2Upload(input: FinalizeUploadInput): Promise<FinalizeUploadResult> {
  const head = await headObject(input.b2Key);
  if (!head.exists) {
    return { status: "failed", reason: "object not found in storage" };
  }
  if (head.contentLength != null && input.byteSize > 0 && head.contentLength !== input.byteSize) {
    return { status: "failed", reason: "upload size mismatch" };
  }

  const kind = classifyMime(input.contentType);
  if (!kind) {
    await deleteKey(input.b2Key).catch(() => undefined);
    return { status: "failed", reason: `unsupported content-type: ${input.contentType}` };
  }

  const { body, contentType } = await getObjectBuffer(input.b2Key);
  const tmpDir = path.join(process.env.INGEST_LOCAL_INBOX ?? ".", ".tmp", "finalize");
  await mkdir(tmpDir, { recursive: true });
  const localPath = path.join(tmpDir, `${randomUUID()}-${input.filename}`);
  await writeFile(localPath, body);

  try {
    const probe = kind === "video" ? await ffprobeFile(localPath) : {};
    let hashSource = body;
    if (kind === "video") {
      const frame = await extractVideoFrame(localPath, probe.duration ?? null);
      if (frame) hashSource = frame;
    }

    let hash: Buffer | null = null;
    try {
      hash = await dhash(hashSource);
    } catch {
      hash = null;
    }

    const db = createAdminClient();
    if (hash) {
      const dup = await db
        .from("media_items")
        .select("id")
        .eq("phash", `\\x${hash.toString("hex")}`)
        .limit(1)
        .maybeSingle();
      if (dup.data?.id) {
        await deleteKey(input.b2Key).catch(() => undefined);
        return {
          status: "skipped_duplicate",
          mediaId: dup.data.id as number,
          reason: "phash match",
        };
      }
    }

    let makePublic = false;
    if (input.galleryId) {
      const { data: gallery } = await db
        .from("galleries")
        .select("id, owner_id, is_public")
        .eq("id", input.galleryId)
        .maybeSingle();
      if (!gallery || gallery.owner_id !== input.uploaderId) {
        return { status: "failed", reason: "gallery not found or not owned" };
      }
      makePublic = gallery.is_public === true;
    }

    const ins = await db
      .from("media_items")
      .insert({
        kind,
        title: input.filename,
        b2_key: input.b2Key,
        mime: contentType || input.contentType,
        byte_size: head.contentLength ?? input.byteSize,
        width: probe.width ?? null,
        height: probe.height ?? null,
        duration_seconds: probe.duration ?? null,
        phash: hash ? `\\x${hash.toString("hex")}` : null,
        source_kind: "upload",
        uploader_id: input.uploaderId,
        is_public: makePublic,
      })
      .select("id")
      .single();

    if (ins.error || !ins.data) {
      return { status: "failed", reason: ins.error?.message ?? "insert failed" };
    }

    const mediaId = ins.data.id as number;

    if (input.galleryId) {
      const { data: maxPos } = await db
        .from("gallery_items")
        .select("position")
        .eq("gallery_id", input.galleryId)
        .order("position", { ascending: false })
        .limit(1)
        .maybeSingle();
      const position = (maxPos?.position ?? -1) + 1;
      await db.from("gallery_items").insert({
        gallery_id: input.galleryId,
        media_id: mediaId,
        position,
      });
    }

    return { status: "done", mediaId };
  } finally {
    await unlink(localPath).catch(() => undefined);
  }
}

export async function getDailyUploadUsage(uploaderId: string): Promise<{ fileCount: number; byteTotal: number }> {
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  const db = createAdminClient();
  const { data } = await db
    .from("media_items")
    .select("byte_size")
    .eq("uploader_id", uploaderId)
    .gte("created_at", since);
  const rows = data ?? [];
  return {
    fileCount: rows.length,
    byteTotal: rows.reduce((s, r) => s + Number(r.byte_size ?? 0), 0),
  };
}
