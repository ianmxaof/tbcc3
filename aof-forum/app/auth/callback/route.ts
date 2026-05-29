import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { requireSupabaseUrlAndAnonKey } from "@/lib/supabase/env";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Supabase magic-link callback. Exchanges the `code` query param for a session.
 *
 * Cookies must be written onto the same NextResponse we return. Using
 * `cookies()` from `next/headers` here often does not attach Set-Cookie to a
 * freshly created `NextResponse.redirect()`, so the session appears missing.
 */
export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get("code");
  const next = req.nextUrl.searchParams.get("next") ?? "/";
  if (!code) {
    return NextResponse.redirect(new URL("/auth/sign-in?error=missing_code", req.url));
  }

  const { url, anonKey } = requireSupabaseUrlAndAnonKey();
  const redirectTarget = new URL(next, req.url);
  let response = NextResponse.redirect(redirectTarget);

  const supabase = createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return req.cookies.getAll();
      },
      setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
        cookiesToSet.forEach(({ name, value, options }) => {
          response.cookies.set(name, value, options);
        });
      },
    },
  });

  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    return NextResponse.redirect(
      new URL(`/auth/sign-in?error=${encodeURIComponent(error.message)}`, req.url)
    );
  }
  return response;
}
