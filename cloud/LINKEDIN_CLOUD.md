# LinkedIn autenticado na Cloudflare

Implementação de navegador remoto com Playwright, Live View e um Durable Object SQLite para coordenar a sessão. Não depende do coletor Python ou de um computador ligado após a conexão. A disponibilidade real do LinkedIn nesse ambiente ainda precisa ser validada pela conta do proprietário. Não há garantia de equivalência de volume, estabilidade ou resultados com o Chromium local.

## Publicar

Na pasta `cloud`, após atualizar o repositório:

```bash
git pull --ff-only
```

Crie a chave de criptografia **somente na primeira configuração**. O comando gera uma chave aleatória e a envia diretamente ao Wrangler; não a copie para o chat ou para arquivos do projeto:

```bash
openssl rand -hex 32 | npx wrangler secret put LINKEDIN_SESSION_KEY
npm run deploy
```

Não é necessária uma chave de API adicional da Cloudflare: o acesso ao navegador usa o binding BROWSER existente. O deploy cria o binding LINKEDIN_CLOUD e aplica a migração `v1-linkedin-cloud` do Durable Object. Não há uma nova migração D1 nesta alteração. As chaves existentes de Gemini, Groq e APP_TOKEN continuam sendo utilizadas.

Trocar LINKEDIN_SESSION_KEY invalida a sessão salva: use “Desconectar e apagar sessão” e conecte novamente. A configuração utiliza Durable Objects SQLite, disponível no Workers Free; não habilita plano pago.

## Prova de funcionamento

1. Recarregue o painel e abra **Fontes → LinkedIn na Cloudflare**.
2. Clique em **Conectar LinkedIn** e depois no link **Abrir navegador remoto**.
3. Faça login diretamente no LinkedIn pelo navegador remoto. A sessão temporária dura até três minutos, contando a abertura. Não deixe essa janela abandonada.
4. Quando o feed estiver aberto, volte ao painel e clique em **Já entrei — salvar sessão**. A conexão é salva criptografada e o navegador fecha.
5. Clique em **Testar busca na nuvem**. O servidor abre um NOVO navegador, restaura a sessão e busca posts com os termos do currículo e os filtros atuais.
6. Confira **Atividade**. O estado “Busca validada em uma nova sessão” exige posts legíveis; sessão salva sozinha não confirma que a restauração funcionou. Zero vagas novas pode significar posts duplicados ou filtrados, mesmo com uma extração bem-sucedida.
7. Só depois de um teste bem-sucedido, o botão **Ativar busca automática após teste** fica disponível. O agendamento geral em Preferências também precisa estar ativado.

Se atualizar a página durante o login e perder o link temporário, cancele a sessão e conecte novamente. Isso consome outra reserva da cota. Links Live View dão acesso à sessão: não os compartilhe.

## Coleta e limites

- Um grupo de até três tecnologias por execução; as primeiras 18 tecnologias alternam entre execuções.
- Busca interna de conteúdo no LinkedIn ordenada por data, usando país/LATAM/Mundo e remoto quando selecionado.
- Até 20 posts legíveis, quatro rolagens e 45 segundos por coleta. Deduplicação por URL canônica; análise posterior por Gemini/Groq no fluxo existente.
- Cota conservadora de **540 segundos reservados por dia UTC**, compartilhada com candidaturas via navegador. Cada login reserva 240 segundos (180 ativos + 60 de margem), coleta 105 segundos (45 + 60) e candidatura 150 segundos (90 + 60). Não há devolução de reservas por encerramento antecipado. Execuções anteriores de candidatura no dia de atualização também entram conservadoramente no cálculo.
- Um alarme persistente encerra sessões de login abandonadas; a coleta também possui temporizador de encerramento. O navegador tem timeout de inatividade de 60 segundos. Falhas da infraestrutura e outros aplicativos na conta podem consumir a cota do provedor; a contagem interna não substitui a medição da Cloudflare.
- Execuções que poderiam atravessar a meia-noite UTC não são iniciadas. O cron atual é a cada duas horas; esgotar a reserva diária faz as próximas buscas agendadas serem ignoradas até haver orçamento.
- Login expirado, verificação, erro ou nenhum post legível pausam a busca automática do LinkedIn. As outras fontes continuam disponíveis. Não há resolução automática de CAPTCHA ou disfarce de automação.

O teste não envia candidaturas nem mensagens pelo LinkedIn. Posts entram no fluxo normal de análise; eventual candidatura continua dependendo das configurações já existentes do painel. Posts sem e-mail de candidatura verificado ainda exigem acompanhamento manual do link.

## Dados e validação

A senha é digitada pelo usuário na página do LinkedIn no Live View. O backend persiste o estado de autenticação do navegador com AES-256-GCM e IV aleatório; a chave fica em um Worker Secret separado do APP_TOKEN. Estado descriptografado existe somente na memória durante uso. Endpoints públicos continuam exigindo APP_TOKEN. Status, eventos e erros não retornam cookies, credenciais de depuração ou estado de autenticação. O link temporário aparece somente na resposta autenticada de início de login.

“Desconectar e apagar sessão” remove o estado persistido no aplicativo, encerra o navegador conhecido e desativa a coleta automática. Não revoga outras sessões da conta LinkedIn. PDFs e vagas já salvos permanecem no D1.

Testes automatizados cobrem criptografia/tampering, orçamento compartilhado, rotação de buscas e ciclo de login/confirmar/restaurar/encerrar usando transporte de navegador simulado. Build e dry-run verificam o empacotamento. Eles não comprovam acesso real ao LinkedIn, compatibilidade dos seletores atuais, Live View em produção ou ausência de bloqueio.

Referências oficiais consultadas:
- https://developers.cloudflare.com/browser-run/features/live-view/
- https://developers.cloudflare.com/browser-run/playwright/
- https://developers.cloudflare.com/browser-run/limits/
- https://developers.cloudflare.com/browser-run/faq/
- https://developers.cloudflare.com/durable-objects/platform/pricing/
