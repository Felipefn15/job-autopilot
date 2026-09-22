ALTER TABLE sources ADD COLUMN audience TEXT NOT NULL DEFAULT 'general';
ALTER TABLE sources ADD COLUMN location_filter TEXT;
UPDATE sources SET audience='software' WHERE kind='github' AND value IN ('frontendbr/vagas','backend-br/vagas','react-brasil/vagas','nodejsdevbr/vagas','pydevbr/vagas','phpdevbr/vagas','dotnetdevbr/vagas','vuejs-br/vagas','qa-brasil/vagas');
UPDATE sources SET audience='software' WHERE kind='telegram' AND value='frontendbrasilvagas';
INSERT OR IGNORE INTO sources(id,kind,value,region,priority,audience,location_filter) VALUES
('br-jobgether','lever','jobgether','BR',1,'general','Brazil'),
('br-bluelight','lever','bluelightconsulting','BR',2,'general',NULL),
('br-ilia','greenhouse','ilia','BR',3,'general',NULL),
('br-linx','greenhouse','linx','BR',4,'general',NULL),
('br-oliver','greenhouse','oliverbrazil','BR',5,'general',NULL),
('br-arco','greenhouse','arcoeducacao','BR',6,'general',NULL);
-- Lever now uses provider-side pagination instead of slicing a full response.
UPDATE sources SET cursor=0 WHERE kind='lever';
