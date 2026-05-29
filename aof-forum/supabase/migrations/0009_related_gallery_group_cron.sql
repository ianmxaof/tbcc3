-- =============================================================================
-- 0009: Related galleries, group-scoped related media, batch hot-score refresh.
-- =============================================================================

-- ---------- Related galleries: same owner + tag overlap ----------
create or replace function public.related_galleries(
  p_gallery_id bigint,
  p_limit int default 12
)
returns table (
  id bigint,
  slug text,
  title text,
  description text,
  item_count int,
  score double precision,
  reason text
)
language sql stable as $$
  with g0 as (
    select owner_id from public.galleries where id = p_gallery_id
  ),
  seed_tags as (
    select distinct mt.tag_id
    from public.gallery_items gi
    join public.media_tags mt on mt.media_id = gi.media_id
    where gi.gallery_id = p_gallery_id
  ),
  same_owner as (
    select
      g.id, g.slug, g.title, g.description, g.item_count,
      (g.score + 10.0)::double precision as sc,
      'same_owner'::text as rnk
    from public.galleries g
    cross join g0
    where g.id <> p_gallery_id
      and g.is_public = true
      and g.owner_id = g0.owner_id
  ),
  tag_overlap as (
    select
      g.id, g.slug, g.title, g.description, g.item_count,
      (count(*)::double precision * 3.0 + g.score)::double precision as sc,
      'tag_overlap'::text as rnk
    from public.galleries g
    join public.gallery_items gi on gi.gallery_id = g.id
    join public.media_tags mt on mt.media_id = gi.media_id
    cross join seed_tags st
    where g.id <> p_gallery_id
      and g.is_public = true
      and mt.tag_id = st.tag_id
    group by g.id, g.slug, g.title, g.description, g.item_count, g.score
  ),
  merged as (
    select * from same_owner
    union all
    select * from tag_overlap
  ),
  dedup as (
    select
      m.id, m.slug, m.title, m.description, m.item_count, m.sc as s_score, m.rnk as s_reason,
      row_number() over (partition by m.id order by m.sc desc) as rn
    from merged m
  )
  select id, slug, title, description, item_count, s_score as score, s_reason as reason
  from dedup
  where rn = 1
  order by score desc
  limit greatest(coalesce(p_limit, 12), 1);
$$;

-- ---------- Related media limited to one group's corpus (tag overlap only) ----------
create or replace function public.related_media_in_group(
  p_media_id bigint,
  p_group_id bigint,
  p_limit int default 24,
  p_user uuid default null,
  p_session text default null
)
returns table (
  id bigint,
  kind public.media_kind,
  title text,
  b2_key text,
  b2_thumb_key text,
  width int,
  height int,
  duration_seconds real,
  views_count bigint,
  score double precision
)
language sql stable as $$
  with ok as (
    select exists(
      select 1 from public.group_media
      where group_id = p_group_id and media_id = p_media_id
    ) as pass
  ),
  seed_tags as (
    select mt.tag_id, mt.weight
    from public.media_tags mt
    cross join ok
    where ok.pass and mt.media_id = p_media_id
  ),
  tag_candidates as (
    select mt.media_id as cand_id, sum(mt.weight * st.weight) as raw_tag_score
    from seed_tags st
    join public.media_tags mt on mt.tag_id = st.tag_id and mt.media_id <> p_media_id
    join public.group_media gm on gm.media_id = mt.media_id and gm.group_id = p_group_id
    group by mt.media_id
  ),
  scored as (
    select
      m.id, m.kind, m.title, m.b2_key, m.b2_thumb_key, m.width, m.height,
      m.duration_seconds, m.views_count,
      (tc.raw_tag_score / (1.0 + tc.raw_tag_score)
        + 0.05 * ln(greatest(m.views_count, 1)::double precision) / 10.0
      ) as score
    from tag_candidates tc
    join public.media_items m on m.id = tc.cand_id
    cross join ok
    where ok.pass
      and m.is_public = true
      and m.is_deleted = false
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
  limit greatest(coalesce(p_limit, 24), 1);
$$;

-- ---------- Refresh denormalized hot scores (cron) ----------
create or replace function public.refresh_row_hot_scores()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.media_items m
  set score = public.hot_score(m.votes_up, m.votes_down, m.created_at)
  where not m.is_deleted;

  update public.groups g
  set score =
    0.45 * ln(greatest(g.member_count::double precision, 1.0))
    + 0.35 * ln(greatest(g.item_count::double precision, 1.0))
    + 0.25 * ln(greatest(g.thread_count::double precision, 1.0))
    + 0.05 * (extract(epoch from now()) - extract(epoch from g.created_at)) / 86400.0 / 365.0;
end;
$$;

grant execute on function public.related_galleries(bigint, int) to anon, authenticated;
grant execute on function public.related_media_in_group(bigint, bigint, int, uuid, text) to anon, authenticated;
grant execute on function public.refresh_row_hot_scores() to service_role;
