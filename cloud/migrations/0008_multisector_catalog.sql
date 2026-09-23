CREATE INDEX IF NOT EXISTS jobs_catalog_date ON jobs(created_at DESC,id);
CREATE INDEX IF NOT EXISTS jobs_catalog_score ON jobs(score DESC,created_at DESC);
INSERT OR IGNORE INTO sources(id,kind,value,region,priority,audience,location_filter) VALUES
('br-sr-bosch','smartrecruiters','BoschGroup','BR',1,'general','br'),
('br-sr-sgs','smartrecruiters','SGS','BR',2,'general','br'),
('br-sr-ldc','smartrecruiters','LouisDreyfusCompany','BR',3,'general','br'),
('br-sr-continental','smartrecruiters','Continental','BR',4,'general','br'),
('br-sr-accor','smartrecruiters','AccorHotel','BR',5,'general','br'),
('br-sr-eurofins','smartrecruiters','Eurofins','BR',6,'general','br'),
('br-sr-syngenta','smartrecruiters','SyngentaGroup','BR',7,'general','br');
