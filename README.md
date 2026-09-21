# Job Autopilot

Evolução independente e privada do [job-automation-engine](https://github.com/Felipefn15/job-automation-engine).

A aplicação web está em [`cloud/`](cloud/README.md): currículo PDF, revisão do perfil, busca em ATS, análise com evidências, candidaturas por Gmail ou navegador e acompanhamento.

**Estado:** implementação inicial com testes automatizados e build local; publicação e testes reais de envio dependem da conexão da Cloudflare e da configuração das credenciais. Nenhuma candidatura real foi enviada durante o desenvolvimento.

## Hospedagem gratuita

React + Cloudflare Workers Free + D1 + Browser Run. Processamento em lotes limitados, com limites de 30 chamadas de IA e 3 tentativas de candidatura por dia. Não exige Redis, VM ou assinatura paga. A disponibilidade e as cotas gratuitas de IA e navegador continuam sujeitas às contas dos provedores.

O catálogo comporta 2.000 fontes e inclui 66 referências iniciais de carreira, instaladas pela migração 0003. Inclui conectores Greenhouse, Lever e Ashby, importação de fontes, leitura de JobPosting e importação de posts públicos do LinkedIn por URL ou texto colado. Cada lote consulta até cinco fontes e analisa uma vaga; no agendamento padrão são até 60 consultas de fontes por dia. Não há descoberta universal da internet nem busca automática no feed do LinkedIn. Disponibilidade das APIs e vagas são verificadas durante as consultas.

Veja [instalação, publicação, limites e recursos implementados](cloud/README.md).

## Origem e preservação

O código Python original permanece na raiz como referência histórica. Não é executado pela aplicação web. Veja [ORIGIN.md](ORIGIN.md) para o commit de origem e os arquivos pessoais omitidos, e [README_LEGACY.md](README_LEGACY.md) para a documentação antiga.

Esta cópia possui histórico independente; não é um fork vinculado à rede de forks do GitHub.
