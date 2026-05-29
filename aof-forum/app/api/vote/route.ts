import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const Body = z.object({
  target_kind: z.enum(["thread", "post", "media", "group", "gallery"]),
  target_id: z.number().int().positive(),
  value: z.union([z.literal(-1), z.literal(0), z.literal(1)]),
});

/**
 * POST /api/vote { target_kind, target_id, value }
 *   value=1   -> upvote
 *   value=-1  -> downvote
 *   value=0   -> clear vote
 *
 * Counter updates on the target row happen in the votes trigger
 * (see 0006_reco.sql -> votes_update_target_counters).
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

  if (parsed.value === 0) {
    const { error } = await db
      .from("votes")
      .delete()
      .eq("user_id", u.user.id)
      .eq("target_kind", parsed.target_kind)
      .eq("target_id", parsed.target_id);
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ ok: true, value: 0 });
  }

  const { error } = await db.from("votes").upsert(
    {
      user_id: u.user.id,
      target_kind: parsed.target_kind,
      target_id: parsed.target_id,
      value: parsed.value,
    },
    { onConflict: "user_id,target_kind,target_id" }
  );
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true, value: parsed.value });
}
