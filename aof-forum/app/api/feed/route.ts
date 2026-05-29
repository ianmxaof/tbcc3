import { NextResponse, type NextRequest } from "next/server";
import { feedHot, feedRecent } from "@/lib/reco";
import { resolveManyMediaUrls } from "@/lib/media-url";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * GET /api/feed?sort=hot|recent&cursor=...&limit=24
 * Cursor format:
 *   hot:    "<score>:<id>"
 *   recent: ISO timestamp
 */
export async function GET(req: NextRequest) {
  const url = req.nextUrl;
  const sort = url.searchParams.get("sort") === "recent" ? "recent" : "hot";
  const limit = Math.min(Math.max(parseInt(url.searchParams.get("limit") ?? "24", 10) || 24, 1), 60);
  const cursorRaw = url.searchParams.get("cursor");

  try {
    if (sort === "recent") {
      const rows = await feedRecent({ limit, before: cursorRaw ?? undefined });
      const items = await resolveManyMediaUrls(rows);
      const nextCursor = items.length === limit ? (items[items.length - 1] as { created_at?: string }).created_at ?? null : null;
      return NextResponse.json({ items, nextCursor });
    }
    let afterScore: number | undefined;
    let afterId: number | undefined;
    if (cursorRaw) {
      const [s, i] = cursorRaw.split(":");
      const sc = Number.parseFloat(s);
      const idc = Number.parseInt(i ?? "0", 10);
      if (Number.isFinite(sc) && Number.isFinite(idc)) {
        afterScore = sc;
        afterId = idc;
      }
    }
    const rows = await feedHot({ limit, afterScore, afterId });
    const items = await resolveManyMediaUrls(rows);
    const last = items[items.length - 1];
    const nextCursor =
      items.length === limit && last ? `${last.score.toFixed(6)}:${last.id}` : null;
    return NextResponse.json({ items, nextCursor });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    if (process.env.NODE_ENV === "development") {
      console.error("[/api/feed]", message, e);
    }
    let hint: string | undefined;
    if (/NEXT_PUBLIC_SUPABASE|Supabase URL and anon key/.test(message)) {
      hint = "Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in aof-forum/.env.local, then restart next dev.";
    } else if (/feed_hot|feed_recent|PGRST202|42883|does not exist|Could not find the function/i.test(message)) {
      hint =
        "Deploy SQL to your Supabase project: from aof-forum run `npx supabase db push` (or link + push) so RPCs like feed_hot exist. See supabase/migrations/0008_reco_functions.sql.";
    } else if (/Missing required env var: B2_/.test(message)) {
      hint =
        "Set B2_* in .env.local, or set NEXT_PUBLIC_MEDIA_BASE_URL to a public CDN base so the API can build media URLs without signing.";
    }
    return NextResponse.json({ error: message, hint }, { status: 500 });
  }
}
