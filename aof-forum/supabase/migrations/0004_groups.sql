-- =============================================================================
-- 0004_groups: Motherless-style first-class communities.
-- A "group" has members, mods, a media feed, and per-group threads.
-- =============================================================================

do $$ begin
  create type public.group_visibility as enum ('public', 'unlisted', 'private');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.group_role as enum ('owner', 'mod', 'member');
exception when duplicate_object then null; end $$;

create table if not exists public.groups (
  id bigserial primary key,
  slug text unique not null,
  name text not null,
  description text,
  rules text,
  avatar_media_id bigint references public.media_items(id) on delete set null,
  banner_media_id bigint references public.media_items(id) on delete set null,
  owner_id uuid not null references public.profiles(id) on delete restrict,
  visibility public.group_visibility not null default 'public',
  is_nsfw boolean not null default true,
  member_count int not null default 1,
  item_count int not null default 0,
  thread_count int not null default 0,
  views_count bigint not null default 0,
  score double precision not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists groups_score_idx on public.groups (score desc) where visibility != 'private';
create index if not exists groups_recent_idx on public.groups (created_at desc) where visibility != 'private';
create index if not exists groups_slug_trgm_idx on public.groups using gin (slug gin_trgm_ops);
create index if not exists groups_name_trgm_idx on public.groups using gin (name gin_trgm_ops);

drop trigger if exists groups_set_updated_at on public.groups;
create trigger groups_set_updated_at
  before update on public.groups
  for each row execute function public.set_updated_at();

create table if not exists public.group_members (
  group_id bigint references public.groups(id) on delete cascade,
  user_id uuid references public.profiles(id) on delete cascade,
  role public.group_role not null default 'member',
  joined_at timestamptz not null default now(),
  primary key (group_id, user_id)
);
create index if not exists group_members_user_idx on public.group_members (user_id);
create index if not exists group_members_role_idx on public.group_members (group_id, role);

create table if not exists public.group_media (
  group_id bigint references public.groups(id) on delete cascade,
  media_id bigint references public.media_items(id) on delete cascade,
  added_by uuid references public.profiles(id) on delete set null,
  is_pinned boolean not null default false,
  position int not null default 0,
  added_at timestamptz not null default now(),
  primary key (group_id, media_id)
);
create index if not exists group_media_recent_idx on public.group_media (group_id, added_at desc);
create index if not exists group_media_pinned_idx on public.group_media (group_id, is_pinned, position) where is_pinned = true;
create index if not exists group_media_media_idx on public.group_media (media_id);

-- Now that public.groups exists, link forum_threads.group_id (forward declared in 0003).
alter table public.forum_threads
  drop constraint if exists forum_threads_group_fk;
alter table public.forum_threads
  add constraint forum_threads_group_fk
  foreign key (group_id) references public.groups(id) on delete cascade;
create index if not exists forum_threads_group_idx
  on public.forum_threads (group_id, last_reply_at desc)
  where group_id is not null;

-- Keep member_count, item_count, thread_count in sync.
create or replace function public.group_members_counter()
returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    update public.groups set member_count = member_count + 1 where id = new.group_id;
  elsif tg_op = 'DELETE' then
    update public.groups set member_count = greatest(member_count - 1, 0) where id = old.group_id;
  end if;
  return null;
end;
$$;

drop trigger if exists group_members_counter_trg on public.group_members;
create trigger group_members_counter_trg
  after insert or delete on public.group_members
  for each row execute function public.group_members_counter();

create or replace function public.group_media_counter()
returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    update public.groups set item_count = item_count + 1 where id = new.group_id;
  elsif tg_op = 'DELETE' then
    update public.groups set item_count = greatest(item_count - 1, 0) where id = old.group_id;
  end if;
  return null;
end;
$$;

drop trigger if exists group_media_counter_trg on public.group_media;
create trigger group_media_counter_trg
  after insert or delete on public.group_media
  for each row execute function public.group_media_counter();

create or replace function public.group_threads_counter()
returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' and new.group_id is not null then
    update public.groups set thread_count = thread_count + 1 where id = new.group_id;
  elsif tg_op = 'DELETE' and old.group_id is not null then
    update public.groups set thread_count = greatest(thread_count - 1, 0) where id = old.group_id;
  elsif tg_op = 'UPDATE' and (new.group_id is distinct from old.group_id) then
    if old.group_id is not null then
      update public.groups set thread_count = greatest(thread_count - 1, 0) where id = old.group_id;
    end if;
    if new.group_id is not null then
      update public.groups set thread_count = thread_count + 1 where id = new.group_id;
    end if;
  end if;
  return null;
end;
$$;

drop trigger if exists group_threads_counter_trg on public.forum_threads;
create trigger group_threads_counter_trg
  after insert or update of group_id or delete on public.forum_threads
  for each row execute function public.group_threads_counter();

-- When a group is created, automatically add the owner as a member with role='owner'.
create or replace function public.groups_owner_join()
returns trigger language plpgsql as $$
begin
  insert into public.group_members (group_id, user_id, role)
  values (new.id, new.owner_id, 'owner')
  on conflict (group_id, user_id) do update set role = 'owner';
  return null;
end;
$$;

drop trigger if exists groups_owner_join_trg on public.groups;
create trigger groups_owner_join_trg
  after insert on public.groups
  for each row execute function public.groups_owner_join();
