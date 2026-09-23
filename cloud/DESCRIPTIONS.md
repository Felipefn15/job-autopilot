# Descrições e recuperação da análise

As descrições já obtidas pelos conectores ATS, páginas JobPosting e coletores
de posts são exibidas como texto escapado, sem executar HTML da fonte.
O catálogo mostra um trecho de 240 caracteres; “Ver descrição” busca o texto
armazenado através de uma rota autenticada. A visão geral também mostra esse
texto no painel de detalhes. O limite de armazenamento existente é 20.000
caracteres por vaga; a fonte original permanece acessível pelo link.

Não há nova requisição ao site da empresa a cada abertura de descrição.
Isso evita gastos e bloqueios desnecessários quando o conteúdo já foi coletado.

O fallback Gemini → Groq agora cobre HTTP 429, 500, 502, 503, 504 e timeout.
Cada tentativa reserva uma unidade do orçamento diário. Há no máximo uma
tentativa por provedor, com 25 segundos por tentativa. Erros de credencial ou
respostas inválidas não acionam fallback. Se ambos falharem, a vaga permanece
na fila; o próximo lote poderá tentar novamente. Não há promessa de sucesso
quando os provedores estão indisponíveis.
