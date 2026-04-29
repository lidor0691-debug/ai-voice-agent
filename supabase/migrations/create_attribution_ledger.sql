-- supabase/migrations/create_attribution_ledger.sql
-- Attribution Ledger v0 — Phase 2a spear tip.
--
-- Three additive tables + one trigger on public.leads.
--
-- Design constraints (v0):
--   * WhatsApp actions only (channel='whatsapp'); voice deferred.
--   * Single outcome type ('booked'); other transitions deferred.
--   * Single-touch attribution; multi-touch deferred.
--   * No RLS; service-key writes only. Earns RLS when dashboard reads these.
--   * No economic literal in this migration. The trigger creates the outcome
--     as a pure state-change fact. Economic value is assigned by the batch
--     worker from a constant in app/services/attribution.py — single source
--     of truth.
--
-- Not in v0: recovered_amount column on outcomes (would have no writer),
-- intent / source_ref / action_type / proof_source / attribution_model
-- columns (each had exactly one possible value), attribution_config table
-- (hardcoded constant in worker), per-client window override.

-- ──────────────────────────────────────────────────────────────────
-- A. attribution_actions — every Maya-originated outbound interaction
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.attribution_actions (
    id          uuid        NOT NULL DEFAULT gen_random_uuid(),
    client_id   uuid        NOT NULL REFERENCES public.clients(id),
    lead_id     uuid        NOT NULL REFERENCES public.leads(id) ON DELETE CASCADE,
    channel     text        NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT attribution_actions_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_attr_actions_lead_occurred
    ON public.attribution_actions (lead_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_attr_actions_client_occurred
    ON public.attribution_actions (client_id, occurred_at DESC);

-- ──────────────────────────────────────────────────────────────────
-- B. attribution_outcomes — revenue-relevant lead state transitions
-- ──────────────────────────────────────────────────────────────────
-- NOTE: no recovered_amount column. v0 single-touch puts value on the
-- edge only (attribution_edges.attributed_amount). When multi-touch
-- arrives in v1, add recovered_amount here as the intrinsic outcome value.
CREATE TABLE IF NOT EXISTS public.attribution_outcomes (
    id           uuid        NOT NULL DEFAULT gen_random_uuid(),
    client_id    uuid        NOT NULL REFERENCES public.clients(id),
    lead_id      uuid        NOT NULL REFERENCES public.leads(id) ON DELETE CASCADE,
    outcome_type text        NOT NULL,
    occurred_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT attribution_outcomes_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_attr_outcomes_client_occurred
    ON public.attribution_outcomes (client_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_attr_outcomes_lead
    ON public.attribution_outcomes (lead_id);

-- ──────────────────────────────────────────────────────────────────
-- C. attribution_edges — the link between an action and an outcome
-- ──────────────────────────────────────────────────────────────────
-- One edge per outcome in v0 (single-touch). action_id NULL means the
-- worker found no Maya action in the attribution window — recorded
-- explicitly so unattributed bookings are queryable as such.
CREATE TABLE IF NOT EXISTS public.attribution_edges (
    id                 uuid        NOT NULL DEFAULT gen_random_uuid(),
    outcome_id         uuid        NOT NULL REFERENCES public.attribution_outcomes(id) ON DELETE CASCADE,
    action_id          uuid        REFERENCES public.attribution_actions(id) ON DELETE SET NULL,
    client_id          uuid        NOT NULL REFERENCES public.clients(id),
    attributed_amount  numeric     NOT NULL DEFAULT 0,
    created_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT attribution_edges_pkey PRIMARY KEY (id),
    CONSTRAINT uq_attr_edges_outcome UNIQUE (outcome_id)
);

CREATE INDEX IF NOT EXISTS idx_attr_edges_client_created
    ON public.attribution_edges (client_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_attr_edges_action
    ON public.attribution_edges (action_id);

-- ──────────────────────────────────────────────────────────────────
-- D. Trigger on public.leads — booked transition writes an outcome
-- ──────────────────────────────────────────────────────────────────
-- Pure state-change detection. No economic value. Skips silently if
-- lead has no client_id (orphan leads cannot be attributed).
CREATE OR REPLACE FUNCTION public.attribution_on_lead_booked()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.client_id IS NOT NULL
       AND NEW.status = 'booked'
       AND (OLD.status IS DISTINCT FROM 'booked')
    THEN
        INSERT INTO public.attribution_outcomes (client_id, lead_id, outcome_type)
        VALUES (NEW.client_id, NEW.id, 'booked');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_attribution_on_lead_booked ON public.leads;
CREATE TRIGGER trg_attribution_on_lead_booked
    AFTER UPDATE OF status ON public.leads
    FOR EACH ROW EXECUTE FUNCTION public.attribution_on_lead_booked();
