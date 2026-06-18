-- =========================================================================
-- Assistant data layer — DB foundations (Telegram studio assistant).
-- Up migration. Schema only: no RPCs, no routes, no executor, no Twilio,
-- no Telegram, no scheduler, no seed data.
--
-- owner_id = studio = public.clients(id). RLS reuses the existing helpers
-- public.maya_auth_is_admin() / public.maya_auth_client_id() created by
-- create_maya_action_foundations.sql (a hard dependency of this migration).
--
-- NOT applied to live/staging by this PR — files land in the repo only.
-- Safe to roll back while all five tables are empty (see _down migration).
-- =========================================================================

BEGIN;

-- -------------------------------------------------------------------------
-- 0. Shared trigger functions
-- -------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.tg_fn_assistant_set_updated_at()
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

CREATE OR REPLACE FUNCTION public.tg_fn_assistant_scheduled_messages_block_delete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RAISE EXCEPTION
    'assistant_scheduled_messages rows must not be deleted; set status = ''cancelled'' or ''expired'' instead';
END;
$$;

CREATE OR REPLACE FUNCTION public.tg_fn_assistant_activity_log_block_delete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RAISE EXCEPTION
    'assistant_activity_log is append-only; rows must not be deleted';
END;
$$;

ALTER FUNCTION public.tg_fn_assistant_set_updated_at()                       OWNER TO postgres;
ALTER FUNCTION public.tg_fn_assistant_scheduled_messages_block_delete()      OWNER TO postgres;
ALTER FUNCTION public.tg_fn_assistant_activity_log_block_delete()            OWNER TO postgres;

-- -------------------------------------------------------------------------
-- 1. assistant_contacts
-- -------------------------------------------------------------------------

CREATE TABLE public.assistant_contacts (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id        uuid NOT NULL
                    REFERENCES public.clients(id) ON DELETE RESTRICT,
  name            text NOT NULL,
  recipient_type  text NOT NULL,
  phone           text NULL,                       -- E.164; NULL forces manual fallback
  last_inbound_at timestamptz NULL,                -- drives the WhatsApp 24h window
  status          text NOT NULL DEFAULT 'active',
  notes           text NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT chk_ac_recipient_type
    CHECK (recipient_type IN ('client','teacher','group')),
  CONSTRAINT chk_ac_status
    CHECK (status IN ('active','archived'))
);

CREATE INDEX idx_ac_owner_status
  ON public.assistant_contacts (owner_id, status);
CREATE INDEX idx_ac_owner_recipient_type
  ON public.assistant_contacts (owner_id, recipient_type);
CREATE INDEX idx_ac_owner_name
  ON public.assistant_contacts (owner_id, name);
CREATE UNIQUE INDEX uq_ac_owner_phone_partial
  ON public.assistant_contacts (owner_id, phone)
  WHERE phone IS NOT NULL;

COMMENT ON TABLE public.assistant_contacts IS
  'Studio assistant recipients (clients/teachers/groups). owner_id references clients(id). phone NULL or group => no API send path.';
COMMENT ON COLUMN public.assistant_contacts.last_inbound_at IS
  'Timestamp of the last inbound message from this contact; the Stage-2 resolver derives the WhatsApp 24h service window from it. Fed by inbound capture in a later PR.';

-- -------------------------------------------------------------------------
-- 2. assistant_message_templates
-- -------------------------------------------------------------------------

CREATE TABLE public.assistant_message_templates (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id               uuid NOT NULL
                           REFERENCES public.clients(id) ON DELETE RESTRICT,
  message_type           text NOT NULL,
  language               text NOT NULL DEFAULT 'he',
  name                   text NULL,
  body                   text NOT NULL,
  status                 text NOT NULL DEFAULT 'active',
  provider_template_name text NULL,                -- WhatsApp template id (future)
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT chk_amt_message_type
    CHECK (message_type IN ('agreement','deposit','video','lesson_coordination')),
  CONSTRAINT chk_amt_status
    CHECK (status IN ('active','inactive'))
);

CREATE INDEX idx_amt_owner_type_status
  ON public.assistant_message_templates (owner_id, message_type, status);
CREATE UNIQUE INDEX uq_amt_owner_type_lang_active_partial
  ON public.assistant_message_templates (owner_id, message_type, language)
  WHERE status = 'active';

