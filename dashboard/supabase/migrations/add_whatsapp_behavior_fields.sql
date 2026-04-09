-- Migration: add WhatsApp behavior-control fields to agents_config
-- Safe to run multiple times (IF NOT EXISTS)

alter table public.agents_config
  add column if not exists whatsapp_goal text;

alter table public.agents_config
  add column if not exists whatsapp_required_fields jsonb;

alter table public.agents_config
  add column if not exists whatsapp_rules jsonb;
