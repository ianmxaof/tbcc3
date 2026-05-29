import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { supabasePublicEnvMissingMessage, normalizeSupabaseUrl } from "./env";

/**
 * Service-role Supabase client for workers + privileged server routes.
 * Bypasses RLS - never expose to the browser.
 */
let cached: SupabaseClient | null = null;

export function createAdminClient(): SupabaseClient {
  if (cached) return cached;
  const rawUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!rawUrl) {
    throw new Error(supabasePublicEnvMissingMessage());
  }
  const url = normalizeSupabaseUrl(rawUrl);
  if (!key) {
    throw new Error(
      "SUPABASE_SERVICE_ROLE_KEY is not set (server-only; never expose to the browser). " +
        "Add it to aof-forum/.env.local from Supabase → Project Settings → API → service_role. " +
        "Restart npm run dev after saving."
    );
  }
  cached = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
    db: { schema: "public" },
  });
  return cached;
}