COMMENT ON TABLE public.assistant_message_templates IS
  'Per-owner WhatsApp templates. message_type excludes custom (free text only). An active row makes api_template available to the Stage-2 resolver.';

-- -------------------------------------------------------------------------
-- 3. assistant_scheduled_messages
-- -------------------------------------------------------------------------

CREATE TABLE public.assistant_scheduled_messages (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id              uuid NOT NULL
                          REFERENCES public.clients(id) ON DELETE RESTRICT,
  contact_id            uuid NULL
                          REFERENCES public.assistant_contacts(id) ON DELETE RESTRICT,

  recipient_type        text NOT NULL,
  message_type          text NOT NULL,
  raw_command           text NOT NULL,             -- original natural-language command

  scheduled_at          timestamptz NULL,          -- the SEND time
  is_explicit_time      boolean NOT NULL DEFAULT false,
  related_event_date    date NULL,                 -- date the message is ABOUT (not a send time)

  send_plan             text NULL,                 -- resolved Stage-2 plan (NULL until resolved)
  status                text NOT NULL DEFAULT 'needs_clarification',

  body                  text NULL,                 -- final message text
  parsed_intent         jsonb NULL,                -- full ParsedIntent snapshot
  inferred_notes        jsonb NULL,                -- surfaced inferences (e.g. defaulted 10:00)

  approval_requested_at timestamptz NULL,
  approval_expires_at   timestamptz NULL,          -- app sets = approval_requested_at + 2h
  approved_at           timestamptz NULL,
  sent_at               timestamptz NULL,

  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),

  -- enum domains
  CONSTRAINT chk_asm_recipient_type
    CHECK (recipient_type IN ('client','teacher','group')),
  CONSTRAINT chk_asm_message_type
    CHECK (message_type IN ('agreement','deposit','video','lesson_coordination','custom')),
  CONSTRAINT chk_asm_send_plan
    CHECK (send_plan IS NULL OR send_plan IN
      ('group_manual','manual_fallback','api_template','api_freeform')),
  CONSTRAINT chk_asm_status
    CHECK (status IN (
      'needs_clarification','scheduled','waiting_for_approval','approved',
      'sent','failed','cancelled','expired','reminded_manual'
    )),

  -- status <-> timestamp coherence
  CONSTRAINT chk_asm_scheduled_requires_when
    CHECK (status <> 'scheduled' OR scheduled_at IS NOT NULL),
  CONSTRAINT chk_asm_waiting_requires_approval_ts
    CHECK (status <> 'waiting_for_approval'
           OR (approval_requested_at IS NOT NULL AND approval_expires_at IS NOT NULL)),
  CONSTRAINT chk_asm_approved_requires_approved_at
    CHECK (status <> 'approved' OR approved_at IS NOT NULL),
  CONSTRAINT chk_asm_sent_requires_sent_at
    CHECK (status <> 'sent' OR sent_at IS NOT NULL),
  CONSTRAINT chk_asm_approval_pairing
    CHECK (approved_at IS NULL OR approval_requested_at IS NOT NULL),
  CONSTRAINT chk_asm_approval_window_order
    CHECK (approval_expires_at IS NULL
           OR (approval_requested_at IS NOT NULL
               AND approval_expires_at > approval_requested_at)),

  -- business invariant: reminded_manual only on manual paths, never API send
  CONSTRAINT chk_asm_reminded_manual_plan
    CHECK (status <> 'reminded_manual'
           OR send_plan IN ('group_manual','manual_fallback'))
);

CREATE INDEX idx_asm_owner_status_scheduled
  ON public.assistant_scheduled_messages (owner_id, status, scheduled_at);
CREATE INDEX idx_asm_owner_scheduled_at
  ON public.assistant_scheduled_messages (owner_id, scheduled_at);
CREATE INDEX idx_asm_contact_id
  ON public.assistant_scheduled_messages (contact_id);
CREATE INDEX idx_asm_approval_expiry_pending
  ON public.assistant_scheduled_messages (approval_expires_at)
  WHERE status = 'waiting_for_approval';

COMMENT ON TABLE public.assistant_scheduled_messages IS
  'Studio assistant intent/send records. Mutable until terminal status. Deletions blocked by trigger; use status cancelled/expired instead. owner_id references clients(id).';
