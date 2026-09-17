-- Verified public Ashby board on 2026-09-17. Additional boards can be imported in the UI.
CREATE UNIQUE INDEX IF NOT EXISTS sources_kind_value_idx ON sources(kind,value);
INSERT OR IGNORE INTO sources(id,kind,value) VALUES ('seed-linear','ashby','linear');
