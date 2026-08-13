import type { SupabaseClient } from "@supabase/supabase-js";
import { filterDemoFixtures } from "./demo-fixtures";
import { resolveMediaUrl } from "@/lib/media-url";
import type { ConnectListingCard, ConnectPlatform } from "./types";

export type ConnectFeedFilters = {
  platform?: ConnectPlatform;
  gender?: string;
  orientation?: string;
  country?: string;
  vip?: boolean;
  hasPhoto?: boolean;
  q?: string;
  sort?: "hot" | "new" | "active";
  limit?: number;
  offset?: number;
};

export async function fetchConnectListings(
  db: SupabaseClient,
  filters: ConnectFeedFilters = {}
): Promise<ConnectListingCard[]> {
  const limit = Math.min(filters.limit ?? 48, 100);
  const offset = filters.offset ?? 0;

  let q = db
    .from("connect_listings")
    .select(
      "id, owner_id, platform, handle, display_name, age, gender, orientation, country, bio, bulletin, bulletin_updated_at, avatar_media_id, is_vip, vip_until, fire_pin_until, stealth_pin_until, last_active_at, views_count, click_count, score, created_at"
    )
    .eq("status", "approved")
    .eq("is_public", true);

  if (filters.platform) q = q.eq("platform", filters.platform);
  if (filters.gender) q = q.eq("gender", filters.gender);
  if (filters.orientation) q = q.eq("orientation", filters.orientation);
  if (filters.country) q = q.eq("country", filters.country);
  if (filters.vip) q = q.eq("is_vip", true);
  if (filters.hasPhoto) q = q.not("avatar_media_id", "is", null);
  if (filters.q?.trim()) q = q.ilike("handle", `%${filters.q.trim()}%`);

  if (filters.sort === "new") {
    q = q.order("created_at", { ascending: false });
  } else if (filters.sort === "active") {
    q = q.order("last_active_at", { ascending: false });
  } else {
    q = q.order("score", { ascending: false }).order("last_active_at", { ascending: false });
  }

  const { data, error } = await q.range(offset, offset + limit - 1);
  if (error) {
    if (error.message.includes("connect_listings")) {
      return filterDemoFixtures({
        platform: filters.platform,
        gender: filters.gender,
        vip: filters.vip,
        hasPhoto: filters.hasPhoto,
      });
    }
    throw new Error(error.message);
  }
  const rows = data ?? [];
  if (rows.length === 0 && process.env.NODE_ENV === "development") {
    const fixtures = filterDemoFixtures({
      platform: filters.platform,
      gender: filters.gender,
      vip: filters.vip,
      hasPhoto: filters.hasPhoto,
    });
    if (fixtures.length) return fixtures;
  }

  const avatarIds = rows.map((r) => r.avatar_media_id).filter((x): x is number => x != null);
  const avatarUrlById = new Map<number, string>();
  if (avatarIds.length) {
    const { data: avatars } = await db.from("media_items").select("id, b2_key").in("id", avatarIds);
    for (const a of avatars ?? []) {
      avatarUrlById.set(a.id, await resolveMediaUrl(a.b2_key));
    }
  }

  const listingIds = rows.map((r) => r.id);
  const tagsByListing = new Map<number, string[]>();
  if (listingIds.length) {
    const { data: tagRows } = await db
      .from("connect_listing_tags")
      .select("listing_id, tags!inner(name)")
      .in("listing_id", listingIds);
    for (const tr of tagRows ?? []) {
      const tag = (tr as { listing_id: number; tags: { name: string } | { name: string }[] }).tags;
      const name = Array.isArray(tag) ? tag[0]?.name : tag?.name;
      if (!name) continue;
      const lid = (tr as { listing_id: number }).listing_id;
      const arr = tagsByListing.get(lid) ?? [];
      arr.push(name);
      tagsByListing.set(lid, arr);
    }
  }

  const now = Date.now();
  const sorted = [...rows].sort((a, b) => {
    const aFire = a.fire_pin_until && new Date(a.fire_pin_until).getTime() > now ? 1 : 0;
    const bFire = b.fire_pin_until && new Date(b.fire_pin_until).getTime() > now ? 1 : 0;
    if (aFire !== bFire) return bFire - aFire;
    const aVip = a.is_vip && (!a.vip_until || new Date(a.vip_until).getTime() > now) ? 1 : 0;
    const bVip = b.is_vip && (!b.vip_until || new Date(b.vip_until).getTime() > now) ? 1 : 0;
    if (aVip !== bVip) return bVip - aVip;
    if (filters.sort === "new") return 0;
    if (filters.sort === "active") return 0;
    return (b.score ?? 0) - (a.score ?? 0);
  });

  return sorted.map((r) => ({
    ...r,
    avatar_url: r.avatar_media_id ? avatarUrlById.get(r.avatar_media_id) ?? null : null,
    tags: tagsByListing.get(r.id) ?? [],
  }));
}

export function formatLastActive(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}
