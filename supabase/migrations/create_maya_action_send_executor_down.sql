-- ============================================================================
-- create_maya_action_executor_down.sql
-- ----------------------------------------------------------------------------
-- Reverses create_maya_action_executor.sql.
--
-- Order:
--   1. DROP finalize_action_execution (full argument signature)
--   2. DROP claim_action_for_execution (full argument signature)
--   3. DROP CHECK maya_action_execution_logs_error_message_bounded
--   4. DROP CHECK maya_action_execution_logs_failure_code_consistency
--
-- Does NOT drop columns. Does NOT touch existing RPCs (approve/skip/edit/
-- set_action_permission). Does NOT touch any table.
-- ============================================================================

BEGIN;

DROP FUNCTION IF EXISTS public.finalize_action_execution(uuid, text, text, text, text, text);
DROP FUNCTION IF EXISTS public.claim_action_for_execution(uuid, int);

ALTER TABLE public.maya_action_execution_logs
  DROP CONSTRAINT IF EXISTS maya_action_execution_logs_error_message_bounded;

ALTER TABLE public.maya_action_execution_logs
  DROP CONSTRAINT IF EXISTS maya_action_execution_logs_failure_code_consistency;

COMMIT;
