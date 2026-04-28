-- supabase/migrations/create_mri_tables.sql
-- Maya Revenue MRI — diagnostic scan system, backend foundation.
--
-- Additive only. No changes to existing tables.
-- Four new tables: mri_scans (parent), mri_intake / mri_probes / mri_reports (children).
--
-- RLS pattern follows public.conversion_leak_signals:
--   admin role  → sees all (auth.jwt user_metadata.role = 'admin')
--   client      → sees own rows only (matched via mri_scans.client_id)
--   service key → bypasses RLS (used by backend writers)
--
-- Child tables (mri_intake / mri_probes / mri_reports) authorize via the
-- parent mri_scans.client_id rather than carrying client_id directly.

-- Reusable updated_at trigger function (safe to re-create — idempotent).
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ──────────────────────────────────────────────────────────────────
-- A. mri_scans — top-level scan record (one per clinic per scan)
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.mri_scans (
    id                          uuid        NOT NULL DEFAULT gen_random_uuid(),
    client_id                   uuid        NOT NULL REFERENCES clients(id),
    clinic_name                 text        NOT NULL,
    vertical                    text        NOT NULL DEFAULT 'premium_implant_cosmetic_dental',
    status                      text        NOT NULL DEFAULT 'draft',
    maya_score                  numeric,
    revenue_at_risk_monthly     numeric,
    recoverable_monthly         numeric,
    top_leaks                   jsonb       NOT NULL DEFAULT '[]'::jsonb,
    metadata                    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at                  timestamptz NOT NULL DEFAULT now(),
    updated_at                  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT mri_scans_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_mri_scans_client_id ON public.mri_scans (client_id);
CREATE INDEX IF NOT EXISTS idx_mri_scans_status    ON public.mri_scans (status);

DROP TRIGGER IF EXISTS trg_mri_scans_updated_at ON public.mri_scans;
CREATE TRIGGER trg_mri_scans_updated_at
    BEFORE UPDATE ON public.mri_scans
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ──────────────────────────────────────────────────────────────────
-- B. mri_intake — clinic-supplied questionnaire + funnel data
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.mri_intake (
    id                  uuid        NOT NULL DEFAULT gen_random_uuid(),
    scan_id             uuid        NOT NULL REFERENCES public.mri_scans(id) ON DELETE CASCADE,
    questionnaire_json  jsonb       NOT NULL DEFAULT '{}'::jsonb,
    funnel_metrics_json jsonb       NOT NULL DEFAULT '{}'::jsonb,
    uploaded_files_json jsonb       NOT NULL DEFAULT '[]'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT mri_intake_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_mri_intake_scan_id ON public.mri_intake (scan_id);

DROP TRIGGER IF EXISTS trg_mri_intake_updated_at ON public.mri_intake;
CREATE TRIGGER trg_mri_intake_updated_at
    BEFORE UPDATE ON public.mri_intake
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ──────────────────────────────────────────────────────────────────
-- C. mri_probes — per-probe placeholder & execution data
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.mri_probes (
    id                   uuid        NOT NULL DEFAULT gen_random_uuid(),
    scan_id              uuid        NOT NULL REFERENCES public.mri_scans(id) ON DELETE CASCADE,
    probe_type           text        NOT NULL,
    status               text        NOT NULL DEFAULT 'pending',
    persona_json         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    scheduled_at         timestamptz,
    executed_at          timestamptz,
    transcript           text,
    metadata_json        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    rubric_scores_json   jsonb       NOT NULL DEFAULT '{}'::jsonb,
    evidence_quotes_json jsonb       NOT NULL DEFAULT '[]'::jsonb,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT mri_probes_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_mri_probes_scan_id    ON public.mri_probes (scan_id);
CREATE INDEX IF NOT EXISTS idx_mri_probes_probe_type ON public.mri_probes (probe_type);
CREATE INDEX IF NOT EXISTS idx_mri_probes_status     ON public.mri_probes (status);

DROP TRIGGER IF EXISTS trg_mri_probes_updated_at ON public.mri_probes;
CREATE TRIGGER trg_mri_probes_updated_at
    BEFORE UPDATE ON public.mri_probes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ──────────────────────────────────────────────────────────────────
-- D. mri_reports — generated narrative + structured report
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.mri_reports (
    id            uuid        NOT NULL DEFAULT gen_random_uuid(),
    scan_id       uuid        NOT NULL REFERENCES public.mri_scans(id) ON DELETE CASCADE,
    narrative_md  text,
    report_json   jsonb       NOT NULL DEFAULT '{}'::jsonb,
    pdf_url       text,
    version       integer     NOT NULL DEFAULT 1,
    generated_at  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT mri_reports_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_mri_reports_scan_id ON public.mri_reports (scan_id);

DROP TRIGGER IF EXISTS trg_mri_reports_updated_at ON public.mri_reports;
CREATE TRIGGER trg_mri_reports_updated_at
    BEFORE UPDATE ON public.mri_reports
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ──────────────────────────────────────────────────────────────────
-- RLS — admin sees all, client sees own scans (and child rows via scan).
-- Backend writes via service key, which bypasses RLS by design.
-- No anon insert/update/delete policies are created.
-- ──────────────────────────────────────────────────────────────────
ALTER TABLE public.mri_scans   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mri_intake  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mri_probes  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mri_reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY mri_scans_admin_all ON public.mri_scans
    FOR ALL
    USING (((auth.jwt() -> 'user_metadata') ->> 'role') = 'admin');

CREATE POLICY mri_scans_client_own ON public.mri_scans
    FOR ALL
    USING ((client_id)::text = ((auth.jwt() -> 'user_metadata') ->> 'client_id'));

CREATE POLICY mri_intake_admin_all ON public.mri_intake
    FOR ALL
    USING (((auth.jwt() -> 'user_metadata') ->> 'role') = 'admin');

CREATE POLICY mri_intake_client_own ON public.mri_intake
    FOR ALL
    USING (EXISTS (
        SELECT 1 FROM public.mri_scans s
        WHERE s.id = mri_intake.scan_id
          AND (s.client_id)::text = ((auth.jwt() -> 'user_metadata') ->> 'client_id')
    ));

CREATE POLICY mri_probes_admin_all ON public.mri_probes
    FOR ALL
    USING (((auth.jwt() -> 'user_metadata') ->> 'role') = 'admin');

CREATE POLICY mri_probes_client_own ON public.mri_probes
    FOR ALL
    USING (EXISTS (
        SELECT 1 FROM public.mri_scans s
        WHERE s.id = mri_probes.scan_id
          AND (s.client_id)::text = ((auth.jwt() -> 'user_metadata') ->> 'client_id')
    ));

CREATE POLICY mri_reports_admin_all ON public.mri_reports
    FOR ALL
    USING (((auth.jwt() -> 'user_metadata') ->> 'role') = 'admin');

CREATE POLICY mri_reports_client_own ON public.mri_reports
    FOR ALL
    USING (EXISTS (
        SELECT 1 FROM public.mri_scans s
        WHERE s.id = mri_reports.scan_id
          AND (s.client_id)::text = ((auth.jwt() -> 'user_metadata') ->> 'client_id')
    ));
