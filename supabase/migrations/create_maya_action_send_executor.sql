-- ============================================================================
-- create_maya_action_executor.sql
-- ----------------------------------------------------------------------------
-- Phase 3.11C-3 — Path A: reuses existing maya_action_execution_logs columns.
--
-- Adds:
--   1. CHECK  maya_action_execution_logs_failure_code_consistency
--             (outcome='failed' ↔ error_code IS NOT NULL)
--   2. CHECK  maya_action_execution_logs_error_message_bounded
--             (length(error_message) <= 500)
--   3. RPC    claim_action_for_execution(uuid, int)
--             approved → executing (success), or → failed (Class A blockers).
--   4. RPC    finalize_action_execution(uuid, text, text, text, text, text)
--             executing → executed | failed.
--
-- Does NOT add columns. Does NOT add a `status` column on the logs table.
-- Does NOT modify approve_action / skip_action / edit_action_payload /
-- set_action_permission. Does NOT touch the leads or agents_config tables.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. CHECK constraints (additive)
-- ----------------------------------------------------------------------------

ALTER TABLE public.maya_action_execution_logs
  ADD CONSTRAINT maya_action_execution_logs_failure_code_consistency
  CHECK (
    (outcome = 'failed' AND error_code IS NOT NULL)
    OR
    (outcome IS DISTINCT FROM 'failed' AND error_code IS NULL)
  );

ALTER TABLE public.maya_action_execution_logs
  ADD CONSTRAINT maya_action_execution_logs_error_message_bounded
  CHECK (
    error_message IS NULL
    OR char_length(error_message) <= 500
  );

