import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { relatedGalleries } from "@/lib/reco";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * GET /api/galleries/[slug]/related?limit=12
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const limit = Math.min(parseInt(req.nextUrl.searchParams.get("limit") ?? "12", 10) || 12, 24);
  const db = await createClient();
  const { data: g } = await db.from("galleries").select("id").eq("slug", slug).eq("is_public", true).maybeSingle();
  if (!g) return NextResponse.json({ error: "not found" }, { status: 404 });
  try {
    const items = await relatedGalleries(g.id, limit);
    return NextResponse.json({ items });
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 500 });
  }
}
