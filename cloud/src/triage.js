import { cleanText, digest } from "./core.js";
import { expandedRoles, normalizeRole } from "./roles.js";
const normal = (value) =>
  cleanText(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
const split = (value) =>
  String(value || "")
    .split(",")
    .map(normal)
    .filter(Boolean);
const broad = new Set([
  "scrum",
  "agile",
  "agil",
  "metodologias ageis",
  "metodologia agil",
  "gestao de projetos",
  "project management",
  "kanban",
  "comunicacao",
  "communication",
  "lideranca",
  "leadership",
  "trabalho em equipe",
  "teamwork",
]);
function has(text, term) {
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^a-z0-9])${escaped}(?=$|[^a-z0-9])`, "i").test(text);
}
function roleTerms(term) {
  if (
    [
      "scrum",
      "agile",
      "agil",
      "metodologias ageis",
      "metodologia agil",
      "kanban",
    ].includes(term)
  )
    return ["scrum master", "agile coach", "agile master", "agilista"];
  if (["gestao de projetos", "project management"].includes(term))
    return [
      "gestor de projetos",
      "gestora de projetos",
      "gerente de projetos",
      "gerenciamento de projetos",
      "coordenador de projetos",
      "coordenadora de projetos",
      "project manager",
      "project management",
    ];
  return [term];
}
export function triageJob(job, config) {
  const title = normal(job.title),
    location = normal(job.location),
    body = normal(job.description),
    headline = title + " " + location,
    all = headline + " " + body;
  if (config.remoteOnly) {
    const nonRemote = /\b(hibrid[oa]s?|hybrid|presencial|on[- ]?site)\b/;
    if (
      nonRemote.test(headline) ||
      /\b(?:modelo|modalidade|regime|trabalho|atuacao)\s*(?:de trabalho\s*)?[:\-]?\s*(?:hibrid[oa]|presencial)\b|\bhybrid (?:work|role|position)|\b(?:required|mandatory) on[- ]?site\b/.test(
        body,
      )
    )
      return {
        pass: false,
        reason:
          "Excluída: trabalho híbrido ou presencial; preferência somente remoto.",
      };
    if (
      !/\b(remot[oa]s?|remote|home office|anywhere|work from home)\b/.test(
        all,
      ) ||
      /\b(?:nao|not)\s+(?:e\s+|is\s+)?(?:remot[oa]|remote)\b/.test(all)
    )
      return {
        pass: false,
        reason: "Excluída: trabalho remoto não confirmado no anúncio.",
      };
  }
  const roles = expandedRoles(config.targetRoles);
  if (roles.length && !roles.some((role) => has(normalizeRole(title), role)))
    return {
      pass: false,
      reason: "Excluída: título fora dos cargos de interesse.",
    };
  const terms = split(config.keywords),
    specific = terms.filter((t) => !broad.has(t));
  if (specific.length && !specific.some((t) => has(title + " " + body, t)))
    return {
      pass: false,
      reason: "Excluída: nenhum termo específico de experiência encontrado.",
    };
  if (
    !specific.length &&
    terms.length &&
    !roles.length &&
    !terms.some((t) => roleTerms(t).some((r) => has(title, r)))
  )
    return {
      pass: false,
      reason:
        "Excluída: termos genéricos no texto não demonstram relação com o cargo. Defina cargos de interesse.",
    };
  return {
    pass: true,
    reason: "Pré-filtros atendidos; aguarda avaliação do currículo pela IA.",
  };
}
export async function triageKey(config) {
  return digest(
    JSON.stringify([
      "triage-v2",
      config.keywords || "",
      config.targetRoles || "",
      !!config.remoteOnly,
      config.country || "",
    ]),
  );
}
export async function retriage(env, config) {
  const key = await triageKey(config);
  const rows = await env.DB.prepare(
    "SELECT id,title,location,description,status FROM jobs WHERE status IN ('discovered','matched','needs_input','filtered') AND (triage_key IS NULL OR triage_key!=?) ORDER BY created_at DESC,id LIMIT 200",
  )
    .bind(key)
    .all();
  const changes = rows.results.map((job) => {
    const verdict = triageJob(job, config);
    const next = verdict.pass
      ? job.status === "filtered"
        ? "discovered"
        : job.status
      : "filtered";
    return env.DB.prepare(
      "UPDATE jobs SET status=?,triage_key=?,proof=CASE WHEN ?='filtered' OR status IN ('discovered','filtered') THEN ? ELSE proof END,score=CASE WHEN ?='filtered' THEN NULL ELSE score END,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('discovered','matched','needs_input','filtered')",
    ).bind(next, key, next, verdict.reason, next, job.id);
  });
  for (let i = 0; i < changes.length; i += 50)
    await env.DB.batch(changes.slice(i, i + 50));
  return key;
}
