import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { relatedGroups } from "@/lib/reco";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * GET /api/groups/[slug]/related?limit=12
 * Returns groups sharing the most members (Jaccard similarity).
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const db = await createClient();
  const { data: g } = await db.from("groups").select("id").eq("slug", slug).maybeSingle();
  if (!g) return NextResponse.json({ error: "not found" }, { status: 404 });
  const limit = Math.min(parseInt(req.nextUrl.searchParams.get("limit") ?? "12", 10) || 12, 30);
  try {
    const items = await relatedGroups(g.id, limit);
    return NextResponse.json({ items });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    if (/group_coview|has not been populated|materialized view/i.test(message)) {
      return NextResponse.json({ items: [] });
    }
    console.warn(`[related] ${slug}: ${message}`);
    return NextResponse.json({ items: [], error: message }, { status: 200 });
  }
}
