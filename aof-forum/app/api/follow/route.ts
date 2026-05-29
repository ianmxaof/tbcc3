import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const Body = z.object({
  target_kind: z.enum(["user", "tag", "gallery", "group"]),
  target_user_id: z.string().uuid().optional(),
  target_object_id: z.number().int().positive().optional(),
  follow: z.boolean(),
});

export async function POST(req: NextRequest) {
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) return NextResponse.json({ error: "auth required" }, { status: 401 });

  let parsed;
  try { parsed = Body.parse(await req.json()); } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 400 });
  }
  if (parsed.target_kind === "user" && !parsed.target_user_id)
    return NextResponse.json({ error: "target_user_id required" }, { status: 400 });
  if (parsed.target_kind !== "user" && !parsed.target_object_id)
    return NextResponse.json({ error: "target_object_id required" }, { status: 400 });

  if (parsed.follow) {
    const { error } = await db.from("follows").insert({
      follower_id: u.user.id,
      target_kind: parsed.target_kind,
      target_user_id: parsed.target_kind === "user" ? parsed.target_user_id : null,
      target_object_id: parsed.target_kind === "user" ? null : parsed.target_object_id,
    });
    if (error && error.code !== "23505")
      return NextResponse.json({ error: error.message }, { status: 500 });
  } else {
    let q = db.from("follows").delete().eq("follower_id", u.user.id).eq("target_kind", parsed.target_kind);
    if (parsed.target_kind === "user") q = q.eq("target_user_id", parsed.target_user_id!);
    else q = q.eq("target_object_id", parsed.target_object_id!);
    const { error } = await q;
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, follow: parsed.follow });
}
