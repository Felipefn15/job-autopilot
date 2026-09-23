# Busca ativa por cargo

## Entrega
A migração 0012 adiciona o portal público da Gupy ao catálogo. Cada lote elegível reserva um dos cinco espaços para essa busca entre várias empresas, usando os cargos salvos do perfil e as equivalências já existentes. Não usa o token de API empresarial da Gupy nem exige um novo segredo.

Cada consulta lê até 25 vagas, com descrição, empresa, localização, modalidade e datas informadas pela fonte. Os cargos são alternados a cada execução; cada termo mantém seu próprio offset. Ao terminar os resultados (ou a janela de 1.000), a consulta volta ao início para encontrar novas publicações. Mantidos intervalo de duas horas, timeout, limites de resposta e pausa após erro. Mudanças nas preferências reiniciam o plano de busca.

As vagas válidas continuam no acervo mesmo fora das preferências. Somente as aprovadas na triagem seguem à fila de compatibilidade por IA. País e elegibilidade permanecem sujeitos à avaliação existente. Não foi relaxada a restrição de trabalho remoto nem a exigência de evidências do currículo para candidaturas.

## Contagem
A migração 0011 adicionou gatilhos de normalização. O contador `meta.changes` do D1 passou a incluir alterações auxiliares. A descoberta agora conta exclusivamente os IDs retornados pelo `INSERT ... RETURNING id`, evitando dobrar vagas novas e gerar duplicados negativos. Eventos históricos não foram reescritos.

## Verificação
- 77 testes aprovados, incluindo rotação de cargos, offsets independentes, deduplicação com gatilhos, seleção de fontes e catálogo.
- Build Vite e Wrangler dry-run aprovados.
- Consulta real ao portal em 23/09/2026: `product owner`, limit=2, offset=0. A fonte informou total de 57; os dois itens retornados foram lidos com descrição e modalidade. Não foram importados no banco de produção.
- Endpoint observado: https://employability-portal.gupy.io/api/v1/jobs ; portal: https://portal.gupy.io/vagas . Integração do portal público, sujeita a alterações de formato; falhas são registradas, sem tentar contornar bloqueios.

## Publicação
Na pasta cloud: `npm run db:remote && npm run deploy`, após atualizar o repositório. A fonte é adicionada automaticamente. Executar um lote após conferir os cargos salvos.

Esta entrega amplia a busca brasileira entre empresas. Não representa integração com todo o índice Google Jobs, nem aumenta a cota diária de análise por IA. Quantidade coletada não garante quantidade de recomendações.
