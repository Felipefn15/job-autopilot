import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { triageJob, retriage } from "../src/triage.js";
const prefs = {
  country: "Brasil",
  remoteOnly: true,
  keywords: "Metodologias ágeis, Scrum, Gestão de projetos",
};
const job = (title) => ({
  title,
  location: title,
  description:
    "Atuação com metodologias ágeis, Scrum e gestão de projetos em equipes de desenvolvimento de software.",
});
test("reported Cobol, Java, C# and Python roles do not pass merely because descriptions mention Scrum", () => {
  for (const title of [
    "[Híbrido-SP] Back-end developer Cobol Sênior",
    "[Home Office] Desenvolvedor Backend Java",
    "[Remoto] Back-end C#/Net",
    "[Remoto] Senior Python Developer",
    "[Remota] Full-stack Engineer Terraform React",
  ])
    assert.equal(triageJob(job(title), prefs).pass, false, title);
  assert.equal(triageJob(job("[Remoto] Scrum Master"), prefs).pass, true);
  assert.equal(
    triageJob(job("[Home office] Gerente de Projetos"), prefs).pass,
    true,
  );
});
test("remote-only rejects explicit hybrid, on-site, negative and missing work arrangements", () => {
  for (const title of [
    "[Híbrido] React developer",
    "[On-site] React engineer",
    "React developer",
  ])
    assert.equal(
      triageJob(job(title), { remoteOnly: true, keywords: "React" }).pass,
      false,
    );
  assert.equal(
    triageJob(
      {
        ...job("React developer"),
        description:
          "Modelo de trabalho: híbrido. React com possibilidade futura de trabalho remoto.",
      },
      { remoteOnly: true, keywords: "React" },
    ).pass,
    false,
  );
  assert.equal(
    triageJob(
      {
        ...job("React developer"),
        description: "This position is not remote. React experience.",
      },
      { remoteOnly: true, keywords: "React" },
    ).pass,
    false,
  );
  assert.equal(
    triageJob(job("[Remoto] React developer"), {
      remoteOnly: true,
      keywords: "React",
    }).pass,
    true,
  );
});
test("specific skills outrank generic mentions and terms respect boundaries", () => {
  assert.equal(
    triageJob(job("[Remoto] Cobol developer"), { keywords: "React, Scrum" })
      .pass,
    false,
  );
  assert.equal(
    triageJob(job("[Remoto] JavaScript developer"), { keywords: "Java" }).pass,
    false,
  );
  assert.equal(
    triageJob(job("[Remoto] C++ developer"), { keywords: "C++" }).pass,
    true,
  );
});
test("explicit role filters do not reinterpret every management skill as a developer role", () => {
  const config = { ...prefs, targetRoles: "Project Manager, Scrum Master" };
  assert.equal(triageJob(job("[Remoto] Project Manager"), config).pass, true);
  assert.equal(triageJob(job("[Remoto] Tech Lead"), config).pass, false);
});
test("stored jobs are retriaged in bounded batches, recover after preference change, and preserve submission evidence", async () => {
  const db = new DatabaseSync(":memory:");
  for (const file of readdirSync(
    new URL("../migrations/", import.meta.url),
  ).sort())
    db.exec(
      readFileSync(new URL("../migrations/" + file, import.meta.url), "utf8"),
    );
  const env = {
    DB: {
      prepare(sql) {
        let values = [];
        return {
          bind(...args) {
            values = args;
            return this;
          },
          async all() {
            return { results: db.prepare(sql).all(...values) };
          },
          async run() {
            return db.prepare(sql).run(...values);
          },
        };
      },
      async batch(stmts) {
        return Promise.all(stmts.map((s) => s.run()));
      },
    },
  };
  try {
    const insert = db.prepare(
      "INSERT INTO jobs(id,title,company,location,url,description,status,proof) VALUES(?,?,'Company','Brasil',?,? ,?,?)",
    );
    for (let i = 0; i < 205; i++)
      insert.run(
        String(i),
        "[Híbrido] Cobol",
        `https://company.com/jobs/${i}`,
        job("").description,
        "discovered",
        null,
      );
    insert.run(
      "submitted",
      "[Híbrido] Cobol",
      "https://company.com/sent",
      job("").description,
      "submitted",
      "real confirmation",
    );
    insert.run(
      "manual",
      "[Remoto] Scrum Master",
      "https://company.com/manual",
      job("").description,
      "needs_input",
      "Application requires manual consent",
    );
    await retriage(env, prefs);
    await retriage(env, prefs);
    assert.equal(
      db.prepare("SELECT count(*) n FROM jobs WHERE status='filtered'").get().n,
      205,
    );
    assert.equal(
      db.prepare("SELECT proof FROM jobs WHERE id='submitted'").get().proof,
      "real confirmation",
    );
    assert.equal(
      db.prepare("SELECT proof FROM jobs WHERE id='manual'").get().proof,
      "Application requires manual consent",
    );
    await retriage(env, { keywords: "Cobol", remoteOnly: false });
    await retriage(env, { keywords: "Cobol", remoteOnly: false });
    assert.equal(
      db.prepare("SELECT count(*) n FROM jobs WHERE status='discovered'").get()
        .n,
      205,
    );
  } finally {
    db.close();
  }
});
