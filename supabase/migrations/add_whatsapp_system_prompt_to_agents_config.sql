-- Migration: add a WhatsApp-specific system prompt to agents_config.
-- Safe to run multiple times (IF NOT EXISTS). Nullable: existing rows keep
-- NULL and the backend falls back to system_prompt, so no behavior changes
-- for current clients and no data backfill is required.
--
-- Grants/RLS: no explicit GRANT is needed. Postgres table-level privileges
-- (Supabase's default grants on public.agents_config to anon/authenticated/
-- service_role) automatically cover newly added columns, and RLS policies
-- operate at the row level, not the column level — adding a column does not
-- require any policy change. The WhatsApp backend reads this table with the
-- service_role key, which bypasses RLS regardless. This matches the existing
-- pattern in add_whatsapp_behavior_fields.sql (no grants added there either).

alter table public.agents_config
  add column if not exists whatsapp_system_prompt text;
