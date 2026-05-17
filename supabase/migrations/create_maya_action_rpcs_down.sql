-- =========================================================================
-- Phase 3.7B-1 — DOWN migration.
-- Safe only in local validation. In production, dropping skip_reason
-- destroys data; do not run this on production once data exists.
-- =========================================================================

BEGIN;

-- RPCs first (depend on validator + schema)
DROP FUNCTION IF EXISTS public.set_action_permission(text, text, jsonb, text);
DROP FUNCTION IF EXISTS public.edit_action_payload(uuid, int, text);
DROP FUNCTION IF EXISTS public.skip_action(uuid, int, text);
DROP FUNCTION IF EXISTS public.approve_action(uuid, int, text);

-- Validator
DROP FUNCTION IF EXISTS public.maya_validate_action_message_he(text);

-- Schema change last
ALTER TABLE public.maya_action_suggestions
  DROP COLUMN IF EXISTS skip_reason;

COMMIT;
