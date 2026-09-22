# Job Autopilot

Evolução independente e privada do [job-automation-engine](https://github.com/Felipefn15/job-automation-engine).

A aplicação web está em [`cloud/`](cloud/README.md): currículo PDF, revisão do perfil, busca em ATS, análise com evidências, candidaturas por Gmail ou navegador e acompanhamento.

**Estado:** implementação inicial com testes automatizados e build local; publicação e testes reais de envio dependem da conexão da Cloudflare e da configuração das credenciais. Nenhuma candidatura real foi enviada durante o desenvolvimento.

## Hospedagem gratuita

React + Cloudflare Workers Free + D1 + Browser Run. Processamento em lotes limitados, com limites de 30 chamadas de IA e 3 tentativas de candidatura por dia. Não exige Redis, VM ou assinatura paga. A disponibilidade e as cotas gratuitas de IA e navegador continuam sujeitas às contas dos provedores.

O catálogo comporta 2.000 fontes e inclui 82 referências após a migração 0006, com 21 fontes marcadas para prioridade brasileira. Buscas de projetos/agilidade deixam as comunidades especializadas em desenvolvimento fora dos lotes; perfis de desenvolvimento continuam usando essas comunidades. Inclui Greenhouse, Lever, Ashby, GitHub, Telegram público, JobPosting e LinkedIn. Cada lote consulta até cinco fontes (quatro brasileiras e uma global, conforme disponibilidade) e analisa uma vaga. A atividade diferencia vagas recebidas, filtradas por motivo, duplicadas e novas. Não há garantia de vagas novas em cada execução.

A busca autenticada de posts tem duas opções: [navegador na Cloudflare](cloud/LINKEDIN_CLOUD.md), com login manual remoto e sessão criptografada, ou [coletor Chromium local](collector/README.md). O modo Cloudflare permite desligar o computador após conectar, mas precisa de validação real do acesso ao LinkedIn e tem coleta limitada pela cota diária gratuita. Veja o guia para configurar LINKEDIN_SESSION_KEY e publicar. O modo local continua disponível como complemento.

Veja [instalação, publicação, limites e recursos implementados](cloud/README.md).

## Origem e preservação

O código Python original permanece na raiz como referência histórica. Não é executado pela aplicação web. Veja [ORIGIN.md](ORIGIN.md) para o commit de origem e os arquivos pessoais omitidos, e [README_LEGACY.md](README_LEGACY.md) para a documentação antiga.

Esta cópia possui histórico independente; não é um fork vinculado à rede de forks do GitHub.
