import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { resolveManyMediaUrls } from "@/lib/media-url";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type RowM = {
  id: number;
  kind: "image" | "video" | "gif";
  title: string | null;
  b2_key: string;
  b2_thumb_key: string | null;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  views_count: number;
};

/**
 * GET /api/galleries/[slug]/media?limit=24&cursor=offset:48
 * Opaque cursor is `offset:<number>` for stable gallery-item ordering (position, media_id).
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const url = req.nextUrl;
  const limit = Math.min(Math.max(parseInt(url.searchParams.get("limit") ?? "24", 10) || 24, 1), 60);
  const cursor = url.searchParams.get("cursor") ?? "";
  let offset = 0;
  if (cursor.startsWith("offset:")) {
    const n = parseInt(cursor.slice("offset:".length), 10);
    if (Number.isFinite(n) && n >= 0) offset = n;
  }

  try {
    const db = await createClient();
    const { data: gallery, error: gErr } = await db.from("galleries").select("id").eq("slug", slug).maybeSingle();
    if (gErr || !gallery) {
      return NextResponse.json({ error: "not found" }, { status: 404 });
    }

    const { data: raw, error } = await db
      .from("gallery_items")
      .select(
        "media_id, position, media_items!inner(id, kind, title, b2_key, b2_thumb_key, width, height, duration_seconds, views_count)"
      )
      .eq("gallery_id", gallery.id)
      .order("position", { ascending: true })
      .order("media_id", { ascending: true })
      .range(offset, offset + limit - 1);
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    const flat: RowM[] = ((raw ?? []) as Array<{ media_items: RowM | RowM[] | null }>)
      .map((r) => (Array.isArray(r.media_items) ? r.media_items[0] : r.media_items))
      .filter((x): x is RowM => !!x);
    const items = await resolveManyMediaUrls(flat);
    const nextCursor = items.length === limit ? `offset:${offset + limit}` : null;
    return NextResponse.json({ items, nextCursor });
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 500 });
  }
}
