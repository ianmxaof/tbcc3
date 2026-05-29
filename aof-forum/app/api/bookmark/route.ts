import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const Body = z.object({
  media_id: z.number().int().positive(),
  bookmarked: z.boolean(),
});

export async function POST(req: NextRequest) {
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) return NextResponse.json({ error: "auth required" }, { status: 401 });
  let parsed;
  try { parsed = Body.parse(await req.json()); } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 400 });
  }
  if (parsed.bookmarked) {
    const { error } = await db
      .from("bookmarks")
      .upsert({ user_id: u.user.id, media_id: parsed.media_id }, { onConflict: "user_id,media_id" });
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  } else {
    const { error } = await db
      .from("bookmarks")
      .delete()
      .eq("user_id", u.user.id)
      .eq("media_id", parsed.media_id);
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, bookmarked: parsed.bookmarked });
}
