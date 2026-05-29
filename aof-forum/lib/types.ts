/**
 * Shared types matching the Supabase schema. Keep in sync with
 * aof-forum/supabase/migrations/*.sql.
 */

export type MediaKind = "image" | "video" | "gif";
export type SourceKind = "upload" | "telegram" | "web_pull" | "stash_import" | "local_inbox";
export type TagKind = "tag" | "performer" | "studio" | "category";
export type MediaTagSource = "manual" | "stash" | "auto";
export type VoteTarget = "thread" | "post" | "media" | "group" | "gallery";
export type FollowTarget = "user" | "tag" | "gallery" | "group";
export type ViewContext =
  | "feed"
  | "media"
  | "gallery"
  | "group"
  | "tag"
  | "profile"
  | "thread"
  | "foryou"
  | "related";
export type GroupVisibility = "public" | "unlisted" | "private";
export type GroupRole = "owner" | "mod" | "member";
export type IngestStatus =
  | "queued"
  | "fetching"
  | "uploading"
  | "done"
  | "failed"
  | "skipped_duplicate";

export interface Profile {
  id: string;
  handle: string;
  display_name: string | null;
  avatar_url: string | null;
  bio: string | null;
  is_admin: boolean;
  created_at: string;
}

export interface Tag {
  id: number;
  slug: string;
  name: string;
  kind: TagKind;
  parent_id: number | null;
  description: string | null;
  cover_url: string | null;
  uses_count: number;
}

export interface MediaItem {
  id: number;
  kind: MediaKind;
  title: string | null;
  description: string | null;
  b2_key: string;
  b2_thumb_key: string | null;
  mime: string;
  byte_size: number | null;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  source_url: string | null;
  source_kind: SourceKind;
  uploader_id: string | null;
  stash_scene_id: string | null;
  views_count: number;
  votes_up: number;
  votes_down: number;
  comment_count: number;
  score: number;
  is_public: boolean;
  is_nsfw: boolean;
  created_at: string;
}

export interface MediaItemWithTags extends MediaItem {
  tags: Pick<Tag, "id" | "slug" | "name" | "kind">[];
  uploader?: Pick<Profile, "id" | "handle" | "display_name" | "avatar_url"> | null;
}

export interface Gallery {
  id: number;
  slug: string;
  owner_id: string;
  title: string;
  description: string | null;
  cover_media_id: number | null;
  is_public: boolean;
  item_count: number;
  views_count: number;
  votes_up: number;
  votes_down: number;
  score: number;
  created_at: string;
}

export interface Group {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  rules: string | null;
  avatar_media_id: number | null;
  banner_media_id: number | null;
  owner_id: string;
  visibility: GroupVisibility;
  is_nsfw: boolean;
  member_count: number;
  item_count: number;
  thread_count: number;
  views_count: number;
  score: number;
  created_at: string;
}

export interface ForumCategory {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  position: number;
  thread_count: number;
}

export interface ForumThread {
  id: number;
  category_id: number;
  group_id: number | null;
  author_id: string;
  title: string;
  slug: string;
  is_pinned: boolean;
  is_locked: boolean;
  reply_count: number;
  views_count: number;
  votes_up: number;
  votes_down: number;
  score: number;
  last_reply_at: string;
  created_at: string;
}

export interface ForumPost {
  id: number;
  thread_id: number;
  author_id: string;
  parent_post_id: number | null;
  body_md: string;
  votes_up: number;
  votes_down: number;
  score: number;
  is_deleted: boolean;
  edited_at: string | null;
  created_at: string;
}

export interface CursorPage<T> {
  items: T[];
  nextCursor: string | null;
}
