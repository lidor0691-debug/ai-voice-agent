-- Maya Watch — operator action persistence (Stage 7 v0)
-- One row per (lead, decision_status, action_type) when the operator clicks
-- "אישור והפעלה" on the hero card. /maya-watch/briefing will read this
-- table to suppress already-acted decisions. Counts, lead state, and the
-- WhatsApp pipeline are unaffected — actions only gate which decisions
-- the operator still sees as "open".
--
-- Multi-tenant ready: client_id (uuid, denormalized from the lead row) and
-- agent_id (text, nullable) mirror the maya_watch_messages pattern. No FK
-- to clients — the lead row is the source of truth for tenant scope, and
-- the on-delete cascade from leads keeps actions in sync.
--
-- RLS enabled with no policies — service role only for v0, matching
-- maya_watch_leads / maya_watch_messages. All access goes through the
-- FastAPI layer + Stage 5 internal key; the frontend never touches this
-- table directly.

create table if not exists public.maya_watch_actions (
  id              uuid        primary key default gen_random_uuid(),
  lead_id         uuid        not null references public.maya_watch_leads(id) on delete cascade,
  -- Denormalized tenant scope (matches maya_watch_messages pattern).
  client_id       uuid,
  agent_id        text,
  -- Denormalized phone for log readability + simple endpoint diagnostics.
  phone           text        not null,
  -- The lead's derived status at the moment of action — e.g.
  -- 'awaiting_attention', 'followup_pending', 'replied_after_followup',
  -- 'no_response'. This is the gate key briefing uses to suppress; when
  -- the lead later transitions to a different status, a new (lead, status)
  -- pair will surface naturally because no row matches.
  decision_status text        not null,
  -- Open verb space. v0 only writes 'acted'. Stage 8+ may add 'dismissed'
  -- without a schema change.
  action_type     text        not null default 'acted',
  -- Operator identity (supabase user id as text). Nullable in v0 to avoid
  -- coupling to a users table or auth shape we don't own; the dashboard
  -- server passes it on a request header when available.
  acted_by        text,
  acted_at        timestamptz not null default now(),
  metadata        jsonb       not null default '{}'::jsonb
);

-- Idempotency primitive: a second click on the same decision can't insert
-- a duplicate row. The endpoint catches the unique violation, fetches the
-- existing row, and returns 200 with already_acted=true.
create unique index if not exists idx_maya_watch_actions_dedup
  on public.maya_watch_actions (lead_id, decision_status, action_type);

-- Briefing's per-tenant suppression scan reads (lead_id, decision_status)
-- filtered by client_id; this index covers it.
create index if not exists idx_maya_watch_actions_tenant
  on public.maya_watch_actions (client_id, decision_status);

-- RLS: locked by default. Service role only for v0; future tenant policies
-- (allow authenticated user where client_id matches their tenant) plug in
-- here when direct-from-frontend Maya Watch reads land.
alter table public.maya_watch_actions enable row level security;
