import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { catalog } from "../src/catalog.js";
import { saveJobs, discover } from "../src/discovery.js";
function fixture() {
  const db = new DatabaseSync(":memory:");
  const dir = new URL("../migrations/", import.meta.url);
  for (const f of readdirSync(dir).sort())
    db.exec(readFileSync(new URL(f, dir), "utf8"));
  return {
    db,
    DB: {
      prepare(sql) {
        let args = [];
        return {
          bind(...a) {
            args = a;
            return this;
          },
          async run() {
            return { meta: { changes: db.prepare(sql).run(...args).changes } };
          },
          async first() {
            return db.prepare(sql).get(...args);
          },
          async all() {
            return { results: db.prepare(sql).all(...args) };
          },
        };
      },
    },
  };
}
test("catalog preserves out-of-preference jobs, paginates, deduplicates and sorts AI recommendations", async () => {
  const env = fixture();
  try {
    const jobs = Array.from({ length: 55 }, (_, i) => ({
      title: `Enfermeiro ${i}`,
      company: "Hospital",
      location: "Presencial Brasil",
      url: `https://example.com/jobs/${i}`,
      description:
        "Atendimento assistencial, cuidados de enfermagem, registro profissional e acompanhamento dos pacientes.",
    }));
    const stats = {};
    assert.equal(
      await saveJobs(
        env,
        { id: "test", value: "hospital", kind: "page" },
        { remoteOnly: true, targetRoles: "Developer" },
        jobs,
        stats,
      ),
      55,
    );
    assert.equal(stats.filtered, 55);
    assert.equal(stats.duplicates, 0);
    assert.equal(
      await saveJobs(
        env,
        { id: "test", value: "hospital", kind: "page" },
        { remoteOnly: true },
        jobs,
      ),
      0,
    );
    assert.equal((await catalog(env, new URLSearchParams())).total, 55);
    assert.equal(
      (await catalog(env, new URLSearchParams("page=2"))).jobs.length,
      5,
    );
    assert.equal(
      (await catalog(env, new URLSearchParams("view=recommended"))).total,
      0,
    );
    env.db.exec("UPDATE settings SET data='{\"minScore\":60}' WHERE id=1");
    env.db.exec(
      "UPDATE jobs SET status='matched',analysis='{}',score=80 WHERE title='Enfermeiro 1'",
    );
    env.db.exec(
      "UPDATE jobs SET status='matched',analysis='{}',score=95 WHERE title='Enfermeiro 2'",
    );
    const rec = await catalog(env, new URLSearchParams("view=recommended"));
    assert.deepEqual(
      rec.jobs.map((j) => j.score),
      [95, 80],
    );
    assert.equal((await catalog(env, new URLSearchParams("q=%"))).total, 0);
    assert.equal(
      (await catalog(env, new URLSearchParams("q=Hospital"))).total,
      55,
    );
  } finally {
    env.db.close();
  }
});
test("SmartRecruiters collects full descriptions and advances bounded Brazilian pages", async (t) => {
  const env = fixture();
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    const u = new URL(url);
    requests.push(u);
    if (u.search)
      return Response.json({
        totalFound: 9,
        content: [{ id: "1" }, { id: "2" }],
      });
    return Response.json({
      id: u.pathname.split("/").at(-1),
      name: "Enfermeiro",
      company: { name: "Saúde" },
      location: { city: "São Paulo", country: "br", remote: false },
      jobAd: {
        sections: {
          jobDescription: {
            text: "Cuidados de enfermagem, assistência aos pacientes e acompanhamento clínico em ambiente hospitalar.",
          },
        },
      },
    });
  });
  try {
    await discover(
      env,
      {
        id: "br-sr-bosch",
        kind: "smartrecruiters",
        value: "BoschGroup",
        location_filter: "br",
        cursor: 0,
      },
      { remoteOnly: true },
    );
    assert.equal(requests.length, 3);
    assert.equal(requests[0].searchParams.get("country"), "br");
    assert.equal(requests[0].searchParams.get("limit"), "5");
    assert.equal(
      env.db.prepare("SELECT cursor FROM sources WHERE id='br-sr-bosch'").get()
        .cursor,
      2,
    );
    assert.equal((await catalog(env, new URLSearchParams())).total, 2);
  } finally {
    env.db.close();
  }
});
