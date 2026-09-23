# Filtros e sugestões de busca

## Alterações
- Busca no acervo por palavras combinadas, sem distinção de acentos; Brasil/Brazil e remoto/remote são equivalentes.
- Área e senioridade de registros antigos sem metadados são calculadas pelo título na consulta. Não é necessário aguardar novos lotes para que apareçam nos filtros.
- O catálogo inicia com os cargos salvos do perfil confirmado, combinados por OU e com equivalências conhecidas. O controle “Cargos do meu perfil” e “Limpar filtros” permitem consultar todo o acervo. Essa seleção não implica compatibilidade pela IA nem substitui os critérios de candidatura.
- A confirmação de novos currículos preenche cargos vazios com títulos extraídos e comprovados no texto; preserva cargos já salvos. Competências vazias ou o exemplo inicial React/Node são preenchidos no primeiro currículo. Preferências existentes não são sobrescritas.
- “Refinar cargos com IA” usa o currículo confirmado, com Gemini/Groq e a cota diária existentes. Sugestões sem citação real contendo o título são rejeitadas. O usuário revisa os campos e salva antes de alterar a coleta.
- Cargos aceitos alimentam a busca dirigida nas fontes que suportam consultas, LinkedIn, triagem e priorização existentes. Equivalências adicionadas para enfermagem, sistemas, engenharia civil/mecânica, finanças e RH.

## Atualização
Aplicar `npm run db:remote` antes de `npm run deploy`. A migração 0011 normaliza o texto já armazenado e mantém a coluna sincronizada com gatilhos de inserção/alteração, evitando repetir a normalização de descrições inteiras a cada consulta.

## Verificação e limites
Suíte de 74 testes aprovada; após a otimização de armazenamento, 20 testes de catálogo, sugestões e LinkedIn aprovados novamente. Build e empacotamento Wrangler validados. Não houve deploy de produção nem teste autenticado no navegador nesta sessão.

Classificação de área/nível permanece baseada no título; não é classificação semântica por IA. Nenhuma restrição de país, modalidade, senioridade ou autorização de trabalho é inferida do currículo. As sugestões não ampliam a quantidade de fontes nem garantem resultados em toda execução.
