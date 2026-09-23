# Acervo e recomendações

A migração 0008 acrescenta sete empresas com operações no Brasil pelo conector
SmartRecruiters: Bosch, SGS, Louis Dreyfus Company, Continental, AccorHotel,
Eurofins e Syngenta Group. O catálogo passa a 89 referências (28 brasileiras),
incluindo a referência Linx pausada. Referências não são vagas verificadas.

Todas as vagas válidas coletadas passam a ser persistidas, inclusive quando não
atendem ao perfil. A triagem registra o motivo e separa a fila de análise; ela
não elimina mais essas vagas. URLs repetidas não duplicam o acervo. Anúncios sem
título, URL pública válida ou descrição mínima continuam sendo rejeitados.

“Todas as vagas” consulta o banco inteiro com busca por cargo, empresa e local,
50 resultados por página. “Recomendadas pela IA” exige análise, nota mínima
configurada e status elegível para acompanhamento, ordenando pela nota.
Vagas com pendências continuam identificadas; uma nota não autoriza envio.
Os contadores da visão geral usam o banco inteiro.

As preferências atuais, incluindo trabalho remoto, continuam valendo para a
triagem e candidaturas, mas não restringem a navegação pelo acervo. Assim, uma
vaga presencial de enfermagem fica disponível no acervo mesmo com um perfil de
gestão remota ativo. Não inferimos registro profissional ou experiência.

O conector usa a API pública documentada de postagens, com filtro de país `br`
nas sete fontes semeadas. Cada visita coleta até cinco descrições completas e
avança o cursor, sem credenciais adicionais. Há até cinco fontes por lote; a
fila de IA continua limitada a uma avaliação por execução e ao orçamento diário.
Isso amplia cobertura gradualmente, sem prometer milhares de vagas novas em
cada execução. A cobertura de saúde ainda não equivale a um catálogo hospitalar
completo. URLs de outras empresas SmartRecruiters podem ser importadas no painel.

Vagas descartadas antes desta versão não existem no banco: serão recuperadas
nas próximas visitas às fontes, caso continuem publicadas. O acervo é histórico;
uma vaga coletada não tem garantia de permanecer aberta no site de origem.

## Referências primárias consultadas em 23/09/2026

- API: https://developers.smartrecruiters.com/docs/endpoints
- Bosch, engenharia: https://jobs.smartrecruiters.com/BoschGroup/744000129728407-engenheiro-de-projetos-sr-34677-34678-34679-36680-36681-
- SGS, engenharia: https://jobs.smartrecruiters.com/SGS/744000126753150-engenheiro-de-seguranca-do-trabalho-
- LDC, enfermagem: https://jobs.smartrecruiters.com/LouisDreyfusCompany/744000137197819-enfermeiro-a-do-trabalho
- Continental, compras: https://jobs.smartrecruiters.com/Continental/744000133105657-estagio-em-compras
- Accor, administração: https://jobs.smartrecruiters.com/AccorHotel/744000128596179-assistente-administrativo-
- Eurofins, ciências agrárias: https://jobs.smartrecruiters.com/Eurofins/744000081089392-pesquisador-junior-em-ciencias-agrarias-
- Syngenta, finanças: https://jobs.smartrecruiters.com/SyngentaGroup/744000121370702-manager-atr

Validação local: SQLite com todas as migrações, persistência de vagas filtradas,
deduplicação, paginação e ordenação das recomendações; transporte simulado para
o novo conector. O acesso real à API a partir do Worker será verificado no lote
após o deploy.
