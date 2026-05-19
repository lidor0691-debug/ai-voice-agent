-- LOCAL VALIDATION ONLY. NOT FOR PRODUCTION. DO NOT APPLY TO PRODUCTION.
--
-- This file lives OUTSIDE supabase/migrations/ on purpose so the Supabase
-- CLI's migration runner ignores it.
--
-- Purpose: build the minimal schema needed by Phase 3.11D-3F local validation
-- of the Maya action send pipeline. Production already has full versions of
-- these tables (created outside this repo's migration history), so we only
-- create here the columns our maya_action_* migrations actually reference
-- via FK or SELECT.
--
-- Idempotent (IF NOT EXISTS) so re-applying after a partial run is safe.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.clients (
  id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL
);

CREATE TABLE IF NOT EXISTS public.agents_config (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       uuid REFERENCES public.clients(id) ON DELETE CASCADE,
  agent_name      text,
  phone_number    text,
  whatsapp_number text,
  is_active       boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS public.leads (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id                uuid REFERENCES public.clients(id) ON DELETE CASCADE,
  agent_id                 uuid REFERENCES public.agents_config(id) ON DELETE SET NULL,
  phone                    text,
  last_whatsapp_inbound_at timestamptz
);