COMMENT ON COLUMN public.assistant_scheduled_messages.status IS
  'Lifecycle: needs_clarification (parse incomplete) | scheduled (resolved, awaiting trigger) | waiting_for_approval (asked owner, within 2h window) | approved (owner cleared to send) | sent (delivered via API) | failed (send error) | cancelled (OWNER cancelled) | expired (approval not given within the 2h window) | reminded_manual (Maya reminded owner to manually send/paste; only valid for group_manual/manual_fallback). cancelled != expired.';
COMMENT ON COLUMN public.assistant_scheduled_messages.scheduled_at IS
  'The SEND time. An event-only date (related_event_date) does NOT populate this.';
COMMENT ON COLUMN public.assistant_scheduled_messages.related_event_date IS
  'Date the message is ABOUT (Hebrew ל-/עד/של). Never a send time on its own.';
COMMENT ON COLUMN public.assistant_scheduled_messages.approval_expires_at IS
  'Set by app logic to approval_requested_at + interval ''2 hours''. Past this with no approved_at, the expiry sweep (later PR) moves status -> expired.';

-- -------------------------------------------------------------------------
-- 4. assistant_activity_log  (append-only)
-- -------------------------------------------------------------------------

CREATE TABLE public.assistant_activity_log (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id              uuid NOT NULL
                          REFERENCES public.clients(id) ON DELETE RESTRICT,
  scheduled_message_id  uuid NULL
                          REFERENCES public.assistant_scheduled_messages(id) ON DELETE SET NULL,
  contact_id            uuid NULL
                          REFERENCES public.assistant_contacts(id) ON DELETE SET NULL,
  event_type            text NOT NULL,
  detail                jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at            timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT chk_aal_event_type
    CHECK (event_type IN (
      'parsed','needs_clarification','resolved','scheduled',
      'approval_requested','approved','sent','send_failed',
      'cancelled','expired','reminded_manual',
      'contact_added','clarification_opened','clarification_resolved'
    ))
);

CREATE INDEX idx_aal_owner_created
  ON public.assistant_activity_log (owner_id, created_at DESC);
CREATE INDEX idx_aal_scheduled_message_id
  ON public.assistant_activity_log (scheduled_message_id);

COMMENT ON TABLE public.assistant_activity_log IS
  'Append-only audit of assistant lifecycle events. Backend-write-only; deletions blocked by trigger. No updated_at (rows are immutable by convention).';

-- -------------------------------------------------------------------------
-- 5. assistant_pending_clarifications
-- -------------------------------------------------------------------------

CREATE TABLE public.assistant_pending_clarifications (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id              uuid NOT NULL
                          REFERENCES public.clients(id) ON DELETE RESTRICT,
  scheduled_message_id  uuid NULL
                          REFERENCES public.assistant_scheduled_messages(id) ON DELETE SET NULL,
  raw_command           text NOT NULL,
  clarification_prompt  text NOT NULL,             -- what Maya asked
  clarification_type    text NOT NULL,
  status                text NOT NULL DEFAULT 'open',
  resolved_payload      jsonb NULL,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  resolved_at           timestamptz NULL,
  expires_at            timestamptz NULL,

  CONSTRAINT chk_apc_type
    CHECK (clarification_type IN
      ('missing_send_time','missing_recipient','unknown_recipient','ambiguous')),
  CONSTRAINT chk_apc_status
    CHECK (status IN ('open','resolved','expired','cancelled')),
  CONSTRAINT chk_apc_resolved_requires_resolved_at
    CHECK (status <> 'resolved' OR resolved_at IS NOT NULL)
);

CREATE INDEX idx_apc_owner_status
  ON public.assistant_pending_clarifications (owner_id, status);
CREATE INDEX idx_apc_scheduled_message_id
  ON public.assistant_pending_clarifications (scheduled_message_id);

COMMENT ON TABLE public.assistant_pending_clarifications IS
  'Open questions Maya asked the owner (missing send time / recipient / unknown recipient / ambiguous). Supports the stateful two-turn inline contact-add flow. owner_id references clients(id).';

-- -------------------------------------------------------------------------
-- 6. Triggers
-- -------------------------------------------------------------------------

CREATE TRIGGER tg_assistant_contacts_touch
  BEFORE UPDATE ON public.assistant_contacts
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_assistant_set_updated_at();

CREATE TRIGGER tg_assistant_message_templates_touch
  BEFORE UPDATE ON public.assistant_message_templates
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_assistant_set_updated_at();