-- ----------------------------------------------------------------------------
-- 2. RPC: claim_action_for_execution
-- ----------------------------------------------------------------------------
-- Atomic Phase A claim. One row UPDATE on maya_action_suggestions plus one
-- INSERT into maya_action_execution_logs. On Class A pre-send blockers, the
-- suggestion is moved to 'failed' and a closed log row is written; on Class B
-- auth/race errors, no DB mutation occurs and an error envelope is returned.
-- On success the suggestion moves to 'executing' and an open log row is
-- inserted (outcome IS NULL, finished_at IS NULL).
--
-- Return envelope (mirrors 3.7B shape for compatibility with the dashboard
-- ActionState mapper):
--   { ok, error_code, error_he, suggestion, current_version, execution_log_id,
--     lead_phone, message_he, agent_id, client_id }
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.claim_action_for_execution(
  p_suggestion_id    uuid,
  p_expected_version int
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_uid                 uuid := auth.uid();
  v_caller_client       uuid := public.maya_auth_client_id();
  v_row_client_id       uuid;
  v_row_agent_id        uuid;
  v_row_lead_id         uuid;
  v_status              text;
  v_version             int;
  v_expires_at          timestamptz;
  v_permission_at_create text;
  v_action_type         text;
  v_payload             jsonb;
  v_payload_edited      jsonb;
  v_message_he          text;
  v_validation          jsonb;
  v_lead_phone          text;
  v_last_in             timestamptz;
  v_live_permission     text;
  v_log_id              uuid;
  v_new_version         int;
  v_updated_at          timestamptz;
BEGIN
  -- Guard 1 — authenticated caller (Class B, no DB mutation)
  IF v_uid IS NULL THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'not_authenticated',
      'error_he', 'נדרשת התחברות',
      'suggestion', NULL, 'current_version', NULL);
  END IF;

  -- Guard 2 — caller has a client_id (Class B)
  IF v_caller_client IS NULL THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'forbidden',
      'error_he', 'אין הרשאה לפעולה זו',
      'suggestion', NULL, 'current_version', NULL);
  END IF;

  -- Guard 3 — suggestion exists; lock row
  SELECT client_id, agent_id, lead_id, status, version, expires_at,
         permission_mode_at_creation, action_type, payload, payload_edited
    INTO v_row_client_id, v_row_agent_id, v_row_lead_id, v_status, v_version,
         v_expires_at, v_permission_at_create, v_action_type, v_payload,
         v_payload_edited
  FROM public.maya_action_suggestions
  WHERE id = p_suggestion_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'not_found',
      'error_he', 'הפעולה לא נמצאה',
      'suggestion', NULL, 'current_version', NULL);
  END IF;

  -- Guard 4 — caller owns the suggestion's client (Class B)
  IF v_row_client_id <> v_caller_client THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'forbidden',
      'error_he', 'אין הרשאה לפעולה זו',
      'suggestion', NULL, 'current_version', NULL);
  END IF;

  -- Guard 5 — MVP action type (Class B; CHECK should make this unreachable)
  IF v_action_type <> 'send_followup_message' THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'invalid_action_type',
      'error_he', 'סוג הפעולה אינו נתמך',
      'suggestion', NULL, 'current_version', NULL);
  END IF;

  -- Guard 6 — already in a non-terminal/non-approvable state (Class B)
  IF v_status IN ('executing', 'skipped', 'cancelled', 'expired') THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'already_acted',
      'error_he', 'הפעולה כבר טופלה',
      'suggestion', NULL, 'current_version', v_version);
  END IF;

  -- Guard 7 — already terminal post-execute (Class B)
  IF v_status IN ('executed', 'failed') THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'already_executed',
      'error_he', 'ההודעה כבר נשלחה',
      'suggestion', NULL, 'current_version', v_version);
  END IF;

  -- Guard 8 — must be approved to claim (Class B)
  IF v_status <> 'approved' THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'invalid_status',
      'error_he', 'מצב הפעולה לא מאפשר שליחה',
      'suggestion', NULL, 'current_version', v_version);
  END IF;

  -- Guard 9 — version match (Class B)
  IF v_version <> p_expected_version THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'stale_version',
      'error_he', 'הפעולה עודכנה ברקע, רעננו ונסו שוב',
      'suggestion', NULL, 'current_version', v_version);
  END IF;

  -- Guard 10 — not expired (Class A: failed + log)
  IF v_expires_at <= now() THEN
    UPDATE public.maya_action_suggestions
       SET status = 'failed', version = version + 1
     WHERE id = p_suggestion_id
     RETURNING version, updated_at INTO v_new_version, v_updated_at;

    INSERT INTO public.maya_action_execution_logs (
      suggestion_id, client_id, lead_id, action_type,
      started_at, finished_at, outcome,
      provider, provider_message_sid, provider_status,
      error_code, error_message
    ) VALUES (
      p_suggestion_id, v_row_client_id, v_row_lead_id, v_action_type,
      now(), now(), 'failed',
      'twilio', NULL, NULL,
      'expired', NULL
    ) RETURNING id INTO v_log_id;

    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'expired',
      'error_he', 'הפעולה פגה',
      'suggestion', jsonb_build_object(
        'id', p_suggestion_id, 'status', 'failed', 'version', v_new_version),
      'current_version', v_new_version,
      'execution_log_id', v_log_id);
  END IF;

  -- Guard 11 — permission still require_approval (Class A)
  IF v_permission_at_create <> 'require_approval' THEN
    UPDATE public.maya_action_suggestions
       SET status = 'failed', version = version + 1
     WHERE id = p_suggestion_id
     RETURNING version, updated_at INTO v_new_version, v_updated_at;

    INSERT INTO public.maya_action_execution_logs (
      suggestion_id, client_id, lead_id, action_type,
      started_at, finished_at, outcome,
      provider, error_code
    ) VALUES (
      p_suggestion_id, v_row_client_id, v_row_lead_id, v_action_type,
      now(), now(), 'failed',
      'twilio', 'permission_drift'
    ) RETURNING id INTO v_log_id;

    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'permission_drift',
      'error_he', 'מצב הפעולה השתנה. הפעולה לא נשלחה',
      'suggestion', jsonb_build_object(
        'id', p_suggestion_id, 'status', 'failed', 'version', v_new_version),
      'current_version', v_new_version,
      'execution_log_id', v_log_id);
  END IF;

  SELECT mode INTO v_live_permission
    FROM public.maya_action_permissions
   WHERE client_id = v_row_client_id
     AND action_type = v_action_type
   LIMIT 1;

  IF v_live_permission IS NULL OR v_live_permission <> 'require_approval' THEN
    UPDATE public.maya_action_suggestions
       SET status = 'failed', version = version + 1
     WHERE id = p_suggestion_id
     RETURNING version, updated_at INTO v_new_version, v_updated_at;

    INSERT INTO public.maya_action_execution_logs (
      suggestion_id, client_id, lead_id, action_type,
      started_at, finished_at, outcome,
      provider, error_code
    ) VALUES (
      p_suggestion_id, v_row_client_id, v_row_lead_id, v_action_type,
      now(), now(), 'failed',
      'twilio', 'permission_drift'
    ) RETURNING id INTO v_log_id;

    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'permission_drift',
      'error_he', 'מצב הפעולה השתנה. הפעולה לא נשלחה',
      'suggestion', jsonb_build_object(
        'id', p_suggestion_id, 'status', 'failed', 'version', v_new_version),
      'current_version', v_new_version,
      'execution_log_id', v_log_id);
  END IF;

  -- Guard 12 — lead exists, phone E.164 (Class A)
  SELECT phone, last_whatsapp_inbound_at
    INTO v_lead_phone, v_last_in
  FROM public.leads
  WHERE id = v_row_lead_id;

  IF NOT FOUND OR v_lead_phone IS NULL OR v_lead_phone !~ '^\+[1-9][0-9]{7,15}$' THEN
    UPDATE public.maya_action_suggestions
       SET status = 'failed', version = version + 1
     WHERE id = p_suggestion_id
     RETURNING version, updated_at INTO v_new_version, v_updated_at;

    INSERT INTO public.maya_action_execution_logs (
      suggestion_id, client_id, lead_id, action_type,
      started_at, finished_at, outcome,
      provider, error_code
    ) VALUES (
      p_suggestion_id, v_row_client_id, v_row_lead_id, v_action_type,
      now(), now(), 'failed',
      'twilio', 'missing_phone'
    ) RETURNING id INTO v_log_id;

    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'missing_phone',
      'error_he', 'חסר מספר טלפון של הליד',
      'suggestion', jsonb_build_object(
        'id', p_suggestion_id, 'status', 'failed', 'version', v_new_version),
      'current_version', v_new_version,
      'execution_log_id', v_log_id);
  END IF;

  -- Guard 13 — message valid (Class A)
  v_message_he := COALESCE(v_payload_edited->>'message_he', v_payload->>'message_he');

  v_validation := public.maya_validate_action_message_he(v_message_he);
  IF (v_validation ->> 'ok')::boolean IS DISTINCT FROM true THEN
    UPDATE public.maya_action_suggestions
       SET status = 'failed', version = version + 1
     WHERE id = p_suggestion_id
     RETURNING version, updated_at INTO v_new_version, v_updated_at;

    INSERT INTO public.maya_action_execution_logs (
      suggestion_id, client_id, lead_id, action_type,
      started_at, finished_at, outcome,
      provider, error_code, error_message
    ) VALUES (
      p_suggestion_id, v_row_client_id, v_row_lead_id, v_action_type,
      now(), now(), 'failed',
      'twilio', 'invalid_message',
      left(coalesce(v_validation ->> 'error_he', ''), 500)
    ) RETURNING id INTO v_log_id;

    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'invalid_message',
      'error_he', coalesce(v_validation ->> 'error_he', 'ההודעה אינה תקינה'),
      'suggestion', jsonb_build_object(
        'id', p_suggestion_id, 'status', 'failed', 'version', v_new_version),
      'current_version', v_new_version,
      'execution_log_id', v_log_id);
  END IF;

  -- Guard 14 — WhatsApp 24h window (Class A)
  IF v_last_in IS NULL OR (now() - v_last_in) > interval '24 hours' THEN
    UPDATE public.maya_action_suggestions
       SET status = 'failed', version = version + 1
     WHERE id = p_suggestion_id
     RETURNING version, updated_at INTO v_new_version, v_updated_at;

    INSERT INTO public.maya_action_execution_logs (
      suggestion_id, client_id, lead_id, action_type,
      started_at, finished_at, outcome,
      provider, error_code
    ) VALUES (
      p_suggestion_id, v_row_client_id, v_row_lead_id, v_action_type,
      now(), now(), 'failed',
      'twilio', 'session_expired'
    ) RETURNING id INTO v_log_id;

    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'session_expired',
      'error_he', 'חלון 24 השעות של WhatsApp נסגר',
      'suggestion', jsonb_build_object(
        'id', p_suggestion_id, 'status', 'failed', 'version', v_new_version),
      'current_version', v_new_version,
      'execution_log_id', v_log_id);
  END IF;

  -- Guard 15 — success: claim
  UPDATE public.maya_action_suggestions
     SET status = 'executing', version = version + 1
   WHERE id = p_suggestion_id
   RETURNING version, updated_at INTO v_new_version, v_updated_at;

  INSERT INTO public.maya_action_execution_logs (
    suggestion_id, client_id, lead_id, action_type,
    started_at, finished_at, outcome,
    provider, provider_message_sid, provider_status,
    error_code, error_message
  ) VALUES (
    p_suggestion_id, v_row_client_id, v_row_lead_id, v_action_type,
    now(), NULL, NULL,
    'twilio', NULL, NULL,
    NULL, NULL
  ) RETURNING id INTO v_log_id;

  RETURN jsonb_build_object(
    'ok', true, 'error_code', 'ok', 'error_he', NULL,
    'suggestion', jsonb_build_object(
      'id', p_suggestion_id, 'status', 'executing', 'version', v_new_version),
    'current_version', v_new_version,
    'execution_log_id', v_log_id,
    'lead_phone', v_lead_phone,
    'message_he', trim(v_message_he),
    'agent_id', v_row_agent_id,
    'client_id', v_row_client_id
  );
