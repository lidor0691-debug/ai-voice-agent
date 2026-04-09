-- Migration: add schedule column to agents_config
-- Safe to run multiple times (IF NOT EXISTS equivalent via column check)

alter table public.agents_config
  add column if not exists schedule jsonb;
