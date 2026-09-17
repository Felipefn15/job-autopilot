CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
INSERT OR IGNORE INTO settings VALUES (1,'{"country":"global","remoteOnly":true,"minScore":80,"autoApply":false,"enabled":false,"keywords":"React, Node.js","dailyApplications":3,"facts":{}}');
CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, filename TEXT NOT NULL, pdf TEXT NOT NULL, data TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, kind TEXT NOT NULL, value TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, checked_at TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, source_id TEXT, title TEXT NOT NULL, company TEXT NOT NULL, location TEXT NOT NULL, url TEXT NOT NULL UNIQUE, description TEXT NOT NULL, email TEXT, language TEXT, status TEXT NOT NULL DEFAULT 'discovered', score INTEGER, analysis TEXT, draft TEXT, profile_id TEXT, proof TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status,updated_at);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, kind TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS usage (day TEXT NOT NULL, kind TEXT NOT NULL, count INTEGER NOT NULL, PRIMARY KEY(day,kind));
CREATE TABLE IF NOT EXISTS locks (name TEXT PRIMARY KEY, token TEXT NOT NULL, expires INTEGER NOT NULL);
