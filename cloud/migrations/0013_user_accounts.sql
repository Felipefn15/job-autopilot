-- Account directory only. Private job workflows live in one SQLite Durable Object per user.
CREATE TABLE auth_users (
 id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 password_hash TEXT NOT NULL, recovery_hash TEXT NOT NULL, auth_version INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 schedule_enabled INTEGER NOT NULL DEFAULT 0,
 last_scheduled TEXT
);
CREATE TABLE auth_sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
 expires INTEGER NOT NULL, auth_version INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX auth_session_user ON auth_sessions(user_id);
CREATE TABLE auth_limits (key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL);
