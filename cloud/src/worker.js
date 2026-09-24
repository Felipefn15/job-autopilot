import { digest } from "./core.js";
import { event } from "./db.js";
import { tick } from "./pipeline.js";
import { cloudLinkedin } from "./linkedin-cloud.js";
import { handleApi } from "./api.js";
import { authRoute, currentUser, validOrigin } from "./auth.js";
export { LinkedInCloud } from "./linkedin-cloud.js";
export { UserWorkspace } from "./user-workspace.js";
const reply = (error, status) =>
  Response.json(
    { error },
    { status, headers: { "Cache-Control": "no-store" } },
  );
async function admin(req, env) {
  const supplied = req.headers.get("Authorization") || "";
  return (
    !!env.APP_TOKEN &&
    env.APP_TOKEN.length >= 32 &&
    supplied.length <= 300 &&
    (await digest(supplied)) === (await digest("Bearer " + env.APP_TOKEN))
  );
}
function forward(req, user, env) {
  const headers = new Headers(req.headers);
  headers.delete("Authorization");
  headers.delete("Cookie");
  headers.set("X-Account-Id", user.id);
  headers.set("X-Account-Name", encodeURIComponent(user.name));
  headers.set("X-Account-Email", user.email);
  return env.USER_WORKSPACES.get(env.USER_WORKSPACES.idFromName(user.id)).fetch(
    new Request(req, { headers }),
  );
}
export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(req);
    if (!env.DB) return reply("Banco de dados não configurado.", 503);
    try {
      if (url.pathname.startsWith("/api/auth/"))
        return await authRoute(req, env);
      if (await admin(req, env)) {
        if (
          req.method !== "GET" &&
          req.headers.get("Origin") &&
          req.headers.get("Origin") !== url.origin
        )
          return reply("Origem não permitida.", 403);
        return await handleApi(req, env, ctx);
      }
      const user = await currentUser(req, env);
      if (!user) return reply("Entre na sua conta para continuar.", 401);
      if (req.method !== "GET" && !validOrigin(req))
        return reply("Origem não permitida.", 403);
      if (!env.USER_WORKSPACES)
        return reply(
          "Área do usuário indisponível. Atualize a configuração da hospedagem.",
          503,
        );
      return await forward(req, user, env);
    } catch {
      return reply(
        "Não foi possível concluir a operação. Tente novamente.",
        500,
      );
    }
  },
  async scheduled(controller, env, ctx) {
    await env.DB.batch([
      env.DB.prepare("DELETE FROM auth_sessions WHERE expires<?").bind(
        Date.now(),
      ),
      env.DB.prepare("DELETE FROM auth_limits WHERE expires<?").bind(
        Date.now(),
      ),
    ]);
    try {
      await tick(env, false);
      if (env.LINKEDIN_CLOUD) await cloudLinkedin(env, "scheduled");
    } catch (e) {
      await event(env, "run_error", e.message).catch(() => {});
    }
    if (!env.USER_WORKSPACES) return;
    const users = await env.DB.prepare(
      "SELECT id,name,email FROM auth_users WHERE schedule_enabled=1 ORDER BY last_scheduled ASC,id LIMIT 3",
    ).all();
    for (const user of users.results) {
      await env.DB.prepare(
        "UPDATE auth_users SET last_scheduled=CURRENT_TIMESTAMP WHERE id=?",
      )
        .bind(user.id)
        .run();
      try {
        await forward(
          new Request("https://internal/internal/scheduled", {
            method: "POST",
          }),
          user,
          env,
        );
      } catch {
        /* The next cron resumes this user's rotation. */
      }
    }
  },
};
