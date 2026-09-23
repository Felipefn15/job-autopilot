# Busca direcionada, fila de IA e disponibilidade

Implementação da migração 0010. Aplicar antes do deploy.

## Busca por cargo

Remotive usa `search`; SmartRecruiters usa `q`. Os cargos salvos e seus aliases
PT/EN existentes geram até 18 termos em rodízio. Cada visita alterna uma busca
direcionada com uma coleta geral. Os cursores da busca e do catálogo geral são
independentes; mudar os cargos reinicia o cursor de busca. Sem cargos, mantém-se
a coleta geral. O log registra o termo consultado.

Remotive mantém uma consulta por 24 horas. SmartRecruiters mantém cinco detalhes
por visita. Demais provedores continuam com seus conectores existentes: não foram
inventados parâmetros de busca em APIs que não oferecem esse recurso.

## Fila de análise

São considerados até 100 candidatos mais antigos que passaram na triagem atual,
estão disponíveis e não aguardam intervalo de nova tentativa. A seleção combina
correspondência do cargo com tempo de espera; tentativas anteriores reduzem a
prioridade. A prioridade é interna e não é apresentada como nota da IA.

Após falha, a vaga aguarda uma hora; da terceira falha em diante, 24 horas.
Outras vagas podem avançar nesse intervalo. Continua uma análise por execução,
com o mesmo limite diário de chamadas. Vagas com prazo vencido ou não listadas
ficam fora da análise e da candidatura automática.

## Área, senioridade e datas

O painel filtra área e senioridade identificadas pelo título. São heurísticas
explícitas, não dados certificados pelo empregador nem avaliação da IA.
Títulos sem indicação de nível ficam como “Não identificada”. Não inferimos
senioridade por idade ou características pessoais. Novas vagas recebem a
classificação ao serem coletadas; até 200 antigas são classificadas por lote.

Datas de publicação são guardadas apenas quando fornecidas pela fonte:
Greenhouse, Ashby, SmartRecruiters, agregadores e JobPosting estruturado.
Data de inclusão no acervo continua separada da data de publicação.

## Disponibilidade

- **Vista na fonte:** registro observado durante coleta bem-sucedida.
- **Não listada na fonte:** ausente de resposta completa e não vazia de
  Greenhouse/Ashby, antes de aplicar a janela local. Isso não prova contratação
  ou encerramento definitivo. Uma nova observação pode reabrir o registro.
- **Prazo encerrado:** `validThrough` informado pelo JobPosting já venceu.
- **Não verificada:** registros antigos ainda não revisitados.

Falhas de rede, respostas vazias, páginas parciais ou buscas por cargo não são
usadas como evidência de encerramento. Fontes sem validade explícita ou catálogo
completo não recebem um encerramento automático por suposição. O histórico de
candidaturas é preservado; apenas a disponibilidade muda.

## Validação e limites

Testes SQLite e transporte simulado cobrem persistência, filtros, expiração,
reabertura, rodízio de consultas, cursor independente, prioridade e intervalo de
tentativas. A consulta real em produção depende do deploy e do próximo lote.
Não houve envio de candidatura nem login externo durante a implementação.

Referências de API:
- https://developers.smartrecruiters.com/docs/endpoints
- https://github.com/remotive-com/remote-jobs-api
- https://developers.ashbyhq.com/docs/public-job-posting-api
- https://docs.greenhouse.io/job-board.html