END;
$$;

COMMENT ON FUNCTION public.claim_action_for_execution(uuid, int) IS
  'Phase 3.11 executor Phase-A claim. Transitions approved → executing (success) or approved → failed (Class A blockers: expired, permission_drift, missing_phone, invalid_message, session_expired). Class B failures (auth/race) return error envelope only, no DB mutation. Always inserts a closed failed log row for Class A, an open log row for success.';

-- ----------------------------------------------------------------------------
-- 3. RPC: finalize_action_execution
-- ----------------------------------------------------------------------------
-- Phase D terminal state transition. Only acts on rows whose suggestion is
-- currently 'executing' with exactly one open log row for that suggestion.
-- Owned by the caller whose JWT brought the suggestion into 'executing'.
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.finalize_action_execution(
  p_suggestion_id          uuid,
  p_terminal_status        text,
  p_twilio_message_sid     text,
  p_twilio_message_status  text,
  p_failure_code           text,
  p_failure_detail         text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_uid             uuid := auth.uid();
  v_caller_client   uuid := public.maya_auth_client_id();
  v_row_client_id   uuid;
  v_status          text;
  v_version         int;
  v_log_id          uuid;
  v_new_version     int;
  v_updated_at      timestamptz;
  v_bounded_detail  text;
  v_terminal_outcome text;
BEGIN
  IF v_uid IS NULL THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'not_authenticated',
      'error_he', 'נדרשת התחברות',
      'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF v_caller_client IS NULL THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'forbidden',
      'error_he', 'אין הרשאה לפעולה זו',
      'suggestion', NULL, 'current_version', NULL);
  END IF;

  -- Validate terminal status input
  IF p_terminal_status NOT IN ('executed', 'failed') THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'invalid_input',
      'error_he', 'מצב סופי לא חוקי',
      'suggestion', NULL, 'current_version', NULL);
  END IF;

  -- Enforce input invariants per terminal status
  IF p_terminal_status = 'executed' THEN
    IF p_failure_code IS NOT NULL THEN
      RETURN jsonb_build_object(
        'ok', false, 'error_code', 'invalid_input',
        'error_he', 'הצלחה אינה יכולה לשאת קוד תקלה',
        'suggestion', NULL, 'current_version', NULL);
    END IF;
    IF p_twilio_message_sid IS NULL OR length(btrim(p_twilio_message_sid)) = 0 THEN
      RETURN jsonb_build_object(
        'ok', false, 'error_code', 'invalid_input',
        'error_he', 'הצלחה חייבת לכלול Twilio SID',
        'suggestion', NULL, 'current_version', NULL);
    END IF;
  ELSE  -- 'failed'
    IF p_failure_code IS NULL OR length(btrim(p_failure_code)) = 0 THEN
      RETURN jsonb_build_object(
        'ok', false, 'error_code', 'invalid_input',
        'error_he', 'כשלון חייב לשאת קוד תקלה',
        'suggestion', NULL, 'current_version', NULL);
    END IF;
  END IF;

  -- Lock the suggestion row
  SELECT client_id, status, version
    INTO v_row_client_id, v_status, v_version
  FROM public.maya_action_suggestions
  WHERE id = p_suggestion_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'not_found',
      'error_he', 'הפעולה לא נמצאה',
      'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF v_row_client_id <> v_caller_client THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'forbidden',
      'error_he', 'אין הרשאה לפעולה זו',
      'suggestion', NULL, 'current_version', NULL);
  END IF;

  -- Only finalize from 'executing'
  IF v_status <> 'executing' THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'invalid_status',
      'error_he', 'הפעולה אינה במצב שליחה',
      'suggestion', NULL, 'current_version', v_version);
  END IF;

  -- Find the single open log row
  SELECT id INTO v_log_id
    FROM public.maya_action_execution_logs
   WHERE suggestion_id = p_suggestion_id
     AND outcome IS NULL
     AND finished_at IS NULL
   FOR UPDATE;

  IF NOT FOUND THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'invalid_status',
      'error_he', 'לא נמצא לוג שליחה פתוח',
      'suggestion', NULL, 'current_version', v_version);
  END IF;

  v_bounded_detail := left(coalesce(p_failure_detail, ''), 500);
  IF v_bounded_detail = '' THEN
    v_bounded_detail := NULL;
  END IF;

  IF p_terminal_status = 'executed' THEN
    UPDATE public.maya_action_execution_logs
       SET outcome              = 'executed',
           finished_at          = now(),
           provider_message_sid = p_twilio_message_sid,
           provider_status      = p_twilio_message_status,
           error_code           = NULL,
           error_message        = NULL
     WHERE id = v_log_id;

    v_terminal_outcome := 'executed';
  ELSE
    UPDATE public.maya_action_execution_logs
       SET outcome              = 'failed',
           finished_at          = now(),
           provider_message_sid = p_twilio_message_sid,  -- may be NULL on failure
           provider_status      = p_twilio_message_status,
           error_code           = p_failure_code,
           error_message        = v_bounded_detail
     WHERE id = v_log_id;

    v_terminal_outcome := 'failed';
  END IF;

  UPDATE public.maya_action_suggestions
     SET status = v_terminal_outcome, version = version + 1
   WHERE id = p_suggestion_id
   RETURNING version, updated_at INTO v_new_version, v_updated_at;

  RETURN jsonb_build_object(
    'ok', true, 'error_code', 'ok', 'error_he', NULL,
    'suggestion', jsonb_build_object(
      'id', p_suggestion_id, 'status', v_terminal_outcome, 'version', v_new_version),
    'current_version', v_new_version,
    'execution_log_id', v_log_id
  );
