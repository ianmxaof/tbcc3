/** Called when public Supabase env is missing (browser + server clients). */
export function supabasePublicEnvMissingMessage(): string {
  return [
    "Supabase URL and anon key are not set.",
    "In the aof-forum folder, copy .env.example to .env.local, then set:",
    "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY (Supabase → Project Settings → API).",
    "Restart npm run dev after saving.",
  ].join(" ");
}

/** Normalize project URL (trailing slashes break some request paths). */
export function normalizeSupabaseUrl(raw: string): string {
  return raw.replace(/\/+$/, "");
}

export function requireSupabaseUrlAndAnonKey(): { url: string; anonKey: string } {
  const rawUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  if (!rawUrl || !anonKey) {
    throw new Error(supabasePublicEnvMissingMessage());
  }
  const url = normalizeSupabaseUrl(rawUrl);
  return { url, anonKey };
}
