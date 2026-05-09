-- Stage 10C-2 — Promote idempotency partial index to UNIQUE.
--
-- 10C-1 shipped a non-unique partial index for fast lookup of existing
-- idempotency keys. 10C-2 adds the operator-send endpoint, which needs
-- DB-layer concurrency safety: two requests with the same idempotency
-- key arriving simultaneously must not both reach Twilio. Promoting the
-- index to UNIQUE means the second concurrent insert fails with 409 at
-- the DB layer; the route catches the conflict, fetches the existing
-- row, and returns it with already_sent=true.
--
-- Idempotent: drops the old non-unique index first, then creates the
-- new unique one with IF NOT EXISTS. Re-running this migration is a
-- no-op once the unique index is in place.
--
-- Existing-row safety: pre-migration row count = 4, all metadata = '{}'
-- so the partial WHERE clause covers ZERO rows. No uniqueness-violation
-- possible during migration.

drop index if exists public.idx_maya_watch_messages_idempotency;

create unique index if not exists idx_maya_watch_messages_idempotency
  on public.maya_watch_messages ((metadata->>'idempotency_key'))
  where metadata ? 'idempotency_key';
