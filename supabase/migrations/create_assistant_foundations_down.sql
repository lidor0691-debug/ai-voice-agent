-- =========================================================================
-- Assistant data layer — DB foundations. DOWN migration.
-- Reverses create_assistant_foundations.sql. Safe only while all five
-- assistant_* tables are empty (CASCADE would drop dependent rows/objects).
-- Drops in reverse dependency order: triggers -> tables -> functions.
-- =========================================================================

BEGIN;

-- Triggers (dropped with their tables, but explicit for clarity / partial runs)
DROP TRIGGER IF EXISTS tg_assistant_contacts_touch                  ON public.assistant_contacts;
DROP TRIGGER IF EXISTS tg_assistant_message_templates_touch         ON public.assistant_message_templates;
DROP TRIGGER IF EXISTS tg_assistant_scheduled_messages_touch        ON public.assistant_scheduled_messages;
DROP TRIGGER IF EXISTS tg_assistant_pending_clarifications_touch    ON public.assistant_pending_clarifications;
DROP TRIGGER IF EXISTS tg_assistant_scheduled_messages_block_delete ON public.assistant_scheduled_messages;
DROP TRIGGER IF EXISTS tg_assistant_activity_log_block_delete       ON public.assistant_activity_log;

-- Tables (children before parents: activity_log + clarifications reference
-- scheduled_messages; scheduled_messages references contacts).
DROP TABLE IF EXISTS public.assistant_activity_log;
DROP TABLE IF EXISTS public.assistant_pending_clarifications;
DROP TABLE IF EXISTS public.assistant_scheduled_messages;
DROP TABLE IF EXISTS public.assistant_message_templates;
DROP TABLE IF EXISTS public.assistant_contacts;

-- Trigger functions (after all dependent triggers are gone).
DROP FUNCTION IF EXISTS public.tg_fn_assistant_activity_log_block_delete();
DROP FUNCTION IF EXISTS public.tg_fn_assistant_scheduled_messages_block_delete();
DROP FUNCTION IF EXISTS public.tg_fn_assistant_set_updated_at();

COMMIT;
