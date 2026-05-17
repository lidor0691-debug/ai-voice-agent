-- =========================================================================
-- Phase 3.7B-1 — Maya Action Approval System: RPC layer
-- Up migration. Adds:
--   1. skip_reason column on maya_action_suggestions
--   2. internal validator function maya_validate_action_message_he
--   3. four SECURITY DEFINER RPCs: approve_action, skip_action,
--      edit_action_payload, set_action_permission
--   4. REVOKE/GRANT for least-privilege access
--
-- Does NOT: send WhatsApp, call Twilio, write to execution_logs,
-- generate suggestions, wire UI, add RLS policies, or write audit_logs.
-- =========================================================================

BEGIN;

-- -------------------------------------------------------------------------
-- 1. Schema change: add skip_reason column
-- -------------------------------------------------------------------------

ALTER TABLE public.maya_action_suggestions
  ADD COLUMN skip_reason text NULL;

COMMENT ON COLUMN public.maya_action_suggestions.skip_reason IS
  'Optional short Hebrew chip text recorded when the client skips a suggestion via skip_action. Decision metadata, not message content.';

-- -------------------------------------------------------------------------
-- 2. Shared validator (SECURITY INVOKER; internal — not granted to client roles)
-- -------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.maya_validate_action_message_he(p_message_he text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_trimmed text;
  v_len     int;
BEGIN
  IF p_message_he IS NULL THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'invalid_payload',
      'error_he', 'חסר טקסט הודעה');
  END IF;

  v_trimmed := trim(p_message_he);
  v_len     := char_length(v_trimmed);

  IF v_len < 1 OR v_len > 2000 THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'invalid_payload',
      'error_he', 'אורך ההודעה צריך להיות בין תו אחד ל-2000 תווים');
  END IF;

  -- Unresolved square-bracket placeholders, e.g. "[מחיר]"
  IF p_message_he ~ '\[[^\]]+\]' THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'invalid_payload',
      'error_he', 'יש להחליף את כל המילים בסוגריים מרובעים לפני שליחה');
  END IF;

  -- Currency mentions: ₪, or standalone Hebrew tokens שח/שקל/שקלים
  IF p_message_he ~ '(₪|\mשח\M|\mשקל\M|\mשקלים\M)' THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'invalid_payload',
      'error_he', 'אסור להזכיר מחיר בנוסח עד שאישור מחיר ייפתח בנפרד');
  END IF;

  -- Disallow control characters except tab (09), LF (0A), CR (0D)
  IF p_message_he ~ '[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]' THEN
    RETURN jsonb_build_object(
      'ok', false, 'error_code', 'invalid_payload',
      'error_he', 'ההודעה מכילה תווים לא חוקיים');
  END IF;

  RETURN jsonb_build_object('ok', true, 'error_code', 'ok', 'error_he', NULL);
END;
$$;

COMMENT ON FUNCTION public.maya_validate_action_message_he(text) IS
  'Internal validator for client-edited action messages. Single source of truth for length, placeholder, currency, and control-char rules. Called by approve_action and edit_action_payload; reusable by the future executor.';

