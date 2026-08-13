import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { buildDashboardBridgeUrl } from "@/lib/admin-bridge";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Forum admin → TBCC dashboard bridge (mint short-lived URL). */
export async function POST() {
  const db = await createClient();
  const { data: auth } = await db.auth.getUser();
  if (!auth.user) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  const admin = createAdminClient();
  const { data: profile } = await admin
    .from("profiles")
    .select("is_admin")
    .eq("id", auth.user.id)
    .maybeSingle();

  if (!profile?.is_admin) {
    return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  }

  try {
    const url = buildDashboardBridgeUrl("/");
    return NextResponse.json({ ok: true, url });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 503 }
    );
  }
}
