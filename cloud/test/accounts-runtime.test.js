import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { build } from "esbuild";
import { Miniflare } from "miniflare";

test("Worker runtime: account cookies route to isolated SQLite workspaces, legacy data stays private", async () => {
  const bundle = await build({
    entryPoints: ["src/worker.js"],
    bundle: true,
    write: false,
    format: "esm",
    platform: "node",
    external: ["cloudflare:*", "node:*"],
  });
  const mf = new Miniflare({
    unsafeInspectDurableObjects: true,
    workers: [
      {
        config: {
          name: "accounts-test",
          type: "worker",
          compatibilityDate: "2026-09-17",
          compatibilityFlags: ["nodejs_compat"],
          manifest: {
            mainModule: "index.js",
            modules: {
              "index.js": { type: "esm", contents: bundle.outputFiles[0].text },
            },
          },
          env: {
            DB: { type: "d1", id: "test-auth" },
            USER_WORKSPACES: {
              type: "durable-object",
              worker: "accounts-test",
              exportName: "UserWorkspace",
            },
            APP_TOKEN: {
              type: "text",
              value: "test-only-administrative-key-123456789",
            },
            GMAIL_FROM: { type: "text", value: "owner@example.com" },
            GMAIL_CLIENT_ID: { type: "text", value: "id" },
            GMAIL_CLIENT_SECRET: { type: "text", value: "secret" },
            GMAIL_REFRESH_TOKEN: { type: "text", value: "refresh" },
          },
          exports: {
            UserWorkspace: { type: "durable-object", storage: "sqlite" },
          },
        },
      },
    ],
  });
  try {
    const db = await mf.getD1Database("DB");
    for (const f of readdirSync("migrations").sort())
      await db.exec(
        readFileSync("migrations/" + f, "utf8")
          .replace(/^--.*$/gm, "")
          .replace(/\n/g, " "),
      );
    await db
      .prepare(
        "INSERT INTO profiles(id,filename,pdf,data,confirmed) VALUES(?,?,?,?,1)",
      )
      .bind(
        "legacy",
        "Owner.pdf",
        "private",
        '{"text":"private owner resume","fields":{"name":"Owner"}}',
      )
      .run();
    const call = (path, body, cookie, extra = {}) =>
      mf.dispatchFetch("https://app.test/api/" + path, {
        method: body === undefined ? "GET" : "POST",
        headers: {
          Origin: "https://app.test",
          "X-Requested-With": "JobAutopilot",
          "Content-Type": "application/json",
          ...(cookie ? { Cookie: cookie } : {}),
          ...extra,
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
    const register = async (email, name) => {
      const r = await call("auth/register", {
        email,
        name,
        password: "Account-password-123",
      });
      assert.equal(r.status, 201, await r.clone().text());
      return {
        cookie: r.headers.get("set-cookie").split(";")[0],
        ...(await r.json()),
      };
    };
    const a = await register("ana@example.com", "Ana"),
      b = await register("bia@example.com", "Bia");
    assert.equal((await call("state")).status, 401);
    const sa = await call("state", undefined, a.cookie);
    assert.equal(sa.status, 200, await sa.clone().text());
    const stateA = await sa.json();
    assert.equal(stateA.profile, null);
    assert.equal(stateA.user.name, "Ana");
    assert.equal(stateA.capabilities.email, false);
    assert.equal(stateA.sources.length, 92);
    const sb = await (
      await call("state", undefined, b.cookie, { "X-Account-Id": a.user.id })
    ).json();
    assert.equal(sb.user.id, b.user.id);
    const storage = await mf.unsafeGetDurableObjectStorage(
      "accounts-test",
      "UserWorkspace",
      { name: a.user.id },
    );
    await storage.exec(
      "INSERT INTO profiles(id,filename,pdf,data,confirmed) VALUES(?,?,?,?,0)",
      "private-a",
      "Ana.pdf",
      "pdf",
      '{"text":"Only Ana may read this resume. Experience in project management and agile delivery with cross functional teams.","fields":{"name":"Ana"},"skills":["Scrum"]}',
    );
    assert.equal(
      (await (await call("state", undefined, a.cookie)).json()).profile.id,
      "private-a",
    );
    assert.equal(
      (await (await call("state", undefined, b.cookie)).json()).profile,
      null,
    );
    assert.equal(
      (
        await call(
          "profile/confirm",
          { id: "private-a", text: "x".repeat(100), fields: {} },
          b.cookie,
        )
      ).status,
      400,
    );
    await storage.exec(
      "INSERT INTO jobs(id,title,company,location,url,description) VALUES('a-job','Secret role','A','BR','https://example.com/job','Private description for Ana')",
    );
    assert.equal(
      (await call("job-description?id=a-job", undefined, b.cookie)).status,
      404,
    );
    assert.equal(
      (await call("job-description?id=a-job", undefined, a.cookie)).status,
      200,
    );
    const cross = await call("run", {}, a.cookie, {
      Origin: "https://evil.test",
    });
    assert.equal(cross.status, 403);
    const legacy = await (
      await call("state", undefined, null, {
        Authorization: "Bearer test-only-administrative-key-123456789",
      })
    ).json();
    assert.equal(legacy.profile.id, "legacy");
    const confirm = await call(
      "profile/confirm",
      {
        id: "private-a",
        text: "Only Ana may read this resume. Experience in project management and agile delivery with cross functional teams.",
        fields: { name: "Ana" },
      },
      a.cookie,
    );
    assert.equal(confirm.status, 200, await confirm.text());
    const confirmed = await (await call("state", undefined, a.cookie)).json();
    assert.equal(confirmed.profile.confirmed, true);
    const config = {
      ...confirmed.config,
      targetRoles: "Scrum Master",
      enabled: true,
    };
    const updated = await mf.dispatchFetch("https://app.test/api/settings", {
      method: "PUT",
      headers: {
        Cookie: a.cookie,
        Origin: "https://app.test",
        "X-Requested-With": "JobAutopilot",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(config),
    });
    assert.equal(updated.status, 200, await updated.text());
    assert.equal(
      (await (await call("state", undefined, b.cookie)).json()).config
        .targetRoles,
      "",
    );
    assert.equal(
      (
        await db
          .prepare("SELECT schedule_enabled FROM auth_users WHERE id=?")
          .bind(a.user.id)
          .first()
      ).schedule_enabled,
      1,
    );
    await call("auth/logout", {}, a.cookie);
    assert.equal((await call("state", undefined, a.cookie)).status, 401);
  } finally {
    await mf.dispose();
  }
});
