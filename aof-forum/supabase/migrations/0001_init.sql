-- =============================================================================
-- 0001_init: extensions, helper functions, profiles, tags, media_items, media_tags
-- =============================================================================

create extension if not exists pg_trgm;
create extension if not exists pgcrypto;

-- ---------- helper functions ----------
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, handle, display_name)
  values (
    new.id,
    coalesce(
      nullif(new.raw_user_meta_data->>'handle', ''),
      'user_' || substring(new.id::text from 1 for 8)
    ),
    coalesce(new.raw_user_meta_data->>'display_name', new.email)
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

-- ---------- enums ----------
do $$ begin
  create type public.media_kind as enum ('image', 'video', 'gif');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.source_kind as enum ('upload', 'telegram', 'web_pull', 'stash_import', 'local_inbox');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.tag_kind as enum ('tag', 'performer', 'studio', 'category');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.media_tag_source as enum ('manual', 'stash', 'auto');
exception when duplicate_object then null; end $$;

-- ---------- profiles ----------
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  handle text unique not null,
  display_name text,
  avatar_url text,
  bio text,
  is_admin boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists profiles_handle_lower_idx on public.profiles (lower(handle));
create index if not exists profiles_handle_trgm_idx on public.profiles using gin (handle gin_trgm_ops);

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------- tags / performers / studios / categories ----------
-- Single table with `kind` discriminator, modeled after Stash entities.
create table if not exists public.tags (
  id bigserial primary key,
  slug text unique not null,
  name text not null,
  kind public.tag_kind not null default 'tag',
  parent_id bigint references public.tags(id) on delete set null,
  description text,
  cover_url text,
  aliases text[] not null default '{}',
  uses_count int not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists tags_slug_trgm_idx on public.tags using gin (slug gin_trgm_ops);
create index if not exists tags_name_trgm_idx on public.tags using gin (name gin_trgm_ops);
create index if not exists tags_kind_idx on public.tags (kind);
create index if not exists tags_parent_idx on public.tags (parent_id);
create index if not exists tags_uses_idx on public.tags (uses_count desc);

-- ---------- media items (canonical record per uploaded blob in B2) ----------
create table if not exists public.media_items (
  id bigserial primary key,
  kind public.media_kind not null,
  title text,
  description text,
  b2_key text unique not null,
  b2_thumb_key text,
  mime text not null,
  byte_size bigint,
  width int,
  height int,
  duration_seconds real,
  phash bytea,
  dhash bytea,
  source_url text,
  source_kind public.source_kind not null default 'upload',
  uploader_id uuid references public.profiles(id) on delete set null,
  stash_scene_id text,
  views_count bigint not null default 0,
  votes_up int not null default 0,
  votes_down int not null default 0,
  comment_count int not null default 0,
  score double precision not null default 0,
  is_public boolean not null default true,
  is_nsfw boolean not null default true,
  is_deleted boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists media_created_idx on public.media_items (created_at desc) where is_deleted = false;
create index if not exists media_score_idx on public.media_items (score desc) where is_deleted = false and is_public = true;
create index if not exists media_phash_idx on public.media_items (phash) where phash is not null;
create index if not exists media_uploader_idx on public.media_items (uploader_id, created_at desc);
create index if not exists media_stash_idx on public.media_items (stash_scene_id) where stash_scene_id is not null;
create index if not exists media_kind_idx on public.media_items (kind);

drop trigger if exists media_set_updated_at on public.media_items;
create trigger media_set_updated_at
  before update on public.media_items
  for each row execute function public.set_updated_at();

-- ---------- media <-> tag (weighted, with source attribution) ----------
create table if not exists public.media_tags (
  media_id bigint references public.media_items(id) on delete cascade,
  tag_id bigint references public.tags(id) on delete cascade,
  weight real not null default 1.0,
  source public.media_tag_source not null default 'manual',
  added_by uuid references public.profiles(id) on delete set null,
  added_at timestamptz not null default now(),
  primary key (media_id, tag_id)
);
create index if not exists media_tags_tag_idx on public.media_tags (tag_id);
create index if not exists media_tags_source_idx on public.media_tags (source);
