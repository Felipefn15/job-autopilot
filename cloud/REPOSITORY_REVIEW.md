# Referências para evolução do Job Autopilot

Revisão de código e documentação em 23/09/2026. Implementação própria; nenhum
arquivo dos projetos abaixo foi copiado. As funcionalidades descritas nos READMEs
não constituem comprovação de operação atual em produção.

| Repositório | Evidência inspecionada | Aproveitamento |
|---|---|---|
| [prodigeris/ai-job-hunter](https://github.com/prodigeris/ai-job-hunter) | `scrape/providers/remoteok.py`, `analyze/analyzer.py`, README | Conector de agregador separado da análise, fila de vagas não analisadas. O README só marca Remote OK como disponível. |
| [replyre/job-hunter](https://github.com/replyre/job-hunter) | `core/collector.py`, `sources/remotive.py`, README | Dois caminhos de coleta: agregadores e ATS; perfis configuráveis e estatísticas por fonte. O conector Remotive fixa `software-dev`, restrição que não adotamos. |
| [FranciscoMoretti/jobsparser](https://github.com/FranciscoMoretti/jobsparser) | `jobsparser/src/jobsparser/cli.py`, README | Consultas por termo/localidade, lotes, descrição opcional, tentativas limitadas e deduplicação por URL. É uma CLI Python; não foi integrada como dependência do Worker. |
| [jmopr/job-hunter](https://github.com/jmopr/job-hunter) | `matcher.rb`, `app/views/jobs/show.html.erb`, README | Revisão da vaga antes da candidatura. O matcher contém habilidades fixas; não serve como avaliação genérica para qualquer profissão. Código inspecionado na branch master. |
| [jimmycrisp1/Automated.Job.Hunter](https://github.com/jimmycrisp1/Automated.Job.Hunter) | `scraper.py`, `config_script.py`, `requirements.txt`, README | Variações de cargo em lista e agendamento. O script inspecionado para ao atingir cinco resultados totais e salva apenas títulos, sem URL nem descrição. |

No quinto projeto, o scraper aplica a mesma construção `/jobs?q=...&l=...`
aos dois sites e busca sempre elementos `div`, apesar de a configuração do
LinkedIn indicar `li`. Os parâmetros `KEYWORDS` e `search_element` não são
usados no scraper. O README descreve envio por e-mail, mas o script público
inspecionado somente salva JSON. O arquivo ZIP não foi inspecionado; estas
conclusões se limitam aos arquivos de código publicados separadamente.
Não executamos Selenium nem presumimos funcionamento atual dos seletores.

## Entregue nesta alteração

- Remote OK e Remotive via APIs públicas, sem uma categoria profissional fixa.
- Duas novas fontes globais: 91 referências no total, mantendo 28 brasileiras.
- Coleta dos agregadores no máximo uma vez por 24 horas por fonte, com a mesma
  janela limitada de 300 registros por visita e rotação do cursor.
- Nome da fonte e link para o anúncio no agregador, conforme atribuição exigida.
- Busca do acervo também dentro da descrição.
- Filtros por plataforma de origem e data de inclusão no acervo (24h, 7d, 30d).
  Essa data não é apresentada como data de publicação da vaga.

São fontes de vagas remotas internacionais; não tornam qualquer anúncio elegível
para residentes no Brasil. Restrições geográficas seguem no texto/localização e
na análise. O pré-filtro não substitui a avaliação de elegibilidade.

## Decisões e próximas extensões

O padrão de coleta por consulta do jobsparser é relevante para reduzir o tempo
até encontrar cargos específicos. Não portamos seus scrapers de LinkedIn/Indeed
sem validar interfaces, estabilidade e consumo no Worker. O LinkedIn existente
continua separado e não foi alterado nesta entrega.

Também não copiamos pesos de habilidades, listas de competências pessoais,
promessas de cotas grátis, envio automático de DMs ou remoção definitiva de vagas
após 14 dias. O histórico e a avaliação baseada no currículo são preservados.

Próximas prioridades sugeridas: consultas direcionadas por cargo em provedores
que as suportam, data de publicação explícita, estado de vaga encerrada,
priorização da fila de IA e filtros de área/senioridade baseados em metadados
verificados. Estas prioridades não estão implementadas nesta alteração.

## Fontes primárias das APIs

- https://remoteok.com/api — resposta JSON e requisitos de atribuição.
- https://remotive.com/remote-jobs/api
- https://github.com/remotive-com/remote-jobs-api — campos, categorias opcionais,
  recomendação de até quatro consultas diárias e atraso de 24h nas vagas públicas.

Uso atual: painel privado, sem revenda ou coleta pública de cadastros. Se o produto
passar a distribuir vagas publicamente, reavaliar as condições dos provedores.
Os testes usam respostas simuladas; o primeiro lote após deploy valida o acesso
real destes endpoints a partir do Cloudflare.
