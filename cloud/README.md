# Job Autopilot Cloud

Private single-user application: React dashboard, Cloudflare Worker, D1 and Cloudflare Playwright. No paid plan is enabled by the configuration.

## Implemented

- PDF upload (1 MB), Gemini extraction and mandatory owner review.
- Country/global, remote preference, minimum score, confirmed application facts.
- Public Greenhouse, Lever and Ashby connectors; conservative JSON-LD JobPosting reader for supplied job URLs.
- Catalog of up to 2,000 sources, bulk import of 100 URLs per request. Migration 0003 seeds 66 career references whose pages were identified on 2026-09-21. API availability and vacancies are checked at runtime; no vacancy counts are preloaded or promised.
- Up to five sources / one analysis / at most one application per run. Sources are revisited no sooner than six hours. Optional two-hour cron, initially disabled.
- Public LinkedIn post URL extraction plus pasted-text import. Login walls, redirects and unavailable or truncated content produce a manual import prompt. No LinkedIn credentials or cookies are collected.
- Evidence-based analysis; exact quotes verified against the confirmed resume and job text.
- Gmail OAuth sending with localized, evidence-backed draft and PDF attachment.
- Bounded Playwright form agent: same-origin navigation, file upload, next steps and submission confirmation.
- Atomic daily reservations, global lease, idempotent job URLs, failure history, explicit reconciliation of uncertain sends.
- Authentication required for every data/API operation. Public assets contain no personal data.

## Deliberate operational limits

This is an initial implementation, not a tested universal application bot. It does **not** search thousands of sources out of the box. The catalog capacity is 2,000; at the default cron it attempts up to 60 source consultations/day, with one job analysis per run. There is no paid search API, automatic internet-wide company discovery, LinkedIn feed/search crawling, login scraping, workarounds for CAPTCHA, or browser session persistence. LinkedIn support imports specific supplied post URLs; it does not search all posts. Imported posts enter the usual evidence-based analysis. Verified email applications use the normal email flow; other LinkedIn applications require manual follow-up. No live LinkedIn post extraction was verified in this environment; HTML layouts and access restrictions may require pasting the post text.

After updating an existing deployment, run `npm run db:remote` then `npm run deploy` from `cloud/`. The catalog migration is idempotent and preserves already paused sources. Run a batch after confirming the resume to fetch actual jobs. References and verification scope are listed in [CATALOG.md](CATALOG.md).

Browser login, cross-origin application flows, checkbox consent, demographic questions, unsupported iframes/custom controls and ambiguous responses become manual tasks. There is no guarantee of completing every ATS form. Email accepted by Gmail is not proof of delivery. A timeout after sending is `unknown`, never automatically retried.

The free Cloudflare plan currently includes 10 browser minutes/day. The app reserves at most 3 sessions/day and imposes a 90-second browser deadline (4.5 minutes maximum requested session time), leaving headroom. Provider enforcement, CPU limits and shared account usage still apply. Workers Free has tight CPU limits: validate with the actual account; CPU exhaustion must pause/reduce work, never silently upgrade billing.

Gemini availability and free quotas depend on the chosen model/account. The code caps requests at 30/day and never switches to a paid provider. Google documents that free-tier content can be used to improve its products; use a provider/account whose data handling fits the resume before enabling it. Set a currently available model using `GEMINI_MODEL`.

## Deploy to a free Cloudflare account

Requirements: Node 22+, Cloudflare account with Workers Free, D1 and Browser Run available; Gemini API key. Gmail is optional until email applications are enabled.

```bash
cd cloud
npm ci
npx wrangler login
npx wrangler d1 create job-autopilot
```

This repository already has the owner's D1 database ID configured. Reuse that database for this deployment. For a separate account, replace `database_id` with its new ID and preserve the binding name `DB`. Preserve Workers Free; do not activate a paid Workers subscription.

```bash
npm run db:remote
npx wrangler secret put APP_TOKEN
npx wrangler secret put GEMINI_API_KEY
npx wrangler secret put GROQ_API_KEY
npm run test
npm run check
npm run deploy
```

Use a randomly generated APP_TOKEN of at least 32 characters. Save it in a password manager and enter it at the dashboard login; it is held only in the current browser tab, never localStorage. Never commit `.dev.vars`, tokens, cookies, PDFs or account credentials.

### Groq quota fallback

`GROQ_API_KEY` is optional. Gemini remains primary; HTTP 429 (quota or rate limit) triggers one Groq attempt using `GROQ_MODEL` (default `llama-3.3-70b-versatile`). With only Groq configured, text tasks also work. Each provider attempt counts against the shared `DAILY_AI_LIMIT` (maximum 30); fallback never bypasses the application's own daily budget. Groq exhaustion stops the operation. Authentication errors, invalid JSON and truncated responses do not trigger further retries. All downstream evidence and form validations remain unchanged.

For resume import, Groq receives text extracted locally by unpdf, not the binary PDF. Up to 20 pages / 60,000 extracted characters are supported. Scanned/image-only pages or pages with insufficient text require a selectable-text PDF or Gemini availability; there is no Groq OCR fallback. Review and confirmation remain mandatory. PDF parsing CPU usage still needs validation on the actual Workers Free account. Groq receives resume/job/form text when used; configure a key for a free account if zero cost is required. Model availability and account quotas still apply.

References: https://console.groq.com/docs/text-chat, https://console.groq.com/docs/rate-limits, https://github.com/unjs/unpdf.

Configure optional Gmail secrets with `wrangler secret put`: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_FROM`. Obtain an offline OAuth refresh token with `https://www.googleapis.com/auth/gmail.send` using your own Google OAuth app; an OAuth testing app may issue expiring refresh tokens. The current implementation expects the refresh token to be provisioned outside the app; no Gmail OAuth onboarding UI is implemented yet.

Once deployed: enter APP_TOKEN, upload the PDF, review/confirm extraction, configure facts/preferences, add career pages, run one batch, inspect results, then enable the schedule and automatic sending if desired. No real job application is performed by tests or deployment.

The backend can send automatically after the owner enables the setting; credentials, consent and CAPTCHA exceptions still pause. To stop all automatic activity, disable the schedule in the dashboard.

## Local validation

```bash
npm ci
npm test
npm run check
```

The unit suite covers decision gates, fabricated evidence, destination restrictions, email header injection, MIME attachments and form action validation. `wrangler deploy --dry-run` builds the Worker without publishing. Live Gmail delivery, provider credentials and real ATS submissions require separate end-to-end validation; do not infer those succeeded from a dry run.

## References (checked 2026-09-17)

- https://developers.cloudflare.com/browser-run/pricing/
- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/browser-run/playwright/
- https://ai.google.dev/gemini-api/docs/pricing
- https://developers.google.com/workspace/gmail/api/guides/sending

## Data lifecycle

Resume versions and application evidence remain in the private D1 database. This version has no data deletion UI or retention job. Use D1 export for backups; add explicit retention/deletion before multi-user use. The account owner is the only intended operator. Do not publish the API token or share this deployment with other users.