CREATE TRIGGER tg_assistant_scheduled_messages_touch
  BEFORE UPDATE ON public.assistant_scheduled_messages
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_assistant_set_updated_at();

CREATE TRIGGER tg_assistant_pending_clarifications_touch
  BEFORE UPDATE ON public.assistant_pending_clarifications
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_assistant_set_updated_at();

CREATE TRIGGER tg_assistant_scheduled_messages_block_delete
  BEFORE DELETE ON public.assistant_scheduled_messages
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_assistant_scheduled_messages_block_delete();

CREATE TRIGGER tg_assistant_activity_log_block_delete
  BEFORE DELETE ON public.assistant_activity_log
  FOR EACH ROW EXECUTE FUNCTION public.tg_fn_assistant_activity_log_block_delete();

-- -------------------------------------------------------------------------
-- 7. Row-Level Security  (SELECT-only for authenticated; default-deny writes)
-- -------------------------------------------------------------------------

ALTER TABLE public.assistant_contacts                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assistant_message_templates       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assistant_scheduled_messages      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assistant_activity_log            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assistant_pending_clarifications  ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.assistant_contacts                FORCE ROW LEVEL SECURITY;
ALTER TABLE public.assistant_message_templates       FORCE ROW LEVEL SECURITY;
ALTER TABLE public.assistant_scheduled_messages      FORCE ROW LEVEL SECURITY;
ALTER TABLE public.assistant_activity_log            FORCE ROW LEVEL SECURITY;
ALTER TABLE public.assistant_pending_clarifications  FORCE ROW LEVEL SECURITY;

CREATE POLICY p_ac_select
  ON public.assistant_contacts
  FOR SELECT TO authenticated
  USING (public.maya_auth_is_admin() OR owner_id = public.maya_auth_client_id());

CREATE POLICY p_amt_select
  ON public.assistant_message_templates
  FOR SELECT TO authenticated
  USING (public.maya_auth_is_admin() OR owner_id = public.maya_auth_client_id());

CREATE POLICY p_asm_select
  ON public.assistant_scheduled_messages
  FOR SELECT TO authenticated
  USING (public.maya_auth_is_admin() OR owner_id = public.maya_auth_client_id());

CREATE POLICY p_aal_select
  ON public.assistant_activity_log
  FOR SELECT TO authenticated
  USING (public.maya_auth_is_admin() OR owner_id = public.maya_auth_client_id());

CREATE POLICY p_apc_select
  ON public.assistant_pending_clarifications
  FOR SELECT TO authenticated
  USING (public.maya_auth_is_admin() OR owner_id = public.maya_auth_client_id());

-- No INSERT/UPDATE/DELETE policies: default-deny for authenticated/anon.
-- service_role (BYPASSRLS) is the backend write path; block-delete triggers
-- still prevent service-role DELETEs on the two protected tables.

-- -------------------------------------------------------------------------
-- 8. Explicit GRANT / REVOKE  (no unsafe public/anon access)
-- -------------------------------------------------------------------------

REVOKE ALL ON public.assistant_contacts                FROM PUBLIC, anon;
REVOKE ALL ON public.assistant_message_templates       FROM PUBLIC, anon;
REVOKE ALL ON public.assistant_scheduled_messages      FROM PUBLIC, anon;
REVOKE ALL ON public.assistant_activity_log            FROM PUBLIC, anon;
REVOKE ALL ON public.assistant_pending_clarifications  FROM PUBLIC, anon;

GRANT SELECT ON public.assistant_contacts                TO authenticated;
GRANT SELECT ON public.assistant_message_templates       TO authenticated;
GRANT SELECT ON public.assistant_scheduled_messages      TO authenticated;
GRANT SELECT ON public.assistant_activity_log            TO authenticated;
GRANT SELECT ON public.assistant_pending_clarifications  TO authenticated;

-- Backend write path (service_role bypasses RLS). No DELETE granted anywhere;
-- append-only / no-delete tables also omit UPDATE where rows are immutable.
GRANT SELECT, INSERT, UPDATE ON public.assistant_contacts                TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.assistant_message_templates       TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.assistant_scheduled_messages      TO service_role;
GRANT SELECT, INSERT         ON public.assistant_activity_log            TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.assistant_pending_clarifications  TO service_role;

COMMIT;
