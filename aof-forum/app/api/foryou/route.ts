import { NextResponse, type NextRequest } from "next/server";
import { foryouFeed } from "@/lib/reco";
import { createClient } from "@/lib/supabase/server";
import { getOrCreateSessionId } from "@/lib/session";
import { resolveManyMediaUrls } from "@/lib/media-url";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * GET /api/foryou?cursor=<offset>&limit=24
 * Personalized feed (v3): tag affinity + trending + epsilon-greedy exploration.
 */
export async function GET(req: NextRequest) {
  const limit = Math.min(Math.max(parseInt(req.nextUrl.searchParams.get("limit") ?? "24", 10) || 24, 1), 60);
  const offset = parseInt(req.nextUrl.searchParams.get("cursor") ?? "0", 10) || 0;
  try {
    const db = await createClient();
    const { data: u } = await db.auth.getUser();
    const sessionId = await getOrCreateSessionId();
    const rows = await foryouFeed({
      userId: u.user?.id ?? null,
      sessionId,
      limit,
      offset,
    });
    const items = await resolveManyMediaUrls(rows);
    const nextCursor = items.length === limit ? String(offset + limit) : null;
    return NextResponse.json({ items, nextCursor });
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 500 });
  }
}