-- Internal-only: revoke from public/anon/authenticated; SECURITY DEFINER
-- RPCs (owned by postgres) can still call it regardless of grants.
REVOKE ALL ON FUNCTION public.maya_validate_action_message_he(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.maya_validate_action_message_he(text) FROM anon, authenticated;

-- -------------------------------------------------------------------------
-- 3. RPC: approve_action
-- -------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.approve_action(
  p_suggestion_id    uuid,
  p_expected_version int,
  p_message_he       text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_uid              uuid := auth.uid();
  v_caller_client    uuid := public.maya_auth_client_id();
  v_row_client_id    uuid;
  v_status           text;
  v_version          int;
  v_expires_at       timestamptz;
  v_validation       jsonb;
  v_payload_edited   jsonb;
  v_updated_at       timestamptz;
  v_approved_at      timestamptz;
BEGIN
  IF v_uid IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'not_authenticated',
      'error_he', 'נדרשת התחברות', 'suggestion', NULL, 'current_version', NULL);
  END IF;
  IF v_caller_client IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'forbidden',
      'error_he', 'אין הרשאה לפעולה זו', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  SELECT client_id, status, version, expires_at
    INTO v_row_client_id, v_status, v_version, v_expires_at
  FROM public.maya_action_suggestions
  WHERE id = p_suggestion_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'not_found',
      'error_he', 'הפעולה לא נמצאה', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF v_row_client_id <> v_caller_client THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'forbidden',
      'error_he', 'אין הרשאה לפעולה זו', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  -- Expiry takes precedence over stale_version and invalid_status checks
  -- for actionable states.
  IF v_status IN ('suggested', 'pending_approval') AND v_expires_at < now() THEN
    UPDATE public.maya_action_suggestions
       SET status = 'expired'
     WHERE id = p_suggestion_id;
    RETURN jsonb_build_object('ok', false, 'error_code', 'expired',
      'error_he', 'הפעולה פגה', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF v_status NOT IN ('suggested', 'pending_approval') THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'invalid_status',
      'error_he', 'מצב הפעולה לא מאפשר אישור', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF v_version <> p_expected_version THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'stale_version',
      'error_he', 'הפעולה עודכנה ברקע, רעננו ונסו שוב',
      'suggestion', NULL, 'current_version', v_version);
  END IF;

  IF p_message_he IS NOT NULL THEN
    v_validation := public.maya_validate_action_message_he(p_message_he);
    IF (v_validation ->> 'ok')::boolean IS DISTINCT FROM true THEN
      RETURN jsonb_build_object('ok', false,
        'error_code', v_validation ->> 'error_code',
        'error_he',   v_validation ->> 'error_he',
        'suggestion', NULL, 'current_version', NULL);
    END IF;
    v_payload_edited := jsonb_build_object('message_he', trim(p_message_he));
  END IF;

  UPDATE public.maya_action_suggestions
     SET status            = 'approved',
         approver_user_id  = v_uid,
         approved_at       = now(),
         payload_edited    = COALESCE(v_payload_edited, payload_edited)
   WHERE id = p_suggestion_id
   RETURNING version, updated_at, approved_at, payload_edited
        INTO v_version, v_updated_at, v_approved_at, v_payload_edited;

  RETURN jsonb_build_object(
    'ok', true, 'error_code', 'ok', 'error_he', NULL,
    'current_version', NULL,
    'suggestion', jsonb_build_object(
      'id',                p_suggestion_id,
      'status',            'approved',
      'version',           v_version,
      'updated_at',        v_updated_at,
      'approved_at',       v_approved_at,
      'approver_user_id',  v_uid,
      'payload_edited',    v_payload_edited
    )
  );
END;
$$;

COMMENT ON FUNCTION public.approve_action(uuid, int, text) IS
  'Approve a Maya action suggestion. Optionally accepts inline-edited message_he, validated through maya_validate_action_message_he. Always sets status=approved on success.';

-- -------------------------------------------------------------------------
-- 4. RPC: skip_action
-- -------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.skip_action(
  p_suggestion_id    uuid,
  p_expected_version int,
  p_reason           text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_uid              uuid := auth.uid();
  v_caller_client    uuid := public.maya_auth_client_id();
  v_row_client_id    uuid;
  v_status           text;
  v_version          int;
  v_expires_at       timestamptz;
  v_trimmed_reason   text;
  v_updated_at       timestamptz;
BEGIN
  IF v_uid IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'not_authenticated',
      'error_he', 'נדרשת התחברות', 'suggestion', NULL, 'current_version', NULL);
  END IF;
  IF v_caller_client IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'forbidden',
      'error_he', 'אין הרשאה לפעולה זו', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF p_reason IS NOT NULL THEN
    v_trimmed_reason := trim(p_reason);
    IF char_length(v_trimmed_reason) < 1 OR char_length(v_trimmed_reason) > 200 THEN
      RETURN jsonb_build_object('ok', false, 'error_code', 'invalid_payload',
        'error_he', 'אורך הסיבה צריך להיות עד 200 תווים',
        'suggestion', NULL, 'current_version', NULL);
    END IF;
  END IF;

  SELECT client_id, status, version, expires_at
    INTO v_row_client_id, v_status, v_version, v_expires_at
  FROM public.maya_action_suggestions
  WHERE id = p_suggestion_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'not_found',
      'error_he', 'הפעולה לא נמצאה', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF v_row_client_id <> v_caller_client THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'forbidden',
      'error_he', 'אין הרשאה לפעולה זו', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF v_status IN ('suggested', 'pending_approval') AND v_expires_at < now() THEN
    UPDATE public.maya_action_suggestions
       SET status = 'expired'
     WHERE id = p_suggestion_id;
    RETURN jsonb_build_object('ok', false, 'error_code', 'expired',
      'error_he', 'הפעולה פגה', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF v_status NOT IN ('suggested', 'pending_approval') THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'invalid_status',
      'error_he', 'מצב הפעולה לא מאפשר דילוג', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF v_version <> p_expected_version THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'stale_version',
      'error_he', 'הפעולה עודכנה ברקע, רעננו ונסו שוב',
      'suggestion', NULL, 'current_version', v_version);
  END IF;

  UPDATE public.maya_action_suggestions
     SET status      = 'skipped',
         skip_reason = COALESCE(v_trimmed_reason, skip_reason)
   WHERE id = p_suggestion_id
   RETURNING version, updated_at, skip_reason
        INTO v_version, v_updated_at, v_trimmed_reason;

  RETURN jsonb_build_object(
    'ok', true, 'error_code', 'ok', 'error_he', NULL,
    'current_version', NULL,
    'suggestion', jsonb_build_object(
      'id',          p_suggestion_id,
      'status',      'skipped',
      'version',     v_version,
      'updated_at',  v_updated_at,
      'skip_reason', v_trimmed_reason
    )
  );
END;
$$;

COMMENT ON FUNCTION public.skip_action(uuid, int, text) IS
  'Mark a Maya action suggestion as skipped by the client, with an optional short Hebrew reason chip stored in skip_reason.';

-- -------------------------------------------------------------------------
-- 5. RPC: edit_action_payload
-- -------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.edit_action_payload(
  p_suggestion_id    uuid,
  p_expected_version int,
  p_message_he       text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_uid              uuid := auth.uid();
  v_caller_client    uuid := public.maya_auth_client_id();
  v_row_client_id    uuid;
  v_status           text;
  v_version          int;
  v_expires_at       timestamptz;
  v_validation       jsonb;
  v_payload_edited   jsonb;
  v_updated_at       timestamptz;
BEGIN
  IF v_uid IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'not_authenticated',
      'error_he', 'נדרשת התחברות', 'suggestion', NULL, 'current_version', NULL);
  END IF;
  IF v_caller_client IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'forbidden',
      'error_he', 'אין הרשאה לפעולה זו', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  SELECT client_id, status, version, expires_at
    INTO v_row_client_id, v_status, v_version, v_expires_at
  FROM public.maya_action_suggestions
  WHERE id = p_suggestion_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'not_found',
      'error_he', 'הפעולה לא נמצאה', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF v_row_client_id <> v_caller_client THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'forbidden',
      'error_he', 'אין הרשאה לפעולה זו', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  -- Expiry precedence for actionable states
  IF v_status IN ('suggested', 'pending_approval', 'approved', 'edited')
     AND v_expires_at < now() THEN
    UPDATE public.maya_action_suggestions
       SET status = 'expired'
     WHERE id = p_suggestion_id;
    RETURN jsonb_build_object('ok', false, 'error_code', 'expired',
      'error_he', 'הפעולה פגה', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF v_status NOT IN ('suggested', 'pending_approval', 'approved', 'edited') THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'invalid_status',
      'error_he', 'מצב הפעולה לא מאפשר עריכה', 'suggestion', NULL, 'current_version', NULL);
  END IF;

  IF v_version <> p_expected_version THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'stale_version',
      'error_he', 'הפעולה עודכנה ברקע, רעננו ונסו שוב',
      'suggestion', NULL, 'current_version', v_version);
  END IF;

  v_validation := public.maya_validate_action_message_he(p_message_he);
  IF (v_validation ->> 'ok')::boolean IS DISTINCT FROM true THEN
    RETURN jsonb_build_object('ok', false,
      'error_code', v_validation ->> 'error_code',
      'error_he',   v_validation ->> 'error_he',
      'suggestion', NULL, 'current_version', NULL);
  END IF;

  v_payload_edited := jsonb_build_object('message_he', trim(p_message_he));

  -- approver_user_id and approved_at intentionally NOT modified.
  UPDATE public.maya_action_suggestions
     SET status         = 'edited',
         payload_edited = v_payload_edited
   WHERE id = p_suggestion_id
   RETURNING version, updated_at, payload_edited
        INTO v_version, v_updated_at, v_payload_edited;

  RETURN jsonb_build_object(
    'ok', true, 'error_code', 'ok', 'error_he', NULL,
    'current_version', NULL,
    'suggestion', jsonb_build_object(
      'id',             p_suggestion_id,
      'status',         'edited',
      'version',        v_version,
      'updated_at',     v_updated_at,
      'payload_edited', v_payload_edited
    )
  );
