import { NextResponse, type NextRequest } from "next/server";
import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { createAdminClient } from "@/lib/supabase/admin";
import { requireSupabaseUrlAndAnonKey } from "@/lib/supabase/env";
import { verifyBridgeToken } from "@/lib/admin-bridge";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function redirectSignIn(req: NextRequest, message: string) {
  return NextResponse.redirect(
    new URL(`/auth/sign-in?error=${encodeURIComponent(message)}`, req.url)
  );
}

/**
 * TBCC dashboard → forum admin bridge.
 * Validates HMAC token, signs the configured admin user into a Supabase session, ensures is_admin.
 */
export async function GET(req: NextRequest) {
  const token = req.nextUrl.searchParams.get("t") || "";
  let next = "/admin";
  try {
    const payload = verifyBridgeToken(token, "forum_admin");
    next = payload.next || "/admin";
  } catch (e) {
    return redirectSignIn(req, e instanceof Error ? e.message : "bridge_invalid");
  }

  const email = (process.env.ADMIN_BRIDGE_EMAIL || process.env.ADMIN_EMAIL || "").trim();
  const userId = (process.env.ADMIN_BRIDGE_USER_ID || process.env.MOCK_SEED_USER_ID || "").trim();
  if (!email && !userId) {
    return redirectSignIn(
      req,
      "ADMIN_BRIDGE_EMAIL or ADMIN_BRIDGE_USER_ID required on forum for bridge login"
    );
  }

  const admin = createAdminClient();
  let targetEmail = email;
  if (!targetEmail && userId) {
    const { data: userData, error: userErr } = await admin.auth.admin.getUserById(userId);
    if (userErr || !userData.user?.email) {
      return redirectSignIn(req, userErr?.message || "admin_user_missing");
    }
    targetEmail = userData.user.email;
  }

  const { data: linkData, error: linkErr } = await admin.auth.admin.generateLink({
    type: "magiclink",
    email: targetEmail,
  });
  if (linkErr || !linkData?.properties?.hashed_token) {
    return redirectSignIn(req, linkErr?.message || "generate_link_failed");
  }

  // Ensure profile is admin
  const uid = linkData.user?.id || userId;
  if (uid) {
    await admin.from("profiles").update({ is_admin: true }).eq("id", uid);
  }

  const { url: supabaseUrl, anonKey } = requireSupabaseUrlAndAnonKey();
  const redirectTarget = new URL(next.startsWith("/") ? next : `/${next}`, req.url);
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

  const { error: otpErr } = await supabase.auth.verifyOtp({
    type: "magiclink",
    token_hash: linkData.properties.hashed_token,
  });
  if (otpErr) {
    return redirectSignIn(req, otpErr.message);
  }

  return response;
}
