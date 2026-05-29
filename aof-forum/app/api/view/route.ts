import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { getOrCreateSessionId } from "@/lib/session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const Body = z.object({
  media_id: z.number().int().positive(),
  context: z
    .enum(["feed", "media", "gallery", "group", "tag", "profile", "thread", "foryou", "related"])
    .nullable()
    .optional(),
  source_id: z.number().int().nullable().optional(),
  dwell_ms: z.number().int().nonnegative().nullable().optional(),
});

/**
 * POST /api/view  -- the doom-scroll heartbeat.
 *
 * Called by the feed/media UI when a card has been on-screen >= ~1s. We use
 * the admin (service-role) client so anonymous sessions can write to
 * view_events even though they have no auth.uid().
 */
export async function POST(req: NextRequest) {
  let parsed;
  try {
    parsed = Body.parse(await req.json());
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 400 });
  }

  const userClient = await createClient();
  const { data: u } = await userClient.auth.getUser();
  const sessionId = await getOrCreateSessionId();

  const admin = createAdminClient();
  const { error } = await admin.from("view_events").insert({
    media_id: parsed.media_id,
    user_id: u.user?.id ?? null,
    session_id: sessionId,
    context: parsed.context ?? null,
    source_id: parsed.source_id ?? null,
    dwell_ms: parsed.dwell_ms ?? null,
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
