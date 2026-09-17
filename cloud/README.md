# Job Autopilot Cloud

Private single-user application: React dashboard, Cloudflare Worker, D1 and Cloudflare Playwright. No paid plan is enabled by the configuration.

## Implemented

- PDF upload (1 MB), Gemini extraction and mandatory owner review.
- Country/global, remote preference, minimum score, confirmed application facts.
- Public Greenhouse, Lever and Ashby connectors; conservative JSON-LD JobPosting reader for supplied job URLs.
- Catalog of up to 2,000 sources, bulk import of 100 URLs per request. One verified Ashby source (Linear) is seeded.
- One source / one analysis / at most one application per run. Optional two-hour cron, initially disabled.
- Evidence-based analysis; exact quotes verified against the confirmed resume and job text.
- Gmail OAuth sending with localized, evidence-backed draft and PDF attachment.
- Bounded Playwright form agent: same-origin navigation, file upload, next steps and submission confirmation.
- Atomic daily reservations, global lease, idempotent job URLs, failure history, explicit reconciliation of uncertain sends.
- Authentication required for every data/API operation. Public assets contain no personal data.

## Deliberate operational limits

This is an initial implementation, not a tested universal application bot. It does **not** search thousands of sources out of the box. The catalog capacity is 2,000; at the default cron it visits 12 sources/day. There is no paid search API, automatic internet-wide company discovery, LinkedIn login scraping, workarounds for CAPTCHA, or browser session persistence.

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

Replace only the placeholder `database_id` in `wrangler.jsonc` with the returned D1 database ID. Preserve Workers Free; do not activate a paid Workers subscription.

```bash
npm run db:remote
npx wrangler secret put APP_TOKEN
npx wrangler secret put GEMINI_API_KEY
npm run test
npm run check
npm run deploy
```

Use a randomly generated APP_TOKEN of at least 32 characters. Save it in a password manager and enter it at the dashboard login; it is held only in the current browser tab, never localStorage. Never commit `.dev.vars`, tokens, cookies, PDFs or account credentials.

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
