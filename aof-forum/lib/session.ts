import { cookies } from "next/headers";
import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

/**
 * Signed anonymous session id used to bucket view_events for the doom-scroll
 * recommender BEFORE a user signs in. After sign-in we still keep the same
 * session id, so a user's pre-auth scrolling continues to feed their tag affinity.
 *
 * Format: <hex32>.<hmac-sha256-truncated-hex16>
 * Storage: httpOnly cookie `aof_sid`, SameSite=Lax, 180-day rolling.
 */

const COOKIE_NAME = "aof_sid";
const SESSION_TTL_S = 60 * 60 * 24 * 180;

function getSecret(): string {
  const s = process.env.SESSION_SIGNING_SECRET;
  if (!s || s.length < 16) {
    // Fall back to a stable-per-process random; dev only.
    if (!globalThis.__AOF_SID_FALLBACK__) {
      globalThis.__AOF_SID_FALLBACK__ = randomBytes(32).toString("hex");
    }
    return globalThis.__AOF_SID_FALLBACK__ as string;
  }
  return s;
}

declare global {
  // eslint-disable-next-line no-var
  var __AOF_SID_FALLBACK__: string | undefined;
}

function sign(sid: string): string {
  return createHmac("sha256", getSecret()).update(sid).digest("hex").slice(0, 16);
}

function verify(value: string): string | null {
  const [sid, sig] = value.split(".");
  if (!sid || !sig || sid.length !== 32) return null;
  const expected = Buffer.from(sign(sid), "hex");
  const got = Buffer.from(sig, "hex");
  if (expected.length !== got.length) return null;
  if (!timingSafeEqual(expected, got)) return null;
  return sid;
}

/**
 * Read the current signed session id from the cookie, or mint a new one and
 * set the cookie. Use only in Route Handlers / Server Actions / RSC.
 */
export async function getOrCreateSessionId(): Promise<string> {
  const store = await cookies();
  const existing = store.get(COOKIE_NAME)?.value;
  if (existing) {
    const sid = verify(existing);
    if (sid) return sid;
  }
  const sid = randomBytes(16).toString("hex");
  const value = `${sid}.${sign(sid)}`;
  try {
    store.set(COOKIE_NAME, value, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: SESSION_TTL_S,
    });
  } catch {
    /* Server Component context - set is a no-op, middleware refresh covers it. */
  }
  return sid;
}

export async function readSessionId(): Promise<string | null> {
  const store = await cookies();
  const v = store.get(COOKIE_NAME)?.value;
  return v ? verify(v) : null;
}
