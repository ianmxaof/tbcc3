import { createBrowserClient } from "@supabase/ssr";
import { requireSupabaseUrlAndAnonKey } from "./env";

export function createClient() {
  const { url, anonKey } = requireSupabaseUrlAndAnonKey();
  return createBrowserClient(url, anonKey);
}
