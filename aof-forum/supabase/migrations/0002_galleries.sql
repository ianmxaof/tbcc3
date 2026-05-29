-- =============================================================================
-- 0002_galleries: user-curated media collections (Erome/Stash-style galleries)
-- =============================================================================

create table if not exists public.galleries (
  id bigserial primary key,
  slug text unique not null,
  owner_id uuid not null references public.profiles(id) on delete cascade,
  title text not null,
  description text,
  cover_media_id bigint references public.media_items(id) on delete set null,
  is_public boolean not null default true,
  item_count int not null default 0,
  views_count bigint not null default 0,
  votes_up int not null default 0,
  votes_down int not null default 0,
  score double precision not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists galleries_owner_idx on public.galleries (owner_id, created_at desc);
create index if not exists galleries_score_idx on public.galleries (score desc) where is_public = true;
create index if not exists galleries_recent_idx on public.galleries (created_at desc) where is_public = true;
create index if not exists galleries_slug_trgm_idx on public.galleries using gin (slug gin_trgm_ops);

drop trigger if exists galleries_set_updated_at on public.galleries;
create trigger galleries_set_updated_at
  before update on public.galleries
  for each row execute function public.set_updated_at();

create table if not exists public.gallery_items (
  gallery_id bigint references public.galleries(id) on delete cascade,
  media_id bigint references public.media_items(id) on delete cascade,
  position int not null default 0,
  added_at timestamptz not null default now(),
  primary key (gallery_id, media_id)
);
create index if not exists gallery_items_position_idx on public.gallery_items (gallery_id, position);
create index if not exists gallery_items_media_idx on public.gallery_items (media_id);

-- Keep item_count in sync.
create or replace function public.galleries_item_count_trigger()
returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    update public.galleries set item_count = item_count + 1 where id = new.gallery_id;
  elsif tg_op = 'DELETE' then
    update public.galleries set item_count = greatest(item_count - 1, 0) where id = old.gallery_id;
  end if;
  return null;
end;
$$;

drop trigger if exists gallery_items_count_trg on public.gallery_items;
create trigger gallery_items_count_trg
  after insert or delete on public.gallery_items
  for each row execute function public.galleries_item_count_trigger();
