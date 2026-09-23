export const normalizeRole = (value) =>
  String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[-–—]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
const groups = [
  ["enfermeiro", "enfermeira", "nurse", "registered nurse"],
  ["analista de sistemas", "systems analyst", "system analyst"],
  ["engenheiro civil", "engenheira civil", "civil engineer"],
  ["engenheiro mecanico", "engenheira mecanica", "mechanical engineer"],
  ["analista financeiro", "analista financeira", "financial analyst"],
  ["analista de recursos humanos", "hr analyst", "human resources analyst"],
  [
    "gerente de projetos",
    "gerente de projeto",
    "gestor de projetos",
    "gestora de projetos",
    "project manager",
  ],
  ["analista de projetos", "analista de projeto", "project analyst"],
  [
    "coordenador de projetos",
    "coordenadora de projetos",
    "project coordinator",
  ],
  ["scrum master", "scrummaster"],
  ["agile coach", "coach agil", "agilista"],
];
export function roleAliases(role) {
  const n = normalizeRole(role);
  return groups.find((g) => g.includes(n)) || [n];
}
export function expandedRoles(value) {
  return [
    ...new Set(
      String(value || "")
        .split(",")
        .filter((v) => v.trim())
        .flatMap(roleAliases),
    ),
  ];
}
export function managementSearch(config = {}) {
  const roles = String(config.targetRoles || "")
    .split(",")
    .map(normalizeRole)
    .filter(Boolean);
  if (roles.length)
    return roles.every(
      (r) =>
        groups.slice(6).some((g) => g.includes(r)) ||
        /\b(project|projeto|projetos|scrum|agile)\b/.test(r),
    );
  const terms = String(config.keywords || "")
    .split(",")
    .map(normalizeRole)
    .filter(Boolean);
  return (
    terms.length > 0 &&
    terms.every((t) =>
      [
        "scrum",
        "metodologias ageis",
        "metodologia agil",
        "gestao de projetos",
        "project management",
        "agile",
        "kanban",
      ].includes(t),
    )
  );
}
export function workplaceLocation(job, location) {
  const type = String(job.workplaceType || "").toLowerCase();
  const mode = ["hybrid", "onsite", "on-site"].includes(type)
    ? type
    : type === "remote" || job.isRemote === true
      ? "Remote"
      : "";
  return [location, mode].filter(Boolean).join(" · ");
}
