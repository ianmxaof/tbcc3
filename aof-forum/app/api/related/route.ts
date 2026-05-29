import { NextResponse, type NextRequest } from "next/server";
import { relatedMedia, relatedMediaInGroup } from "@/lib/reco";
import { createClient } from "@/lib/supabase/server";
import { readSessionId } from "@/lib/session";
import { resolveManyMediaUrls } from "@/lib/media-url";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * GET /api/related?media_id=123&limit=24&group_slug=my-group
 * Without group_slug: global related (tag + coview).
 * With group_slug: related only among media in that group (caller must have navigated from the group).
 */
export async function GET(req: NextRequest) {
  const url = req.nextUrl;
  const mediaId = Number.parseInt(url.searchParams.get("media_id") ?? "", 10);
  const limit = Math.min(Math.max(parseInt(url.searchParams.get("limit") ?? "24", 10) || 24, 1), 60);
  const groupSlug = url.searchParams.get("group_slug")?.trim() || null;
  if (!Number.isFinite(mediaId) || mediaId <= 0) {
    return NextResponse.json({ error: "bad media_id" }, { status: 400 });
  }
  try {
    const db = await createClient();
    const { data: u } = await db.auth.getUser();
    const sessionId = await readSessionId();

    let rows;
    if (groupSlug) {
      const { data: grp } = await db.from("groups").select("id").eq("slug", groupSlug).maybeSingle();
      if (!grp) return NextResponse.json({ error: "unknown group" }, { status: 404 });
      rows = await relatedMediaInGroup({
        mediaId,
        groupId: grp.id,
        limit,
        userId: u.user?.id ?? null,
        sessionId,
      });
    } else {
      rows = await relatedMedia({
        mediaId,
        limit,
        userId: u.user?.id ?? null,
        sessionId,
      });
    }
    const items = await resolveManyMediaUrls(rows);
    return NextResponse.json({ items });
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 500 });
  }
}
