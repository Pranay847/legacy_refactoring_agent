-- ============================================================================
-- 0001_init.sql  —  Legacy Refactoring Agent: core multi-tenant schema + RLS
-- ----------------------------------------------------------------------------
-- Auth model: Clerk is the identity provider. Configure Clerk as a Supabase
-- third-party auth provider (Supabase Dashboard -> Authentication -> Third
-- Party Auth -> Clerk) so Clerk-issued JWTs are accepted. The JWT `sub` claim
-- is the Clerk user id; the RLS policies below authorize rows by matching that
-- `sub` to public.users.clerk_user_id.
--
-- The backend talks to Supabase with the SERVICE ROLE key, which BYPASSES RLS.
-- RLS here is defense-in-depth for any browser/anon access path.
--
-- Apply via Supabase SQL Editor (paste this file) or the Supabase CLI:
--     supabase db push
-- ============================================================================

-- gen_random_uuid() is built into Postgres 13+ (Supabase default).

-- ---------------------------------------------------------------------------
-- updated_at helper
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- users  (mirror of Clerk users; populated on first authenticated request)
-- ---------------------------------------------------------------------------
create table if not exists public.users (
  id            uuid primary key default gen_random_uuid(),
  clerk_user_id text not null unique,
  email         text,
  display_name  text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

drop trigger if exists users_set_updated_at on public.users;
create trigger users_set_updated_at
  before update on public.users
  for each row execute function public.set_updated_at();

-- Map the current JWT (Clerk `sub`) to a public.users.id for use in policies.
create or replace function public.current_app_user_id()
returns uuid
language sql
stable
as $$
  select u.id
  from public.users u
  where u.clerk_user_id = (auth.jwt() ->> 'sub');
$$;

-- ---------------------------------------------------------------------------
-- projects
-- ---------------------------------------------------------------------------
create table if not exists public.projects (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references public.users(id) on delete cascade,
  name        text not null,
  slug        text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists projects_owner_id_idx on public.projects(owner_id);

drop trigger if exists projects_set_updated_at on public.projects;
create trigger projects_set_updated_at
  before update on public.projects
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- pipeline_runs  (one row per pipeline execution for a project)
-- ---------------------------------------------------------------------------
create table if not exists public.pipeline_runs (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references public.projects(id) on delete cascade,
  created_by   uuid references public.users(id) on delete set null,
  status       text not null default 'pending'
                 check (status in ('pending','running','succeeded','failed')),
  current_step text,
  stats        jsonb not null default '{}'::jsonb,
  error        text,
  started_at   timestamptz,
  finished_at  timestamptz,
  created_at   timestamptz not null default now()
);
create index if not exists pipeline_runs_project_id_idx on public.pipeline_runs(project_id);

-- ---------------------------------------------------------------------------
-- generated_services
-- ---------------------------------------------------------------------------
create table if not exists public.generated_services (
  id           uuid primary key default gen_random_uuid(),
  run_id       uuid not null references public.pipeline_runs(id) on delete cascade,
  project_id   uuid not null references public.projects(id) on delete cascade,
  name         text not null,
  file_count   int not null default 0,
  storage_path text,
  metadata     jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now()
);
create index if not exists generated_services_run_id_idx on public.generated_services(run_id);
create index if not exists generated_services_project_id_idx on public.generated_services(project_id);

-- ---------------------------------------------------------------------------
-- usage_events  (drives plan-limit enforcement + analytics)
-- ---------------------------------------------------------------------------
create table if not exists public.usage_events (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references public.users(id) on delete cascade,
  project_id  uuid references public.projects(id) on delete set null,
  event_type  text not null
                check (event_type in ('scan','cluster','generate','generate_all','chat')),
  quantity    int not null default 1,
  metadata    jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);
create index if not exists usage_events_user_id_created_at_idx
  on public.usage_events(user_id, created_at);

-- ---------------------------------------------------------------------------
-- subscriptions  (Stripe-backed plan state, one row per user)
-- ---------------------------------------------------------------------------
create table if not exists public.subscriptions (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null unique references public.users(id) on delete cascade,
  plan                   text not null default 'free'
                           check (plan in ('free','pro','team')),
  status                 text not null default 'active',
  stripe_customer_id     text unique,
  stripe_subscription_id text unique,
  current_period_end     timestamptz,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);
create index if not exists subscriptions_user_id_idx on public.subscriptions(user_id);

drop trigger if exists subscriptions_set_updated_at on public.subscriptions;
create trigger subscriptions_set_updated_at
  before update on public.subscriptions
  for each row execute function public.set_updated_at();

-- ============================================================================
-- Row-Level Security
-- Enable on every table; deny by default; allow owners (matched via Clerk sub).
-- The service-role key used by the backend bypasses all of these policies.
-- ============================================================================
alter table public.users              enable row level security;
alter table public.projects           enable row level security;
alter table public.pipeline_runs      enable row level security;
alter table public.generated_services enable row level security;
alter table public.usage_events       enable row level security;
alter table public.subscriptions      enable row level security;

-- users: a user can read/update only their own row.
drop policy if exists users_select_self on public.users;
create policy users_select_self on public.users
  for select using (clerk_user_id = (auth.jwt() ->> 'sub'));

drop policy if exists users_update_self on public.users;
create policy users_update_self on public.users
  for update using (clerk_user_id = (auth.jwt() ->> 'sub'));

-- projects: owner-only across all verbs.
drop policy if exists projects_owner_all on public.projects;
create policy projects_owner_all on public.projects
  for all
  using (owner_id = public.current_app_user_id())
  with check (owner_id = public.current_app_user_id());

-- pipeline_runs: authorized when the parent project is owned by the user.
drop policy if exists pipeline_runs_owner_all on public.pipeline_runs;
create policy pipeline_runs_owner_all on public.pipeline_runs
  for all
  using (exists (
    select 1 from public.projects p
    where p.id = pipeline_runs.project_id
      and p.owner_id = public.current_app_user_id()))
  with check (exists (
    select 1 from public.projects p
    where p.id = pipeline_runs.project_id
      and p.owner_id = public.current_app_user_id()));

-- generated_services: same ownership rule via project_id.
drop policy if exists generated_services_owner_all on public.generated_services;
create policy generated_services_owner_all on public.generated_services
  for all
  using (exists (
    select 1 from public.projects p
    where p.id = generated_services.project_id
      and p.owner_id = public.current_app_user_id()))
  with check (exists (
    select 1 from public.projects p
    where p.id = generated_services.project_id
      and p.owner_id = public.current_app_user_id()));

-- usage_events: a user sees only their own events; inserts must be their own.
drop policy if exists usage_events_owner_all on public.usage_events;
create policy usage_events_owner_all on public.usage_events
  for all
  using (user_id = public.current_app_user_id())
  with check (user_id = public.current_app_user_id());

-- subscriptions: a user can read their own subscription. Writes happen via the
-- service role (Stripe webhooks), so no insert/update policy is granted here.
drop policy if exists subscriptions_select_self on public.subscriptions;
create policy subscriptions_select_self on public.subscriptions
  for select using (user_id = public.current_app_user_id());
