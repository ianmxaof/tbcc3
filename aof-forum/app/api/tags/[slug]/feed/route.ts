import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { tagFeed } from "@/lib/reco";
import { resolveManyMediaUrls } from "@/lib/media-url";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const db = await createClient();
  const { data: t } = await db.from("tags").select("id").eq("slug", slug).maybeSingle();
  if (!t) return NextResponse.json({ error: "not found" }, { status: 404 });
  const limit = Math.min(parseInt(req.nextUrl.searchParams.get("limit") ?? "24", 10) || 24, 60);
  const cursor = req.nextUrl.searchParams.get("cursor");
  const rows = await tagFeed({ tagId: t.id, limit, before: cursor ?? undefined });
  const items = await resolveManyMediaUrls(rows);
  const last = items[items.length - 1] as { created_at?: string } | undefined;
  const nextCursor = items.length === limit && last?.created_at ? last.created_at : null;
  return NextResponse.json({ items, nextCursor });
}
