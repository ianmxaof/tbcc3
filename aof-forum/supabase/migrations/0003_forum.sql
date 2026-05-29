-- =============================================================================
-- 0003_forum: site-wide forum (categories, threads, posts) + per-post media
-- group_id on threads is a forward declaration; FK to public.groups added in 0004.
-- =============================================================================

create table if not exists public.forum_categories (
  id bigserial primary key,
  slug text unique not null,
  name text not null,
  description text,
  position int not null default 0,
  thread_count int not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists public.forum_threads (
  id bigserial primary key,
  category_id bigint not null references public.forum_categories(id) on delete cascade,
  group_id bigint, -- FK added in 0004 (groups don't exist yet at this point)
  author_id uuid not null references public.profiles(id) on delete cascade,
  title text not null,
  slug text not null,
  is_pinned boolean not null default false,
  is_locked boolean not null default false,
  reply_count int not null default 0,
  views_count bigint not null default 0,
  votes_up int not null default 0,
  votes_down int not null default 0,
  score double precision not null default 0,
  last_reply_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create unique index if not exists forum_threads_slug_idx on public.forum_threads (category_id, slug);
create index if not exists forum_threads_recent_idx on public.forum_threads (category_id, last_reply_at desc);
create index if not exists forum_threads_score_idx on public.forum_threads (score desc);
create index if not exists forum_threads_author_idx on public.forum_threads (author_id, created_at desc);

create table if not exists public.forum_posts (
  id bigserial primary key,
  thread_id bigint not null references public.forum_threads(id) on delete cascade,
  author_id uuid not null references public.profiles(id) on delete cascade,
  parent_post_id bigint references public.forum_posts(id) on delete set null,
  body_md text not null,
  votes_up int not null default 0,
  votes_down int not null default 0,
  score double precision not null default 0,
  is_deleted boolean not null default false,
  edited_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists forum_posts_thread_idx on public.forum_posts (thread_id, created_at);
create index if not exists forum_posts_parent_idx on public.forum_posts (parent_post_id);
create index if not exists forum_posts_author_idx on public.forum_posts (author_id, created_at desc);

create table if not exists public.post_media (
  post_id bigint references public.forum_posts(id) on delete cascade,
  media_id bigint references public.media_items(id) on delete cascade,
  position int not null default 0,
  primary key (post_id, media_id)
);
create index if not exists post_media_media_idx on public.post_media (media_id);

-- Keep reply_count + last_reply_at on threads in sync.
create or replace function public.forum_posts_thread_counters()
returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    update public.forum_threads
    set reply_count = reply_count + 1,
        last_reply_at = greatest(last_reply_at, new.created_at)
    where id = new.thread_id;
  elsif tg_op = 'DELETE' then
    update public.forum_threads
    set reply_count = greatest(reply_count - 1, 0)
    where id = old.thread_id;
  end if;
  return null;
end;
$$;

drop trigger if exists forum_posts_counters_trg on public.forum_posts;
create trigger forum_posts_counters_trg
  after insert or delete on public.forum_posts
  for each row execute function public.forum_posts_thread_counters();

-- Keep thread_count on categories in sync.
create or replace function public.forum_threads_cat_counter()
returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    update public.forum_categories set thread_count = thread_count + 1 where id = new.category_id;
  elsif tg_op = 'DELETE' then
    update public.forum_categories set thread_count = greatest(thread_count - 1, 0) where id = old.category_id;
  end if;
  return null;
end;
$$;

drop trigger if exists forum_threads_cat_trg on public.forum_threads;
create trigger forum_threads_cat_trg
  after insert or delete on public.forum_threads
  for each row execute function public.forum_threads_cat_counter();
