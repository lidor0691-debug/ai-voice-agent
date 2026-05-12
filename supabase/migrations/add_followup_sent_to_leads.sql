-- Idempotency markers for post-call WhatsApp template follow-ups.
-- Set by POST /followup/mark-sent after Make confirms Twilio template send succeeded.
ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS followup_sent_at  timestamptz,
    ADD COLUMN IF NOT EXISTS followup_sent_kind text;

CREATE INDEX IF NOT EXISTS idx_leads_followup_sent_at
    ON leads (followup_sent_at)
    WHERE followup_sent_at IS NOT NULL;
