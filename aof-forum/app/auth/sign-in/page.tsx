import Link from "next/link";
import { SignInForm } from "@/components/SignInForm";
import { devPasswordAuthEnabled } from "@/lib/auth-dev";

export const dynamic = "force-dynamic";

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ sent?: string; email?: string; error?: string }>;
}) {
  const sp = await searchParams;
  const authError = sp.error ? decodeURIComponent(sp.error) : null;
  const allowPassword = devPasswordAuthEnabled();

  return (
    <main style={{ maxWidth: 400, margin: "5rem auto", padding: "0 1rem" }}>
      <h1>Sign in</h1>
      {authError && (
        <div className="card" style={{ marginBottom: "1rem", borderColor: "var(--live-accent)" }}>
          <p style={{ margin: 0, color: "var(--live-accent)", fontSize: "0.9rem" }}>
            Sign-in failed: {authError}
          </p>
          <p className="muted" style={{ fontSize: "0.8rem", margin: "0.5rem 0 0" }}>
            In Supabase → Authentication → URL configuration, add redirect URLs for both{" "}
            <code>http://localhost:3001/auth/callback</code> and{" "}
            <code>http://127.0.0.1:3001/auth/callback</code> (match the host you use in the
            browser).
          </p>
        </div>
      )}
      {sp.sent === "1" && sp.email ? (
        <div className="card">
          <p>
            We sent a magic link to <strong>{sp.email}</strong>. Click it to finish signing in.
          </p>
        </div>
      ) : (
        <SignInForm defaultEmail={sp.email ?? ""} allowPassword={allowPassword} />
      )}
      <p style={{ marginTop: "1.5rem", textAlign: "center" }}>
        <Link href="/">← Back to feed</Link>
      </p>
    </main>
  );
}
