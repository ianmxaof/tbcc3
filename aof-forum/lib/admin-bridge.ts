/**
 * Shared HMAC admin-bridge tokens (must match TBCC `app.services.admin_bridge`).
 * Secret: TBCC_ADMIN_BRIDGE_SECRET or TBCC_INTERNAL_API_KEY.
 */

import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export type BridgeAudience = "forum_admin" | "dashboard";

function b64urlEncode(buf: Buffer | string): string {
  const b = Buffer.isBuffer(buf) ? buf : Buffer.from(buf, "utf8");
  return b.toString("base64url");
}

function b64urlDecode(text: string): Buffer {
  return Buffer.from(text, "base64url");
}

function bridgeSecret(): string {
  const secret =
    process.env.TBCC_ADMIN_BRIDGE_SECRET?.trim() ||
    process.env.TBCC_INTERNAL_API_KEY?.trim() ||
    "";
  if (!secret) {
    throw new Error("TBCC_ADMIN_BRIDGE_SECRET (or TBCC_INTERNAL_API_KEY) not set");
  }
  return secret;
}

export function mintBridgeToken(opts: {
  audience: BridgeAudience;
  nextPath?: string;
  ttlSeconds?: number;
}): string {
  const ttl = Math.max(30, Math.min(opts.ttlSeconds ?? 120, 600));
  let next = (opts.nextPath || "/").trim() || "/";
  if (!next.startsWith("/")) next = `/${next}`;
  const payload = {
    aud: opts.audience,
    exp: Math.floor(Date.now() / 1000) + ttl,
    next,
    nonce: cryptoRandomHex(16),
    v: 1,
  };
  const body = b64urlEncode(JSON.stringify(payload));
  const sig = createHmac("sha256", bridgeSecret()).update(body, "ascii").digest("hex");
  return `${body}.${sig}`;
}

export function verifyBridgeToken(
  token: string,
  expectedAudience: BridgeAudience
): { aud: string; exp: number; next: string } {
  const raw = (token || "").trim();
  const i = raw.lastIndexOf(".");
  if (i <= 0) throw new Error("malformed_token");
  const body = raw.slice(0, i);
  const sig = raw.slice(i + 1).toLowerCase();
  if (!body || sig.length !== 64) throw new Error("malformed_token");
  const expect = createHmac("sha256", bridgeSecret()).update(body, "ascii").digest("hex");
  const a = Buffer.from(expect, "utf8");
  const b = Buffer.from(sig, "utf8");
  if (a.length !== b.length || !timingSafeEqual(a, b)) throw new Error("bad_signature");
  const payload = JSON.parse(b64urlDecode(body).toString("utf8")) as Record<string, unknown>;
  if (payload.aud !== expectedAudience) throw new Error("wrong_audience");
  const exp = Number(payload.exp || 0);
  if (!Number.isFinite(exp) || exp < Math.floor(Date.now() / 1000)) throw new Error("expired");
  let next = String(payload.next || "/");
  if (!next.startsWith("/")) next = "/";
  return { aud: String(payload.aud), exp, next };
}

function cryptoRandomHex(bytes: number): string {
  return randomBytes(bytes).toString("hex");
}

export function dashboardPublicUrl(): string {
  return (
    process.env.TBCC_DASHBOARD_PUBLIC_URL?.trim().replace(/\/$/, "") ||
    "https://dash.powercore.app"
  );
}

export function buildDashboardBridgeUrl(nextPath = "/"): string {
  const token = mintBridgeToken({ audience: "dashboard", nextPath });
  const qNext = encodeURIComponent(nextPath.startsWith("/") ? nextPath : `/${nextPath}`);
  return `${dashboardPublicUrl()}/?bridge=${token}&next=${qNext}`;
}
