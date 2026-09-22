# Coletor local do LinkedIn

O Chromium roda no seu Mac com um perfil persistente autenticado. O coletor busca posts usando as tecnologias, país/LATAM/Mundo e preferência de trabalho remoto salvos no painel. Envia somente texto e URL dos posts ao Job Autopilot; a análise e a deduplicação acontecem na nuvem. Não envia cookies ou senha do LinkedIn.

## Instalação

Na raiz do repositório atualizado:

```bash
cd collector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python linkedin_collector.py login
python linkedin_collector.py run
```

No comando `login`, faça login manualmente no navegador aberto, abra o feed e pressione Enter no terminal. No comando `run`, informe o APP_TOKEN já usado no painel quando solicitado; a digitação fica oculta. Confirme o currículo e salve suas tecnologias antes de executar.

### Usar a sessão antiga

Feche o Chromium da automação antiga e informe a pasta persistente exata que ela usava:

```bash
python linkedin_collector.py run --profile-dir /caminho/absoluto/do/perfil
```

Use um perfil dedicado à automação, não a pasta do Chrome pessoal aberto. Não execute dois processos no mesmo perfil. Se a sessão expirou, use `login --profile-dir /caminho/absoluto/do/perfil`. O programa não copia cookies, não remove travas e para se aparecer login, CAPTCHA ou verificação.

Sem `--profile-dir`, o perfil fica em `~/.job-autopilot/linkedin-profile`. Use sempre a mesma pasta em login/run/watch. Para outro painel, passe `--url https://seu-worker.workers.dev`.

## Repetir a busca

Ative o agendamento no painel e execute:

```bash
python linkedin_collector.py watch
```

O Mac precisa permanecer ligado, acordado e com o processo aberto. O intervalo padrão é 120 minutos; `--interval-minutes` aceita a partir de 30. Ctrl+C encerra imediatamente. Desativar o agendamento encerra o coletor na próxima consulta ao painel, não durante a espera atual. `run` executa uma coleta manual independentemente do agendamento.

São até 30 posts por ciclo por padrão (`--max-posts`, máximo 100), até três buscas usando as primeiras nove tecnologias. Posts incompletos ou menores que 80 caracteres são ignorados. Duplicados não viram novas vagas. O painel mostra o último resultado em Fontes e Atividade; esse registro não é uma confirmação de que o computador continua conectado.

Depois da coleta, execute um lote no painel ou aguarde o cron para analisar os posts. Posts de comunidades sem e-mail de candidatura verificado exigem abrir o anúncio e seguir o link manualmente. Este coletor não envia mensagens, não se candidata pelo LinkedIn e não altera seu perfil.

Os testes cobrem preparação de consultas, URLs e configuração da API. A extração autenticada precisa ser validada no seu navegador: alterações no layout do LinkedIn podem exigir atualizar os seletores. Zero posts pode significar ausência de resultados ou incompatibilidade do layout, não necessariamente ausência de vagas.

```bash
python -m unittest discover -s . -p 'test_*.py'
```
