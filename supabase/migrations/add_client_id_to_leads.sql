ALTER TABLE leads ADD COLUMN IF NOT EXISTS client_id uuid REFERENCES clients(id);
CREATE INDEX IF NOT EXISTS idx_leads_client_id ON leads(client_id);