END;
$$;

COMMENT ON FUNCTION public.edit_action_payload(uuid, int, text) IS
  'Replace the action''s prepared message text. Allowed from suggested/pending_approval/approved/edited. Does not affect approver fields. Always sets status=edited.';

-- -------------------------------------------------------------------------
-- 6. RPC: set_action_permission
-- -------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.set_action_permission(
  p_action_type text,
  p_mode        text,
  p_scope       jsonb DEFAULT NULL,
  p_reason      text  DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_uid             uuid := auth.uid();
  v_caller_client   uuid := public.maya_auth_client_id();
  v_trimmed_reason  text;
  v_result_id       uuid;
  v_result_mode     text;
  v_result_scope    jsonb;
  v_result_prev     text;
  v_result_changed  timestamptz;
BEGIN
  IF v_uid IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'not_authenticated',
      'error_he', 'נדרשת התחברות', 'permission', NULL);
  END IF;
  IF v_caller_client IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'forbidden',
      'error_he', 'אין הרשאה לפעולה זו', 'permission', NULL);
  END IF;

  IF p_action_type IS DISTINCT FROM 'send_followup_message' THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'action_type_not_supported',
      'error_he', 'סוג הפעולה אינו נתמך', 'permission', NULL);
  END IF;

  IF p_mode NOT IN ('suggest_only', 'require_approval') THEN
    RETURN jsonb_build_object('ok', false, 'error_code', 'unsupported_permission_mode',
      'error_he', 'מצב ההרשאה אינו נתמך', 'permission', NULL);
  END IF;

  IF p_reason IS NOT NULL THEN
    v_trimmed_reason := trim(p_reason);
    IF char_length(v_trimmed_reason) < 1 OR char_length(v_trimmed_reason) > 200 THEN
      RETURN jsonb_build_object('ok', false, 'error_code', 'invalid_payload',
        'error_he', 'אורך הסיבה צריך להיות עד 200 תווים',
        'permission', NULL);
    END IF;
  END IF;

  -- Atomic upsert; race-safe under concurrent absent-row inserts.
  -- ON CONFLICT path uses qualified table reference for OLD values and
  -- the function parameter p_scope (not EXCLUDED.scope) so scope is
  -- preserved when the caller passes NULL.
  INSERT INTO public.maya_action_permissions
    (client_id, action_type, mode, scope, previous_mode,
     changed_by_user_id, changed_at, reason)
  VALUES
    (v_caller_client, p_action_type, p_mode,
     COALESCE(p_scope, '{}'::jsonb), NULL,
     v_uid, now(), v_trimmed_reason)
  ON CONFLICT (client_id, action_type) DO UPDATE
    SET previous_mode      = public.maya_action_permissions.mode,
        mode               = EXCLUDED.mode,
        scope              = COALESCE(p_scope, public.maya_action_permissions.scope),
        changed_by_user_id = EXCLUDED.changed_by_user_id,
        changed_at         = EXCLUDED.changed_at,
        reason             = EXCLUDED.reason
  RETURNING id, mode, scope, previous_mode, changed_at
       INTO v_result_id, v_result_mode, v_result_scope, v_result_prev, v_result_changed;

  RETURN jsonb_build_object(
    'ok', true, 'error_code', 'ok', 'error_he', NULL,
    'permission', jsonb_build_object(
      'id',            v_result_id,
      'action_type',   p_action_type,
      'mode',          v_result_mode,
      'scope',         v_result_scope,
      'previous_mode', v_result_prev,
      'changed_at',    v_result_changed
    )
  );
