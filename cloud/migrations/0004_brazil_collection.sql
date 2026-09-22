ALTER TABLE sources ADD COLUMN region TEXT NOT NULL DEFAULT 'global';
ALTER TABLE sources ADD COLUMN priority INTEGER NOT NULL DEFAULT 50;
ALTER TABLE sources ADD COLUMN cursor INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sources ADD COLUMN last_stats TEXT;
ALTER TABLE sources ADD COLUMN retry_after TEXT;
UPDATE sources SET region='BR',priority=20 WHERE (kind='greenhouse' AND value IN ('nubank','quintoandar','gympass','stone')) OR (kind='lever' AND value='ciandt');
INSERT OR IGNORE INTO sources(id,kind,value,region,priority) VALUES
('br-frontend','github','frontendbr/vagas','BR',1),
('br-backend','github','backend-br/vagas','BR',2),
('br-react','github','react-brasil/vagas','BR',3),
('br-node','github','nodejsdevbr/vagas','BR',4),
('br-python','github','pydevbr/vagas','BR',5),
('br-php','github','phpdevbr/vagas','BR',6),
('br-dotnet','github','dotnetdevbr/vagas','BR',7),
('br-vue','github','vuejs-br/vagas','BR',8),
('br-qa','github','qa-brasil/vagas','BR',9),
('br-telegram-frontend','telegram','frontendbrasilvagas','BR',10);
