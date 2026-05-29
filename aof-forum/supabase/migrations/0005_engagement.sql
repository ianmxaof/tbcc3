-- =============================================================================
-- 0005_engagement: the signals the doom-scroll recommender feeds on.
-- votes, view_events, follows, bookmarks, ingest_jobs.
-- =============================================================================

do $$ begin
  create type public.vote_target as enum ('thread', 'post', 'media', 'group', 'gallery');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.follow_target as enum ('user', 'tag', 'gallery', 'group');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.view_context as enum (
    'feed', 'media', 'gallery', 'group', 'tag', 'profile', 'thread', 'foryou', 'related'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.ingest_status as enum (
    'queued', 'fetching', 'uploading', 'done', 'failed', 'skipped_duplicate'
  );
exception when duplicate_object then null; end $$;

-- ---------- votes ----------
create table if not exists public.votes (
  user_id uuid not null references public.profiles(id) on delete cascade,
  target_kind public.vote_target not null,
  target_id bigint not null,
  value smallint not null check (value in (-1, 1)),
  created_at timestamptz not null default now(),
  primary key (user_id, target_kind, target_id)
);
create index if not exists votes_target_idx on public.votes (target_kind, target_id);
create index if not exists votes_recent_idx on public.votes (created_at desc);

-- ---------- bookmarks ----------
create table if not exists public.bookmarks (
  user_id uuid not null references public.profiles(id) on delete cascade,
  media_id bigint not null references public.media_items(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, media_id)
);
create index if not exists bookmarks_user_idx on public.bookmarks (user_id, created_at desc);
create index if not exists bookmarks_media_idx on public.bookmarks (media_id);

-- ---------- follows ----------
-- Two-column FK to accommodate user (uuid) vs tag/gallery/group (bigint) targets.
create table if not exists public.follows (
  follower_id uuid not null references public.profiles(id) on delete cascade,
  target_kind public.follow_target not null,
  target_user_id uuid references public.profiles(id) on delete cascade,
  target_object_id bigint,
  created_at timestamptz not null default now(),
  check (
    (target_kind = 'user'
       and target_user_id is not null
       and target_object_id is null)
    or
    (target_kind <> 'user'
       and target_user_id is null
       and target_object_id is not null)
  )
);
create unique index if not exists follows_user_target_idx
  on public.follows (follower_id, target_user_id)
  where target_user_id is not null;
create unique index if not exists follows_obj_target_idx
  on public.follows (follower_id, target_kind, target_object_id)
  where target_object_id is not null;
create index if not exists follows_target_user_idx
  on public.follows (target_user_id)
  where target_user_id is not null;
create index if not exists follows_target_obj_idx
  on public.follows (target_kind, target_object_id)
  where target_object_id is not null;

-- ---------- view_events (the doom-scroll signal source) ----------
create table if not exists public.view_events (
  id bigserial primary key,
  user_id uuid references public.profiles(id) on delete set null,
  session_id text not null,
  media_id bigint not null references public.media_items(id) on delete cascade,
  context public.view_context,
  source_id bigint,             -- e.g. group_id when context='group', tag_id when context='tag'
  dwell_ms int,
  ts timestamptz not null default now()
);
create index if not exists view_events_media_ts_idx on public.view_events (media_id, ts desc);
create index if not exists view_events_user_ts_idx on public.view_events (user_id, ts desc) where user_id is not null;
create index if not exists view_events_session_ts_idx on public.view_events (session_id, ts desc);
create index if not exists view_events_context_idx on public.view_events (context, source_id) where source_id is not null;

-- Bump media_items.views_count on every insert.
create or replace function public.view_events_bump_counter()
returns trigger language plpgsql as $$
begin
  update public.media_items
  set views_count = views_count + 1
  where id = new.media_id;
  return null;
end;
$$;

drop trigger if exists view_events_counter_trg on public.view_events;
create trigger view_events_counter_trg
  after insert on public.view_events
  for each row execute function public.view_events_bump_counter();

-- ---------- ingest_jobs ----------
create table if not exists public.ingest_jobs (
  id bigserial primary key,
  requester_id uuid references public.profiles(id) on delete set null,
  source_url text,
  source_kind public.source_kind not null,
  destination_group_id bigint references public.groups(id) on delete set null,
  destination_gallery_id bigint references public.galleries(id) on delete set null,
  payload jsonb not null default '{}'::jsonb,
  status public.ingest_status not null default 'queued',
  result_media_id bigint references public.media_items(id) on delete set null,
  error text,
  attempts int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists ingest_jobs_status_idx on public.ingest_jobs (status, created_at);
create index if not exists ingest_jobs_requester_idx on public.ingest_jobs (requester_id, created_at desc);

drop trigger if exists ingest_jobs_set_updated_at on public.ingest_jobs;
create trigger ingest_jobs_set_updated_at
  before update on public.ingest_jobs
  for each row execute function public.set_updated_at();
