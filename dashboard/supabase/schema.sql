-- Maya AI Platform — Supabase Schema
-- Run this in your Supabase SQL editor

-- =============================================
-- agents_config
-- =============================================
create table if not exists public.agents_config (
  id              uuid primary key default gen_random_uuid(),
  business_name   text,
  agent_name      text not null,
  phone_number    text unique,
  is_active       boolean not null default true,

  -- Conversation
  first_message   text,
  system_prompt   text,
  tone            text default 'professional',
  language        text default 'en',

  -- Voice
  voice_provider  text default 'elevenlabs',
  voice_id        text,
  speaking_rate   numeric default 1.0,
  style_prompt    text,

  -- Model
  model_provider  text default 'openai',
  model_name      text default 'gpt-4o',
  temperature     numeric default 0.7,

  -- Tools
  transfer_number         text,
  post_call_webhook_url   text,           -- legacy: kept for backward compat

  -- Lead delivery
  lead_delivery_method    text default 'webhook',   -- webhook | whatsapp | email
  lead_delivery_target    text,                     -- URL, phone (+E.164), or email address

  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

-- Auto-update updated_at
create or replace function update_updated_at_column()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger agents_config_updated_at
  before update on public.agents_config
  for each row execute function update_updated_at_column();

-- =============================================
-- knowledge_items
-- =============================================
create table if not exists public.knowledge_items (
  id          uuid primary key default gen_random_uuid(),
  agent_id    uuid not null references public.agents_config(id) on delete cascade,
  category    text,
  title       text not null,
  content     text not null,
  priority    int default 5,
  is_active   boolean not null default true,
  created_at  timestamptz not null default now()
);

create index if not exists knowledge_items_agent_id_idx on public.knowledge_items(agent_id);

-- =============================================
-- call_logs
-- =============================================
create table if not exists public.call_logs (
  id            uuid primary key default gen_random_uuid(),
  agent_id      uuid references public.agents_config(id) on delete set null,
  phone_number  text,
  status        text default 'completed',   -- completed | missed | failed
  duration      int,                        -- seconds
  created_at    timestamptz not null default now()
);

create index if not exists call_logs_agent_id_idx on public.call_logs(agent_id);
create index if not exists call_logs_created_at_idx on public.call_logs(created_at desc);

-- =============================================
-- RLS — disable for now (enable when you add auth)
-- =============================================
alter table public.agents_config  disable row level security;
alter table public.knowledge_items disable row level security;
alter table public.call_logs       disable row level security;

-- =============================================
-- Migration: lead delivery fields
-- Run this block if agents_config already exists
-- =============================================
alter table public.agents_config
  add column if not exists business_name text,
  add column if not exists lead_delivery_method text default 'webhook',
  add column if not exists lead_delivery_target text;

-- =============================================
-- Migration: WhatsApp channel fields
-- =============================================
alter table public.agents_config
  add column if not exists whatsapp_enabled          boolean default false,
  add column if not exists whatsapp_number           text,
  add column if not exists whatsapp_followup_enabled boolean default false,
  add column if not exists whatsapp_followup_type    text default 'none',   -- none | summary | appointment | next_step
  add column if not exists whatsapp_followup_template text;

-- =============================================
-- Migration: structured call summary on call_logs
-- =============================================
alter table public.call_logs
  add column if not exists lead_data        jsonb,     -- raw collected lead args
  add column if not exists summary          text,      -- human-readable call summary
  add column if not exists outcome          text,      -- lead_collected | no_lead | transferred | failed
  add column if not exists appointment_set  boolean default false,
  add column if not exists followup_needed  boolean default false,
  add column if not exists next_action      text;      -- free-text next step

-- =============================================
-- Migration: clients table (multi-tenant root)
-- =============================================
create table if not exists public.clients (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  metadata   jsonb,
  created_at timestamptz not null default now()
);

alter table public.clients disable row level security;

-- =============================================
-- Migration: add client_id + channel to agents_config
-- =============================================
alter table public.agents_config
  add column if not exists client_id uuid references public.clients(id),
  add column if not exists channel   text default 'voice'
                                     check (channel in ('voice', 'whatsapp'));

-- =============================================
-- Migration: client_assets table
-- =============================================
create table if not exists public.client_assets (
  id          uuid primary key default gen_random_uuid(),
  client_id   uuid not null references public.clients(id) on delete cascade,
  asset_name  text not null,
  asset_type  text not null check (asset_type in ('text', 'link', 'pdf', 'image', 'video')),
  trigger_key text not null,
  content     text not null,
  sort_order  int  not null default 0,
  enabled     boolean not null default true,
  created_at  timestamptz not null default now()
);

create index if not exists client_assets_client_id_idx
  on public.client_assets(client_id);

create index if not exists client_assets_trigger_key_idx
  on public.client_assets(trigger_key);

create index if not exists client_assets_lookup_idx
  on public.client_assets(client_id, trigger_key, enabled);

alter table public.client_assets disable row level security;

-- =============================================
-- Bootstrap: run once after clients table created
-- Creates one clients row per existing agent and back-fills client_id.
-- Run manually in Supabase SQL editor:
--
-- do $$
-- declare
--   agent_row record;
--   new_client_id uuid;
-- begin
--   for agent_row in
--     select id, coalesce(business_name, agent_name, 'Unknown') as client_name
--     from public.agents_config
--     where client_id is null
--   loop
--     insert into public.clients (name)
--     values (agent_row.client_name)
--     returning id into new_client_id;
--
--     update public.agents_config
--     set client_id = new_client_id
--     where id = agent_row.id;
--   end loop;
-- end $$;
-- =============================================
