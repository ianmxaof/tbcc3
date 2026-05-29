import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * GET /api/groups/[slug]  -- group details + is_member for the caller.
 */
export async function GET(_req: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const db = await createClient();
  const { data: u } = await db.auth.getUser();

  const { data: group, error } = await db
    .from("groups")
    .select(
      "id, slug, name, description, rules, avatar_media_id, banner_media_id, owner_id, visibility, is_nsfw, member_count, item_count, thread_count, score, created_at"
    )
    .eq("slug", slug)
    .maybeSingle();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  if (!group) return NextResponse.json({ error: "not found" }, { status: 404 });

  let role: "owner" | "mod" | "member" | null = null;
  if (u.user) {
    const { data: gm } = await db
      .from("group_members")
      .select("role")
      .eq("group_id", group.id)
      .eq("user_id", u.user.id)
      .maybeSingle();
    role = (gm?.role as typeof role) ?? null;
  }
  return NextResponse.json({ group, role });
}
