-- =============================================================================
-- 0008_reco_functions: stored procedures the API route handlers call via
-- Supabase RPC. Keeps the heavy joins in Postgres where the planner has stats
-- and the matviews live, so the Node side just has thin typed wrappers.
-- =============================================================================

-- ---------- Public Feed (hot blend) ----------
-- Sort: 0.5 * hot_score + 0.5 * log(views_count + 1).
-- Cursor: (score, id) so deterministic next-page even with ties.
create or replace function public.feed_hot(
  p_limit int default 24,
  p_after_score double precision default null,
  p_after_id bigint default null
)
returns table (
  id bigint, kind public.media_kind, title text, b2_key text, b2_thumb_key text,
  width int, height int, duration_seconds real,
  views_count bigint, votes_up int, votes_down int, score double precision,
  created_at timestamptz, uploader_id uuid
)
language sql stable as $$
  select m.id, m.kind, m.title, m.b2_key, m.b2_thumb_key,
         m.width, m.height, m.duration_seconds,
         m.views_count, m.votes_up, m.votes_down,
         (0.5 * public.hot_score(m.votes_up, m.votes_down, m.created_at)
          + 0.5 * ln(greatest(m.views_count, 1))) as score,
         m.created_at, m.uploader_id
  from public.media_items m
  where m.is_public = true and m.is_deleted = false
    and (
      p_after_score is null
      or (
        (0.5 * public.hot_score(m.votes_up, m.votes_down, m.created_at)
         + 0.5 * ln(greatest(m.views_count, 1))) < p_after_score
        or (
          (0.5 * public.hot_score(m.votes_up, m.votes_down, m.created_at)
           + 0.5 * ln(greatest(m.views_count, 1))) = p_after_score
          and m.id < coalesce(p_after_id, 0)
        )
      )
    )
  order by score desc, m.id desc
  limit greatest(p_limit, 1);
$$;

-- ---------- Public Feed (recent) ----------
create or replace function public.feed_recent(
  p_limit int default 24,
  p_before timestamptz default null
)
returns setof public.media_items
language sql stable as $$
  select * from public.media_items
  where is_public = true and is_deleted = false
    and (p_before is null or created_at < p_before)
  order by created_at desc
  limit greatest(p_limit, 1);
$$;

-- ---------- Related Media (v1 tag overlap + v2 coview blend + novelty) ----------
-- For each candidate `b`, score = 0.6 * tag_overlap_score + 0.4 * coview_score.
-- Both normalized to roughly [0, 1] then re-weighted. Excludes items the user
-- (or anon session) has viewed in the last 24h.
create or replace function public.related_media(
  p_media_id bigint,
  p_limit int default 24,
  p_user uuid default null,
  p_session text default null
)
returns table (
  id bigint, kind public.media_kind, title text, b2_key text, b2_thumb_key text,
  width int, height int, duration_seconds real,
  views_count bigint, score double precision
)
language sql stable as $$
  with seed_tags as (
    select tag_id, weight from public.media_tags where media_id = p_media_id
  ),
  tag_candidates as (
    select mt.media_id as id, sum(mt.weight * st.weight) as raw_tag_score
    from seed_tags st
    join public.media_tags mt on mt.tag_id = st.tag_id and mt.media_id <> p_media_id
    group by mt.media_id
  ),
  coview_candidates as (
    select cv.b as id, cv.c as raw_coview_score
    from public.media_coview cv
    where cv.a = p_media_id
  ),
  merged as (
    select coalesce(t.id, cv.id) as id,
           coalesce(t.raw_tag_score, 0) as tag_score,
           coalesce(cv.raw_coview_score, 0) as coview_score
    from tag_candidates t
    full outer join coview_candidates cv on cv.id = t.id
  ),
  scored as (
    select
      m.id, m.kind, m.title, m.b2_key, m.b2_thumb_key, m.width, m.height,
      m.duration_seconds, m.views_count,
      (0.6 * (mg.tag_score / (1 + mg.tag_score))
       + 0.4 * (mg.coview_score / (1 + mg.coview_score))
       + 0.05 * ln(greatest(m.views_count, 1)) / 10.0
      ) as score
    from merged mg
    join public.media_items m on m.id = mg.id
    where m.is_public = true and m.is_deleted = false
      and not exists (
        select 1 from public.view_events ve
        where ve.media_id = m.id
          and ve.ts > now() - interval '24 hours'
          and (
            (p_user is not null and ve.user_id = p_user)
            or (p_user is null and p_session is not null and ve.session_id = p_session)
          )
      )
  )
  select id, kind, title, b2_key, b2_thumb_key, width, height,
         duration_seconds, views_count, score
  from scored
  order by score desc, id desc
  limit greatest(p_limit, 1);
$$;

-- ---------- Tag Feed ----------
create or replace function public.tag_feed(
  p_tag_id bigint,
  p_limit int default 24,
  p_before timestamptz default null
)
returns setof public.media_items
language sql stable as $$
  select m.* from public.media_items m
  join public.media_tags mt on mt.media_id = m.id and mt.tag_id = p_tag_id
  where m.is_public = true and m.is_deleted = false
    and (p_before is null or m.created_at < p_before)
  order by m.created_at desc
  limit greatest(p_limit, 1);
$$;

