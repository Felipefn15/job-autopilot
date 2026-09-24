import { DurableObject } from "cloudflare:workers";
import { migrations } from "./workspace-schema.js";
import { workspaceDB } from "./workspace-db.js";
import { handleApi } from "./api.js";
import { LinkedInCloud } from "./linkedin-cloud.js";
import { settings, event } from "./db.js";
import { tick } from "./pipeline.js";
export class UserWorkspace extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.ctx = ctx;
    this.env = { ...env, GLOBAL_DB: env.DB, DB: workspaceDB(ctx.storage) };
    // A new account must never send through the deployment owner's Gmail identity.
    for (const key of [
      "GMAIL_CLIENT_ID",
      "GMAIL_CLIENT_SECRET",
      "GMAIL_REFRESH_TOKEN",
      "GMAIL_FROM",
    ])
      delete this.env[key];
    this.linkedin = new LinkedInCloud(ctx, this.env);
    this.env.USER_LINKEDIN = (action) =>
      this.linkedin.fetch(
        new Request(`https://internal/${action}`, {
          method: action === "status" ? "GET" : "POST",
        }),
      );
    ctx.blockConcurrencyWhile(async () => {
      ctx.storage.sql.exec(
        "CREATE TABLE IF NOT EXISTS workspace_migrations(name TEXT PRIMARY KEY)",
      );
      for (const migration of migrations) {
        if (
          ctx.storage.sql
            .exec(
              "SELECT name FROM workspace_migrations WHERE name=?",
              migration.name,
            )
            .toArray().length
        )
          continue;
        ctx.storage.transactionSync(() => {
          ctx.storage.sql.exec(migration.sql);
          ctx.storage.sql.exec(
            "INSERT INTO workspace_migrations(name) VALUES(?)",
            migration.name,
          );
        });
      }
      if (!(await ctx.storage.get("initialized"))) {
        const config = await settings(this.env);
        Object.assign(config, {
          keywords: "",
          targetRoles: "",
          country: "Brasil",
          sourceFocus: "brasil",
          enabled: false,
          autoApply: false,
        });
        await this.env.DB.prepare("UPDATE settings SET data=? WHERE id=1")
          .bind(JSON.stringify(config))
          .run();
        await ctx.storage.put("initialized", true);
      }
    });
  }
  async fetch(req) {
    const id = req.headers.get("X-Account-Id");
    if (!id)
      return Response.json(
        { error: "Conta não identificada." },
        { status: 403 },
      );
    const bound = await this.ctx.storage.get("account");
    if (bound && bound !== id)
      return Response.json({ error: "Conta inválida." }, { status: 403 });
    if (!bound) await this.ctx.storage.put("account", id);
    this.env.USER = {
      id,
      name: decodeURIComponent(req.headers.get("X-Account-Name") || ""),
      email: req.headers.get("X-Account-Email") || "",
    };
    if (new URL(req.url).pathname === "/internal/scheduled") {
      try {
        await tick(this.env, false);
        await this.env.USER_LINKEDIN("scheduled");
      } catch (e) {
        await event(this.env, "run_error", e.message);
      }
      return Response.json({ ok: true });
    }
    const response = await handleApi(req, this.env, this.ctx);
    if (
      new URL(req.url).pathname === "/api/settings" &&
      req.method === "PUT" &&
      response.ok
    ) {
      const config = await settings(this.env);
      await this.env.GLOBAL_DB.prepare(
        "UPDATE auth_users SET schedule_enabled=? WHERE id=?",
      )
        .bind(config.enabled ? 1 : 0, id)
        .run();
    }
    return response;
  }
  async alarm() {
    await this.linkedin.alarm();
  }
}
