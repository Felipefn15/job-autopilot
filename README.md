# 🎯 Job Automation Engine - LinkedIn Post Sniper Edition

A high-performance Python backend engine specialized in **LinkedIn Post Scraping** and automated applications. Engineered for senior developers to bypass traditional application forms by reaching recruiters directly via email.

## 🚀 Key Evolutions (Current Version)

* **LinkedIn Post Sniper Mode**: Specialized boolean search logic to find hidden job opportunities in LinkedIn posts.
* **Multi-AI Failover Architecture**: Seamlessly switches between **Google Gemini 1.5 Flash** and **Groq (Llama 3.3 70B)** to bypass API rate limits (429 errors).
* **Deep HTML Email Extractor**: Advanced Regex + HTML cleaning that extracts obfuscated emails (e.g., `name [at] domain.com`) without consuming AI tokens.
* **Smart Scale & Persistence**:
* Synchronized scroll depth based on `--max-applications` per skill.
* Automatic **2FA (Two-Factor Authentication)** handling with session sequestration.
* **Offline Fallback**: Continues extracting and sending even when all AI quotas are exhausted.



## 🛠️ Architecture & Modules

```
/
├── curriculo.pdf           # Your optimized Senior Resume
├── .env                    # AI Credentials (Gemini & Groq)
├── jobs.db                 # SQLite database for persistence & deduplication
├── main.py                 # Core Orchestrator
├── modules/
│   ├── brain.py            # AI Logic (Gemini & Groq fallback)
│   ├── parser.py           # Resume extraction with hardcoded skill safety
│   ├── linkedin_searcher.py# The Sniper: Post scraping, scrolling & email extraction
│   ├── emailer.py          # SMTP Dispatcher with "Blank Body" failover
│   └── models.py           # Data structures (JobListing, ResumeData)
├── temp_session/           # Isolated Chrome profile (auto-created)
└── logs/                   # Detailed execution history

```

## ⚡ Setup & Requirements

1. **Install Dependencies:**

```bash
pip install -r requirements.txt
playwright install chromium

```

2. **Environment Variables (`.env`):**
Create a `.env` file in the root directory:

```env
# AI API Keys
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key

# SMTP Configuration (Gmail - pessoal tem limite diário/taxa)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USER=felipefrancanogueira@gmail.com
EMAIL_PASS=your_app_password  # Use Google App Password

```

3. **Resume Placement:**
Place your updated `curriculo.pdf` (focused on metrics and impact) in the root folder.

## 🏁 Execution (The Sniper Command)

The engine now supports advanced filtering directly from the CLI:

```bash
./run.sh --location "Latam" --max-applications 200 --min-score 0.1 --query-search '"remote" AND "email"' --blocked-keys "junior" "intern" "hiring"

```

### Parameters:

* `--max-applications`: Number of posts to analyze **per technology**.
* `--query-search`: Custom boolean string to refine LinkedIn results.
* `--blocked-keys`: Terms to exclude from search (NOT condition).
* `--location`: Target geographic area.
* `--stats`: Show **analytics dashboard** (volume, success rate, avg AI score by source) and exit — no pipeline run.
* `--no-ai-fallback`: When Groq and Gemini fail (e.g. 429), use **local heuristic scoring** instead of default 0.6 so the pipeline keeps running.
* `--send-only`: Skip Step 1 (Extraction) and Step 2 (Discovery); run **only Step 3 (apply)** for jobs already in `jobs.db` with status `PENDING` (respects `--max-applications`).

## 🧠 Smart Failover System

The engine is designed to **never stop**:

1. **Primary**: Uses **Gemini 1.5 Flash** for resume parsing and cover letter generation.
2. **Secondary**: If Gemini hits a rate limit (429), it instantly switches to **Groq (Llama 3.3)**.
3. **Tertiary (Offline)**: If both quotas are gone, the engine uses **Deep Regex Extraction** for emails and sends the application with a **Blank Email Body + Resume Attachment**.

## 🛡️ Anti-Bot & Persistence

* **Profile Sequestration**: Copies your essential Chrome data (Cookies/LocalStorage) to a temporary session, allowing the bot to browse as a logged-in user without triggering "suspicious login" flags.
* **2FA Support**: Pauses execution for 60 seconds to allow manual approval on your mobile device.
* **Indentation-Safe Processing**: Robust error handling to prevent the pipeline from crashing during long scroll sessions.

## 📧 Gmail Limits & Email Resilience

Contas **@gmail.com** pessoais têm limite de envios diários e por minuto. O engine protege sua reputação:

* **Trava em quota**: Se o Gmail retornar erro de quota/limite (ex.: `mailer-daemon@googlemail.com`, SMTPDataError), o script **pausa a execução**, mantém o estado em `jobs.db` e avisa no terminal. **Não** continua tentando enviar. Rode novamente após ~2 horas.
* **Escalar com APIs**: Para centenas de envios, use um provedor de transmissão (ex.: **SendGrid**, **Resend**, **Mailgun**) em vez do SMTP do Gmail: limites maiores e métricas de abertura. Configure no seu provedor e aponte `SMTP_SERVER`/credenciais para a API deles, ou estenda `modules/emailer.py` para enviar via API (SendGrid/Resend) quando `SENDGRID_API_KEY` estiver definido.

Recomendação para Full Pipeline: reduzir `--max-applications` (ex.: 50 por execução) e aumentar `--min-score` para focar em vagas de alto fit.

## 📈 Database & Deduplication

All found jobs and emails are stored in `jobs.db`. The system automatically skips:

* Emails already successfully contacted in the last 24h.
* Duplicate posts found across different technology searches (e.g., a post mentioning both Python and React).

## 📝 License

MIT - Developed by Felipe França Nogueira

## ☁️ Persistent Cloud Deployment

For the Oracle Cloud Always Free deployment with Docker, persistent Chromium
profile, noVNC session setup, and a systemd schedule, see
[DEPLOY_OCI.md](DEPLOY_OCI.md).

Use `python main.py --once` for scheduled execution. The original continuous
loop remains available when `--once` is omitted.

