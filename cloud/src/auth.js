import { digest } from "./core.js";
const COOKIE = "__Host-job_session";
const TTL = 7 * 86400;
const random = () =>
  Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString("base64url");
const reply = (body, status = 200, cookie) =>
  Response.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
      ...(cookie ? { "Set-Cookie": cookie } : {}),
    },
  });
const cookie = (value, age = TTL) =>
  `${COOKIE}=${value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${age}`;
function passwordValid(value) {
  return typeof value === "string" && value.length >= 12 && value.length <= 128;
}
export async function passwordHash(password, salt = random()) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const result = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      salt: new TextEncoder().encode(salt),
      iterations: 100000,
      hash: "SHA-256",
    },
    key,
    256,
  );
  return `pbkdf2-sha256$100000$${salt}$${Buffer.from(result).toString("base64url")}`;
}
export async function passwordMatches(password, stored) {
  const parts = String(stored || "").split("$");
  const expected =
    parts.length === 4
      ? stored
      : `pbkdf2-sha256$100000$invalid$${"0".repeat(43)}`;
  const actual = await passwordHash(
    password,
    parts.length === 4 ? parts[2] : "invalid",
  );
  let different = actual.length ^ expected.length;
  for (let i = 0; i < actual.length; i++)
    different |= actual.charCodeAt(i) ^ (expected.charCodeAt(i) || 0);
  return different === 0;
}
function sessionToken(req) {
  const value = (req.headers.get("Cookie") || "")
    .split(";")
    .map((s) => s.trim())
    .find((s) => s.startsWith(COOKIE + "="))
    ?.slice(COOKIE.length + 1);
  return /^[A-Za-z0-9_-]{43}$/.test(value || "") ? value : null;
}
export async function currentUser(req, env) {
  const token = sessionToken(req);
  if (!token) return null;
  return env.DB.prepare(
    "SELECT u.id,u.email,u.name FROM auth_sessions s JOIN auth_users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>? AND s.auth_version=u.auth_version",
  )
    .bind(await digest(token), Date.now())
    .first();
}
async function throttle(req, env, email, action) {
  const now = Date.now();
  const window = action === "register" ? 3600000 : 900000;
  const max = action === "register" ? 5 : 10;
  const keys = [
    await digest(
      `ip:${req.headers.get("CF-Connecting-IP") || "local"}:${action}`,
    ),
    await digest(`email:${email}:${action}`),
  ];
  for (const key of keys) {
    const row = await env.DB.prepare(
      "INSERT INTO auth_limits(key,count,expires) VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN expires<=? THEN 1 ELSE count+1 END,expires=CASE WHEN expires<=? THEN ? ELSE expires END WHERE expires<=? OR count<? RETURNING count",
    )
      .bind(key, now + window, now, now, now + window, now, max)
      .first();
    if (!row) return false;
  }
  return true;
}
export function validOrigin(req) {
  const origin = req.headers.get("Origin");
  return (
    origin === new URL(req.url).origin &&
    req.headers.get("X-Requested-With") === "JobAutopilot"
  );
}
export async function authRoute(req, env) {
  const action = new URL(req.url).pathname.slice("/api/auth/".length);
  if (action === "me" && req.method === "GET") {
    const user = await currentUser(req, env);
    return user
      ? reply({ user })
      : reply({ error: "Entre na sua conta para continuar." }, 401);
  }
  if (req.method !== "POST")
    return reply({ error: "Rota não encontrada." }, 404);
  if (!validOrigin(req)) return reply({ error: "Origem não permitida." }, 403);
  if (action === "logout") {
    const token = sessionToken(req);
    if (token)
      await env.DB.prepare("DELETE FROM auth_sessions WHERE token_hash=?")
        .bind(await digest(token))
        .run();
    return reply({ ok: true }, 200, cookie("", 0));
  }
  if (!["register", "login", "recover", "password"].includes(action))
    return reply({ error: "Rota não encontrada." }, 404);
  let input;
  try {
    if (Number(req.headers.get("Content-Length")) > 4096 || !req.body)
      throw Error();
    const reader = req.body.getReader(),
      decoder = new TextDecoder();
    let raw = "",
      bytes = 0;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > 4096) {
        await reader.cancel();
        throw Error();
      }
      raw += decoder.decode(value, { stream: true });
    }
    raw += decoder.decode();
    input = JSON.parse(raw);
    if (!input || Array.isArray(input) || typeof input !== "object")
      throw Error();
  } catch {
    return reply({ error: "Dados inválidos." }, 400);
  }
  const user = action === "password" ? await currentUser(req, env) : null;
  if (action === "password" && !user)
    return reply({ error: "Entre na sua conta." }, 401);
  const email = String(user?.email || input.email || "")
    .trim()
    .toLowerCase();
  if (
    !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ||
    email.length > 254 ||
    !passwordValid(input.password)
  )
    return reply(
      { error: "Informe um e-mail válido e senha de 12 a 128 caracteres." },
      400,
    );
  if (!(await throttle(req, env, email, action)))
    return reply(
      { error: "Muitas tentativas. Aguarde antes de tentar novamente." },
      429,
    );
  const record = await env.DB.prepare("SELECT * FROM auth_users WHERE email=?")
    .bind(email)
    .first();
  let account = record,
    recoveryCode;
  if (action === "register") {
    const name = String(input.name || "")
      .trim()
      .slice(0, 80);
    if (name.length < 2) return reply({ error: "Informe seu nome." }, 400);
    if (record)
      return reply(
        {
          error:
            "Não foi possível criar a conta. Tente entrar ou recuperar o acesso.",
        },
        409,
      );
    recoveryCode = random();
    account = { id: crypto.randomUUID(), name, email, auth_version: 0 };
    try {
      await env.DB.prepare(
        "INSERT INTO auth_users(id,name,email,password_hash,recovery_hash) VALUES(?,?,?,?,?)",
      )
        .bind(
          account.id,
          name,
          email,
          await passwordHash(input.password),
          await digest(recoveryCode),
        )
        .run();
    } catch {
      return reply({ error: "Não foi possível criar a conta." }, 409);
    }
  } else if (action === "login") {
    if (
      !(await passwordMatches(input.password, record?.password_hash)) ||
      !record
    )
      return reply({ error: "E-mail ou senha incorretos." }, 401);
  } else {
    const authorized =
      action === "recover"
        ? typeof input.recoveryCode === "string" &&
          input.recoveryCode.length < 100 &&
          record &&
          (await digest(input.recoveryCode.trim())) === record.recovery_hash
        : typeof input.currentPassword === "string" &&
          input.currentPassword.length <= 128 &&
          record &&
          (await passwordMatches(input.currentPassword, record.password_hash));
    if (!authorized)
      return reply(
        { error: "Não foi possível validar os dados de acesso." },
        401,
      );
    recoveryCode = random();
    const changed = await env.DB.batch([
      env.DB.prepare(
        "UPDATE auth_users SET password_hash=?,recovery_hash=?,auth_version=auth_version+1 WHERE id=? AND auth_version=? RETURNING auth_version",
      ).bind(
        await passwordHash(input.password),
        await digest(recoveryCode),
        record.id,
        record.auth_version,
      ),
      env.DB.prepare(
        "DELETE FROM auth_sessions WHERE user_id=? AND auth_version<?",
      ).bind(record.id, record.auth_version + 1),
    ]);
    if (!changed[0].results.length)
      return reply(
        { error: "Os dados de acesso mudaram. Tente novamente." },
        409,
      );
    account = { ...record, auth_version: record.auth_version + 1 };
  }
  const token = random();
  await env.DB.prepare(
    "INSERT INTO auth_sessions(token_hash,user_id,expires,auth_version) VALUES(?,?,?,?)",
  )
    .bind(
      await digest(token),
      account.id,
      Date.now() + TTL * 1000,
      account.auth_version,
    )
    .run();
  return reply(
    {
      user: { id: account.id, name: account.name, email: account.email },
      ...(recoveryCode ? { recoveryCode } : {}),
    },
    action === "register" ? 201 : 200,
    cookie(token),
  );
}
