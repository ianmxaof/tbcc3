-- =============================================================================
-- 0006_reco: scoring functions + co-view materialized views for the
-- Motherless-style related/for-you recommender. Refreshed by a cron Route Handler.
-- =============================================================================

-- ---------- scoring function (Reddit-style hot score) ----------
-- Returns a sortable score combining vote balance with recency.
create or replace function public.hot_score(votes_up int, votes_down int, created_at timestamptz)
returns double precision language sql immutable as $$
  select
    sign(coalesce(votes_up, 0) - coalesce(votes_down, 0)) *
      ln(greatest(abs(coalesce(votes_up, 0) - coalesce(votes_down, 0)), 1))
    + extract(epoch from coalesce(created_at, now())) / 45000.0
$$;

-- ---------- media co-view: which items get viewed by the same session ----------
-- Built as a materialized view because the underlying scan is expensive.
-- Refresh after enough view_events accumulate; the recommender falls back to
-- tag-overlap until this is populated.
create materialized view if not exists public.media_coview as
select
  v1.media_id as a,
  v2.media_id as b,
  count(*)::int as c
from public.view_events v1
join public.view_events v2
  on v1.session_id = v2.session_id
  and v1.media_id <> v2.media_id
  and abs(extract(epoch from (v1.ts - v2.ts))) < 3600
group by v1.media_id, v2.media_id
having count(*) > 1
with no data;
create index if not exists media_coview_a_idx on public.media_coview (a, c desc);
create index if not exists media_coview_b_idx on public.media_coview (b, c desc);

-- ---------- group co-membership: which groups share members ----------
-- Used for "Related Groups" panels: similar Motherless behavior where joining
-- one group nudges you toward adjacent ones.
create materialized view if not exists public.group_coview as
select
  gm1.group_id as a,
  gm2.group_id as b,
  count(*)::int as c
from public.group_members gm1
join public.group_members gm2
  on gm1.user_id = gm2.user_id
  and gm1.group_id <> gm2.group_id
group by gm1.group_id, gm2.group_id
with no data;
create index if not exists group_coview_a_idx on public.group_coview (a, c desc);
create index if not exists group_coview_b_idx on public.group_coview (b, c desc);

-- ---------- tag co-occurrence: which tags appear on the same media ----------
-- Used for tag pages and to fan out from a known tag affinity.
create materialized view if not exists public.tag_coocc as
select
  mt1.tag_id as a,
  mt2.tag_id as b,
  count(*)::int as c
from public.media_tags mt1
join public.media_tags mt2
  on mt1.media_id = mt2.media_id
  and mt1.tag_id <> mt2.tag_id
group by mt1.tag_id, mt2.tag_id
having count(*) > 2
with no data;
create index if not exists tag_coocc_a_idx on public.tag_coocc (a, c desc);

-- ---------- helper: refresh all reco materialized views ----------
-- Call from a cron Route Handler (Vercel cron) or from npm run reco:refresh.
create or replace function public.refresh_reco_views()
returns void language plpgsql security definer as $$
begin
  refresh materialized view concurrently public.media_coview;
exception when others then
  refresh materialized view public.media_coview;
end;
$$;

-- Note: refresh ... concurrently requires a unique index on the matview.
-- If we ever want concurrent refresh on group_coview / tag_coocc, add a
-- unique (a, b) index. For now those refresh in a separate function:
create or replace function public.refresh_group_coview() returns void
language sql security definer as $$ refresh materialized view public.group_coview $$;
create or replace function public.refresh_tag_coocc() returns void
language sql security definer as $$ refresh materialized view public.tag_coocc $$;

-- ---------- helper: vote counters trigger (kept simple, no UPSERT churn) ----------
-- Triggered by votes insert/update/delete to keep votes_up/votes_down on the
-- target row in sync, so feed sort can use indexed columns instead of joining votes.
create or replace function public.votes_update_target_counters()
returns trigger language plpgsql as $$
declare
  delta_up int := 0;
  delta_down int := 0;
  the_kind public.vote_target;
  the_id bigint;
begin
  if tg_op = 'INSERT' then
    the_kind := new.target_kind; the_id := new.target_id;
    if new.value = 1 then delta_up := 1; else delta_down := 1; end if;
  elsif tg_op = 'DELETE' then
    the_kind := old.target_kind; the_id := old.target_id;
    if old.value = 1 then delta_up := -1; else delta_down := -1; end if;
  elsif tg_op = 'UPDATE' then
    the_kind := new.target_kind; the_id := new.target_id;
    if old.value = 1 then delta_up := delta_up - 1; else delta_down := delta_down - 1; end if;
    if new.value = 1 then delta_up := delta_up + 1; else delta_down := delta_down + 1; end if;
  end if;

  if the_kind = 'media' then
    update public.media_items set votes_up = votes_up + delta_up, votes_down = votes_down + delta_down where id = the_id;
  elsif the_kind = 'thread' then
    update public.forum_threads set votes_up = votes_up + delta_up, votes_down = votes_down + delta_down where id = the_id;
  elsif the_kind = 'post' then
    update public.forum_posts set votes_up = votes_up + delta_up, votes_down = votes_down + delta_down where id = the_id;
  elsif the_kind = 'gallery' then
    update public.galleries set votes_up = votes_up + delta_up, votes_down = votes_down + delta_down where id = the_id;
  end if;
  return null;
end;
$$;

drop trigger if exists votes_counters_trg on public.votes;
create trigger votes_counters_trg
  after insert or update or delete on public.votes
  for each row execute function public.votes_update_target_counters();
