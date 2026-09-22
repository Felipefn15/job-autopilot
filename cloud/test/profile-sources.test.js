import test from "node:test";
import assert from "node:assert/strict";
import { selectSources } from "../src/community.js";
import { triageJob } from "../src/triage.js";
import { workplaceLocation } from "../src/roles.js";
import { discover, fetchText } from "../src/discovery.js";
const config = {
  targetRoles: "Scrum master, Analista de Projetos, Gerente de Projetos",
  keywords: "Metodologias ágeis, Scrum, Gestão de projetos",
  remoteOnly: true,
};
test("project searches skip development communities but mixed developer searches retain them", () => {
  const rows = [
    { id: "php", kind: "github", audience: "software", region: "BR" },
    ...Array.from({ length: 5 }, (_, i) => ({
      id: "company" + i,
      audience: "general",
      region: "BR",
    })),
  ];
  assert.ok(!selectSources(rows, "brasil", config).some((s) => s.id === "php"));
  assert.equal(selectSources(rows, "brasil", config).length, 5);
  assert.ok(
    selectSources([{ ...rows[0], priority: 0 }, ...rows.slice(1)], "brasil", {
      targetRoles: "React developer",
    }).some((s) => s.id === "php"),
  );
});
test("Portuguese roles match English equivalents without treating product management as project management", () => {
  for (const title of [
    "Senior Project Manager",
    "Project Analyst",
    "Scrum Master/Project Manager",
  ])
    assert.equal(
      triageJob(
        { title, location: "Remote Brazil", description: "Agile delivery." },
        config,
      ).pass,
      true,
    );
  assert.equal(
    triageJob(
      { title: "Product Manager", location: "Remote", description: "Scrum" },
      config,
    ).pass,
    false,
  );
});
test("ATS remote metadata reaches triage without inventing remote status for unspecified roles", () => {
  assert.equal(
    triageJob(
      {
        title: "Project Manager",
        location: workplaceLocation({ isRemote: true }, "Brazil"),
        description: "Agile",
      },
      config,
    ).pass,
    true,
  );
  assert.equal(
    triageJob(
      {
        title: "Project Manager",
        location: workplaceLocation(
          { isRemote: true, workplaceType: "Hybrid" },
          "Brazil",
        ),
        description: "Remote work",
      },
      config,
    ).pass,
    false,
  );
  assert.equal(workplaceLocation({}, "Brazil"), "Brazil");
});
test("GitHub distinguishes quota exhaustion from other 403 responses", async (t) => {
  t.mock.method(
    globalThis,
    "fetch",
    async () =>
      new Response("{}", {
        status: 403,
        headers: {
          "x-ratelimit-remaining": "0",
          "x-ratelimit-reset": String(Math.floor(Date.now() / 1000) + 3600),
        },
      }),
  );
  await assert.rejects(
    fetchText("https://api.github.com/repos/vuejs-br/vagas/issues"),
    (e) => e.code === "GITHUB_RATE_LIMIT" && !!e.retryAt,
  );
  globalThis.fetch = async () => new Response("{}", { status: 403 });
  await assert.rejects(
    fetchText("https://api.github.com/repos/vuejs-br/vagas/issues"),
    (e) => !e.code && e.message.includes("sem confirmação"),
  );
});
test("Lever requests bounded pages and configured location, and reports exclusion reasons", async (t) => {
  let requested, stats;
  const writes = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    requested = String(url);
    return Response.json([
      {
        text: "Project Manager",
        workplaceType: "remote",
        categories: { location: "Brazil" },
        hostedUrl: "https://jobs.lever.co/company/1",
        descriptionPlain:
          "An opportunity for project management and agile delivery in a large distributed team. ".repeat(
            2,
          ),
      },
      {
        text: "PHP Developer",
        workplaceType: "remote",
        categories: { location: "Brazil" },
        hostedUrl: "https://jobs.lever.co/company/2",
        descriptionPlain:
          "Scrum software development and project delivery in a large distributed team. ".repeat(
            2,
          ),
      },
    ]);
  });
  const env = {
    DB: {
      prepare(sql) {
        return {
          bind(...args) {
            writes.push({ sql, args });
            if (sql.startsWith("UPDATE sources")) stats = JSON.parse(args[1]);
            return this;
          },
          async run() {
            return { meta: { changes: 1 } };
          },
        };
      },
    },
  };
  assert.equal(
    await discover(
      env,
      {
        id: "s",
        kind: "lever",
        value: "jobgether",
        cursor: 100,
        location_filter: "Brazil",
      },
      config,
    ),
    1,
  );
  const u = new URL(requested);
  assert.equal(u.searchParams.get("limit"), "100");
  assert.equal(u.searchParams.get("skip"), "100");
  assert.equal(u.searchParams.get("location"), "Brazil");
  assert.equal(stats.filtered, 1);
  assert.equal(Object.values(stats.reasons)[0], 1);
  assert.equal(
    writes.find((w) => w.sql.startsWith("UPDATE sources")).args[0],
    0,
  );
});
