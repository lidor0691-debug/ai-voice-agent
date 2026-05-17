-- =========================================================================
-- Phase 3.7A — DOWN migration. Safe only while all four tables are empty.
-- =========================================================================

BEGIN;

-- Delete-block triggers
DROP TRIGGER IF EXISTS tg_maya_action_execution_logs_block_delete       ON public.maya_action_execution_logs;
DROP TRIGGER IF EXISTS tg_maya_action_permissions_history_block_delete  ON public.maya_action_permissions_history;
DROP TRIGGER IF EXISTS tg_maya_action_permissions_block_delete          ON public.maya_action_permissions;
DROP TRIGGER IF EXISTS tg_maya_action_suggestions_block_delete          ON public.maya_action_suggestions;

-- Mutation triggers (history capture + touches)
DROP TRIGGER IF EXISTS tg_maya_action_permissions_history_capture       ON public.maya_action_permissions;
DROP TRIGGER IF EXISTS tg_maya_action_execution_logs_touch              ON public.maya_action_execution_logs;
DROP TRIGGER IF EXISTS tg_maya_action_permissions_touch                 ON public.maya_action_permissions;
DROP TRIGGER IF EXISTS tg_maya_action_suggestions_touch                 ON public.maya_action_suggestions;

-- Policies
DROP POLICY IF EXISTS p_maya_action_execution_logs_select       ON public.maya_action_execution_logs;
DROP POLICY IF EXISTS p_maya_action_permissions_history_select  ON public.maya_action_permissions_history;
DROP POLICY IF EXISTS p_maya_action_permissions_select          ON public.maya_action_permissions;
DROP POLICY IF EXISTS p_maya_action_suggestions_select          ON public.maya_action_suggestions;

-- Tables (reverse FK dependency order)
DROP TABLE IF EXISTS public.maya_action_execution_logs;
DROP TABLE IF EXISTS public.maya_action_permissions_history;
DROP TABLE IF EXISTS public.maya_action_permissions;
DROP TABLE IF EXISTS public.maya_action_suggestions;

-- Trigger functions (after tables / triggers gone)
DROP FUNCTION IF EXISTS public.tg_fn_maya_action_execution_logs_block_delete();
DROP FUNCTION IF EXISTS public.tg_fn_maya_action_permissions_history_block_delete();
DROP FUNCTION IF EXISTS public.tg_fn_maya_action_permissions_block_delete();
DROP FUNCTION IF EXISTS public.tg_fn_maya_action_suggestions_block_delete();
DROP FUNCTION IF EXISTS public.tg_fn_maya_action_permissions_history_capture();
DROP FUNCTION IF EXISTS public.tg_fn_maya_action_execution_logs_touch();
DROP FUNCTION IF EXISTS public.tg_fn_maya_action_permissions_touch();
DROP FUNCTION IF EXISTS public.tg_fn_maya_action_suggestions_touch();

-- Helper functions: drop only if no other migration depends on them.
-- In Phase 3.7A they are exclusive to this migration; later phases that
-- add tables using these helpers must update this section accordingly.
DROP FUNCTION IF EXISTS public.maya_auth_client_id();
DROP FUNCTION IF EXISTS public.maya_auth_is_admin();

COMMIT;
