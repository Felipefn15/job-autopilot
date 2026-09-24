# Contas de usuário

## Acesso e fluxo
A página inicial oferece cadastro por nome, e-mail e senha, login e recuperação por código. Depois do cadastro, o usuário recebe um código de recuperação de uso único e segue para envio do currículo, confirmação dos dados e preferências. Uma nova conta começa sem currículo e sem os termos de exemplo React/Node. A ação principal passa a ser “Buscar vagas”.

“Minha conta” permite alterar a senha. Alteração ou recuperação revogam todas as sessões anteriores e geram novo código. Não há envio de recuperação por e-mail nem verificação do endereço de e-mail nesta versão. O código deve ser guardado pelo usuário. O cadastro não prova que o usuário é dono do endereço informado.

## Isolamento
O D1 existente guarda somente o diretório de contas, hashes das senhas, hashes dos códigos e sessões revogáveis, além dos dados legados. Cada conta tem seu próprio `UserWorkspace`, um Durable Object com SQLite separado para currículo/PDF, preferências, catálogo, análise, candidaturas, atividade, cotas locais e sessão criptografada do LinkedIn. O Worker escolhe o objeto a partir da sessão autenticada; cabeçalhos e IDs enviados pelo cliente não definem o proprietário.

As migrações funcionais existentes são empacotadas por `cloud/scripts/workspace-schema.mjs` e aplicadas em cada área individual. A migração de autenticação 0013 fica somente no D1 central. Novas migrações de autenticação devem ser explicitamente excluídas desse empacotamento. `npm run build` e `npm test` atualizam o arquivo gerado. Não editar `workspace-schema.js` diretamente.

As chaves Gemini/Groq e a infraestrutura Browser Run pertencem à instalação; as cotas existentes continuam sendo um teto global compartilhado, além das contagens por conta. Não há multiplicação de franquia gratuita por usuário. O cron visita até três contas com agendamento habilitado por execução, em rodízio. Para maior volume, esse processamento precisará ser dimensionado.

Credenciais Gmail do proprietário não são repassadas às contas novas. O fluxo de busca, análise e candidatura pelo navegador continua disponível conforme os requisitos existentes; envio automatizado por e-mail em contas individuais exige uma futura conexão de e-mail por usuário. A interface informa a indisponibilidade do envio por e-mail.

## Autenticação
- Cookie `__Host-job_session`, HttpOnly, Secure, SameSite=Strict, validade absoluta de sete dias.
- Sessões aleatórias de 256 bits; somente hashes são armazenados.
- PBKDF2-SHA256 com sal aleatório e 100.000 iterações, compatível com o limite do runtime Workers. Não há senhas em texto puro nem token de sessão no localStorage.
- Limite de tentativas por IP e e-mail; escritas autenticadas por cookie exigem mesma origem e cabeçalho próprio.
- Versão de credencial invalida inclusive uma sessão emitida por login concorrente com alteração de senha.

## Dados anteriores
“Acessar painel anterior” mantém o acesso via APP_TOKEN. O currículo e histórico anteriores não são atribuídos automaticamente ao primeiro cadastrado, pois isso permitiria apropriação indevida. Novas contas enviam seu próprio currículo. Nenhum dado anterior é apagado.

## Publicação
Na pasta `cloud`, após `git pull --ff-only`:

```sh
npm run db:remote
npm run deploy
```

Wrangler cria a nova classe SQLite `UserWorkspace` pela migração `v2-user-workspaces`. Não é necessária chave adicional para cadastro/login. O uso permanece sujeito às cotas gratuitas da instalação.

## Validação
Testes de cadastro, hashes, login, revogação, recuperação, senha fraca, expiração, limites e origem. Teste real em Miniflare/workerd com duas contas, D1 e Durable Objects: estado inicial, isolamento de currículos e vagas, rejeição de confirmação de perfil alheio, cabeçalho de proprietário forjado, preservação do painel antigo, confirmação de currículo, preferências e registro do agendamento. Não houve deploy de produção nesta sessão.
