import test from "node:test";
import assert from "node:assert/strict";
import { githubJobs, selectSources, sourceWindow } from "../src/community.js";
import { fetchText, sourceSpec } from "../src/discovery.js";

test("community jobs exclude closed issues, pull requests and stale posts", () => {
  const now = Date.parse("2026-09-22T12:00:00Z");
  const job = {
    state: "open",
    created_at: "2026-09-21T10:00:00Z",
    title: "React remoto",
    html_url: "https://github.com/frontendbr/vagas/issues/1",
    body: "Descrição",
  };
  const result = githubJobs(
    [
      job,
      { ...job, state: "closed" },
      { ...job, pull_request: {} },
      { ...job, created_at: "2025-01-01" },
    ],
    "frontendbr/vagas",
    now,
  );
  assert.equal(result.length, 1);
  assert.equal(result[0].url, job.html_url);
  assert.throws(() => githubJobs({}, "a/b"));
});
test("Brazil focus reserves four slots and rotates previously checked sources", () => {
  const rows = Array.from({ length: 8 }, (_, i) => ({
    id: String(i),
    region: i < 6 ? "BR" : "global",
    priority: i,
    checked_at: null,
  }));
  assert.deepEqual(
    selectSources(rows).map((s) => s.id),
    ["0", "1", "2", "3", "6"],
  );
  for (const s of selectSources(rows)) s.checked_at = "2026-09-22 10:00:00";
  assert.deepEqual(
    selectSources(rows).map((s) => s.id),
    ["4", "5", "0", "1", "7"],
  );
  assert.equal(selectSources(rows.filter((s) => s.region === "BR")).length, 5);
  assert.deepEqual(
    selectSources(rows, "global")
      .slice(0, 3)
      .map((s) => s.id),
    ["4", "5", "7"],
  );
});
test("large ATS catalog windows visit every job before wrapping", () => {
  const all = Array.from({ length: 721 }, (_, i) => ({
    url: `https://example.com/${i}`,
  }));
  let cursor = 0;
  const seen = new Set();
  for (let i = 0; i < 3; i++) {
    const page = sourceWindow(all, cursor);
    page.jobs.forEach((j) => seen.add(j.url));
    cursor = page.cursor;
  }
  assert.equal(seen.size, 721);
  assert.equal(cursor, 0);
  assert.deepEqual(sourceWindow([], 100), { jobs: [], cursor: 0 });
});
test("stream limit accepts responses larger than old 2 MB cap and stops oversized sources", async (t) => {
  t.mock.method(
    globalThis,
    "fetch",
    async () => new Response("x".repeat(2500000)),
  );
  assert.equal((await fetchText("https://example.com/jobs")).length, 2500000);
  await assert.rejects(
    fetchText("https://example.com/jobs", 2000000),
    /limite de 2 MB/,
  );
});
test("community source identifiers reject paths and invalid channel names", () => {
  assert.deepEqual(sourceSpec("github", "FrontendBR/vagas"), {
    kind: "github",
    value: "frontendbr/vagas",
  });
  assert.throws(() => sourceSpec("github", "a/b/issues"));
  assert.throws(() => sourceSpec("telegram", "../private"));
});
