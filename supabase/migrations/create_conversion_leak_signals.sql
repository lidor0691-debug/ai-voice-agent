-- Maya's Daily Priorities — Conversion Leak Signals
-- Stores detected conversion leaks for the Action Queue.
-- Each signal = one lead + one leak type + one day (deduplicated).

CREATE TABLE IF NOT EXISTS public.conversion_leak_signals (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    client_id       uuid        NOT NULL REFERENCES clients(id),
    lead_id         uuid        NOT NULL,
    lead_phone      text        NOT NULL,
    lead_name       text,

    signal_type     text        NOT NULL,
    detail          jsonb       NOT NULL DEFAULT '{}',
    suggested_action text,

    status          text        NOT NULL DEFAULT 'open',
    acted_at        timestamptz,

    scan_date       date        NOT NULL DEFAULT CURRENT_DATE,

    CONSTRAINT conversion_leak_signals_pkey PRIMARY KEY (id),
    CONSTRAINT chk_signal_type CHECK (signal_type IN (
        'noshow_not_reactivated',
        'conversation_drop',
        'high_intent_no_booking'
    )),
    CONSTRAINT chk_status CHECK (status IN ('open', 'acted', 'dismissed', 'resolved')),
    CONSTRAINT uq_signal_per_day UNIQUE (client_id, lead_id, signal_type, scan_date)
);

CREATE INDEX IF NOT EXISTS idx_cls_client_status
    ON public.conversion_leak_signals (client_id, status);

CREATE INDEX IF NOT EXISTS idx_cls_client_open
    ON public.conversion_leak_signals (client_id)
    WHERE status = 'open';

DROP TRIGGER IF EXISTS trg_cls_updated_at ON public.conversion_leak_signals;
CREATE TRIGGER trg_cls_updated_at
    BEFORE UPDATE ON public.conversion_leak_signals
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