END;
$$;

COMMENT ON FUNCTION public.set_action_permission(text, text, jsonb, text) IS
  'Upsert the caller client''s permission row for an action_type. MVP accepts only action_type=send_followup_message and mode in (suggest_only, require_approval). History trigger captures the change.';

-- -------------------------------------------------------------------------
-- 7. Ownership + grants (least-privilege)
-- -------------------------------------------------------------------------

ALTER FUNCTION public.maya_validate_action_message_he(text)              OWNER TO postgres;
ALTER FUNCTION public.approve_action(uuid, int, text)                    OWNER TO postgres;
ALTER FUNCTION public.skip_action(uuid, int, text)                       OWNER TO postgres;
ALTER FUNCTION public.edit_action_payload(uuid, int, text)               OWNER TO postgres;
ALTER FUNCTION public.set_action_permission(text, text, jsonb, text)     OWNER TO postgres;

-- Strip default PUBLIC EXECUTE grants Postgres adds on CREATE FUNCTION.
REVOKE ALL ON FUNCTION public.approve_action(uuid, int, text)                FROM PUBLIC;
REVOKE ALL ON FUNCTION public.approve_action(uuid, int, text)                FROM anon;
REVOKE ALL ON FUNCTION public.skip_action(uuid, int, text)                   FROM PUBLIC;
REVOKE ALL ON FUNCTION public.skip_action(uuid, int, text)                   FROM anon;
REVOKE ALL ON FUNCTION public.edit_action_payload(uuid, int, text)           FROM PUBLIC;
REVOKE ALL ON FUNCTION public.edit_action_payload(uuid, int, text)           FROM anon;
REVOKE ALL ON FUNCTION public.set_action_permission(text, text, jsonb, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.set_action_permission(text, text, jsonb, text) FROM anon;

GRANT EXECUTE ON FUNCTION public.approve_action(uuid, int, text)                TO authenticated;
GRANT EXECUTE ON FUNCTION public.skip_action(uuid, int, text)                   TO authenticated;
GRANT EXECUTE ON FUNCTION public.edit_action_payload(uuid, int, text)           TO authenticated;
GRANT EXECUTE ON FUNCTION public.set_action_permission(text, text, jsonb, text) TO authenticated;

-- Validator is internal: no grants beyond owner. The SECURITY DEFINER RPCs
-- (owned by postgres) can call it regardless of grants.

COMMIT;
