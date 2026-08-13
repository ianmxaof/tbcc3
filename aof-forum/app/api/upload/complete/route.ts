import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { finalizeB2Upload } from "@/lib/server/finalize-b2-upload";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const Item = z.object({
  key: z.string().min(1),
  filename: z.string().min(1).max(255),
  contentType: z.string().min(1).max(128),
  byteSize: z.number().int().positive(),
});

const Body = z.object({
  items: z.array(Item).min(1),
  galleryId: z.number().int().positive().nullable().optional(),
});

/**
 * POST /api/upload/complete
 * After browser PUT to B2, finalize: dedupe, media_items row, optional gallery attach.
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

  const results = [];
  for (const item of parsed.items) {
    const r = await finalizeB2Upload({
      b2Key: item.key,
      filename: item.filename,
      contentType: item.contentType,
      byteSize: item.byteSize,
      uploaderId: u.user.id,
      galleryId: parsed.galleryId ?? null,
    });
    results.push({
      key: item.key,
      filename: item.filename,
      status: r.status,
      mediaId: "mediaId" in r ? r.mediaId : undefined,
      reason: "reason" in r ? r.reason : undefined,
    });
  }

  return NextResponse.json({ results });
}
