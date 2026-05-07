-- Stage 10C-1 — Source tracking + idempotency primitive on maya_watch_messages.
--
-- Pure additive: nullable text column, jsonb-with-default, partial index.
-- Zero risk to existing reads. Legacy rows get NULL source / {} metadata,
-- both safe defaults.
--
-- Why now (foundation for 10C-2+):
--  * The status_callback handler (update_outbound_status) currently mirrors
--    every matched outbound row's delivery state into maya_watch_leads.
--    followup_*. That denormalization is exclusively Maya's followup
--    snapshot — operator-sent messages must NOT overwrite it. The new
--    `source` column lets the mirror gate on source IN ('followup', NULL).
--  * `metadata` jsonb gives 10C-2 a place to record idempotency_key,
--    decision_id, sent_by without further schema churn.
--  * The partial index on `metadata->>'idempotency_key'` makes the future
--    "have I already sent this?" lookup cheap and ships now so 10C-2 needs
--    no follow-on migration.
--
-- Idempotent: every statement uses IF NOT EXISTS.

alter table public.maya_watch_messages
  add column if not exists source   text,
  add column if not exists metadata jsonb not null default '{}'::jsonb;

create index if not exists idx_maya_watch_messages_idempotency
  on public.maya_watch_messages ((metadata->>'idempotency_key'))
  where metadata ? 'idempotency_key';
