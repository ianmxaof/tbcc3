import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const Body = z.object({
  source_url: z.string().url(),
  source_kind: z
    .enum(["upload", "telegram", "web_pull", "stash_import", "local_inbox"])
    .default("web_pull"),
  destination_group_id: z.number().int().positive().nullable().optional(),
  destination_gallery_id: z.number().int().positive().nullable().optional(),
});

/**
 * POST /api/ingest
 * Creates a queued `ingest_jobs` row. The local worker (npm run ingest:watch)
 * picks it up, downloads + dedupes + uploads to B2 + inserts media_items.
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

  const { data, error } = await db
    .from("ingest_jobs")
    .insert({
      requester_id: u.user.id,
      source_url: parsed.source_url,
      source_kind: parsed.source_kind,
      destination_group_id: parsed.destination_group_id ?? null,
      destination_gallery_id: parsed.destination_gallery_id ?? null,
      status: "queued",
    })
    .select("id, status, created_at")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ job: data }, { status: 201 });
}

/**
 * GET /api/ingest?status=queued&limit=20
 * Lists the caller's recent jobs.
 */
export async function GET(req: NextRequest) {
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) return NextResponse.json({ error: "auth required" }, { status: 401 });

  const status = req.nextUrl.searchParams.get("status");
  const limit = Math.min(parseInt(req.nextUrl.searchParams.get("limit") ?? "20", 10) || 20, 100);
  let q = db.from("ingest_jobs").select("*").eq("requester_id", u.user.id).order("created_at", { ascending: false }).limit(limit);
  if (status) q = q.eq("status", status);
  const { data, error } = await q;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ items: data ?? [] });
}
