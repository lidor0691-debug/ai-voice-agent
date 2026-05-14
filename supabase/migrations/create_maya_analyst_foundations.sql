-- ============================================================================
-- Maya Vertical Intelligence — Phase 3.1 foundations (schema + RLS only)
-- ============================================================================
-- Creates four empty tables that back the four-layer learning model:
--
--   L1  client-private memory          existing leads / call_logs / WA /
--                                      maya_watch_* / lead_intelligence_*
--                                      (unchanged — not touched here)
--   L2  vertical_shared_knowledge      vertical_patterns  (this migration)
--   L3  curated_expert_knowledge       expert_knowledge   (this migration)
--   L4  analyst_briefings              analyst_briefings + findings (this
--                                      migration)
--
-- Privacy invariants enforced structurally:
--   * L2/L3 carry NO client_id column — cross-tenant association is
--     impossible.
--   * L4 carries client_id everywhere (denormalized onto findings) so RLS
--     is a single index lookup per row.
--   * Client RLS sees ONLY L4, and only their own client_id, only
--     published+client-visible rows.
--   * L2/L3 are admin/service only over Supabase REST.
--
-- See docs/MAYA-ARCHITECTURE.md for the broader architecture, promotion
-- rules, evidence discipline, and the "clients see L4 outputs only" rule.
-- ============================================================================

-- ─── L2 ─── vertical_patterns ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.vertical_patterns (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  vertical              text NOT NULL,
  pattern_type          text NOT NULL,
  canonical_text        text NOT NULL,
  language              text,
  support_count         integer NOT NULL DEFAULT 0,
  total_event_count     integer NOT NULL DEFAULT 0,
  first_seen            timestamptz,
  last_seen             timestamptz,
  confidence            numeric NOT NULL DEFAULT 0,
  promotion_method      text NOT NULL DEFAULT 'manual_curator',
  status                text NOT NULL DEFAULT 'candidate',
  evidence_digest       text,
  approved_by           uuid,
  approved_at           timestamptz,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT vertical_patterns_status_check
    CHECK (status IN ('candidate','approved','retired'))
);

CREATE INDEX IF NOT EXISTS vertical_patterns_vertical_status_lastseen_idx
  ON public.vertical_patterns (vertical, status, last_seen DESC);
CREATE INDEX IF NOT EXISTS vertical_patterns_status_confidence_idx
  ON public.vertical_patterns (status, confidence DESC);

ALTER TABLE public.vertical_patterns ENABLE ROW LEVEL SECURITY;

-- Admin-only access. Service-role bypasses RLS by default in Supabase.
CREATE POLICY vertical_patterns_admin_select ON public.vertical_patterns
  FOR SELECT USING ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );
CREATE POLICY vertical_patterns_admin_insert ON public.vertical_patterns
  FOR INSERT WITH CHECK ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );
CREATE POLICY vertical_patterns_admin_update ON public.vertical_patterns
  FOR UPDATE USING ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' )
             WITH CHECK ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );
CREATE POLICY vertical_patterns_admin_delete ON public.vertical_patterns
  FOR DELETE USING ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );


-- ─── L3 ─── expert_knowledge ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.expert_knowledge (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  vertical        text NOT NULL,
  topic           text NOT NULL,
  title           text NOT NULL,
  body_md         text NOT NULL,
  source_kind     text,
  source_ref      text,
  version         integer NOT NULL DEFAULT 1,
  status          text NOT NULL DEFAULT 'draft',
  language        text,
  created_by      uuid,
  approved_by     uuid,
  approved_at     timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT expert_knowledge_status_check
    CHECK (status IN ('draft','approved','retired'))
);

CREATE INDEX IF NOT EXISTS expert_knowledge_lookup_idx
  ON public.expert_knowledge (vertical, topic, status, version DESC);

ALTER TABLE public.expert_knowledge ENABLE ROW LEVEL SECURITY;

CREATE POLICY expert_knowledge_admin_select ON public.expert_knowledge
  FOR SELECT USING ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );
CREATE POLICY expert_knowledge_admin_insert ON public.expert_knowledge
  FOR INSERT WITH CHECK ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );
CREATE POLICY expert_knowledge_admin_update ON public.expert_knowledge
  FOR UPDATE USING ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' )
             WITH CHECK ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );
CREATE POLICY expert_knowledge_admin_delete ON public.expert_knowledge
  FOR DELETE USING ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );


-- ─── L4 ─── analyst_briefings ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.analyst_briefings (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id         uuid NOT NULL,
  agent_id          uuid,
  period_start      timestamptz NOT NULL,
  period_end        timestamptz NOT NULL,
  generated_at      timestamptz NOT NULL DEFAULT now(),
  status            text NOT NULL DEFAULT 'draft',
  data_volume       integer,
  volume_warning    text,
  summary_md        text,
  model_version     text,
  prompt_hash       text,
  created_by        text,
  approved_by       uuid,
  visibility        text NOT NULL DEFAULT 'client',
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT analyst_briefings_status_check
    CHECK (status IN ('draft','published','archived')),
  CONSTRAINT analyst_briefings_visibility_check
    CHECK (visibility IN ('client','admin_only'))
);

