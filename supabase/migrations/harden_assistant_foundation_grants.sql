-- =========================================================================
-- harden_assistant_foundation_grants
-- Corrective migration: tighten table privileges on the 5 assistant_* tables
-- to least-privilege, and remove direct EXECUTE on the assistant trigger
-- functions from PUBLIC/anon/authenticated. Touches ONLY assistant_* objects.
-- No RLS policy changes, no data, no drops.
--
-- WHY THIS EXISTS:
--   create_assistant_foundations.sql revoked table privileges only from
--   PUBLIC and anon. Supabase's project-level default privileges
--   (ALTER DEFAULT PRIVILEGES ... GRANT ALL ... TO anon, authenticated,
--   service_role) had already granted ALL on the new tables at creation, so
--   authenticated and service_role retained the full privilege set
--   (incl. INSERT/UPDATE/DELETE/TRUNCATE). RLS (enabled + forced, SELECT-only
--   policies) blocked DML at the row level, but TRUNCATE is RLS-exempt — so
--   this migration removes the excess grants to reach least-privilege while
--   the tables are still empty.
--
-- This file records SQL already applied to production project
-- wymphxeancscjoseazlk via MCP apply_migration (name:
-- harden_assistant_foundation_grants). It is recorded here so the repo
-- migration history matches the remote Supabase migration history.
--
-- No _down migration is provided: a rollback would re-introduce the
-- over-broad Supabase default grants, which is intentionally undesirable.
-- =========================================================================

BEGIN;

-- 1. Reset all table privileges on the 5 assistant tables to a clean slate
REVOKE ALL ON public.assistant_contacts                FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.assistant_message_templates       FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.assistant_scheduled_messages      FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.assistant_activity_log            FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.assistant_pending_clarifications  FROM PUBLIC, anon, authenticated, service_role;

-- 2. Re-grant least-privilege
GRANT SELECT ON public.assistant_contacts                TO authenticated;
GRANT SELECT ON public.assistant_message_templates       TO authenticated;
GRANT SELECT ON public.assistant_scheduled_messages      TO authenticated;
GRANT SELECT ON public.assistant_activity_log            TO authenticated;
GRANT SELECT ON public.assistant_pending_clarifications  TO authenticated;

GRANT SELECT, INSERT, UPDATE ON public.assistant_contacts                TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.assistant_message_templates       TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.assistant_scheduled_messages      TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.assistant_pending_clarifications  TO service_role;

GRANT SELECT, INSERT ON public.assistant_activity_log TO service_role;

-- 3. Remove direct EXECUTE on the assistant trigger functions
--    (trigger firing is unaffected; triggers do not check EXECUTE privilege).
REVOKE EXECUTE ON FUNCTION public.tg_fn_assistant_set_updated_at()                  FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.tg_fn_assistant_scheduled_messages_block_delete() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.tg_fn_assistant_activity_log_block_delete()       FROM PUBLIC, anon, authenticated;

COMMIT;
