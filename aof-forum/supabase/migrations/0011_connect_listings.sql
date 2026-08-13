-- =============================================================================
-- 0011_connect: UGC contact listings (SextingFinder-style Connect directory)
-- P-A slice: listings + tags + RLS. Shop/orders deferred to P-C.
-- =============================================================================

do $$ begin
  create type public.connect_platform as enum ('snapchat', 'telegram', 'instagram', 'other');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.connect_gender as enum ('female', 'male', 'trans', 'couple', 'other');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.connect_orientation as enum ('straight', 'gay', 'lesbian', 'bi', 'other');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.connect_status as enum ('pending', 'approved', 'rejected', 'removed');
exception when duplicate_object then null; end $$;

create table if not exists public.connect_listings (
  id bigserial primary key,
  owner_id uuid not null references public.profiles(id) on delete cascade,
  platform public.connect_platform not null,
  handle text not null,
  display_name text,
  age int not null check (age >= 18),
  age_attested boolean not null default false,
  gender public.connect_gender,
  orientation public.connect_orientation,
  country text,
  bio text,
  bulletin text,
  bulletin_updated_at timestamptz,
  avatar_media_id bigint references public.media_items(id) on delete set null,
  status public.connect_status not null default 'pending',
  is_public boolean not null default false,
  is_vip boolean not null default false,
  vip_until timestamptz,
  fire_pin_until timestamptz,
  stealth_pin_until timestamptz,
  auto_bump_until timestamptz,
  last_active_at timestamptz not null default now(),
  views_count bigint not null default 0,
  click_count bigint not null default 0,
  score double precision not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists connect_listings_score_idx on public.connect_listings (score desc)
  where status = 'approved' and is_public = true;
create index if not exists connect_listings_platform_idx on public.connect_listings (platform, status);
create index if not exists connect_listings_country_idx on public.connect_listings (country)
  where status = 'approved';
create index if not exists connect_listings_owner_idx on public.connect_listings (owner_id, created_at desc);
create index if not exists connect_listings_handle_trgm_idx on public.connect_listings using gin (handle gin_trgm_ops);
create index if not exists connect_listings_pending_idx on public.connect_listings (created_at)
  where status = 'pending';
create unique index if not exists connect_listings_platform_handle_uq
  on public.connect_listings (platform, lower(handle))
  where status <> 'removed';

drop trigger if exists connect_listings_set_updated_at on public.connect_listings;
create trigger connect_listings_set_updated_at
  before update on public.connect_listings
  for each row execute function public.set_updated_at();

create table if not exists public.connect_listing_tags (
  listing_id bigint references public.connect_listings(id) on delete cascade,
  tag_id bigint references public.tags(id) on delete cascade,
  added_by uuid references public.profiles(id) on delete set null,
  added_at timestamptz not null default now(),
  primary key (listing_id, tag_id)
);
create index if not exists connect_listing_tags_tag_idx on public.connect_listing_tags (tag_id);

alter table public.connect_listings enable row level security;
alter table public.connect_listing_tags enable row level security;

drop policy if exists connect_listings_read_public on public.connect_listings;
drop policy if exists connect_listings_read_own on public.connect_listings;
drop policy if exists connect_listings_insert_self on public.connect_listings;
drop policy if exists connect_listings_update_own on public.connect_listings;

create policy connect_listings_read_public on public.connect_listings
  for select using (status = 'approved' and is_public = true);
create policy connect_listings_read_own on public.connect_listings
  for select using (owner_id = auth.uid());
create policy connect_listings_insert_self on public.connect_listings
  for insert with check (owner_id = auth.uid());
create policy connect_listings_update_own on public.connect_listings
  for update using (owner_id = auth.uid());

drop policy if exists connect_listing_tags_read on public.connect_listing_tags;
drop policy if exists connect_listing_tags_insert_auth on public.connect_listing_tags;
create policy connect_listing_tags_read on public.connect_listing_tags for select using (true);
create policy connect_listing_tags_insert_auth on public.connect_listing_tags
  for insert with check (auth.uid() is not null);

-- Extend flags for Connect listing reports (P-A).
alter table public.flags drop constraint if exists flags_target_kind_check;
alter table public.flags add constraint flags_target_kind_check
  check (target_kind in ('media', 'gallery', 'group', 'thread', 'post', 'connect_listing'));
