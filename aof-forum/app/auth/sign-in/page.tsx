import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

async function sendMagicLink(formData: FormData) {
  "use server";
  const email = String(formData.get("email") ?? "").trim();
  if (!email) throw new Error("email required");
  const db = await createClient();
  const origin =
    process.env.NEXT_PUBLIC_SITE_URL ?? "http://127.0.0.1:3001";
  try {
    const { error } = await db.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${origin}/auth/callback` },
    });
    if (error) throw new Error(error.message);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (/fetch failed|Failed to fetch|ECONNREFUSED|ENOTFOUND|getaddrinfo|certificate/i.test(msg)) {
      throw new Error(
        "Cannot reach Supabase from this machine. Check aof-forum/.env.local: " +
          "NEXT_PUBLIC_SUPABASE_URL must be https://YOUR-PROJECT-REF.supabase.co (exact copy from Dashboard → Project Settings → API, no typo, no trailing slash). " +
          "NEXT_PUBLIC_SUPABASE_ANON_KEY must be the anon public key from the same page. " +
          "Restart npm run dev after saving .env.local. " +
          "If the URL/key are correct, confirm the project is not paused and your network allows HTTPS to *.supabase.co."
      );
    }
    throw e;
  }
  redirect(`/auth/sign-in?sent=1&email=${encodeURIComponent(email)}`);
}

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ sent?: string; email?: string; next?: string }>;
}) {
  const { sent, email } = await searchParams;
  return (
    <main style={{ maxWidth: 400, margin: "5rem auto", padding: "0 1rem" }}>
      <h1>Sign in</h1>
      {sent ? (
        <div className="card">
          <p>We sent a magic link to <strong>{email}</strong>. Click it to finish signing in.</p>
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            Check Supabase project &rarr; Authentication &rarr; Logs if you don&apos;t see it.
          </p>
        </div>
      ) : (
        <form action={sendMagicLink} className="card">
          <p className="muted" style={{ marginTop: 0 }}>Enter your email and we&apos;ll send a magic link. No passwords.</p>
          <input name="email" type="email" placeholder="you@example.com" required autoFocus />
          <button type="submit" className="primary" style={{ marginTop: "1rem", width: "100%" }}>
            Send magic link
          </button>
        </form>
      )}
      <p style={{ marginTop: "1.5rem", textAlign: "center" }}>
        <Link href="/">← Back to feed</Link>
      </p>
    </main>
  );
}
