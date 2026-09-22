-- The seeded Greenhouse board returned HTTP 404 in production.
-- Keep its history, but stop scheduling requests to an unavailable board.
UPDATE sources SET enabled=0, error='Fonte pausada: endereço Greenhouse retornou HTTP 404. Revise a URL antes de reativar.'
WHERE id='br-linx' AND kind='greenhouse' AND value='linx';
