import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(_req: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) return NextResponse.json({ error: "auth required" }, { status: 401 });

  const { data: g } = await db.from("groups").select("id, owner_id").eq("slug", slug).maybeSingle();
  if (!g) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (g.owner_id === u.user.id)
    return NextResponse.json({ error: "owner cannot leave; transfer or delete" }, { status: 400 });

  const { error } = await db.from("group_members").delete().eq("group_id", g.id).eq("user_id", u.user.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
