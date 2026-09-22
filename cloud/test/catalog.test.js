import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { saveJobs } from "../src/discovery.js";
test("bulk discovery persists jobs, deduplicates URLs and uses bounded database writes", async () => {
  const db = new DatabaseSync(":memory:");
  db.exec(
    readFileSync(
      new URL("../migrations/0001_initial.sql", import.meta.url),
      "utf8",
    ),
  );
  let writes = 0;
  const env = {
    DB: {
      prepare(sql) {
        return {
          bind(...args) {
            return {
              async run() {
                writes++;
                return {
                  meta: { changes: db.prepare(sql).run(...args).changes },
                };
              },
            };
          },
        };
      },
    },
  };
  try {
    const jobs = Array.from({ length: 100 }, (_, i) => ({
      title: "React engineer",
      company: "Example",
      location: "Remote",
      url: `https://example.com/jobs/${i}`,
      description:
        "React software development and experience building accessible interfaces. ".repeat(
          4,
        ),
    }));
    assert.equal(
      await saveJobs(
        env,
        { id: "s", kind: "greenhouse", value: "example" },
        { keywords: "React" },
        jobs,
      ),
      100,
    );
    assert.equal(
      await saveJobs(
        env,
        { id: "s", kind: "greenhouse", value: "example" },
        { keywords: "React" },
        jobs,
      ),
      0,
    );
    assert.equal(writes, 4);
  } finally {
    db.close();
  }
});
test("catalog migrations install 82 references, prioritize 21 Brazilian sources and preserve paused sources", () => {
  const db = new DatabaseSync(":memory:");
  try {
    const dir = new URL("../migrations/", import.meta.url);
    for (const f of readdirSync(dir).sort())
      db.exec(readFileSync(new URL(f, dir), "utf8"));
    assert.equal(db.prepare("SELECT count(*) AS n FROM sources").get().n, 82);
    assert.equal(
      db.prepare("SELECT count(*) AS n FROM sources WHERE region='BR'").get().n,
      21,
    );
    db.exec("UPDATE sources SET enabled=0 WHERE value='linear'");
    db.exec(readFileSync(new URL("0003_source_catalog.sql", dir), "utf8"));
    assert.equal(
      db.prepare("SELECT enabled FROM sources WHERE value='linear'").get()
        .enabled,
      0,
    );
  } finally {
    db.close();
  }
});
