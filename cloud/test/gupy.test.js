import test from "node:test";
import assert from "node:assert/strict";
import { gupyPage } from "../src/gupy.js";
import { selectSources } from "../src/community.js";
test("Gupy validates payload and preserves unknown/hybrid modality and deadline", () => {
  assert.throws(() => gupyPage({ error: "blocked" }));
  const parsed = gupyPage({
    pagination: { total: 1 },
    data: [
      {
        name: "Enfermeiro",
        jobUrl: "https://hospital.gupy.io/jobs/1",
        country: "Brasil",
        workplaceType: "hybrid",
        isRemoteWork: true,
        applicationDeadline: "2026-12-31",
      },
    ],
  });
  assert.equal(parsed.jobs[0].location, "Brasil · Híbrido");
  assert.equal(parsed.jobs[0].valid_through, "2026-12-31T23:59:59Z");
  assert.equal(
    gupyPage({
      pagination: { total: 1 },
      data: [{ jobUrl: "https://evil.example/jobs/1" }],
    }).jobs.length,
    0,
  );
});
test("active cross-company query gets a slot without removing general rotation", () => {
  const rows = Array.from({ length: 8 }, (_, i) => ({
    id: String(i),
    kind: "ashby",
    region: "BR",
  }));
  const gupy = {
    id: "g",
    kind: "gupy",
    region: "BR",
    checked_at: "2026-09-23",
  };
  const selected = selectSources([...rows, gupy], "brasil", {
    targetRoles: "Product Owner",
  });
  assert.equal(selected.length, 5);
  assert.equal(selected[0].id, "g");
  assert.equal(selected[1].id, "0");
});
