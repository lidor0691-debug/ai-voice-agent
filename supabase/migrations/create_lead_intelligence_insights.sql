-- supabase/migrations/create_lead_intelligence_insights.sql
-- Lead Intelligence System — initial schema
-- RLS NOTE: This table uses client_id for tenant scoping.
-- Before any non-service-key or direct dashboard DB access is introduced,
-- add ENABLE ROW LEVEL SECURITY and a policy based on the actual
-- user→client ownership model in the project at that time.
-- Do NOT assume client_id = auth.uid().

-- Reusable updated_at trigger function (create only if not already defined)
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS public.lead_intelligence_insights (
    id                uuid        NOT NULL DEFAULT gen_random_uuid(),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    client_id         uuid        NOT NULL REFERENCES clients(id),
    agent_id          text,
    source_type       text        NOT NULL,
    source_record_id  text,
    insight_type      text        NOT NULL,
    title             text        NOT NULL,
    normalized_text   text        NOT NULL,
    original_text     text        NOT NULL,
    intent_category   text,
    frequency_count   int         NOT NULL DEFAULT 1,
    status            text        NOT NULL DEFAULT 'new',
    metadata          jsonb,

    CONSTRAINT lead_intelligence_insights_pkey PRIMARY KEY (id),
    CONSTRAINT chk_source_type   CHECK (source_type  IN ('whatsapp', 'call', 'chat')),
    CONSTRAINT chk_insight_type  CHECK (insight_type IN ('question', 'objection', 'topic', 'faq_candidate', 'intent_signal', 'content_opportunity')),
    CONSTRAINT chk_status        CHECK (status       IN ('new', 'reviewed', 'dismissed')),
    CONSTRAINT chk_frequency     CHECK (frequency_count > 0),
    CONSTRAINT uq_dedup          UNIQUE (client_id, insight_type, normalized_text)
);

CREATE INDEX IF NOT EXISTS idx_lii_client_id
    ON public.lead_intelligence_insights (client_id);

CREATE INDEX IF NOT EXISTS idx_lii_client_insight_type
    ON public.lead_intelligence_insights (client_id, insight_type);

DROP TRIGGER IF EXISTS trg_lii_updated_at ON public.lead_intelligence_insights;
CREATE TRIGGER trg_lii_updated_at
    BEFORE UPDATE ON public.lead_intelligence_insights
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
