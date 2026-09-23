import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { catalog } from "../src/catalog.js";
import { saveJobs, discover } from "../src/discovery.js";
import { boardJobs } from "../src/boards.js";
import { nextAnalysis, deferAnalysis } from "../src/job-insights.js";
import {
  classifyTitle,
  searchPlan,
  prioritize,
  refreshMetadata,
} from "../src/job-insights.js";
function fixture() {
  const db = new DatabaseSync(":memory:");
  const dir = new URL("../migrations/", import.meta.url);
  for (const f of readdirSync(dir).sort())
    db.exec(readFileSync(new URL(f, dir), "utf8"));
  return {
    db,
    DB: {
      async batch(items) {
        return Promise.all(items.map((i) => i.run()));
      },
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
test("failed analysis defers retries without blocking another candidate or changing application history", async () => {
  const env = fixture();
  try {
    const base = {
      title: "Scrum Master",
      company: "Company",
      location: "Remote",
      description:
        "Facilitação de cerimônias e acompanhamento das entregas de projetos com equipes de diferentes áreas.",
    };
    await saveJobs(env, { id: "queue", kind: "page", value: "Company" }, {}, [
      { ...base, url: "https://example.com/queue1" },
      { ...base, url: "https://example.com/queue2" },
    ]);
    const key = env.db
      .prepare("SELECT triage_key FROM jobs LIMIT 1")
      .get().triage_key;
    const first = await nextAnalysis(env, {}, key);
    await deferAnalysis(env, first.id);
    const second = await nextAnalysis(env, {}, key);
    assert.notEqual(second.id, first.id);
    await deferAnalysis(env, first.id);
    await deferAnalysis(env, first.id);
    const delayed = env.db
      .prepare(
        "SELECT status,analysis_attempts,analysis_retry_after FROM jobs WHERE id=?",
      )
      .get(first.id);
    assert.equal(delayed.status, "discovered");
    assert.equal(delayed.analysis_attempts, 3);
    assert.ok(
      Date.parse(delayed.analysis_retry_after + "Z") >
        Date.now() + 23 * 3600000,
    );
    env.db
      .prepare("UPDATE jobs SET availability='closed' WHERE id=?")
      .run(second.id);
    assert.equal(await nextAnalysis(env, {}, key), undefined);
  } finally {
    env.db.close();
  }
});
test("SmartRecruiters sends directed query and preserves the general pagination cursor", async (t) => {
  const env = fixture();
  const requested = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    requested.push(new URL(url));
    return Response.json({ totalFound: 0, content: [] });
  });
  try {
    const source = {
      id: "br-sr-bosch",
      value: "BoschGroup",
      kind: "smartrecruiters",
      cursor: 15,
      location_filter: "br",
    };
    await discover(env, source, { targetRoles: "Scrum master" });
    assert.equal(requested[0].searchParams.get("q"), "scrum master");
    assert.equal(requested[0].searchParams.get("offset"), "0");
    const persisted = env.db
      .prepare("SELECT * FROM sources WHERE id='br-sr-bosch'")
      .get();
    assert.equal(persisted.cursor, 15);
    await discover(env, persisted, { targetRoles: "Scrum master" });
    assert.equal(requested[1].searchParams.has("q"), false);
    assert.equal(requested[1].searchParams.get("offset"), "15");
  } finally {
    env.db.close();
  }
});
test("multi-profession title signals do not infer missing seniority", () => {
  assert.deepEqual(classifyTitle("Enfermeiro Júnior"), {
    area: "health",
    seniority: "junior",
  });
  assert.equal(classifyTitle("Engenheira Civil Sênior").area, "engineering");
  assert.equal(classifyTitle("Analista de Sistemas Pleno").seniority, "mid");
  assert.equal(classifyTitle("Scrum Master").seniority, "unknown");
});
test("directed search alternates with catalog collection and resets on preference changes", () => {
  const config = { targetRoles: "Scrum master" };
  const first = searchPlan({}, config);
  assert.equal(first.term, "scrum master");
  const next = searchPlan(
    { search_state: JSON.stringify({ ...first.state, turn: 1 }) },
    config,
  );
  assert.equal(next.targeted, false);
  assert.equal(
    searchPlan(
      { search_state: JSON.stringify({ ...first.state, turn: 1 }) },
      { targetRoles: "Enfermeiro" },
    ).term,
    "enfermeiro",
  );
});
test("priority favors title matches but aging eventually gives older candidates a turn", () => {
  const now = Date.parse("2026-09-23T12:00:00Z");
  const a = {
    id: "a",
    title: "Scrum Master",
    created_at: "2026-09-23 10:00:00",
  };
  const b = {
    id: "b",
    title: "Agile facilitator",
    created_at: "2026-09-22 10:00:00",
  };
  assert.equal(
    prioritize([b, a], { targetRoles: "Scrum master" }, now).id,
    "a",
  );
  assert.equal(
    prioritize(
      [{ ...b, created_at: "2026-07-01 10:00:00" }, a],
      { targetRoles: "Scrum master" },
      now,
    ).id,
    "b",
  );
});
test("full-board absence is not confirmed closure; expiration blocks recommendations; sightings reopen listings", async (t) => {
  const env = fixture();
  const source = { id: "life", kind: "greenhouse", value: "example" };
  const job = {
    title: "Enfermeiro Sênior",
    company: "Saúde",
    location: "Brazil",
    url: "https://example.com/old",
    description:
      "Assistência de enfermagem, acompanhamento dos pacientes e administração de tratamentos conforme prescrição.",
  };
  try {
    await saveJobs(env, source, {}, [job]);
    t.mock.method(globalThis, "fetch", async () =>
      Response.json({
        jobs: [
          {
            title: "Outra vaga",
            absolute_url: "https://example.com/new",
            content: job.description,
            location: { name: "Brazil" },
          },
        ],
      }),
    );
    await discover(env, source, {});
    assert.equal(
      env.db
        .prepare(
          "SELECT availability FROM jobs WHERE url='https://example.com/old'",
        )
        .get().availability,
      "not_listed",
    );
    await saveJobs(env, source, {}, [job]);
    assert.equal(
      env.db
        .prepare(
          "SELECT availability FROM jobs WHERE url='https://example.com/old'",
        )
        .get().availability,
      "open",
    );
    env.db.exec(
      "UPDATE jobs SET status='matched',score=99,analysis='{}',valid_through='2000-01-01T00:00:00Z' WHERE url='https://example.com/old'",
    );
    assert.equal(
      (await catalog(env, new URLSearchParams("view=recommended"))).total,
      0,
    );
    assert.equal(
      (
        await catalog(
          env,
          new URLSearchParams(
            "availability=closed&area=health&seniority=senior",
          ),
        )
      ).total,
      1,
    );
    await refreshMetadata(env);
    assert.equal(
      env.db
        .prepare(
          "SELECT availability FROM jobs WHERE url='https://example.com/old'",
        )
        .get().availability,
      "closed",
    );
  } finally {
    env.db.close();
  }
});
test("public boards skip metadata, retain attribution URLs and do not invent worldwide eligibility", () => {
  const jobs = boardJobs("remoteok", [
    { legal: "terms" },
    {
      position: "Operations manager",
      company: "Test",
      url: "https://remoteok.com/remote-jobs/123",
      description: "Details",
    },
    { position: "Bad", url: "https://other.example/job" },
  ]);
  assert.equal(jobs.length, 1);
  assert.match(jobs[0].location, /não informada/);
  assert.equal(jobs[0].url, "https://remoteok.com/remote-jobs/123");
  assert.equal(
    boardJobs("remotive", {
      jobs: [
        {
          title: "Nurse",
          candidate_required_location: "United States",
          url: "https://remotive.com/remote-jobs/health/123",
        },
      ],
    })[0].location,
    "United States · Remote",
  );
});
test("catalog filters source and collection date and searches descriptions", async () => {
  const env = fixture();
  try {
    await saveJobs(
      env,
      { id: "board-remotive", kind: "remotive", value: "remotive" },
      {},
      [
        {
          title: "Analista",
          company: "Example",
          url: "https://remotive.com/remote-jobs/123",
          description:
            "Responsável por coordenação operacional e planejamento. Experiência com atendimento e acompanhamento de pacientes.",
        },
      ],
    );
    assert.equal(
      (
        await catalog(
          env,
          new URLSearchParams("q=pacientes&source=remotive&days=1"),
        )
      ).total,
      1,
    );
    assert.equal(
      (await catalog(env, new URLSearchParams("source=remoteok"))).total,
      0,
    );
    env.db.exec("UPDATE jobs SET created_at=datetime('now','-40 days')");
    assert.equal((await catalog(env, new URLSearchParams("days=30"))).total, 0);
    assert.equal((await catalog(env, new URLSearchParams())).total, 1);
  } finally {
    env.db.close();
  }
});
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

test("catalog normalizes accents and Brazil aliases; legacy facets and profile role OR work together", async () => {
  const env = fixture();
  try {
    await saveJobs(env, { id: "test", value: "hospital", kind: "page" }, {}, [
      {
        title: "Enfermeira Sênior",
        company: "Saúde",
        location: "Brazil",
        url: "https://example.com/nurse",
        description:
          "Assistência aos pacientes e cuidados de enfermagem, avaliação clínica e acompanhamento dos tratamentos prescritos.",
      },
      {
        title: "Systems Analyst",
        company: "Systems",
        location: "Brasil",
        url: "https://example.com/analyst",
        description:
          "Análise de sistemas, desenvolvimento de soluções e levantamento de requisitos junto aos responsáveis pelos projetos.",
      },
    ]);
    env.db.exec("UPDATE jobs SET area=NULL,seniority=NULL");
    assert.equal(
      (await catalog(env, new URLSearchParams("q=Brasil"))).total,
      2,
    );
    assert.equal(
      (
        await catalog(
          env,
          new URLSearchParams("q=saude+Brazil&area=health&seniority=senior"),
        )
      ).total,
      1,
    );
    assert.equal(
      (await catalog(env, new URLSearchParams("q=Brasil&area=operations")))
        .total,
      0,
    );
    env.db
      .prepare("UPDATE settings SET data=? WHERE id=1")
      .run(
        JSON.stringify({
          targetRoles: "Enfermeiro, Analista de sistemas",
          minScore: 60,
        }),
      );
    assert.equal(
      (await catalog(env, new URLSearchParams("profile=1"))).total,
      2,
    );
    env.db
      .prepare("UPDATE settings SET data=? WHERE id=1")
      .run(JSON.stringify({ targetRoles: "Scrum Master", minScore: 60 }));
    assert.equal(
      (await catalog(env, new URLSearchParams("profile=1"))).total,
      0,
    );
    assert.equal((await catalog(env, new URLSearchParams())).total, 2);
    assert.equal((await catalog(env, new URLSearchParams("q=%25"))).total, 0);
  } finally {
    env.db.close();
  }
});
