-- =============================================================================
-- 0007_rls: Row Level Security policies.
-- Service role (used by workers + privileged API routes) bypasses RLS automatically.
-- =============================================================================

alter table public.profiles          enable row level security;
alter table public.tags              enable row level security;
alter table public.media_items       enable row level security;
alter table public.media_tags        enable row level security;
alter table public.galleries         enable row level security;
alter table public.gallery_items     enable row level security;
alter table public.forum_categories  enable row level security;
alter table public.forum_threads     enable row level security;
alter table public.forum_posts       enable row level security;
alter table public.post_media        enable row level security;
alter table public.groups            enable row level security;
alter table public.group_members     enable row level security;
alter table public.group_media       enable row level security;
alter table public.votes             enable row level security;
alter table public.bookmarks         enable row level security;
alter table public.follows           enable row level security;
alter table public.view_events       enable row level security;
alter table public.ingest_jobs       enable row level security;

-- ---------- profiles ----------
drop policy if exists profiles_read_all   on public.profiles;
drop policy if exists profiles_update_self on public.profiles;
drop policy if exists profiles_insert_self on public.profiles;
create policy profiles_read_all    on public.profiles for select using (true);
create policy profiles_update_self on public.profiles for update using (auth.uid() = id);
create policy profiles_insert_self on public.profiles for insert with check (auth.uid() = id);

-- ---------- tags ----------
-- Public read. Writes only via service role (workers + Stash sync).
drop policy if exists tags_read_all on public.tags;
create policy tags_read_all on public.tags for select using (true);

-- ---------- media_items ----------
drop policy if exists media_read_public on public.media_items;
drop policy if exists media_read_own    on public.media_items;
drop policy if exists media_insert_self on public.media_items;
drop policy if exists media_update_own  on public.media_items;
drop policy if exists media_delete_own  on public.media_items;
create policy media_read_public on public.media_items for select using (is_public = true and is_deleted = false);
create policy media_read_own    on public.media_items for select using (uploader_id = auth.uid());
create policy media_insert_self on public.media_items for insert with check (uploader_id = auth.uid());
create policy media_update_own  on public.media_items for update using (uploader_id = auth.uid());
create policy media_delete_own  on public.media_items for delete using (uploader_id = auth.uid());

-- ---------- media_tags ----------
drop policy if exists media_tags_read on public.media_tags;
drop policy if exists media_tags_insert_auth on public.media_tags;
drop policy if exists media_tags_delete_owner on public.media_tags;
create policy media_tags_read         on public.media_tags for select using (true);
create policy media_tags_insert_auth  on public.media_tags for insert with check (auth.uid() is not null);
create policy media_tags_delete_owner on public.media_tags for delete using (
  added_by = auth.uid()
  or exists (select 1 from public.media_items m where m.id = media_id and m.uploader_id = auth.uid())
);

-- ---------- galleries ----------
drop policy if exists galleries_read_public on public.galleries;
drop policy if exists galleries_read_own    on public.galleries;
drop policy if exists galleries_write_own   on public.galleries;
create policy galleries_read_public on public.galleries for select using (is_public = true);
create policy galleries_read_own    on public.galleries for select using (owner_id = auth.uid());
create policy galleries_write_own   on public.galleries for all  using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy if exists gallery_items_read on public.gallery_items;
drop policy if exists gallery_items_write on public.gallery_items;
create policy gallery_items_read on public.gallery_items for select using (
  exists (select 1 from public.galleries g where g.id = gallery_id and (g.is_public or g.owner_id = auth.uid()))
);
create policy gallery_items_write on public.gallery_items for all using (
  exists (select 1 from public.galleries g where g.id = gallery_id and g.owner_id = auth.uid())
);

-- ---------- forum ----------
drop policy if exists forum_cats_read on public.forum_categories;
create policy forum_cats_read on public.forum_categories for select using (true);

drop policy if exists forum_threads_read on public.forum_threads;
drop policy if exists forum_threads_insert on public.forum_threads;
drop policy if exists forum_threads_update_own on public.forum_threads;
create policy forum_threads_read       on public.forum_threads for select using (true);
create policy forum_threads_insert     on public.forum_threads for insert with check (author_id = auth.uid());
create policy forum_threads_update_own on public.forum_threads for update using (author_id = auth.uid());

