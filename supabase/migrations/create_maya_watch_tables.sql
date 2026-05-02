-- Maya Watch persistence (Stage 3 v0)
-- Two tables: leads (per-phone state, denormalized followup) + messages (every in/out body).
-- Multi-tenant ready: client_id (uuid, nullable, FK soft) and agent_id (text, nullable, no FK
-- so it can hold either the agents_config UUID as text OR a slug like "default" pre-routing).
-- RLS enabled with no policies — service role only for v0; future tenant policies plug in here.

create table if not exists public.maya_watch_leads (
  id                     uuid        primary key default gen_random_uuid(),
  client_id              uuid        references public.clients(id) on delete set null,
  agent_id               text,
  phone                  text        not null,
  name                   text,
  booked                 boolean     not null default false,
  booked_at              timestamptz,
  -- Denormalized latest-followup snapshot for fast /maya-watch/leads reads.
  followup_sid           text,
  followup_body          text,
  followup_sent_at       timestamptz,
  followup_status        text,
  followup_error_code    text,
  followup_error_message text,
  followup_status_at     timestamptz,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

-- Tenant-scoped uniqueness on phone. coalesce sentinel makes NULL behave
-- like a fixed key so a single-tenant pre-routing setup can't insert
-- duplicates for the same phone.
create unique index if not exists idx_maya_watch_leads_tenant_phone
  on public.maya_watch_leads(coalesce(client_id, '00000000-0000-0000-0000-000000000000'::uuid), phone);

create index if not exists idx_maya_watch_leads_phone on public.maya_watch_leads(phone);


create table if not exists public.maya_watch_messages (
  id            bigserial   primary key,
  lead_id       uuid        not null references public.maya_watch_leads(id) on delete cascade,
  -- Denormalized for fast tenant-filtered queries without a join.
  client_id     uuid,
  agent_id      text,
  direction     text        not null check (direction in ('in', 'out')),
  body          text        not null,
  ts            timestamptz not null default now(),
  -- Outbound delivery tracking (populated by Twilio status_callback).
  sid           text,
  status        text,
  error_code    text,
  error_message text,
  status_at     timestamptz
);

create index if not exists idx_maya_watch_messages_lead on public.maya_watch_messages(lead_id, ts desc);
create index if not exists idx_maya_watch_messages_sid  on public.maya_watch_messages(sid) where sid is not null;


-- Auto-touch updated_at on lead row updates.
create or replace function public.maya_watch_touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists trg_maya_watch_leads_touch_updated_at on public.maya_watch_leads;
create trigger trg_maya_watch_leads_touch_updated_at
  before update on public.maya_watch_leads
  for each row execute function public.maya_watch_touch_updated_at();


-- RLS: lock down by default, only service role can read/write for v0.
-- Tenant policies (e.g. allow authenticated user where client_id = auth.uid()'s tenant)
-- will be added in a follow-up migration when multi-tenant routing lands.
alter table public.maya_watch_leads    enable row level security;
alter table public.maya_watch_messages enable row level security;
