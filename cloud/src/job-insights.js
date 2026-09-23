import { expandedRoles, normalizeRole } from "./roles.js";
export const areas = {
  technology: "Tecnologia",
  projects: "Projetos e agilidade",
  health: "Saúde",
  engineering: "Engenharia",
  finance: "Finanças",
  commercial: "Comercial e marketing",
  people: "Recursos humanos",
  operations: "Operações e logística",
  education: "Educação",
  other: "Não identificada",
};
export const levels = {
  intern: "Estágio / aprendiz",
  junior: "Júnior",
  mid: "Pleno",
  senior: "Sênior",
  lead: "Liderança",
  unknown: "Não identificada",
};
// Explicit title signals only: an organizational level is not inferred from years or age.
export function classifyTitle(title) {
  const t = normalizeRole(title);
  const area =
    [
      [
        "health",
        /enferm|nurs|medic|physician|fisioterap|farmaceut|pharmac|dentist|psicolog/,
      ],
      [
        "projects",
        /scrum|agilista|agile coach|project (manager|analyst|coordinator)|(?:gerente|analista|coordenador).*projeto/,
      ],
      [
        "technology",
        /software|developer|desenvolv|programador|sistemas|systems analyst|devops|frontend|backend|full.?stack|data (engineer|scientist)|engenheir.*dados/,
      ],
      ["engineering", /engenheir|engineer|arquiteto|architect/],
      ["finance", /financ|contab|accountant|controller|auditor/],
      [
        "people",
        /recursos humanos|human resources|recruit|recrut|talent|people operations/,
      ],
      ["commercial", /vendedor|sales|comercial|marketing|customer success/],
      ["education", /professor|teacher|pedagog|educador/],
      [
        "operations",
        /logistic|operac|operations|supply|compras|recepc|cozinha|warehouse/,
      ],
    ].find(([, re]) => re.test(t))?.[0] || "other";
  const seniority =
    /\b(estagio|estagiario|estagiaria|intern|internship|aprendiz)\b/.test(t)
      ? "intern"
      : /\b(junior|jr)\b/.test(t)
        ? "junior"
        : /\b(pleno|mid|intermediate)\b/.test(t)
          ? "mid"
          : /\b(senior|sr)\b/.test(t)
            ? "senior"
            : /\b(lead|head|director|diretor|manager|gerente|coordenador|coordenadora)\b/.test(
                  t,
                )
              ? "lead"
              : "unknown";
  return { area, seniority };
}
export function searchPlan(source, config) {
  const terms = expandedRoles(config.targetRoles).slice(0, 18);
  const signature = JSON.stringify(terms);
  let state;
  try {
    state = JSON.parse(source.search_state || "{}");
  } catch {
    state = {};
  }
  if (state.signature !== signature)
    state = { signature, turn: 0, index: 0, offset: 0 };
  const targeted = terms.length > 0 && (state.turn || 0) % 2 === 0;
  return {
    state,
    targeted,
    term: targeted ? terms[(state.index || 0) % terms.length] : "",
    terms,
  };
}
export function prioritize(jobs, config, now = Date.now()) {
  const terms = expandedRoles(config.targetRoles);
  const rank = (j) => {
    const title = normalizeRole(j.title);
    const relevance = terms.some((t) => title.includes(t)) ? 30 : 0;
    const age = Math.min(
      40,
      Math.max(0, (now - Date.parse(j.created_at + "Z")) / 86400000),
    );
    return (
      relevance +
      (Number.isFinite(age) ? age : 0) -
      Math.min(20, (j.analysis_attempts || 0) * 5)
    );
  };
  return [...jobs].sort(
    (a, b) => rank(b) - rank(a) || String(a.id).localeCompare(String(b.id)),
  )[0];
}
export async function refreshMetadata(env) {
  const rows = await env.DB.prepare(
    "SELECT id,title FROM jobs WHERE area IS NULL OR seniority IS NULL LIMIT 200",
  ).all();
  const updates = rows.results.map((j) => {
    const c = classifyTitle(j.title);
    return env.DB.prepare("UPDATE jobs SET area=?,seniority=? WHERE id=?").bind(
      c.area,
      c.seniority,
      j.id,
    );
  });
  for (let i = 0; i < updates.length; i += 50)
    await env.DB.batch(updates.slice(i, i + 50));
  await env.DB.prepare(
    "UPDATE jobs SET availability='closed' WHERE valid_through IS NOT NULL AND datetime(valid_through)<CURRENT_TIMESTAMP",
  ).run();
}
export async function nextAnalysis(env, config, key) {
  const candidates = await env.DB.prepare(
    "SELECT * FROM jobs WHERE status='discovered' AND availability NOT IN ('closed','not_listed') AND (valid_through IS NULL OR datetime(valid_through)>=CURRENT_TIMESTAMP) AND (analysis_retry_after IS NULL OR analysis_retry_after<=CURRENT_TIMESTAMP) AND triage_key=? ORDER BY created_at LIMIT 100",
  )
    .bind(key)
    .all();
  return prioritize(candidates.results, config);
}
export async function deferAnalysis(env, id) {
  await env.DB.prepare(
    "UPDATE jobs SET analysis_attempts=analysis_attempts+1,analysis_retry_after=datetime('now',CASE WHEN analysis_attempts>=2 THEN '+24 hours' ELSE '+1 hour' END) WHERE id=?",
  )
    .bind(id)
    .run();
}