-- ---------- Tag Co-occurrence (for "Related tags" sidebar) ----------
create or replace function public.related_tags(
  p_tag_id bigint,
  p_limit int default 20
)
returns table (id bigint, slug text, name text, kind public.tag_kind, c int)
language sql stable as $$
  select t.id, t.slug, t.name, t.kind, tc.c
  from public.tag_coocc tc
  join public.tags t on t.id = tc.b
  where tc.a = p_tag_id
  order by tc.c desc
  limit greatest(p_limit, 1);
$$;

-- ---------- Group Feed (media in a group, recent first) ----------
create or replace function public.group_feed(
  p_group_id bigint,
  p_limit int default 24,
  p_before timestamptz default null
)
returns table (
  id bigint, kind public.media_kind, title text, b2_key text, b2_thumb_key text,
  width int, height int, duration_seconds real,
  views_count bigint, score double precision, added_at timestamptz,
  is_pinned boolean
)
language sql stable as $$
  select m.id, m.kind, m.title, m.b2_key, m.b2_thumb_key,
         m.width, m.height, m.duration_seconds,
         m.views_count, m.score, gm.added_at, gm.is_pinned
  from public.group_media gm
  join public.media_items m on m.id = gm.media_id
  where gm.group_id = p_group_id
    and m.is_public = true and m.is_deleted = false
    and (p_before is null or gm.added_at < p_before)
  order by gm.is_pinned desc, gm.added_at desc
  limit greatest(p_limit, 1);
$$;

-- ---------- Related Groups (Jaccard over shared members) ----------
-- score = |A ∩ B| / |A ∪ B|. We approximate the union via member_count to keep
-- the query cheap.
create or replace function public.related_groups(
  p_group_id bigint,
  p_limit int default 12
)
returns table (
  id bigint, slug text, name text, description text,
  member_count int, item_count int, score double precision
)
language sql stable as $$
  with seed as (select member_count as a_count from public.groups where id = p_group_id)
  select g.id, g.slug, g.name, g.description, g.member_count, g.item_count,
         (cv.c::double precision /
          greatest((seed.a_count + g.member_count - cv.c)::double precision, 1.0)
         ) as score
  from public.group_coview cv
  cross join seed
  join public.groups g on g.id = cv.b
  where cv.a = p_group_id
    and g.visibility <> 'private'
  order by score desc, g.score desc, g.id desc
  limit greatest(p_limit, 1);
$$;

-- ---------- For You Feed (v3) ----------
-- 1. Build the user's tag-affinity vector from view_events in last 30 days.
-- 2. Score candidates by sum(matching tag affinities) + small hot bonus.
-- 3. With 10% probability per slot, swap in a random globally-trending item
--    for exploration (epsilon-greedy). We implement that swap on the API side
--    to keep the SQL deterministic.
-- 4. Exclude items the user already viewed in last 7 days.
create or replace function public.foryou_feed(
  p_user uuid,
  p_session text,
  p_limit int default 24,
  p_offset int default 0
)
returns table (
  id bigint, kind public.media_kind, title text, b2_key text, b2_thumb_key text,
  width int, height int, duration_seconds real,
  views_count bigint, score double precision
)
language sql stable as $$
  with affinity as (
    select mt.tag_id, count(*)::double precision as w
    from public.view_events ve
    join public.media_tags mt on mt.media_id = ve.media_id
    where ve.ts > now() - interval '30 days'
      and (
        (p_user is not null and ve.user_id = p_user)
        or (p_user is null and p_session is not null and ve.session_id = p_session)
      )
    group by mt.tag_id
  ),
  scored as (
    select m.id, m.kind, m.title, m.b2_key, m.b2_thumb_key,
           m.width, m.height, m.duration_seconds, m.views_count,
           (sum(coalesce(a.w, 0) * mt.weight)
            + 0.1 * public.hot_score(m.votes_up, m.votes_down, m.created_at)
           ) as score
    from public.media_items m
    join public.media_tags mt on mt.media_id = m.id
    left join affinity a on a.tag_id = mt.tag_id
    where m.is_public = true and m.is_deleted = false
      and not exists (
        select 1 from public.view_events ve
        where ve.media_id = m.id
          and ve.ts > now() - interval '7 days'
          and (
            (p_user is not null and ve.user_id = p_user)
            or (p_user is null and p_session is not null and ve.session_id = p_session)
          )
      )
    group by m.id
  )
  select id, kind, title, b2_key, b2_thumb_key, width, height,
         duration_seconds, views_count, score
  from scored
  order by score desc, id desc
  offset greatest(p_offset, 0)
  limit greatest(p_limit, 1);
$$;

-- Grant execute on all reco RPCs to anon (they're public reads anyway, scoped
-- by RLS on the underlying tables).
grant execute on function public.feed_hot(int, double precision, bigint)         to anon, authenticated;
grant execute on function public.feed_recent(int, timestamptz)                   to anon, authenticated;
grant execute on function public.related_media(bigint, int, uuid, text)          to anon, authenticated;
grant execute on function public.tag_feed(bigint, int, timestamptz)              to anon, authenticated;
grant execute on function public.related_tags(bigint, int)                       to anon, authenticated;
grant execute on function public.group_feed(bigint, int, timestamptz)            to anon, authenticated;
grant execute on function public.related_groups(bigint, int)                     to anon, authenticated;
grant execute on function public.foryou_feed(uuid, text, int, int)               to anon, authenticated;