CREATE INDEX IF NOT EXISTS analyst_briefings_client_status_period_idx
  ON public.analyst_briefings (client_id, status, period_end DESC);
CREATE INDEX IF NOT EXISTS analyst_briefings_status_generated_idx
  ON public.analyst_briefings (status, generated_at DESC);

ALTER TABLE public.analyst_briefings ENABLE ROW LEVEL SECURITY;

-- Clients see only their own client_id, only published, only client-visible.
-- Admins see all. Service-role bypasses RLS.
CREATE POLICY analyst_briefings_select ON public.analyst_briefings
  FOR SELECT USING (
    (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin'
    OR (
      client_id = ((auth.jwt() -> 'user_metadata' ->> 'client_id'))::uuid
      AND status = 'published'
      AND visibility = 'client'
    )
  );

-- Writes admin/service only. Service-role bypasses RLS so these policies
-- exist to allow an authenticated admin user to act through REST as well.
CREATE POLICY analyst_briefings_admin_insert ON public.analyst_briefings
  FOR INSERT WITH CHECK ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );
CREATE POLICY analyst_briefings_admin_update ON public.analyst_briefings
  FOR UPDATE USING ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' )
             WITH CHECK ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );
CREATE POLICY analyst_briefings_admin_delete ON public.analyst_briefings
  FOR DELETE USING ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );


-- ─── L4 ─── analyst_briefing_findings ────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.analyst_briefing_findings (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  briefing_id             uuid NOT NULL REFERENCES public.analyst_briefings(id) ON DELETE CASCADE,
  client_id               uuid NOT NULL,             -- DENORMALIZED for RLS perf + defense-in-depth
  finding_type            text NOT NULL,
  title                   text NOT NULL,
  fact                    text NOT NULL,
  interpretation          text,
  recommendation          text,
  recommendation_target   text,
  confidence              numeric,
  sample_size             integer,
  evidence                jsonb,
  created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS analyst_briefing_findings_briefing_idx
  ON public.analyst_briefing_findings (briefing_id);
CREATE INDEX IF NOT EXISTS analyst_briefing_findings_client_type_idx
  ON public.analyst_briefing_findings (client_id, finding_type);
CREATE INDEX IF NOT EXISTS analyst_briefing_findings_target_idx
  ON public.analyst_briefing_findings (recommendation_target);

ALTER TABLE public.analyst_briefing_findings ENABLE ROW LEVEL SECURITY;

-- Same scope as parent briefing. Subquery ensures findings are only readable
-- when the parent briefing is published AND client-visible — orphaned
-- findings stay hidden.
CREATE POLICY analyst_briefing_findings_select ON public.analyst_briefing_findings
  FOR SELECT USING (
    (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin'
    OR (
      client_id = ((auth.jwt() -> 'user_metadata' ->> 'client_id'))::uuid
      AND EXISTS (
        SELECT 1 FROM public.analyst_briefings b
        WHERE b.id = analyst_briefing_findings.briefing_id
          AND b.status = 'published'
          AND b.visibility = 'client'
      )
    )
  );

CREATE POLICY analyst_briefing_findings_admin_insert ON public.analyst_briefing_findings
  FOR INSERT WITH CHECK ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );
CREATE POLICY analyst_briefing_findings_admin_update ON public.analyst_briefing_findings
  FOR UPDATE USING ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' )
             WITH CHECK ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );
CREATE POLICY analyst_briefing_findings_admin_delete ON public.analyst_briefing_findings
  FOR DELETE USING ( (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin' );


-- ─── Drift-prevention trigger ────────────────────────────────────────────
-- Findings.client_id must always equal the parent briefing's client_id.
-- Prevents accidental cross-tenant attribution if a future code path
-- forgets to denormalize correctly. Service-role inserts are still subject
-- to this trigger; RLS bypass does not bypass triggers.

CREATE OR REPLACE FUNCTION public.analyst_briefing_findings_enforce_client_id()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  parent_client uuid;
BEGIN
  SELECT client_id INTO parent_client
    FROM public.analyst_briefings
   WHERE id = NEW.briefing_id;
  IF parent_client IS NULL THEN
    RAISE EXCEPTION 'analyst_briefing_findings: briefing_id % not found', NEW.briefing_id;
  END IF;
  IF NEW.client_id IS DISTINCT FROM parent_client THEN
    RAISE EXCEPTION 'analyst_briefing_findings: client_id (%) must match parent briefing client_id (%)',
      NEW.client_id, parent_client;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS analyst_briefing_findings_client_id_drift
  ON public.analyst_briefing_findings;
CREATE TRIGGER analyst_briefing_findings_client_id_drift
  BEFORE INSERT OR UPDATE OF client_id, briefing_id
  ON public.analyst_briefing_findings
  FOR EACH ROW
  EXECUTE FUNCTION public.analyst_briefing_findings_enforce_client_id();
