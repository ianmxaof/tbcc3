import { createServerClient, type CookieOptions } from "@supabase/ssr";
import type { EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";
import { requireSupabaseUrlAndAnonKey } from "@/lib/supabase/env";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function redirectSignIn(req: NextRequest, message: string) {
  return NextResponse.redirect(
    new URL(`/auth/sign-in?error=${encodeURIComponent(message)}`, req.url)
  );
}

/**
 * Supabase magic-link callback. Supports PKCE (?code=) and email OTP (?token_hash=&type=).
 *
 * Cookies must be written onto the same NextResponse we return.
 */
export async function GET(req: NextRequest) {
  const url = req.nextUrl;
  const next = url.searchParams.get("next") ?? "/";
  const oauthError = url.searchParams.get("error_description") ?? url.searchParams.get("error");
  if (oauthError) {
    return redirectSignIn(req, oauthError);
  }

  const code = url.searchParams.get("code");
  const tokenHash = url.searchParams.get("token_hash");
  const type = url.searchParams.get("type");

  if (!code && !(tokenHash && type)) {
    return redirectSignIn(
      req,
      "missing_code — magic link did not include auth params. Check Supabase redirect URL allowlist matches your browser host (localhost vs 127.0.0.1)."
    );
  }

  const { url: supabaseUrl, anonKey } = requireSupabaseUrlAndAnonKey();
  const redirectTarget = new URL(next, req.url);
  let response = NextResponse.redirect(redirectTarget);

  const supabase = createServerClient(supabaseUrl, anonKey, {
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

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) {
      return redirectSignIn(req, error.message);
    }
  } else if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type: type as EmailOtpType,
    });
    if (error) {
      return redirectSignIn(req, error.message);
    }
  }

  return response;
}