drop policy if exists forum_posts_read on public.forum_posts;
drop policy if exists forum_posts_insert on public.forum_posts;
drop policy if exists forum_posts_update_own on public.forum_posts;
create policy forum_posts_read       on public.forum_posts for select using (is_deleted = false);
create policy forum_posts_insert     on public.forum_posts for insert with check (author_id = auth.uid());
create policy forum_posts_update_own on public.forum_posts for update using (author_id = auth.uid());

drop policy if exists post_media_read on public.post_media;
drop policy if exists post_media_write on public.post_media;
create policy post_media_read  on public.post_media for select using (true);
create policy post_media_write on public.post_media for all using (
  exists (select 1 from public.forum_posts p where p.id = post_id and p.author_id = auth.uid())
);

-- ---------- groups ----------
drop policy if exists groups_read_visible on public.groups;
drop policy if exists groups_read_private_members on public.groups;
drop policy if exists groups_insert on public.groups;
drop policy if exists groups_update_mods on public.groups;
create policy groups_read_visible on public.groups for select using (visibility <> 'private');
create policy groups_read_private_members on public.groups for select using (
  visibility = 'private'
  and exists (select 1 from public.group_members gm where gm.group_id = id and gm.user_id = auth.uid())
);
create policy groups_insert      on public.groups for insert with check (owner_id = auth.uid());
create policy groups_update_mods on public.groups for update using (
  owner_id = auth.uid()
  or exists (
    select 1 from public.group_members gm
    where gm.group_id = id and gm.user_id = auth.uid() and gm.role in ('owner', 'mod')
  )
);

drop policy if exists group_members_read on public.group_members;
drop policy if exists group_members_self_join on public.group_members;
drop policy if exists group_members_self_leave on public.group_members;
drop policy if exists group_members_mod_manage on public.group_members;
create policy group_members_read       on public.group_members for select using (true);
create policy group_members_self_join  on public.group_members for insert with check (user_id = auth.uid());
create policy group_members_self_leave on public.group_members for delete using (user_id = auth.uid());
create policy group_members_mod_manage on public.group_members for update using (
  exists (
    select 1 from public.group_members gm
    where gm.group_id = group_members.group_id and gm.user_id = auth.uid() and gm.role in ('owner', 'mod')
  )
);

drop policy if exists group_media_read on public.group_media;
drop policy if exists group_media_insert on public.group_media;
drop policy if exists group_media_delete_mod on public.group_media;
create policy group_media_read on public.group_media for select using (
  exists (
    select 1 from public.groups g
    where g.id = group_id
      and (g.visibility <> 'private'
           or exists (select 1 from public.group_members gm where gm.group_id = g.id and gm.user_id = auth.uid()))
  )
);
create policy group_media_insert on public.group_media for insert with check (
  exists (select 1 from public.group_members gm where gm.group_id = group_id and gm.user_id = auth.uid())
);
create policy group_media_delete_mod on public.group_media for delete using (
  added_by = auth.uid()
  or exists (
    select 1 from public.group_members gm
    where gm.group_id = group_media.group_id and gm.user_id = auth.uid() and gm.role in ('owner', 'mod')
  )
);

-- ---------- engagement ----------
drop policy if exists votes_read on public.votes;
drop policy if exists votes_self on public.votes;
create policy votes_read on public.votes for select using (true);
create policy votes_self on public.votes for all using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists bookmarks_self on public.bookmarks;
create policy bookmarks_self on public.bookmarks for all using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists follows_read on public.follows;
drop policy if exists follows_self on public.follows;
create policy follows_read on public.follows for select using (true);
create policy follows_self on public.follows for all using (follower_id = auth.uid()) with check (follower_id = auth.uid());

-- view_events: anonymous inserts allowed (session-scoped doom-scroll telemetry).
-- Reads are server-side via service role only (no select policy = no rows visible).
drop policy if exists view_events_insert on public.view_events;
create policy view_events_insert on public.view_events for insert with check (true);

drop policy if exists ingest_jobs_read_own on public.ingest_jobs;
drop policy if exists ingest_jobs_insert_auth on public.ingest_jobs;
create policy ingest_jobs_read_own   on public.ingest_jobs for select using (requester_id = auth.uid());
create policy ingest_jobs_insert_auth on public.ingest_jobs for insert with check (requester_id = auth.uid());
