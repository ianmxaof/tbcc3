import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

const Body = z.object({
  targetKind: z.enum(["media", "gallery", "group", "thread", "post", "connect_listing"]),
  targetId: z.number().int().positive(),
  reason: z.string().max(500).optional(),
});

/** POST /api/report — flag content for moderation. */
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

  const { error } = await db.from("flags").insert({
    target_kind: parsed.targetKind,
    target_id: parsed.targetId,
    reporter_id: u.user.id,
    reason: parsed.reason?.trim() || null,
  });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true }, { status: 201 });
}
