import {
  settings,
  profile,
  event,
  reserve,
  lock,
  unlock,
  status,
} from "./db.js";
import { ai } from "./ai.js";
import { validateAnalysis, validateDraft, verifiedEmail } from "./core.js";
import { discover } from "./discovery.js";
import { selectSources } from "./community.js";
import { sendEmail, emailConfigured } from "./email.js";
import { browserApply } from "./browser.js";
import { reserveBrowserSeconds } from "./linkedin-cloud-core.js";
export async function analyze(env, job, p, config) {
  const a = await ai(
    env,
    `Compare this job with the confirmed resume and preferences. Assess mandatory country/residency/work authorization restrictions separately from technical fit. Global means search anywhere, NOT permission to work anywhere. Missing mandatory facts => unknown. Return {score:integer 0..100,eligibility:"eligible"|"ineligible"|"unknown",reason:"Portuguese explanation",language:"language code",evidence:[{resumeQuote:"exact substring",jobQuote:"exact substring",reason:"..."}],gaps:["..."],blockers:["..."],emailApplication:boolean,email:"explicit application email or null",emailInstruction:"verbatim instruction to apply by email or null"}. Email must explicitly be an application channel, never just a contact/privacy email.\nPREFERENCES ${JSON.stringify(config)}\nRESUME ${JSON.stringify(p.data)}\nJOB ${JSON.stringify({ title: job.title, company: job.company, location: job.location, description: job.description })}`,
  );
  const checked = validateAnalysis(a, p.data, job, config.minScore);
  const email = verifiedEmail(job, checked);
  let draft = null;
  if (checked.status === "matched" && email) {
    draft = validateDraft(
      await ai(
        env,
        `Write a concise job application email in the language requested in the job, otherwise its language (${checked.language}). Never add invented years, skills or achievements. Return {subject:"...",body:"...",resumeQuotes:["verbatim evidence supporting each experience claim"]}. Include role, company and resume attachment reference.\nRESUME ${JSON.stringify(p.data)}\nJOB ${JSON.stringify(job)}\nANALYSIS ${JSON.stringify(checked)}`,
      ),
      p.data,
    );
  }
  await env.DB.prepare(
    "UPDATE jobs SET status=?,score=?,analysis=?,draft=?,profile_id=?,email=?,language=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
  )
    .bind(
      checked.status,
      checked.score,
      JSON.stringify(checked),
      draft ? JSON.stringify(draft) : null,
      p.id,
      email,
      checked.language || "unknown",
      job.id,
    )
    .run();
  await event(env, "analysis", checked.reason, job.id);
}
export async function apply(env, id, p, config) {
  const job = await env.DB.prepare("SELECT * FROM jobs WHERE id=?")
    .bind(id)
    .first();
  if (!job || job.status !== "matched" || job.profile_id !== p.id)
    throw new Error("Candidatura não está pronta para este currículo.");
  if (!p.confirmed) throw new Error("Confirme o perfil extraído do currículo.");
  if (
    !job.email &&
    ["linkedin.com", "www.linkedin.com", "github.com", "t.me"].includes(
      new URL(job.url).hostname,
    )
  ) {
    await status(
      env,
      id,
      "needs_input",
      "Post de comunidade sem candidatura por e-mail verificada. Abra o anúncio e siga o link de candidatura manualmente.",
    );
    return;
  }
  const checked = validateAnalysis(
    JSON.parse(job.analysis),
    p.data,
    job,
    config.minScore,
  );
  if (checked.status !== "matched")
    throw new Error("Vaga incompatível com os filtros atuais.");
  if (job.email && !emailConfigured(env))
    throw new Error("Envio Gmail não configurado.");
  if (!job.email && !env.BROWSER)
    throw new Error("Navegador remoto não configurado.");
  if (
    !(await reserve(
      env,
      "applications",
      Math.min(
        3,
        config.dailyApplications,
        Number(env.DAILY_APPLICATION_LIMIT || 3),
      ),
    ))
  )
    throw new Error("Limite diário de candidaturas atingido.");
  if (!job.email && !(await reserveBrowserSeconds(env, 150)))
    throw new Error("Cota diária compartilhada de navegador atingida.");
  if (
    !job.email &&
    !(await reserve(
      env,
      "browser",
      Math.min(3, Number(env.DAILY_BROWSER_LIMIT || 3)),
    ))
  )
    throw new Error("Limite diário de navegador atingido.");
  const claim = await env.DB.prepare(
    "UPDATE jobs SET status='preparing',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='matched' RETURNING id",
  )
    .bind(id)
    .first();
  if (!claim) throw new Error("Candidatura já em processamento.");
  let sending = false;
  const markSending = async () => {
    await status(env, id, "sending");
    sending = true;
  };
  try {
    const proof = job.email
      ? await sendEmail(env, job, p, markSending)
      : await browserApply(env, job, p, config, markSending);
    await status(env, id, "submitted", proof);
    await event(env, "submitted", "Confirmação de envio registrada.", id);
  } catch (e) {
    await status(env, id, sending ? "unknown" : "needs_input", e.message);
    await event(env, "application_pending", e.message, id);
  }
}
export async function tick(env, manual = false, applyId = null) {
  const lease = await lock(env, "pipeline");
  if (!lease) throw new Error("Já existe uma execução em andamento.");
  try {
    const config = await settings(env),
      p = await profile(env);
    if (!manual && !config.enabled) return;
    if (!p?.confirmed)
      throw new Error("Envie o PDF e confirme o perfil antes de executar.");
    // Never resend ambiguous attempts. This also recovers workers terminated mid-flight.
    await env.DB.prepare(
      "UPDATE jobs SET status='unknown',proof='Execução interrompida. Verifique o destino antes de repetir.' WHERE status IN ('sending','preparing') AND updated_at < datetime('now','-10 minutes')",
    ).run();
    if (applyId) {
      await apply(env, applyId, p, config);
      return;
    }
    const sources = await env.DB.prepare(
      "SELECT * FROM sources WHERE enabled=1 AND (retry_after IS NULL OR retry_after <= CURRENT_TIMESTAMP) AND (checked_at IS NULL OR checked_at < datetime('now','-2 hours')) ORDER BY checked_at ASC,id LIMIT 2000",
    ).all();
    const selected = selectSources(
      sources.results,
      config.sourceFocus || "brasil",
    );
    if (!selected.length)
      await event(
        env,
        "discovery_idle",
        "Nenhuma fonte disponível agora. As fontes são consultadas em rodízio a cada duas horas; falhas aguardam seis horas.",
      );
    for (const source of selected) {
      let error = null;
      try {
        await discover(env, source, config);
      } catch (e) {
        error = e.message;
        await event(env, "source_error", `${source.value}: ${error}`);
      }
      await env.DB.prepare(
        "UPDATE sources SET checked_at=CURRENT_TIMESTAMP,error=?,retry_after=CASE WHEN ? IS NULL THEN NULL ELSE datetime('now','+6 hours') END WHERE id=?",
      )
        .bind(error, error, source.id)
        .run();
    }
    const job = await env.DB.prepare(
      "SELECT * FROM jobs WHERE status='discovered' ORDER BY created_at LIMIT 1",
    ).first();
    if (job)
      try {
        await analyze(env, job, p, config);
      } catch (e) {
        await event(env, "analysis_error", e.message, job.id);
      }
    if (config.autoApply) {
      const ready = await env.DB.prepare(
        "SELECT id FROM jobs WHERE status='matched' AND profile_id=? ORDER BY score DESC LIMIT 1",
      )
        .bind(p.id)
        .first();
      if (ready) await apply(env, ready.id, p, config);
    }
  } finally {
    await unlock(env, "pipeline", lease);
  }
}
