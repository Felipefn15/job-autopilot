import { LIMITS, digest, validateSettings, resumeKeywords } from "./core.js";
import { settings, profile, event, lock, unlock } from "./db.js";
import { sourceSpec, fetchText, saveJobs } from "./discovery.js";
import { linkedinUrl, parseLinkedinPost, linkedinJob } from "./linkedin.js";
import { ai, resumePrompt } from "./ai.js";
import { tick } from "./pipeline.js";
import { emailConfigured } from "./email.js";
import { cloudLinkedin } from "./linkedin-cloud.js";
export { LinkedInCloud } from "./linkedin-cloud.js";
const headers = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
};
const json = (value, status = 200) =>
  new Response(JSON.stringify(value), { status, headers });
async function authorized(req, env) {
  if (!env.APP_TOKEN || env.APP_TOKEN.length < 32) return false;
  const supplied = req.headers.get("Authorization") || "";
  if (supplied.length > 300) return false;
  return (await digest(supplied)) === (await digest("Bearer " + env.APP_TOKEN));
}
async function body(req, max = 100000) {
  if (Number(req.headers.get("Content-Length")) > max)
    throw new Error("Requisição muito grande.");
  const raw = await req.text();
  if (raw.length > max) throw new Error("Requisição muito grande.");
  return JSON.parse(raw);
}
async function mutateProfile(env, fn) {
  const lease = await lock(env, "pipeline");
  if (!lease) throw new Error("Aguarde a execução em andamento.");
  try {
    return await fn();
  } finally {
    await unlock(env, "pipeline", lease);
  }
}
export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(req);
    if (!env.APP_TOKEN || env.APP_TOKEN.length < 32)
      return json(
        {
          error:
            "Configure APP_TOKEN com ao menos 32 caracteres para ativar o acesso privado.",
        },
        503,
      );
    if (!(await authorized(req, env)))
      return json({ error: "Chave de acesso inválida." }, 401);
    if (!env.DB) return json({ error: "Banco de dados não configurado." }, 503);
    if (
      req.method !== "GET" &&
      req.headers.get("Origin") &&
      req.headers.get("Origin") !== url.origin
    )
      return json({ error: "Origem não permitida." }, 403);
    try {
      if (url.pathname.startsWith("/api/linkedin/cloud/")) {
        const action = url.pathname.slice("/api/linkedin/cloud/".length);
        if (
          (action === "status" && req.method === "GET") ||
          ([
            "login",
            "confirm",
            "collect",
            "disconnect",
            "cancel",
            "enable",
            "disable",
          ].includes(action) &&
            req.method === "POST")
        ) {
          return await cloudLinkedin(env, action);
        }
        return json({ error: "Rota não encontrada." }, 404);
      }
      if (url.pathname === "/api/state" && req.method === "GET") {
        const [config, p, sources, jobs, events, usage, collector] =
          await Promise.all([
            settings(env),
            profile(env),
            env.DB.prepare(
              "SELECT * FROM sources ORDER BY value LIMIT 2000",
            ).all(),
            env.DB.prepare(
              "SELECT id,title,company,location,url,status,score,analysis,draft,proof,created_at FROM jobs ORDER BY created_at DESC LIMIT 200",
            ).all(),
            env.DB.prepare(
              "SELECT * FROM events ORDER BY id DESC LIMIT 30",
            ).all(),
            env.DB.prepare(
              "SELECT kind,count FROM usage WHERE day=date('now')",
            ).all(),
            env.DB.prepare(
              "SELECT detail,created_at FROM events WHERE kind='linkedin_collector' ORDER BY id DESC LIMIT 1",
            ).first(),
          ]);
        return json({
          config,
          profile: p
            ? {
                id: p.id,
                filename: p.filename,
                data: p.data,
                confirmed: !!p.confirmed,
              }
            : null,
          sources: sources.results,
          jobs: jobs.results,
          events: events.results,
          usage: usage.results,
          collector,
          capabilities: {
            ai: !!(env.GEMINI_API_KEY || env.GROQ_API_KEY),
            email: emailConfigured(env),
            browser: !!env.BROWSER,
          },
        });
      }
      if (url.pathname === "/api/settings" && req.method === "PUT") {
        const config = validateSettings(await body(req));
        await mutateProfile(env, async () => {
          await env.DB.batch([
            env.DB.prepare("UPDATE settings SET data=? WHERE id=1").bind(
              JSON.stringify(config),
            ),
            env.DB.prepare(
              "UPDATE jobs SET status='discovered',analysis=NULL,draft=NULL,score=NULL WHERE status IN ('matched','rejected','needs_input')",
            ),
          ]);
        });
        return json({ ok: true });
      }
      if (url.pathname === "/api/resume" && req.method === "POST") {
        if (Number(req.headers.get("Content-Length")) > LIMITS.pdf + 10000)
          throw new Error("PDF deve ter no máximo 1 MB.");
        const f = (await req.formData()).get("file");
        if (
          !f ||
          typeof f.arrayBuffer !== "function" ||
          f.size > LIMITS.pdf ||
          !f.size
        )
          throw new Error("Selecione um PDF de até 1 MB.");
        const bytes = new Uint8Array(await f.arrayBuffer());
        if (new TextDecoder().decode(bytes.slice(0, 5)) !== "%PDF-")
          throw new Error("Arquivo PDF inválido.");
        return await mutateProfile(env, async () => {
          const pdf = Buffer.from(bytes).toString("base64");
          const data = await ai(env, resumePrompt, pdf);
          if (
            typeof data.text !== "string" ||
            data.text.length < 80 ||
            data.text.length > 60000 ||
            !data.fields ||
            !Array.isArray(data.skills)
          )
            throw new Error("Não foi possível extrair o currículo.");
          const id = crypto.randomUUID();
          await env.DB.batch([
            env.DB.prepare(
              "INSERT INTO profiles(id,filename,pdf,data) VALUES(?,?,?,?)",
            ).bind(id, String(f.name).slice(0, 200), pdf, JSON.stringify(data)),
            env.DB.prepare(
              "UPDATE jobs SET status='discovered',analysis=NULL,draft=NULL,score=NULL WHERE status IN ('matched','rejected','needs_input')",
            ),
          ]);
          return json({ ok: true, id });
        });
      }
      if (url.pathname === "/api/profile/confirm" && req.method === "POST") {
        const input = await body(req);
        return await mutateProfile(env, async () => {
          const p = await profile(env);
          if (!p || p.id !== input.id) throw new Error("Perfil desatualizado.");
          if (
            typeof input.text !== "string" ||
            input.text.length < 80 ||
            input.text.length > 60000
          )
            throw new Error("Revise o texto extraído.");
          const fields = {};
          for (const [k, v] of Object.entries(input.fields || {}))
            if (typeof v === "string" && k.length < 100)
              fields[k] = v.slice(0, 2000);
          const data = { ...p.data, text: input.text, fields };
          const config = await settings(env);
          const keywords = resumeKeywords(data.skills);
          if (keywords) config.keywords = keywords;
          await env.DB.batch([
            env.DB.prepare("UPDATE settings SET data=? WHERE id=1").bind(
              JSON.stringify(config),
            ),
            env.DB.prepare(
              "INSERT INTO profiles(id,filename,pdf,data,confirmed) VALUES(?,?,?,?,1)",
            ).bind(
              crypto.randomUUID(),
              p.filename,
              p.pdf,
              JSON.stringify(data),
            ),
            env.DB.prepare(
              "UPDATE jobs SET status='discovered',analysis=NULL,draft=NULL,score=NULL WHERE status IN ('matched','rejected','needs_input')",
            ),
          ]);
          return json({ ok: true });
        });
      }
      if (
        url.pathname === "/api/linkedin/collector-config" &&
        req.method === "GET"
      ) {
        const config = await settings(env),
          p = await profile(env);
        return json({ config, confirmed: !!p?.confirmed });
      }
      if (
        url.pathname === "/api/linkedin/collector-status" &&
        req.method === "POST"
      ) {
        const input = await body(req);
        const labels = {
          running: "Coleta local iniciada",
          completed: "Coleta local concluída",
          no_results:
            "Coleta local sem posts legíveis; verifique os termos ou o layout do LinkedIn",
          login_required:
            "Coletor local precisa de login ou verificação no navegador",
          error: "Coletor local interrompido; consulte o terminal",
          paused: "Coletor local pausado pelo agendamento",
        };
        if (!Object.hasOwn(labels, input.state))
          throw new Error("Estado de coletor inválido.");
        const count = Number(input.count || 0);
        if (!Number.isInteger(count) || count < 0 || count > 100)
          throw new Error("Contagem inválida.");
        await event(
          env,
          "linkedin_collector",
          `${labels[input.state]}. ${count} novos posts.`,
        );
        return json({ ok: true });
      }
      if (url.pathname === "/api/linkedin/import" && req.method === "POST") {
        const input = await body(req);
        const postUrl = linkedinUrl(input.url);
        return await mutateProfile(env, async () => {
          let text = input.text;
          if (!text) {
            try {
              text = parseLinkedinPost(await fetchText(postUrl));
            } catch {
              throw new Error(
                "Não foi possível ler o post público. Cole o texto integral do post e importe novamente.",
              );
            }
          }
          const job = linkedinJob({ ...input, url: postUrl }, text);
          const id = await digest("linkedin:" + postUrl);
          const saved = await saveJobs(
            env,
            { id, kind: "linkedin", value: postUrl },
            { keywords: "" },
            [job],
          );
          return json({ ok: true, saved });
        });
      }
      if (url.pathname === "/api/sources" && req.method === "POST") {
        const input = await body(req);
        const entries = input.sources;
        if (!Array.isArray(entries) || !entries.length || entries.length > 100)
          throw new Error("Importe de 1 a 100 fontes por vez.");
        const count = await env.DB.prepare(
          "SELECT count(*) AS n FROM sources",
        ).first();
        if (count.n + entries.length > LIMITS.sources)
          throw new Error("Catálogo limitado a 2.000 fontes.");
        const specs = entries.map((s) =>
          sourceSpec(s.kind, String(s.value || "").trim()),
        );
        const statements = [];
        for (const s of specs)
          statements.push(
            env.DB.prepare(
              "INSERT OR IGNORE INTO sources(id,kind,value,region) VALUES(?,?,?,?)",
            ).bind(
              await digest(s.kind + ":" + s.value),
              s.kind,
              s.value,
              input.region === "BR" ? "BR" : "global",
            ),
          );
        await env.DB.batch(statements);
        return json({ ok: true });
      }
      if (url.pathname === "/api/source/toggle" && req.method === "POST") {
        const input = await body(req);
        await env.DB.prepare("UPDATE sources SET enabled=? WHERE id=?")
          .bind(input.enabled === true ? 1 : 0, String(input.id))
          .run();
        return json({ ok: true });
      }
      if (url.pathname === "/api/run" && req.method === "POST") {
        // Keep the request alive: browser jobs can exceed waitUntil's 30-second lifetime.
        await tick(env, true);
        return json({ ok: true });
      }
      if (url.pathname === "/api/apply" && req.method === "POST") {
        const input = await body(req);
        await tick(env, true, String(input.id));
        return json({ ok: true });
      }
      if (url.pathname === "/api/job/reconcile" && req.method === "POST") {
        const input = await body(req);
        if (!["submitted", "discovered"].includes(input.status))
          throw new Error("Estado inválido.");
        if (input.confirmed !== true)
          throw new Error("Confirme a verificação no destino.");
        await mutateProfile(env, async () => {
          await env.DB.prepare(
            "UPDATE jobs SET status=?,proof=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('unknown','needs_input')",
          )
            .bind(
              input.status,
              "Estado verificado manualmente pelo usuário.",
              String(input.id),
            )
            .run();
          await event(
            env,
            "manual_reconciliation",
            input.status,
            String(input.id),
          );
        });
        return json({ ok: true });
      }
      return json({ error: "Rota não encontrada." }, 404);
    } catch (e) {
      return json(
        { error: e.message || "Não foi possível concluir a operação." },
        400,
      );
    }
  },
  async scheduled(controller, env, ctx) {
    // Processing is bounded to one source, one analysis, and optionally one application.
    // Keep automatic processing disabled until the owner confirms the profile/preferences.
    try {
      await tick(env, false);
      if (env.LINKEDIN_CLOUD) await cloudLinkedin(env, "scheduled");
    } catch (e) {
      await event(env, "run_error", e.message).catch(() => {});
    }
  },
};
