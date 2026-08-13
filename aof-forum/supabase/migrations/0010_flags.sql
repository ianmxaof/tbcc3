-- =============================================================================
-- 0010_flags: user reports for moderation (P4)
-- =============================================================================

create table if not exists public.flags (
  id bigserial primary key,
  target_kind text not null check (target_kind in ('media', 'gallery', 'group', 'thread', 'post')),
  target_id bigint not null,
  reporter_id uuid references public.profiles(id) on delete set null,
  reason text,
  created_at timestamptz not null default now()
);

create index if not exists flags_target_idx on public.flags (target_kind, target_id, created_at desc);
create index if not exists flags_reporter_idx on public.flags (reporter_id, created_at desc);

alter table public.flags enable row level security;

drop policy if exists flags_insert_auth on public.flags;
drop policy if exists flags_read_admin on public.flags;

create policy flags_insert_auth on public.flags
  for insert
  with check (auth.uid() is not null and reporter_id = auth.uid());

create policy flags_read_admin on public.flags
  for select
  using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_admin = true)
  );
