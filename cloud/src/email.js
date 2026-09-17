import { emailAddress, validateDraft } from "./core.js";
const base64 = (s) => Buffer.from(s, "utf8").toString("base64");
export function mimeMessage(from, to, draft, pdf, id) {
  from = emailAddress(from);
  to = emailAddress(to);
  const boundary = "autopilot_" + id.replace(/[^a-z0-9]/gi, "");
  if (/[\r\n]/.test(draft.subject)) throw new Error("Assunto inválido.");
  const messageId = `<${id}@job-autopilot.local>`;
  const mime = [
    `From: ${from}`,
    `To: ${to}`,
    `Subject: =?UTF-8?B?${base64(draft.subject)}?=`,
    `Message-ID: ${messageId}`,
    "MIME-Version: 1.0",
    `Content-Type: multipart/mixed; boundary="${boundary}"`,
    "",
    `--${boundary}`,
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
    "",
    base64(draft.body),
    `--${boundary}`,
    'Content-Type: application/pdf; name="resume.pdf"',
    'Content-Disposition: attachment; filename="resume.pdf"',
    "Content-Transfer-Encoding: base64",
    "",
    pdf.match(/.{1,76}/g).join("\r\n"),
    `--${boundary}--`,
    "",
  ].join("\r\n");
  return { raw: Buffer.from(mime).toString("base64url"), messageId };
}
export function emailConfigured(env) {
  return [
    "GMAIL_CLIENT_ID",
    "GMAIL_CLIENT_SECRET",
    "GMAIL_REFRESH_TOKEN",
    "GMAIL_FROM",
  ].every((k) => !!env[k]);
}
export async function sendEmail(env, job, p, markSending) {
  if (!emailConfigured(env))
    throw new Error("Configure a conta Gmail antes do envio.");
  const draft = validateDraft(JSON.parse(job.draft), p.data);
  const auth = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env.GMAIL_CLIENT_ID,
      client_secret: env.GMAIL_CLIENT_SECRET,
      refresh_token: env.GMAIL_REFRESH_TOKEN,
      grant_type: "refresh_token",
    }),
    signal: AbortSignal.timeout(15000),
  });
  if (!auth.ok) throw new Error("Gmail não autorizado.");
  const token = await auth.json();
  if (!token.access_token) throw new Error("Gmail não autorizado.");
  const { raw, messageId } = mimeMessage(
    env.GMAIL_FROM,
    job.email,
    draft,
    p.pdf,
    job.id,
  );
  await markSending();
  const r = await fetch(
    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token.access_token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ raw }),
      signal: AbortSignal.timeout(20000),
    },
  );
  if (!r.ok)
    throw new Error(
      `Envio sem confirmação (HTTP ${r.status}). Verifique a pasta Enviados antes de repetir.`,
    );
  const sent = await r.json();
  if (!sent.id)
    throw new Error("Gmail não confirmou o identificador da mensagem.");
  return JSON.stringify({
    provider: "gmail",
    id: sent.id,
    messageId,
    meaning: "accepted by Gmail; delivery not guaranteed",
  });
}
