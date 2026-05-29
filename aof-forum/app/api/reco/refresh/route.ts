import { NextResponse, type NextRequest } from "next/server";
import { runFullRecoMaintenance } from "@/lib/reco";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * POST /api/reco/refresh
 * 1. refresh_row_hot_scores() — updates `media_items.score` and `groups.score`
 * 2. refresh media_coview, group_coview, tag_coocc matviews
 *
 * Vercel cron example:
 *   { "crons": [ { "path": "/api/reco/refresh", "schedule": "0 * * * *" } ] }
 *
 * Headers: Authorization: Bearer <RECO_REFRESH_TOKEN>
 */
export async function POST(req: NextRequest) {
  const token = req.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  const expected = process.env.RECO_REFRESH_TOKEN;
  if (!expected || token !== expected) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  try {
    await runFullRecoMaintenance();
    return NextResponse.json({
      ok: true,
      at: new Date().toISOString(),
      steps: ["refresh_row_hot_scores", "media_coview", "group_coview", "tag_coocc"],
    });
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 500 });
  }
}
