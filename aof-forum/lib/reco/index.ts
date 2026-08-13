import { createClient as createServerClient } from "../supabase/server";
import { createAdminClient } from "../supabase/admin";
import type { MediaKind } from "../types";

/**
 * Thin typed wrappers around the Postgres RPCs declared in
 * supabase/migrations/0008_reco_functions.sql.
 *
 * All functions are stable / read-only so we hit the anon-keyed server client
 * by default. The For You feed honors `auth.uid()` via the standard JWT
 * forwarded by createServerClient().
 */

export interface FeedRow {
  id: number;
  kind: MediaKind;
  title: string | null;
  b2_key: string;
  b2_thumb_key: string | null;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  views_count: number;
  votes_up?: number;
  votes_down?: number;
  score: number;
  created_at?: string;
  uploader_id?: string | null;
}

export interface GroupFeedRow extends FeedRow {
  added_at: string;
  is_pinned: boolean;
}

export interface RelatedGroupRow {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  member_count: number;
  item_count: number;
  score: number;
}

export interface RelatedTagRow {
  id: number;
  slug: string;
  name: string;
  kind: "tag" | "performer" | "studio" | "category";
  c: number;
}

async function client() {
  return await createServerClient();
}

// ---------- Public feed ----------

export async function feedHot(opts: { limit?: number; afterScore?: number; afterId?: number } = {}) {
  const db = await client();
  const { data, error } = await db.rpc("feed_hot", {
    p_limit: opts.limit ?? 24,
    p_after_score: opts.afterScore ?? null,
    p_after_id: opts.afterId ?? null,
  });
  if (error) {
    const detail = [error.message, error.code, error.details].filter(Boolean).join(" | ");
    throw new Error(`feed_hot: ${detail}`);
  }
  return (data ?? []) as FeedRow[];
}

export async function feedRecent(opts: { limit?: number; before?: string } = {}) {
  const db = await client();
  const { data, error } = await db.rpc("feed_recent", {
    p_limit: opts.limit ?? 24,
    p_before: opts.before ?? null,
  });
  if (error) {
    const detail = [error.message, error.code, error.details].filter(Boolean).join(" | ");
    throw new Error(`feed_recent: ${detail}`);
  }
  return (data ?? []) as FeedRow[];
}

// ---------- Related media ----------

export async function relatedMedia(opts: {
  mediaId: number;
  limit?: number;
  userId?: string | null;
  sessionId?: string | null;
}) {
  const db = await client();
  const { data, error } = await db.rpc("related_media", {
    p_media_id: opts.mediaId,
    p_limit: opts.limit ?? 24,
    p_user: opts.userId ?? null,
    p_session: opts.sessionId ?? null,
  });
  if (error) throw new Error(`related_media: ${error.message}`);
  return (data ?? []) as FeedRow[];
}

/** Tag-overlap related, candidates restricted to `group_media` for this group. */
export async function relatedMediaInGroup(opts: {
  mediaId: number;
  groupId: number;
  limit?: number;
  userId?: string | null;
  sessionId?: string | null;
}) {
  const db = await client();
  const { data, error } = await db.rpc("related_media_in_group", {
    p_media_id: opts.mediaId,
    p_group_id: opts.groupId,
    p_limit: opts.limit ?? 24,
    p_user: opts.userId ?? null,
    p_session: opts.sessionId ?? null,
  });
  if (error) throw new Error(`related_media_in_group: ${error.message}`);
  return (data ?? []) as FeedRow[];
}

export interface RelatedGalleryRow {
  id: number;
  slug: string;
  title: string;
  description: string | null;
  item_count: number;
  score: number;
  reason: string;
}

export async function relatedGalleries(galleryId: number, limit = 12) {
  const db = await client();
  const { data, error } = await db.rpc("related_galleries", {
    p_gallery_id: galleryId,
    p_limit: limit,
  });
  if (error) throw new Error(`related_galleries: ${error.message}`);
  return (data ?? []) as RelatedGalleryRow[];
}

// ---------- Tag pages ----------

