import { NextResponse, type NextRequest } from "next/server";
import { randomUUID } from "node:crypto";
import { z } from "zod";
import { buildMediaKey, signedPutUrl } from "@/lib/b2";
import { createClient } from "@/lib/supabase/server";
import { getDailyUploadUsage } from "@/lib/server/finalize-b2-upload";
import {
  UPLOAD_MAX_FILE_BYTES,
  checkUploadQuota,
  isAllowedUploadMime,
} from "@/lib/upload-limits";
import mime from "mime-types";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const FileSpec = z.object({
  name: z.string().min(1).max(255),
  contentType: z.string().min(1).max(128),
  size: z.number().int().positive(),
});

const Body = z.object({
  files: z.array(FileSpec).min(1),
  galleryId: z.number().int().positive().nullable().optional(),
});

function safeExt(filename: string, contentType: string): string {
  const fromMime = mime.extension(contentType);
  if (fromMime && typeof fromMime === "string") return fromMime;
  const part = filename.split(".").pop();
  return part && part.length <= 8 ? part.toLowerCase() : "bin";
}

/**
 * POST /api/upload/presign
 * Returns presigned PUT URLs for direct browser → B2 upload.
 */
export async function POST(req: NextRequest) {
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) return NextResponse.json({ error: "auth required" }, { status: 401 });

  let parsed;
  try {
    parsed = Body.parse(await req.json());
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 400 });
  }

  for (const f of parsed.files) {
    if (!isAllowedUploadMime(f.contentType)) {
      return NextResponse.json({ error: `unsupported type: ${f.contentType}` }, { status: 400 });
    }
    if (f.size > UPLOAD_MAX_FILE_BYTES) {
      return NextResponse.json({ error: `file too large (max ${UPLOAD_MAX_FILE_BYTES} bytes)` }, { status: 400 });
    }
  }

  const usage = await getDailyUploadUsage(u.user.id);
  const incomingBytes = parsed.files.reduce((s, f) => s + f.size, 0);
  const quota = checkUploadQuota(usage, parsed.files.length, incomingBytes);
  if (!quota.ok) {
    return NextResponse.json({ error: quota.reason, quota }, { status: 429 });
  }

  if (parsed.galleryId) {
    const { data: gallery } = await db
      .from("galleries")
      .select("id")
      .eq("id", parsed.galleryId)
      .eq("owner_id", u.user.id)
      .maybeSingle();
    if (!gallery) {
      return NextResponse.json({ error: "gallery not found" }, { status: 400 });
    }
  }

  const uploads = [];
  for (const f of parsed.files) {
    const ext = safeExt(f.name, f.contentType);
    const key = buildMediaKey(randomUUID(), ext);
    const putUrl = await signedPutUrl(key, f.contentType);
    uploads.push({
      key,
      putUrl,
      contentType: f.contentType,
      filename: f.name,
      byteSize: f.size,
    });
  }

  return NextResponse.json({
    uploads,
    quota: quota.limits,
    galleryId: parsed.galleryId ?? null,
  });
}
