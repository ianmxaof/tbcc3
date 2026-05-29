import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(_req: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) return NextResponse.json({ error: "auth required" }, { status: 401 });

  const { data: g } = await db.from("groups").select("id, visibility").eq("slug", slug).maybeSingle();
  if (!g) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { error } = await db
    .from("group_members")
    .insert({ group_id: g.id, user_id: u.user.id, role: "member" });
  if (error && error.code !== "23505") {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true });
}
