import { NextResponse } from "next/server";

/** Cold-start friendly health check for Vercel + uptime monitors */
export async function GET() {
  const supabaseConfigured = Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  );
  return NextResponse.json({
    ok: true,
    service: "aof-forum",
    supabase_env_configured: supabaseConfigured,
  });
}
