export function sessionKeyReady(secret) {
  return typeof secret === "string" && /^[0-9a-f]{64}$/i.test(secret);
}
async function key(secret) {
  if (!sessionKeyReady(secret))
    throw new Error(
      "Configure LINKEDIN_SESSION_KEY: 64 caracteres hexadecimais.",
    );
  return crypto.subtle.importKey(
    "raw",
    Uint8Array.from(secret.match(/../g), (x) => parseInt(x, 16)),
    "AES-GCM",
    false,
    ["encrypt", "decrypt"],
  );
}
const aad = new TextEncoder().encode("job-autopilot:linkedin:v1");
export async function sealSession(value, secret) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = new TextEncoder().encode(JSON.stringify(value));
  if (plaintext.length > 100000)
    throw new Error("Estado de sessão excede o limite de armazenamento.");
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: aad },
    await key(secret),
    plaintext,
  );
  return {
    v: 1,
    iv: Array.from(iv),
    data: new Uint8Array(ciphertext),
  };
}
export async function openSession(value, secret) {
  if (value?.v !== 1) throw new Error("Sessão inválida.");
  const raw = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: new Uint8Array(value.iv), additionalData: aad },
    await key(secret),
    new Uint8Array(value.data),
  );
  return JSON.parse(new TextDecoder().decode(raw));
}
export function linkedinQuery(config, cursor = 0) {
  const terms = String(config.targetRoles || config.keywords || "")
    .split(",")
    .map((t) => t.replace(/[^\p{L}\p{N} .+#-]/gu, "").trim())
    .filter(Boolean)
    .slice(0, 18);
  if (!terms.length)
    throw new Error("Salve as tecnologias nas preferências antes de buscar.");
  const groups = Math.ceil(terms.length / 3),
    index = Math.max(0, Number(cursor) || 0) % groups;
  const country = String(config.country || "global").replace(
    /[^\p{L}\p{N} .-]/gu,
    "",
  );
  const region = /^(global|world|mundo)$/i.test(country)
    ? ""
    : /^latam$/i.test(country)
      ? ' (LATAM OR "Latin America" OR "América Latina")'
      : ` "${country}"`;
  return {
    text: `(${terms
      .slice(index * 3, index * 3 + 3)
      .map((t) => `"${t.slice(0, 60)}"`)
      .join(
        " OR ",
      )}) (vaga OR contratando OR hiring)${region}${config.remoteOnly ? " (remoto OR remote)" : ""}`,
    next: (index + 1) % groups,
  };
}
export function canonicalCloudPost(value) {
  try {
    const u = new URL(value);
    if (
      u.protocol !== "https:" ||
      !["linkedin.com", "www.linkedin.com"].includes(u.hostname) ||
      u.username ||
      u.password
    )
      return null;
    const m = u.pathname.match(/(?:urn:li:activity:|activity-)(\d+)/);
    if (m)
      return `https://www.linkedin.com/feed/update/urn:li:activity:${m[1]}/`;
    if (/^\/posts\/[^/]+\/?$/.test(u.pathname))
      return `https://www.linkedin.com${u.pathname.replace(/\/$/, "")}`;
  } catch {}
  return null;
}
// Reserve maximum active time plus a 60-second idle cleanup allowance. Never refund.
// Existing browser runs on migration day are conservatively included in the first reservation.
export async function reserveBrowserSeconds(env, seconds) {
  if (!Number.isInteger(seconds) || seconds < 1 || seconds > 540) return false;
  if (
    new Date().toISOString().slice(0, 10) !==
    new Date(Date.now() + seconds * 1000).toISOString().slice(0, 10)
  )
    return false;
  const row = await env.DB.prepare(
    "INSERT INTO usage(day,kind,count) SELECT date('now'),'browser_seconds',? + COALESCE((SELECT count*150 FROM usage WHERE day=date('now') AND kind='browser'),0) WHERE ? + COALESCE((SELECT count*150 FROM usage WHERE day=date('now') AND kind='browser'),0) <= 540 ON CONFLICT(day,kind) DO UPDATE SET count=count+? WHERE count+?<=540 RETURNING count",
  )
    .bind(seconds, seconds, seconds, seconds)
    .first();
  return !!row;
}
