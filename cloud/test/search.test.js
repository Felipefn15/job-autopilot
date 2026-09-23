import test from "node:test";
import assert from "node:assert/strict";
import { verifiedRoles, queryGroups } from "../src/search.js";
import { expandedRoles, managementSearch } from "../src/roles.js";

test("AI search suggestions require real quotes and explicit titles, deduplicate and reject invented roles", () => {
  const text =
    "Experiência: Analista de Projetos na Empresa A de 2020 a 2024. Gestão de cronogramas.";
  const roles = verifiedRoles(
    {
      roles: [
        {
          title: "Analista de Projetos",
          evidence: "Analista de Projetos na Empresa A de 2020 a 2024",
        },
        {
          title: "Analista de Projetos",
          evidence: "Analista de Projetos na Empresa A",
        },
        { title: "Diretor de Projetos", evidence: "Gestão de cronogramas." },
        { title: "Scrum Master", evidence: "Scrum Master de 2020 a 2024" },
        { title: 4, evidence: null },
      ],
    },
    text,
  );
  assert.deepEqual(
    roles.map((r) => r.title),
    ["Analista de Projetos"],
  );
  assert.deepEqual(verifiedRoles({}, text), []);
});
test("search expansion covers professions without classifying them as project management", () => {
  assert.ok(expandedRoles("Enfermeiro").includes("nurse"));
  assert.ok(expandedRoles("Analista de sistemas").includes("systems analyst"));
  assert.equal(managementSearch({ targetRoles: "Enfermeiro" }), false);
  assert.equal(managementSearch({ targetRoles: "Scrum Master" }), true);
  assert.deepEqual(queryGroups("SAÚDE Brasil"), [
    ["saude"],
    ["brasil", "brazil"],
  ]);
});
