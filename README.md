# Job Autopilot

Evolução independente e privada do [job-automation-engine](https://github.com/Felipefn15/job-automation-engine).

A aplicação web está em [`cloud/`](cloud/README.md): currículo PDF, revisão do perfil, busca em ATS, análise com evidências, candidaturas por Gmail ou navegador e acompanhamento.

**Estado:** implementação inicial com testes automatizados e build local; publicação e testes reais de envio dependem da conexão da Cloudflare e da configuração das credenciais. Nenhuma candidatura real foi enviada durante o desenvolvimento.

## Hospedagem gratuita

React + Cloudflare Workers Free + D1 + Browser Run. Processamento em lotes limitados, com limites de 30 chamadas de IA e 3 tentativas de candidatura por dia. Não exige Redis, VM ou assinatura paga. A disponibilidade e as cotas gratuitas de IA e navegador continuam sujeitas às contas dos provedores.

O catálogo comporta 2.000 fontes e inclui 76 referências após a migração 0004, com 15 fontes brasileiras priorizadas por padrão. Inclui Greenhouse, Lever, Ashby, comunidades de vagas no GitHub, canal público do Telegram, JobPosting e posts do LinkedIn. Cada lote consulta até cinco fontes (quatro brasileiras e uma global, conforme disponibilidade) e analisa uma vaga; no agendamento padrão são até 60 consultas de fontes por dia. A atividade diferencia vagas recebidas, filtradas, duplicadas e novas. Não há garantia de vagas novas em cada execução.

A busca autenticada de posts do LinkedIn usa o [coletor Chromium local](collector/README.md), com perfil persistente no seu computador e integração ao painel. Para manter a busca periódica, o computador precisa permanecer ligado e o coletor aberto. Cookies e senha não são enviados à nuvem. Atualize o banco e o Worker antes de usar: em `cloud/`, execute `npm run db:remote` e `npm run deploy`.

Veja [instalação, publicação, limites e recursos implementados](cloud/README.md).

## Origem e preservação

O código Python original permanece na raiz como referência histórica. Não é executado pela aplicação web. Veja [ORIGIN.md](ORIGIN.md) para o commit de origem e os arquivos pessoais omitidos, e [README_LEGACY.md](README_LEGACY.md) para a documentação antiga.

Esta cópia possui histórico independente; não é um fork vinculado à rede de forks do GitHub.
