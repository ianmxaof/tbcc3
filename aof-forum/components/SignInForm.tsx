"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { isEmailRateLimitError, rateLimitHelpText } from "@/lib/auth-dev";

type Mode = "magic" | "password";

export function SignInForm({
  defaultEmail = "",
  allowPassword = false,
}: {
  defaultEmail?: string;
  allowPassword?: boolean;
}) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>(allowPassword ? "password" : "magic");
  const [email, setEmail] = useState(defaultEmail);
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rateLimited, setRateLimited] = useState(false);

  async function onMagicSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) return;
    setPending(true);
    setError(null);
    setRateLimited(false);
    const db = createClient();
    const redirectTo = `${window.location.origin}/auth/callback`;
    const { error: authError } = await db.auth.signInWithOtp({
      email: trimmed,
      options: { emailRedirectTo: redirectTo },
    });
    setPending(false);
    if (authError) {
      setError(authError.message);
      if (isEmailRateLimitError(authError.message)) {
        setRateLimited(true);
        if (allowPassword) setMode("password");
      }
      return;
    }
    setSent(true);
  }

  async function onPasswordSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed || !password) return;
    setPending(true);
    setError(null);
    const db = createClient();
    const { error: authError } = await db.auth.signInWithPassword({
      email: trimmed,
      password,
    });
    setPending(false);
    if (authError) {
      const msg = authError.message;
      if (/invalid login credentials/i.test(msg)) {
        setError(
          `${msg} — run: npm run dev:bootstrap-user -- your@email.com YourPassword (creates/resets user in Supabase).`
        );
      } else {
        setError(msg);
      }
      return;
    }
    router.push("/");
    router.refresh();
  }

  if (sent) {
    return (
      <div className="card">
        <p>
          We sent a magic link to <strong>{email}</strong>. Click it to finish signing in.
        </p>
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          Open the link in <strong>this same browser</strong>. Check Supabase → Authentication →
          Logs if it doesn&apos;t arrive.
        </p>
        {allowPassword && (
          <button
            type="button"
            className="primary"
            style={{ marginTop: "1rem", width: "100%" }}
            onClick={() => {
              setSent(false);
              setMode("password");
            }}
          >
            Use password instead (dev)
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="card">
      {allowPassword && (
        <div className="tabs" style={{ marginBottom: "1rem" }}>
          <button
            type="button"
            className={mode === "magic" ? "active" : ""}
            onClick={() => setMode("magic")}
            style={{ background: "none", border: "none", cursor: "pointer", padding: "0.35rem 0.75rem" }}
          >
            Magic link
          </button>
          <button
            type="button"
            className={mode === "password" ? "active" : ""}
            onClick={() => setMode("password")}
            style={{ background: "none", border: "none", cursor: "pointer", padding: "0.35rem 0.75rem" }}
          >
            Password (dev)
          </button>
        </div>
      )}

      {mode === "password" && allowPassword ? (
        <form onSubmit={onPasswordSubmit}>
          <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
            Local dev only. Create the user in Supabase → Authentication → Users (email + password),
            with &quot;Auto confirm user&quot; checked.
          </p>
          {error && (
            <p style={{ color: "var(--live-accent)", fontSize: "0.9rem", margin: "0 0 0.75rem" }}>
              {error}
            </p>
          )}
          <input
            name="email"
            type="email"
            placeholder="you@example.com"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            name="password"
            type="password"
            placeholder="Password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ marginTop: "0.65rem" }}
          />
          <button
            type="submit"
            className="primary"
            style={{ marginTop: "1rem", width: "100%" }}
            disabled={pending}
          >
            {pending ? "Signing in…" : "Sign in with password"}
          </button>
        </form>
      ) : (
        <form onSubmit={onMagicSubmit}>
          <p className="muted" style={{ marginTop: 0 }}>
            Enter your email and we&apos;ll send a magic link. No passwords.
          </p>
          {error && (
            <div style={{ marginBottom: "0.75rem" }}>
              <p style={{ color: "var(--live-accent)", fontSize: "0.9rem", margin: 0 }}>{error}</p>
              {rateLimited && (
                <p className="muted" style={{ fontSize: "0.8rem", margin: "0.5rem 0 0" }}>
                  {rateLimitHelpText()}
                </p>
              )}
            </div>
          )}
          <input
            name="email"
            type="email"
            placeholder="you@example.com"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <button
            type="submit"
            className="primary"
            style={{ marginTop: "1rem", width: "100%" }}
            disabled={pending}
          >
            {pending ? "Sending…" : "Send magic link"}
          </button>
        </form>
      )}
    </div>
  );
}
