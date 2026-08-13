import { publicMediaUrl, signedGetUrl } from "./b2";

/**
 * Build a delivery URL for a media row.
 *
 * - If NEXT_PUBLIC_MEDIA_BASE_URL is set (CDN/public bucket), uses the public
 *   path-style URL. Cheap; reusable across clients.
 * - Otherwise, mints a signed B2 URL valid for ~1 hour. Falls back to the
 *   direct (non-working) URL if signing fails so the UI still has something
 *   to display.
 *
 * Safe to call from Route Handlers / RSC. Do not import from client components.
 */
export async function resolveMediaUrl(b2Key: string): Promise<string> {
  // Demo seed stores direct HTTPS URLs in b2_key when B2 is not configured locally.
  if (b2Key.startsWith("http://") || b2Key.startsWith("https://")) {
    return b2Key;
  }
  if (process.env.NEXT_PUBLIC_MEDIA_BASE_URL) {
    return publicMediaUrl(b2Key);
  }
  try {
    return await signedGetUrl(b2Key, 60 * 60);
  } catch {
    return publicMediaUrl(b2Key);
  }
}

export async function resolveManyMediaUrls<T extends { b2_key: string; b2_thumb_key?: string | null }>(
  rows: T[]
): Promise<(T & { url: string; thumb_url: string })[]> {
  const out: (T & { url: string; thumb_url: string })[] = [];
  for (const r of rows) {
    const url = await resolveMediaUrl(r.b2_key);
    const thumbUrl = r.b2_thumb_key ? await resolveMediaUrl(r.b2_thumb_key) : url;
    out.push({ ...r, url, thumb_url: thumbUrl });
  }
  return out;
}
