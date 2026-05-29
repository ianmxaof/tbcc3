import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";
import { requireSupabaseUrlAndAnonKey } from "./env";

export async function createClient() {
  const cookieStore = await cookies();
  const { url, anonKey } = requireSupabaseUrlAndAnonKey();

  return createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          );
        } catch {
          /* Server Component — set may be no-op; middleware refresh handles session */
        }
      },
    },
  });
}
