ALTER TABLE jobs ADD COLUMN triage_key TEXT;
CREATE INDEX IF NOT EXISTS jobs_triage_idx ON jobs(status,triage_key);
