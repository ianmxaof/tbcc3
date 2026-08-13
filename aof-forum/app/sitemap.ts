import type { MetadataRoute } from "next";
import { createAdminClient } from "@/lib/supabase/admin";
import { liveEmbedsConfigured } from "@/lib/live-embeds";
import { vpapiConfigured } from "@/lib/awempire-vpapi";
import { getVpapiLabels } from "@/lib/vpapi-labels";

/**
 * Minimal indexability baseline (P1.5) — static routes + the highest-value
 * dynamic surfaces (tags, galleries, media), capped well under the 50k/sitemap
 * limit. Split into a sitemap index if any bucket grows past a few thousand
 * rows; not needed at current content volume.
 */

function siteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3001").replace(/\/$/, "");
}

const TAG_CAP = 1000;
const GALLERY_CAP = 500;
const MEDIA_CAP = 2000;
const GROUP_CAP = 300;

// Regenerate hourly instead of freezing at build time — otherwise new
// galleries/media/tags never enter the sitemap until a redeploy, which
// defeats the compounding-indexable-pages point of shipping this at all.
export const revalidate = 3600;
export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = siteUrl();
  try {
    return await buildSitemap(base);
  } catch (e) {
    console.error("sitemap build failed (build-time or missing Supabase):", e);
    return [{ url: `${base}/`, changeFrequency: "hourly", priority: 1 }];
  }
}

async function buildSitemap(base: string): Promise<MetadataRoute.Sitemap> {
  const db = createAdminClient();

  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${base}/`, changeFrequency: "hourly", priority: 1 },
    { url: `${base}/g`, changeFrequency: "hourly", priority: 0.8 },
    { url: `${base}/groups`, changeFrequency: "daily", priority: 0.6 },
    { url: `${base}/f`, changeFrequency: "daily", priority: 0.6 },
    ...(liveEmbedsConfigured()
      ? [{ url: `${base}/live`, changeFrequency: "hourly" as const, priority: 0.75 }]
      : []),
    // Fixture-mode label pages are thin content until AWEMPIRE_PSID/AWEMPIRE_ACCESS_KEY
    // are set — same reasoning as gating /live above, and the /live stub removal in P1.5.
    ...(vpapiConfigured()
      ? getVpapiLabels().map((l) => ({
          url: `${base}/tube/awempire/${l.slug}`,
          changeFrequency: "daily" as const,
          priority: 0.55,
        }))
      : []),
  ];

  const [{ data: tags }, { data: galleries }, { data: media }, { data: groups }] =
    await Promise.all([
      db
        .from("tags")
        .select("slug, uses_count")
        .gt("uses_count", 0)
        .order("uses_count", { ascending: false })
        .limit(TAG_CAP),
      db
        .from("galleries")
        .select("slug, updated_at")
        .eq("is_public", true)
        .order("score", { ascending: false })
        .limit(GALLERY_CAP),
      db
        .from("media_items")
        .select("id, created_at")
        .eq("is_public", true)
        .eq("is_deleted", false)
        .order("score", { ascending: false })
        .limit(MEDIA_CAP),
      db
        .from("groups")
        .select("slug, updated_at")
        .neq("visibility", "private")
        .order("score", { ascending: false })
        .limit(GROUP_CAP),
    ]);

  const tagRoutes: MetadataRoute.Sitemap = (tags ?? []).map((t) => ({
    url: `${base}/t/${encodeURIComponent(t.slug as string)}`,
    changeFrequency: "daily",
    priority: 0.7,
  }));

  const galleryRoutes: MetadataRoute.Sitemap = (galleries ?? []).map((g) => ({
    url: `${base}/g/${encodeURIComponent(g.slug as string)}`,
    lastModified: g.updated_at ? new Date(g.updated_at as string) : undefined,
    changeFrequency: "daily",
    priority: 0.6,
  }));

  const mediaRoutes: MetadataRoute.Sitemap = (media ?? []).map((m) => ({
    url: `${base}/m/${m.id}`,
    lastModified: m.created_at ? new Date(m.created_at as string) : undefined,
    changeFrequency: "weekly",
    priority: 0.5,
  }));

  const groupRoutes: MetadataRoute.Sitemap = (groups ?? []).map((g) => ({
    url: `${base}/groups/${encodeURIComponent(g.slug as string)}`,
    lastModified: g.updated_at ? new Date(g.updated_at as string) : undefined,
    changeFrequency: "daily",
    priority: 0.5,
  }));

  return [...staticRoutes, ...tagRoutes, ...galleryRoutes, ...mediaRoutes, ...groupRoutes];
}
