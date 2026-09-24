import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { authRoute, currentUser, passwordMatches } from "../src/auth.js";
function fixture() {
  const db = new DatabaseSync(":memory:");
  db.exec(
    readFileSync(
      new URL("../migrations/0013_user_accounts.sql", import.meta.url),
      "utf8",
    ),
  );
  const DB = {
    prepare(sql) {
      let args = [];
      return {
        bind(...values) {
          args = values;
          return this;
        },
        async first() {
          return db.prepare(sql).get(...args) || null;
        },
        async all() {
          return { results: db.prepare(sql).all(...args) };
        },
        async run() {
          return { meta: db.prepare(sql).run(...args) };
        },
        _sql: sql,
        _args: () => args,
      };
    },
    async batch(items) {
      db.exec("BEGIN");
      try {
        const results = items.map((s) => ({
          results: db.prepare(s._sql).all(...s._args()),
        }));
        db.exec("COMMIT");
        return results;
      } catch (e) {
        db.exec("ROLLBACK");
        throw e;
      }
    },
  };
  return { db, DB };
}
const req = (action, body, cookie, origin = "https://app.test") =>
  new Request("https://app.test/api/auth/" + action, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: origin,
      "X-Requested-With": "JobAutopilot",
      ...(cookie ? { Cookie: cookie } : {}),
    },
    body: JSON.stringify(body),
  });
const session = (response) => response.headers.get("set-cookie")?.split(";")[0];
test("registration stores salted hashes, secure session; login, logout and recovery invalidate access", async () => {
  const env = fixture();
  try {
    const input = {
      email: "USER@EXAMPLE.COM",
      name: "Ana",
      password: "Example-password-123",
    };
    const r = await authRoute(req("register", input), env);
    assert.equal(r.status, 201);
    const body = await r.json(),
      cookie = session(r);
    assert.match(
      r.headers.get("set-cookie"),
      /HttpOnly; Secure; SameSite=Strict/,
    );
    const stored = env.db.prepare("SELECT * FROM auth_users").get();
    assert.notEqual(stored.password_hash, input.password);
    assert.notEqual(stored.recovery_hash, body.recoveryCode);
    assert.equal(
      await passwordMatches(input.password, stored.password_hash),
      true,
    );
    const read = () =>
      currentUser(
        new Request("https://app.test/api/state", {
          headers: { Cookie: cookie },
        }),
        env,
      );
    assert.equal((await read()).email, "user@example.com");
    assert.equal(
      (
        await authRoute(
          req("login", { ...input, password: "wrong-password-123" }),
          env,
        )
      ).status,
      401,
    );
    const second = await authRoute(req("login", input), env);
    assert.equal(second.status, 200);
    const recovered = await authRoute(
      req("recover", {
        email: input.email,
        password: "Changed-password-123",
        recoveryCode: body.recoveryCode,
      }),
      env,
    );
    assert.equal(recovered.status, 200);
    assert.equal(await read(), null);
    assert.equal(
      await currentUser(
        new Request("https://app.test/", {
          headers: { Cookie: session(second) },
        }),
        env,
      ),
      null,
    );
    assert.equal(
      (
        await authRoute(
          req("recover", {
            email: input.email,
            password: "Changed-password-123",
            recoveryCode: body.recoveryCode,
          }),
          env,
        )
      ).status,
      401,
    );
    const newCookie = session(recovered);
    assert.ok(
      await currentUser(
        new Request("https://app.test/", { headers: { Cookie: newCookie } }),
        env,
      ),
    );
    await authRoute(req("logout", {}, newCookie), env);
    assert.equal(
      await currentUser(
        new Request("https://app.test/", { headers: { Cookie: newCookie } }),
        env,
      ),
      null,
    );
  } finally {
    env.db.close();
  }
});
test("auth rejects cross-site writes, missing session, duplicate account, malformed and weak credentials; throttles login", async () => {
  const env = fixture();
  try {
    const input = {
      email: "a@example.com",
      name: "Alice",
      password: "Strong-password-123",
    };
    assert.equal(
      (await authRoute(req("register", input, null, "https://evil.test"), env))
        .status,
      403,
    );
    assert.equal(
      (await authRoute(req("register", { ...input, password: "short" }), env))
        .status,
      400,
    );
    assert.equal((await authRoute(req("register", null), env)).status, 400);
    assert.equal((await authRoute(req("password", input), env)).status, 401);
    assert.equal((await authRoute(req("register", input), env)).status, 201);
    assert.equal((await authRoute(req("register", input), env)).status, 409);
    for (let i = 0; i < 10; i++)
      assert.equal(
        (
          await authRoute(
            req("login", { ...input, password: "Wrong-password-123" }),
            env,
          )
        ).status,
        401,
      );
    assert.equal((await authRoute(req("login", input), env)).status, 429);
  } finally {
    env.db.close();
  }
});

test("password change revokes old sessions and absolute expiry prevents reuse", async () => {
  const env = fixture();
  try {
    const registration = await authRoute(
      req("register", {
        email: "expiry@example.com",
        name: "Eva",
        password: "Initial-password-123",
      }),
      env,
    );
    const oldCookie = session(registration);
    const changed = await authRoute(
      req(
        "password",
        {
          currentPassword: "Initial-password-123",
          password: "Updated-password-123",
        },
        oldCookie,
      ),
      env,
    );
    assert.equal(changed.status, 200);
    assert.equal(
      await currentUser(
        new Request("https://app.test/", { headers: { Cookie: oldCookie } }),
        env,
      ),
      null,
    );
    const newCookie = session(changed);
    assert.ok(
      await currentUser(
        new Request("https://app.test/", { headers: { Cookie: newCookie } }),
        env,
      ),
    );
    env.db.exec("UPDATE auth_sessions SET expires=0");
    assert.equal(
      await currentUser(
        new Request("https://app.test/", { headers: { Cookie: newCookie } }),
        env,
      ),
      null,
    );
  } finally {
    env.db.close();
  }
});
