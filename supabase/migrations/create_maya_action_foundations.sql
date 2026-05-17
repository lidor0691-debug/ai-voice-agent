-- =========================================================================
-- Phase 3.7A — Maya Action Approval System: DB foundations
-- Up migration. No RPCs, no UI, no executor, no Twilio, no seed data.
-- Safe to roll back while all four tables are empty. After Phase 3.8
-- begins inserting suggestions, rollback becomes data-loss.
-- =========================================================================

BEGIN;

-- -------------------------------------------------------------------------
-- 1. Helper functions (JWT-backed, STABLE, SECURITY INVOKER)
-- -------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.maya_auth_is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
  SELECT COALESCE(
    (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin',
    false
  );
$$;

COMMENT ON FUNCTION public.maya_auth_is_admin() IS
  'True when the caller is an admin (user_metadata.role = admin). False if no JWT or claim missing.';

CREATE OR REPLACE FUNCTION public.maya_auth_client_id()
RETURNS uuid
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  v_raw text;
  v_id  uuid;
BEGIN
  v_raw := (auth.jwt() -> 'user_metadata' ->> 'client_id');
  IF v_raw IS NULL OR v_raw = '' THEN
    RETURN NULL;
  END IF;
  BEGIN
    v_id := v_raw::uuid;
  EXCEPTION WHEN others THEN
    RETURN NULL;
  END;
  RETURN v_id;
END;
$$;

COMMENT ON FUNCTION public.maya_auth_client_id() IS
  'Caller''s client_id from user_metadata.client_id. NULL if absent or unparseable.';

GRANT EXECUTE ON FUNCTION public.maya_auth_is_admin()    TO authenticated, anon, service_role;
GRANT EXECUTE ON FUNCTION public.maya_auth_client_id()   TO authenticated, anon, service_role;

-- -------------------------------------------------------------------------
-- 2. maya_action_suggestions
-- -------------------------------------------------------------------------

CREATE TABLE public.maya_action_suggestions (
  id                            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id                     uuid NOT NULL
                                  REFERENCES public.clients(id) ON DELETE RESTRICT,
  agent_id                      uuid NULL
                                  REFERENCES public.agents_config(id) ON DELETE SET NULL,
  lead_id                       uuid NULL
                                  REFERENCES public.leads(id) ON DELETE RESTRICT,
  briefing_id                   uuid NULL
                                  REFERENCES public.analyst_briefings(id) ON DELETE SET NULL,
  finding_id                    uuid NULL
                                  REFERENCES public.analyst_briefing_findings(id) ON DELETE SET NULL,
  action_type                   text NOT NULL,
  status                        text NOT NULL DEFAULT 'suggested',
  permission_mode_at_creation   text NOT NULL,
  risk_level                    text NOT NULL,
  payload                       jsonb NOT NULL,
  payload_edited                jsonb NULL,
  rationale_he                  text NULL,
  expires_at                    timestamptz NOT NULL DEFAULT (now() + interval '72 hours'),
  approver_user_id              uuid NULL
                                  REFERENCES auth.users(id) ON DELETE SET NULL,
  approved_at                   timestamptz NULL,
  version                       int NOT NULL DEFAULT 1,
  created_at                    timestamptz NOT NULL DEFAULT now(),
  updated_at                    timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT chk_maya_action_suggestions_action_type
    CHECK (action_type IN (
      'send_followup_message',
      'send_appointment_confirmation',
      'add_faq_answer',
      'update_maya_reply_snippet',
      'tag_hot_lead',
      'create_owner_task'
    )),
  CONSTRAINT chk_maya_action_suggestions_action_type_mvp
    CHECK (action_type = 'send_followup_message'),
  CONSTRAINT chk_maya_action_suggestions_status
    CHECK (status IN (
      'suggested','pending_approval','approved','edited','skipped',
      'executing','executed','failed','expired','cancelled'
    )),
  CONSTRAINT chk_maya_action_suggestions_risk_level
    CHECK (risk_level IN ('low','medium','high')),
  CONSTRAINT chk_maya_action_suggestions_permission_mode_at_creation
    CHECK (permission_mode_at_creation IN (
      'suggest_only','require_approval','auto_execute_allowed','disabled'
    )),
  CONSTRAINT chk_maya_action_suggestions_followup_requires_lead
    CHECK (action_type <> 'send_followup_message' OR lead_id IS NOT NULL),
  CONSTRAINT chk_maya_action_suggestions_expires_after_created
    CHECK (expires_at > created_at),
  CONSTRAINT chk_maya_action_suggestions_approval_paired
    CHECK ((approver_user_id IS NULL) = (approved_at IS NULL))
);

CREATE INDEX idx_maya_action_suggestions_client_status_expires
  ON public.maya_action_suggestions (client_id, status, expires_at);
CREATE INDEX idx_maya_action_suggestions_briefing_id
  ON public.maya_action_suggestions (briefing_id);
CREATE INDEX idx_maya_action_suggestions_finding_id
  ON public.maya_action_suggestions (finding_id);
CREATE INDEX idx_maya_action_suggestions_lead_action_type
  ON public.maya_action_suggestions (lead_id, action_type);
CREATE UNIQUE INDEX uq_maya_action_suggestions_finding_action_partial
  ON public.maya_action_suggestions (finding_id, action_type)
  WHERE finding_id IS NOT NULL;

COMMENT ON TABLE  public.maya_action_suggestions IS
  'Maya-prepared action proposals. Mutable until terminal status. Deletions blocked by trigger.';
COMMENT ON COLUMN public.maya_action_suggestions.payload IS
  'Original prepared content (e.g., {"message_he": "..."}) authored by Maya.';
COMMENT ON COLUMN public.maya_action_suggestions.payload_edited IS
  'Approver-edited content; present only if the approver changed the message text.';
COMMENT ON COLUMN public.maya_action_suggestions.version IS
  'Optimistic-lock counter, bumped by tg_maya_action_suggestions_touch on every UPDATE.';
COMMENT ON COLUMN public.maya_action_suggestions.permission_mode_at_creation IS
  'Snapshot of the permission mode at creation time; live mode is read from maya_action_permissions at execution.';

-- -------------------------------------------------------------------------
-- 3. maya_action_permissions
-- -------------------------------------------------------------------------

CREATE TABLE public.maya_action_permissions (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id           uuid NOT NULL
                        REFERENCES public.clients(id) ON DELETE CASCADE,
  action_type         text NOT NULL,
  mode                text NOT NULL,
  scope               jsonb NOT NULL DEFAULT '{}'::jsonb,
  previous_mode       text NULL,
  changed_by_user_id  uuid NULL
                        REFERENCES auth.users(id) ON DELETE SET NULL,
  changed_at          timestamptz NOT NULL DEFAULT now(),
  reason              text NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT chk_maya_action_permissions_action_type
    CHECK (action_type IN (
      'send_followup_message',
      'send_appointment_confirmation',
      'add_faq_answer',
      'update_maya_reply_snippet',
      'tag_hot_lead',
      'create_owner_task'
    )),
  CONSTRAINT chk_maya_action_permissions_mode
    CHECK (mode IN (
      'suggest_only','require_approval','auto_execute_allowed','disabled'
    )),
  CONSTRAINT chk_maya_action_permissions_mode_mvp
    CHECK (mode IN ('suggest_only','require_approval'))
);

CREATE UNIQUE INDEX uq_maya_action_permissions_client_action
  ON public.maya_action_permissions (client_id, action_type);

COMMENT ON TABLE public.maya_action_permissions IS
  'Per-client per-action-type permission contract. Absence of a row means suggest_only by convention. Deletions blocked by trigger; disable by setting mode = disabled.';

-- -------------------------------------------------------------------------
-- 4. maya_action_permissions_history
-- -------------------------------------------------------------------------

CREATE TABLE public.maya_action_permissions_history (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  permission_id       uuid NULL
                        REFERENCES public.maya_action_permissions(id) ON DELETE SET NULL,
  client_id           uuid NOT NULL,
  action_type         text NOT NULL,
  from_mode           text NULL,
  to_mode             text NOT NULL,
  from_scope          jsonb NULL,
  to_scope            jsonb NOT NULL,
  changed_by_user_id  uuid NULL
                        REFERENCES auth.users(id) ON DELETE SET NULL,
  changed_at          timestamptz NOT NULL DEFAULT now(),
  reason              text NULL,
  op                  text NOT NULL,

  CONSTRAINT chk_maya_action_permissions_history_op
    CHECK (op IN ('insert','update'))
);

CREATE INDEX idx_maya_action_permissions_history_client_action_time
  ON public.maya_action_permissions_history (client_id, action_type, changed_at DESC);
CREATE INDEX idx_maya_action_permissions_history_permission_id
  ON public.maya_action_permissions_history (permission_id);

COMMENT ON TABLE public.maya_action_permissions_history IS
  'Append-only audit of permission changes. Written exclusively by the capture trigger. Deletions blocked by trigger. permission_id is nullable so history survives if the parent row is ever removed.';

-- -------------------------------------------------------------------------
-- 5. maya_action_execution_logs
-- -------------------------------------------------------------------------

CREATE TABLE public.maya_action_execution_logs (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  suggestion_id          uuid NOT NULL
                           REFERENCES public.maya_action_suggestions(id) ON DELETE RESTRICT,
  client_id              uuid NOT NULL
                           REFERENCES public.clients(id) ON DELETE RESTRICT,
  lead_id                uuid NULL
                           REFERENCES public.leads(id) ON DELETE RESTRICT,
  action_type            text NOT NULL,
  started_at             timestamptz NOT NULL DEFAULT now(),
  finished_at            timestamptz NULL,
  duration_ms            int NULL,
  outcome                text NULL,
  provider               text NULL,
  provider_message_sid   text NULL,
  provider_status        text NULL,
  error_code             text NULL,
  error_message          text NULL,
  effect_summary         jsonb NOT NULL DEFAULT '{}'::jsonb,
  reversible             boolean NOT NULL DEFAULT false,
  reversed_by_log_id     uuid NULL
                           REFERENCES public.maya_action_execution_logs(id) ON DELETE RESTRICT,
  request_payload        jsonb NULL,
  response_payload       jsonb NULL,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT chk_maya_action_execution_logs_action_type
    CHECK (action_type IN (
      'send_followup_message',
      'send_appointment_confirmation',
      'add_faq_answer',
      'update_maya_reply_snippet',
      'tag_hot_lead',
      'create_owner_task'
    )),
  CONSTRAINT chk_maya_action_execution_logs_action_type_mvp
    CHECK (action_type = 'send_followup_message'),
  CONSTRAINT chk_maya_action_execution_logs_outcome
    CHECK (outcome IS NULL OR outcome IN ('executed','failed')),
  CONSTRAINT chk_maya_action_execution_logs_finished_when_outcome
    CHECK (outcome IS NULL OR finished_at IS NOT NULL),
  CONSTRAINT chk_maya_action_execution_logs_reversed_requires_reversible
    CHECK (reversed_by_log_id IS NULL OR reversible = true)
);

CREATE INDEX idx_maya_action_execution_logs_client_started
  ON public.maya_action_execution_logs (client_id, started_at DESC);
CREATE INDEX idx_maya_action_execution_logs_suggestion_id
  ON public.maya_action_execution_logs (suggestion_id);
CREATE INDEX idx_maya_action_execution_logs_lead_started
  ON public.maya_action_execution_logs (lead_id, started_at DESC);
CREATE UNIQUE INDEX uq_maya_action_execution_logs_provider_sid_partial
  ON public.maya_action_execution_logs (provider_message_sid)
  WHERE provider_message_sid IS NOT NULL;

COMMENT ON TABLE public.maya_action_execution_logs IS
  'No-delete, backend-write-only audit of execution attempts. Limited UPDATEs by the executor for finished_at/outcome/provider_status/error fields. Deletions blocked by trigger.';
COMMENT ON COLUMN public.maya_action_execution_logs.effect_summary IS
  'Outcome side-effects (rows touched, reply received, etc.). JSON shape evolves with action types.';
COMMENT ON COLUMN public.maya_action_execution_logs.reversed_by_log_id IS
  'Points at the execution log that reversed this one; only set when reversible = true.';

-- -------------------------------------------------------------------------
-- 6. Mutation trigger functions
-- -------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.tg_fn_maya_action_suggestions_touch()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  NEW.updated_at := now();
  NEW.version    := COALESCE(OLD.version, 0) + 1;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.tg_fn_maya_action_permissions_touch()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.tg_fn_maya_action_execution_logs_touch()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.tg_fn_maya_action_permissions_history_capture()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO public.maya_action_permissions_history (
      permission_id, client_id, action_type,
      from_mode, to_mode, from_scope, to_scope,
      changed_by_user_id, changed_at, reason, op
    ) VALUES (
      NEW.id, NEW.client_id, NEW.action_type,
      NULL, NEW.mode, NULL, NEW.scope,
      NEW.changed_by_user_id, COALESCE(NEW.changed_at, now()), NEW.reason, 'insert'
    );
  ELSIF TG_OP = 'UPDATE' THEN
    INSERT INTO public.maya_action_permissions_history (
      permission_id, client_id, action_type,
      from_mode, to_mode, from_scope, to_scope,
      changed_by_user_id, changed_at, reason, op
    ) VALUES (
      NEW.id, NEW.client_id, NEW.action_type,
      OLD.mode, NEW.mode, OLD.scope, NEW.scope,
      NEW.changed_by_user_id, COALESCE(NEW.changed_at, now()), NEW.reason, 'update'
    );
  END IF;
  RETURN NEW;
END;
$$;

-- -------------------------------------------------------------------------
-- 7. Defensive delete-block trigger functions (block all roles)
-- -------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.tg_fn_maya_action_suggestions_block_delete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RAISE EXCEPTION
    'maya_action_suggestions rows must not be deleted; set status = ''cancelled'' or ''expired'' instead';
END;
$$;

CREATE OR REPLACE FUNCTION public.tg_fn_maya_action_permissions_block_delete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RAISE EXCEPTION
    'maya_action_permissions rows must not be deleted; set mode = ''disabled'' instead';
END;
$$;

CREATE OR REPLACE FUNCTION public.tg_fn_maya_action_permissions_history_block_delete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RAISE EXCEPTION
    'maya_action_permissions_history is append-only; rows must not be deleted';
END;
$$;

CREATE OR REPLACE FUNCTION public.tg_fn_maya_action_execution_logs_block_delete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RAISE EXCEPTION
    'maya_action_execution_logs is the irreversible audit of action executions; rows must not be deleted. Use status/effect fields or a linked reversal log instead';
END;
$$;

-- Ownership: ensure trigger functions are owned by a role that can bypass
-- RLS for the SECURITY DEFINER inserts into the history table. In Supabase
-- the standard migration role is `postgres`.
ALTER FUNCTION public.tg_fn_maya_action_suggestions_touch()                    OWNER TO postgres;
ALTER FUNCTION public.tg_fn_maya_action_permissions_touch()                    OWNER TO postgres;
ALTER FUNCTION public.tg_fn_maya_action_execution_logs_touch()                 OWNER TO postgres;
ALTER FUNCTION public.tg_fn_maya_action_permissions_history_capture()          OWNER TO postgres;
ALTER FUNCTION public.tg_fn_maya_action_suggestions_block_delete()             OWNER TO postgres;
ALTER FUNCTION public.tg_fn_maya_action_permissions_block_delete()             OWNER TO postgres;
ALTER FUNCTION public.tg_fn_maya_action_permissions_history_block_delete()     OWNER TO postgres;
ALTER FUNCTION public.tg_fn_maya_action_execution_logs_block_delete()          OWNER TO postgres;

-- -------------------------------------------------------------------------
-- 8. Triggers
-- -------------------------------------------------------------------------

CREATE TRIGGER tg_maya_action_suggestions_touch
  BEFORE UPDATE ON public.maya_action_suggestions
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_maya_action_suggestions_touch();

CREATE TRIGGER tg_maya_action_permissions_touch
  BEFORE UPDATE ON public.maya_action_permissions
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_maya_action_permissions_touch();

CREATE TRIGGER tg_maya_action_execution_logs_touch
  BEFORE UPDATE ON public.maya_action_execution_logs
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_maya_action_execution_logs_touch();

CREATE TRIGGER tg_maya_action_permissions_history_capture
  AFTER INSERT OR UPDATE ON public.maya_action_permissions
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_maya_action_permissions_history_capture();

CREATE TRIGGER tg_maya_action_suggestions_block_delete
  BEFORE DELETE ON public.maya_action_suggestions
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_maya_action_suggestions_block_delete();

CREATE TRIGGER tg_maya_action_permissions_block_delete
  BEFORE DELETE ON public.maya_action_permissions
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_maya_action_permissions_block_delete();

CREATE TRIGGER tg_maya_action_permissions_history_block_delete
  BEFORE DELETE ON public.maya_action_permissions_history
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_maya_action_permissions_history_block_delete();

CREATE TRIGGER tg_maya_action_execution_logs_block_delete
  BEFORE DELETE ON public.maya_action_execution_logs
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_maya_action_execution_logs_block_delete();

-- -------------------------------------------------------------------------
-- 9. Row-Level Security
-- -------------------------------------------------------------------------

ALTER TABLE public.maya_action_suggestions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.maya_action_permissions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.maya_action_permissions_history  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.maya_action_execution_logs       ENABLE ROW LEVEL SECURITY;

-- Force RLS even for table owners (defense-in-depth; service_role still
-- bypasses RLS via BYPASSRLS attribute, which is the intended write path
-- for backend code in later phases).
ALTER TABLE public.maya_action_suggestions          FORCE ROW LEVEL SECURITY;
ALTER TABLE public.maya_action_permissions          FORCE ROW LEVEL SECURITY;
ALTER TABLE public.maya_action_permissions_history  FORCE ROW LEVEL SECURITY;
ALTER TABLE public.maya_action_execution_logs       FORCE ROW LEVEL SECURITY;

CREATE POLICY p_maya_action_suggestions_select
  ON public.maya_action_suggestions
  FOR SELECT
  TO authenticated
  USING (public.maya_auth_is_admin() OR client_id = public.maya_auth_client_id());

CREATE POLICY p_maya_action_permissions_select
  ON public.maya_action_permissions
  FOR SELECT
  TO authenticated
  USING (public.maya_auth_is_admin() OR client_id = public.maya_auth_client_id());

CREATE POLICY p_maya_action_permissions_history_select
  ON public.maya_action_permissions_history
  FOR SELECT
  TO authenticated
  USING (public.maya_auth_is_admin() OR client_id = public.maya_auth_client_id());

CREATE POLICY p_maya_action_execution_logs_select
  ON public.maya_action_execution_logs
  FOR SELECT
  TO authenticated
  USING (public.maya_auth_is_admin() OR client_id = public.maya_auth_client_id());

-- No INSERT/UPDATE/DELETE policies in 3.7A. Default-deny applies to all
-- client roles. service_role bypasses RLS for backend writes in later
-- phases; defensive delete-block triggers prevent service-role DELETEs.

COMMIT;
