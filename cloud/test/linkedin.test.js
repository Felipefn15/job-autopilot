import test from "node:test";
import assert from "node:assert/strict";
import {
  linkedinUrl,
  parseLinkedinPost,
  linkedinJob,
} from "../src/linkedin.js";
const text =
  "Hiring a senior React developer for a remote team in Brazil. Apply with your resume by email to jobs@example.com.";
test("LinkedIn post URLs reject unrelated hosts, profiles and login routes", () => {
  assert.equal(
    linkedinUrl("https://www.linkedin.com/posts/hiring-activity-123?trk=test"),
    "https://www.linkedin.com/posts/hiring-activity-123",
  );
  assert.ok(
    linkedinUrl("https://www.linkedin.com/feed/update/urn:li:activity:123/"),
  );
  for (const url of [
    "https://evil.com/posts/x",
    "https://www.linkedin.com.evil.com/posts/x",
    "https://www.linkedin.com/in/name",
    "https://www.linkedin.com/login",
  ])
    assert.throws(() => linkedinUrl(url));
});
test("public post extraction reads body but rejects login or truncated previews", () => {
  assert.equal(
    parseLinkedinPost(
      `<script type="application/ld+json">${JSON.stringify({ "@type": "SocialMediaPosting", articleBody: text })}</script>`,
    ),
    text,
  );
  assert.throws(() => parseLinkedinPost("<h1>Sign in to LinkedIn</h1>"));
  assert.throws(() =>
    parseLinkedinPost(
      `<p class="share-update-card__update-text">${text}...</p>`,
    ),
  );
});
test("pasted posts retain their content and never invent company details", () => {
  const j = linkedinJob(
    {
      url: "https://www.linkedin.com/posts/example-activity-123",
      title: "React developer",
    },
    text,
  );
  assert.equal(j.description, text);
  assert.equal(j.title, "React developer");
  assert.match(j.company, /Não informada/);
  assert.throws(() => linkedinJob({ url: j.url }, "short"));
});