export async function tagFeed(opts: { tagId: number; limit?: number; before?: string }) {
  const db = await client();
  const { data, error } = await db.rpc("tag_feed", {
    p_tag_id: opts.tagId,
    p_limit: opts.limit ?? 24,
    p_before: opts.before ?? null,
  });
  if (error) throw new Error(`tag_feed: ${error.message}`);
  return (data ?? []) as FeedRow[];
}

export async function relatedTags(tagId: number, limit = 20) {
  const db = await client();
  const { data, error } = await db.rpc("related_tags", { p_tag_id: tagId, p_limit: limit });
  if (error) throw new Error(`related_tags: ${error.message}`);
  return (data ?? []) as RelatedTagRow[];
}

// ---------- Groups ----------

export async function groupFeed(opts: { groupId: number; limit?: number; before?: string }) {
  const db = await client();
  const { data, error } = await db.rpc("group_feed", {
    p_group_id: opts.groupId,
    p_limit: opts.limit ?? 24,
    p_before: opts.before ?? null,
  });
  if (error) throw new Error(`group_feed: ${error.message}`);
  return (data ?? []) as GroupFeedRow[];
}

export async function relatedGroups(groupId: number, limit = 12) {
  const db = await client();
  const { data, error } = await db.rpc("related_groups", { p_group_id: groupId, p_limit: limit });
  if (error) {
    // group_coview MV may be empty / unpopulated in early local projects — soft-fail.
    const msg = error.message || "";
    if (/group_coview|has not been populated|materialized view/i.test(msg)) {
      console.warn(`[relatedGroups] soft-fail (coview): ${msg}`);
      return [] as RelatedGroupRow[];
    }
    throw new Error(`related_groups: ${msg}`);
  }
  return (data ?? []) as RelatedGroupRow[];
}

// ---------- For You feed (epsilon-greedy applied on top of RPC) ----------

const EXPLORE_RATE = 0.1;

export async function foryouFeed(opts: {
  userId?: string | null;
  sessionId: string;
  limit?: number;
  offset?: number;
}) {
  const db = await client();
  const limit = opts.limit ?? 24;
  const want = Math.ceil(limit / (1 - EXPLORE_RATE));
  const { data, error } = await db.rpc("foryou_feed", {
    p_user: opts.userId ?? null,
    p_session: opts.sessionId,
    p_limit: want,
    p_offset: opts.offset ?? 0,
  });
  if (error) throw new Error(`foryou_feed: ${error.message}`);
  const ranked = (data ?? []) as FeedRow[];

  // Sprinkle in EXPLORE_RATE random "trending" items so the feed never stagnates.
  if (ranked.length === 0) return ranked;
  const out: FeedRow[] = [];
  const explorePool = await feedHot({ limit: Math.max(limit, 24) });
  const exploreIds = new Set<number>();
  for (let i = 0; i < limit; i++) {
    if (Math.random() < EXPLORE_RATE && explorePool.length > 0) {
      // Pop one that isn't already in `out`.
      let candidate: FeedRow | undefined;
      for (let k = 0; k < explorePool.length; k++) {
        const c = explorePool[k];
        if (!exploreIds.has(c.id) && !out.find((r) => r.id === c.id)) {
          candidate = c;
          exploreIds.add(c.id);
          break;
        }
      }
      if (candidate) {
        out.push(candidate);
        continue;
      }
    }
    const r = ranked[i] ?? ranked[ranked.length - 1];
    if (r && !out.find((x) => x.id === r.id)) out.push(r);
  }
  return out.slice(0, limit);
}

// ---------- Admin: refresh matviews ----------

export async function refreshAllMatviews() {
  const db = createAdminClient();
  await db.rpc("refresh_reco_views");
  await db.rpc("refresh_group_coview");
  await db.rpc("refresh_tag_coocc");
}

/** Recompute `media_items.score` and `groups.score` (service role only). */
export async function refreshRowHotScores() {
  const db = createAdminClient();
  const { error } = await db.rpc("refresh_row_hot_scores");
  if (error) throw new Error(`refresh_row_hot_scores: ${error.message}`);
}

/** Full reco maintenance: row scores then matviews. */
export async function runFullRecoMaintenance() {
  await refreshRowHotScores();
  await refreshAllMatviews();
}