END;
$$;

COMMENT ON FUNCTION public.finalize_action_execution(uuid, text, text, text, text, text) IS
  'Phase 3.11 executor Phase-D finalize. Transitions executing → executed or executing → failed atomically with the matching open execution-log row. Caller must own the suggestion''s client_id. Refuses if suggestion is not in executing or if no open log row exists.';

-- ----------------------------------------------------------------------------
-- 4. Ownership, REVOKE, GRANT
-- ----------------------------------------------------------------------------

ALTER FUNCTION public.claim_action_for_execution(uuid, int)                            OWNER TO postgres;
ALTER FUNCTION public.finalize_action_execution(uuid, text, text, text, text, text)    OWNER TO postgres;

REVOKE ALL ON FUNCTION public.claim_action_for_execution(uuid, int)                            FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_action_for_execution(uuid, int)                            FROM anon;
REVOKE ALL ON FUNCTION public.finalize_action_execution(uuid, text, text, text, text, text)    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.finalize_action_execution(uuid, text, text, text, text, text)    FROM anon;

GRANT EXECUTE ON FUNCTION public.claim_action_for_execution(uuid, int)                            TO authenticated;
GRANT EXECUTE ON FUNCTION public.finalize_action_execution(uuid, text, text, text, text, text)    TO authenticated;

COMMIT;
