import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { reserve, lock, unlock, profile } from "../src/db.js";
function env() {
  const db = new DatabaseSync(":memory:");
  db.exec(
    readFileSync(
      new URL("../migrations/0001_initial.sql", import.meta.url),
      "utf8",
    ),
  );
  return {
    db,
    DB: {
      prepare(sql) {
        let values = [];
        return {
          bind(...v) {
            values = v;
            return this;
          },
          async first() {
            return db.prepare(sql).get(...values) || null;
          },
          async run() {
            return db.prepare(sql).run(...values);
          },
        };
      },
    },
  };
}
test("daily reservations stop exactly at the budget and isolate channels", async () => {
  const e = env();
  try {
    assert.deepEqual(
      await Promise.all(
        Array.from({ length: 20 }, () => reserve(e, "applications", 3)),
      ),
      [true, true, true, ...Array(17).fill(false)],
    );
    assert.equal(await reserve(e, "browser", 3), true);
    assert.equal(
      e.db.prepare("SELECT count FROM usage WHERE kind='applications'").get()
        .count,
      3,
    );
  } finally {
    e.db.close();
  }
});
test("a pipeline lease blocks another worker and only its owner releases it", async () => {
  const e = env();
  try {
    const token = await lock(e, "pipeline");
    assert.ok(token);
    assert.equal(await lock(e, "pipeline"), null);
    await unlock(e, "pipeline", "wrong-token");
    assert.equal(await lock(e, "pipeline"), null);
    await unlock(e, "pipeline", token);
    assert.ok(await lock(e, "pipeline"));
  } finally {
    e.db.close();
  }
});
test("an expired lease can be taken over", async () => {
  const e = env();
  try {
    await lock(e, "pipeline");
    e.db.exec("UPDATE locks SET expires=0");
    assert.ok(await lock(e, "pipeline"));
  } finally {
    e.db.close();
  }
});
test("latest profile is deterministic when timestamps are equal", async () => {
  const e = env();
  try {
    const insert = e.db.prepare(
      "INSERT INTO profiles(id,filename,pdf,data,confirmed,created_at) VALUES(?,'cv.pdf','x','{}',1,'2026-09-17 12:00:00')",
    );
    insert.run("first");
    insert.run("second");
    assert.equal((await profile(e)).id, "second");
  } finally {
    e.db.close();
  }
});
