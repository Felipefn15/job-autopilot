import test from "node:test";
import assert from "node:assert/strict";
import {
  publicUrl,
  validateAnalysis,
  verifiedEmail,
  validateDraft,
  validateAction,
  validateSettings,
  parseJSON,
  emailAddress,
} from "../src/core.js";
import { parseStructuredJobs, sourceSpec } from "../src/discovery.js";
import { mimeMessage } from "../src/email.js";
const profile = {
  text: "Built React interfaces and Node.js APIs for international teams.",
  fields: { name: "Candidate", email: "person@company.com" },
};
const job = {
  description:
    "Must have React experience. Apply by email to jobs@company.com.",
  url: "https://company.com/jobs/1",
};
const analysis = {
  score: 90,
  eligibility: "eligible",
  evidence: [
    {
      resumeQuote: "Built React interfaces",
      jobQuote: "Must have React experience.",
    },
  ],
  gaps: [],
  blockers: [],
};
test("canonicalization drops tracking without losing job identity", () =>
  assert.equal(
    publicUrl("https://company.com/job?id=42&utm_source=x#apply"),
    "https://company.com/job?id=42",
  ));
test("unsafe destinations are rejected", () => {
  for (const u of [
    "http://example.com",
    "https://127.0.0.1",
    "https://[::1]",
    "https://x.internal",
    "https://user:pass@company.com",
    "https://company.com:8080",
  ])
    assert.throws(() => publicUrl(u));
});
test("unsupported ATS slug cannot inject a URL", () =>
  assert.throws(() => sourceSpec("lever", "../foo?url=http://x")));
test("evidence-backed fit is eligible", () =>
  assert.equal(validateAnalysis(analysis, profile, job, 80).status, "matched"));
test("a high score never overrides a blocker", () =>
  assert.equal(
    validateAnalysis(
      { ...analysis, blockers: ["US authorization missing"] },
      profile,
      job,
      80,
    ).status,
    "needs_input",
  ));
test("unknown eligibility is never eligible", () =>
  assert.equal(
    validateAnalysis({ ...analysis, eligibility: "unknown" }, profile, job, 80)
      .status,
    "needs_input",
  ));
test("hallucinated evidence stops matching", () =>
  assert.throws(() =>
    validateAnalysis(
      {
        ...analysis,
        evidence: [
          {
            resumeQuote: "10 years of Java",
            jobQuote: "Must have React experience.",
          },
        ],
      },
      profile,
      job,
      80,
    ),
  ));
test("missing evidence cannot authorize an application", () =>
  assert.equal(
    validateAnalysis({ ...analysis, evidence: [] }, profile, job, 80).status,
    "needs_input",
  ));
test("an email must be supported by job instructions", () => {
  assert.equal(
    verifiedEmail(job, {
      emailApplication: true,
      email: "jobs@company.com",
      emailInstruction: "Apply by email to jobs@company.com.",
    }),
    "jobs@company.com",
  );
  assert.throws(() =>
    verifiedEmail(job, {
      emailApplication: true,
      email: "attacker@elsewhere.com",
      emailInstruction: "Apply by email to jobs@company.com.",
    }),
  );
});
test("empty drafts and invented experience are blocked", () => {
  assert.throws(() =>
    validateDraft({ subject: "Hi", body: "", resumeQuotes: [] }, profile),
  );
  assert.throws(() =>
    validateDraft(
      {
        subject: "Hi",
        body: "A".repeat(70),
        resumeQuotes: ["Invented achievement"],
      },
      profile,
    ),
  );
});
test("header injection is rejected", () => {
  assert.throws(() => emailAddress("x@company.com\r\nBcc: y@evil.com"));
  assert.throws(() =>
    mimeMessage(
      "me@company.com",
      "you@company.com",
      { subject: "Hi\r\nBcc: z@evil.com", body: "Body" },
      "JVBERi0=",
      "test",
    ),
  );
});
test("MIME preserves Unicode subject, attachment and recipient", () => {
  const m = mimeMessage(
    "me@company.com",
    "jobs@company.com",
    { subject: "Candidatura — React", body: "Olá, equipe!" },
    "JVBERi0=",
    "abc123",
  );
  const s = Buffer.from(m.raw, "base64url").toString();
  assert.match(s, /To: jobs@company.com/);
  assert.match(s, /application\/pdf/);
  assert.match(s, /Subject: =\?UTF-8\?B\?/);
  assert.equal(m.messageId, "<abc123@job-autopilot.local>");
});
test("generic unknown answers do not become Yes", () =>
  assert.throws(() =>
    validateAction(
      { type: "fill", id: 1, value: "Yes" },
      [{ id: 1, label: "Work authorization", name: "visa" }],
      profile,
      {},
    ),
  ));
test("candidate supplied facts can fill a salary field", () =>
  assert.doesNotThrow(() =>
    validateAction(
      { type: "fill", id: 1, value: "USD 5000" },
      [{ id: 1, label: "Salary", name: "salary" }],
      profile,
      { salary: "USD 5000" },
    ),
  ));
test("credentials and consents cannot be filled by the agent", () => {
  for (const label of ["Password", "Consent to terms", "Gender"])
    assert.throws(() =>
      validateAction(
        { type: "fill", id: 1, value: "Candidate" },
        [{ id: 1, label, name: label }],
        profile,
        {},
      ),
    );
});
test("unobserved controls and navigation cannot be used", () => {
  assert.throws(() =>
    validateAction({ type: "next", id: 88 }, [], profile, {}),
  );
  assert.throws(() =>
    validateAction(
      { type: "next", id: 1 },
      [{ id: 1, label: "Delete account" }],
      profile,
      {},
    ),
  );
});
test("structured jobs keep valid posts and ignore expired ones", () => {
  const html =
    '<script type="application/ld+json">' +
    JSON.stringify({
      "@graph": [
        {
          "@type": "JobPosting",
          title: "React Engineer",
          description: "Build frontend",
          url: "/jobs/42",
          hiringOrganization: { name: "Company" },
        },
        { "@type": "JobPosting", title: "Expired", validThrough: "2000-01-01" },
      ],
    }) +
    "</script>";
  const jobs = parseStructuredJobs(html, "https://company.com/careers");
  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].url, "https://company.com/jobs/42");
});
test("free application budget cannot be expanded in settings", () =>
  assert.throws(() =>
    validateSettings({
      country: "global",
      minScore: 80,
      dailyApplications: 1000,
    }),
  ));
test("malformed model output never silently defaults to approval", () =>
  assert.throws(() => parseJSON("Sure, apply!")));
