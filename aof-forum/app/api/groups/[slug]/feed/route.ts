import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { groupFeed } from "@/lib/reco";
import { resolveManyMediaUrls } from "@/lib/media-url";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * GET /api/groups/[slug]/feed?cursor=<iso>&limit=24
 * Returns the media feed for a group (pinned first, then recent).
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const db = await createClient();
  const { data: g, error: gerr } = await db.from("groups").select("id").eq("slug", slug).maybeSingle();
  if (gerr) return NextResponse.json({ error: gerr.message }, { status: 500 });
  if (!g) return NextResponse.json({ error: "not found" }, { status: 404 });

  const limit = Math.min(parseInt(req.nextUrl.searchParams.get("limit") ?? "24", 10) || 24, 60);
  const cursor = req.nextUrl.searchParams.get("cursor");
  const rows = await groupFeed({ groupId: g.id, limit, before: cursor ?? undefined });
  const items = await resolveManyMediaUrls(rows);
  const last = items[items.length - 1];
  const nextCursor = items.length === limit && last ? last.added_at : null;
  return NextResponse.json({ items, nextCursor });
}
