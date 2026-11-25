-- gublan.xyz publishing: the table behind "publish" in the playground and gublan studio, and behind gublan.xyz/explore.
--
-- run it once in supabase: open the project, then sql editor > new query, paste all of this and press run.
-- running it again is safe. it never removes anything that's already published.
--
-- anyone can read creations (that's the point of publishing). only the person who published one can change it or
-- take it down. the database fills in who made it, their name and the times itself, so a page can't fake them.

create table if not exists public.creations (
  id         text primary key default substr(replace(gen_random_uuid()::text, '-', ''), 1, 12),
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  author     text not null default 'someone',
  title      text not null check (char_length(title) between 1 and 80),
  about      text not null default '' check (char_length(about) <= 1000),
  files      jsonb not null check (jsonb_typeof(files) = 'object' and pg_column_size(files) <= 262144),
  main       text not null default '' check (char_length(main) <= 120),
  uses_3d    boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists creations_newest on public.creations (created_at desc);
create index if not exists creations_by_user on public.creations (user_id);

-- who made it, their discord name, and the times always come from here, never from the page
create or replace function public.creations_stamp()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  me uuid := auth.uid();
  meta jsonb;
begin
  if me is null then
    return new; -- you, editing in the supabase dashboard
  end if;
  select raw_user_meta_data into meta from auth.users where id = me;
  new.user_id := me;
  new.author := left(coalesce(
    nullif(meta -> 'custom_claims' ->> 'global_name', ''),
    nullif(meta ->> 'full_name', ''),
    nullif(meta ->> 'name', ''),
    nullif(meta ->> 'user_name', ''),
    'someone'), 60);
  new.updated_at := now();
  if tg_op = 'INSERT' then
    new.id := substr(replace(gen_random_uuid()::text, '-', ''), 1, 12);
    new.created_at := now();
    if (select count(*) from public.creations where user_id = me) >= 100 then
      raise exception 'you can publish up to 100 creations. take one down first.';
    end if;
  else
    new.id := old.id;
    new.created_at := old.created_at;
  end if;
  return new;
end;
$$;

drop trigger if exists creations_stamp on public.creations;
create trigger creations_stamp
  before insert or update on public.creations
  for each row execute function public.creations_stamp();

alter table public.creations enable row level security;

drop policy if exists "anyone can see creations" on public.creations;
create policy "anyone can see creations" on public.creations
  for select to anon, authenticated using (true);

drop policy if exists "people publish as themselves" on public.creations;
create policy "people publish as themselves" on public.creations
  for insert to authenticated with check (user_id = (select auth.uid()));

drop policy if exists "people change their own" on public.creations;
create policy "people change their own" on public.creations
  for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

drop policy if exists "people take down their own" on public.creations;
create policy "people take down their own" on public.creations
  for delete to authenticated using (user_id = (select auth.uid()));

-- pages may only send these five columns. the rest are filled in above.
revoke all on public.creations from anon, authenticated;
grant select on public.creations to anon, authenticated;
grant insert (title, about, files, main, uses_3d) on public.creations to authenticated;
grant update (title, about, files, main, uses_3d) on public.creations to authenticated;
grant delete on public.creations to authenticated;
