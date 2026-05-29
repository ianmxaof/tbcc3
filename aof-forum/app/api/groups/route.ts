import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const Create = z.object({
  slug: z.string().min(2).max(64).regex(/^[a-z0-9][a-z0-9-]*[a-z0-9]$/),
  name: z.string().min(2).max(80),
  description: z.string().max(2000).optional(),
  rules: z.string().max(4000).optional(),
  visibility: z.enum(["public", "unlisted", "private"]).default("public"),
  is_nsfw: z.boolean().default(true),
});

/**
 * GET /api/groups?sort=hot|new&cursor=...&limit=24
 * POST /api/groups   -- create a new group (owner = auth.uid())
 */
export async function GET(req: NextRequest) {
  const db = await createClient();
  const sort = req.nextUrl.searchParams.get("sort") === "new" ? "new" : "hot";
  const limit = Math.min(parseInt(req.nextUrl.searchParams.get("limit") ?? "24", 10) || 24, 60);
  const cursor = req.nextUrl.searchParams.get("cursor");

  let q = db
    .from("groups")
    .select("id, slug, name, description, avatar_media_id, member_count, item_count, thread_count, score, created_at")
    .neq("visibility", "private");
  if (sort === "new") {
    q = q.order("created_at", { ascending: false });
    if (cursor) q = q.lt("created_at", cursor);
  } else {
    q = q.order("score", { ascending: false }).order("id", { ascending: false });
    if (cursor) {
      const [s, i] = cursor.split(":");
      const score = Number.parseFloat(s);
      q = q.or(`score.lt.${score},and(score.eq.${score},id.lt.${i ?? 0})`);
    }
  }
  const { data, error } = await q.limit(limit);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  const items = data ?? [];
  let nextCursor: string | null = null;
  if (items.length === limit) {
    const last = items[items.length - 1] as { score: number; id: number; created_at: string };
    nextCursor = sort === "new" ? last.created_at : `${last.score}:${last.id}`;
  }
  return NextResponse.json({ items, nextCursor });
}

export async function POST(req: NextRequest) {
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) return NextResponse.json({ error: "auth required" }, { status: 401 });

  let parsed;
  try {
    parsed = Create.parse(await req.json());
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 400 });
  }

  const { data, error } = await db
    .from("groups")
    .insert({
      slug: parsed.slug,
      name: parsed.name,
      description: parsed.description ?? null,
      rules: parsed.rules ?? null,
      owner_id: u.user.id,
      visibility: parsed.visibility,
      is_nsfw: parsed.is_nsfw,
    })
    .select("*")
    .single();
  if (error) {
    if (error.code === "23505")
      return NextResponse.json({ error: "slug already in use" }, { status: 409 });
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ group: data }, { status: 201 });
}
