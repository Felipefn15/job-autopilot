export const LIMITS = {
  pdf: 1024 * 1024,
  sources: 2000,
  description: 20000,
  browserMs: 90000,
};
export function publicUrl(value) {
  const u = new URL(value);
  const h = u.hostname.toLowerCase();
  if (
    u.protocol !== "https:" ||
    u.username ||
    u.password ||
    (u.port && u.port !== "443") ||
    !h.includes(".") ||
    /^[\d.]+$/.test(h) ||
    h.includes(":") ||
    /(^|\.)(localhost|local|internal|invalid|test|example|onion)$/.test(h)
  )
    throw new Error("URL pública HTTPS necessária.");
  u.hash = "";
  for (const k of [...u.searchParams.keys()])
    if (/^(utm_|fbclid|gclid)/i.test(k)) u.searchParams.delete(k);
  return u.href;
}
export function cleanText(value) {
  return String(value || "")
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}
export async function digest(text) {
  return [
    ...new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)),
    ),
  ]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
export function parseJSON(value) {
  const v = JSON.parse(
    String(value)
      .trim()
      .replace(/^```(?:json)?\s*/, "")
      .replace(/\s*```$/, ""),
  );
  if (!v || Array.isArray(v) || typeof v !== "object")
    throw new Error("Resposta estruturada inválida.");
  return v;
}
export function validateSettings(input) {
  const country = String(input.country || "global")
    .trim()
    .slice(0, 80);
  const minScore = Number(input.minScore);
  const dailyApplications = Number(input.dailyApplications);
  if (
    !country ||
    !Number.isInteger(minScore) ||
    minScore < 60 ||
    minScore > 100 ||
    !Number.isInteger(dailyApplications) ||
    dailyApplications < 1 ||
    dailyApplications > 3
  )
    throw new Error(
      "Pontuação entre 60 e 100; limite de 1 a 3 candidaturas/dia.",
    );
  const facts = {};
  for (const [k, v] of Object.entries(input.facts || {}).slice(0, 30))
    if (typeof v === "string" && k.length < 100) facts[k] = v.slice(0, 2000);
  return {
    country,
    minScore,
    dailyApplications,
    remoteOnly: input.remoteOnly === true,
    autoApply: input.autoApply === true,
    enabled: input.enabled === true,
    keywords: String(input.keywords || "").slice(0, 500),
    facts,
  };
}
export function validateAnalysis(a, profile, job, minScore) {
  if (
    !Number.isInteger(a.score) ||
    a.score < 0 ||
    a.score > 100 ||
    !["eligible", "ineligible", "unknown"].includes(a.eligibility) ||
    !Array.isArray(a.evidence) ||
    !Array.isArray(a.gaps) ||
    !Array.isArray(a.blockers)
  )
    throw new Error("Análise incompleta.");
  const evidence = a.evidence.filter(
    (e) =>
      typeof e.resumeQuote === "string" &&
      e.resumeQuote.trim().length >= 8 &&
      profile.text.includes(e.resumeQuote) &&
      typeof e.jobQuote === "string" &&
      e.jobQuote.trim().length >= 8 &&
      job.description.includes(e.jobQuote),
  );
  if (evidence.length !== a.evidence.length)
    throw new Error("Evidência não encontrada no currículo ou vaga.");
  const ready =
    a.eligibility === "eligible" &&
    a.blockers.length === 0 &&
    evidence.length > 0 &&
    a.score >= minScore;
  return {
    ...a,
    evidence,
    status:
      a.eligibility === "ineligible" || a.score < minScore
        ? "rejected"
        : ready
          ? "matched"
          : "needs_input",
  };
}
export function emailAddress(value) {
  const s = String(value || "").trim();
  if (
    !/^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)+$/i.test(s) ||
    /[\r\n]/.test(s)
  )
    throw new Error("Destinatário inválido.");
  return s.toLowerCase();
}
export function verifiedEmail(job, analysis) {
  if (
    analysis.emailApplication !== true ||
    !analysis.email ||
    !analysis.emailInstruction
  )
    return null;
  const address = emailAddress(analysis.email);
  if (
    !job.description.toLowerCase().includes(address) ||
    !job.description.includes(analysis.emailInstruction)
  )
    throw new Error("Canal de e-mail sem evidência na vaga.");
  return address;
}
export function validateDraft(d, profile) {
  if (
    typeof d.subject !== "string" ||
    !d.subject.trim() ||
    /[\r\n]/.test(d.subject) ||
    d.subject.length > 200 ||
    typeof d.body !== "string" ||
    d.body.trim().length < 60 ||
    d.body.length > 8000 ||
    !Array.isArray(d.resumeQuotes) ||
    !d.resumeQuotes.length ||
    d.resumeQuotes.some(
      (q) => typeof q !== "string" || q.length < 8 || !profile.text.includes(q),
    )
  )
    throw new Error("Mensagem sem conteúdo ou evidências válidas.");
  return d;
}
export const ALLOWED_ACTIONS = new Set([
  "fill",
  "select",
  "check",
  "upload",
  "next",
  "submit",
  "done",
  "blocked",
]);
export function validateAction(action, controls, profile, facts) {
  if (!ALLOWED_ACTIONS.has(action.type)) throw new Error("Ação não permitida.");
  if (["done", "blocked"].includes(action.type)) return action;
  const control = controls.find((c) => c.id === action.id);
  if (!control) throw new Error("Campo não observado.");
  const label = `${control.label} ${control.name}`.toLowerCase();
  if (
    /(captcha|password|senha|2fa|one.time|verification code|código de verificação|signature|assinatura|terms|termos|consent|consentimento|race|raça|gender|gênero|disability|deficiência|veteran|veterano)/i.test(
      label,
    )
  )
    throw new Error("Campo exige intervenção do usuário.");
  if (action.type === "fill" || action.type === "select") {
    if (typeof action.value !== "string" || action.value.length > 4000)
      throw new Error("Valor inválido.");
    const values = [
      ...Object.values(profile.fields || {}),
      ...Object.values(facts || {}),
    ].filter((v) => typeof v === "string");
    const direct = values.includes(action.value);
    const quote =
      typeof action.resumeQuote === "string" &&
      action.resumeQuote.length >= 8 &&
      profile.text.includes(action.resumeQuote);
    if (!direct && !quote)
      throw new Error("Resposta sem informação confirmada.");
    if (
      /(salary|salário|pretens|sponsor|visa|visto|authoriz|autoriza|relocat|mudança)/i.test(
        label,
      ) &&
      !direct
    )
      throw new Error("Preferência não informada.");
  }
  if (
    action.type === "next" &&
    !/next|continue|próxim|continuar|avançar/i.test(control.label)
  )
    throw new Error("Navegação não reconhecida.");
  if (
    action.type === "submit" &&
    !/submit|send|apply|enviar|candidat|inscri/i.test(control.label)
  )
    throw new Error("Envio não reconhecido.");
  if (action.type === "check")
    throw new Error(
      "Seleção por checkbox exige confirmação manual nesta versão.",
    );
  return action;
}
