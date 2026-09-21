import test from "node:test";
import assert from "node:assert/strict";
import { ai, pdfText } from "../src/ai.js";

function environment(limit = 30) {
  let used = 0;
  return {
    GEMINI_API_KEY: "test-gemini",
    GROQ_API_KEY: "test-groq",
    DAILY_AI_LIMIT: String(limit),
    get used() {
      return used;
    },
    DB: {
      prepare() {
        return {
          bind(_kind, max) {
            return {
              async first() {
                return used < max ? { count: ++used } : null;
              },
            };
          },
        };
      },
    },
  };
}
const geminiOK = () =>
  Response.json({
    candidates: [
      { finishReason: "STOP", content: { parts: [{ text: '{"ok":true}' }] } },
    ],
  });
const groqOK = (finish = "stop", content = '{"ok":true}') =>
  Response.json({ choices: [{ finish_reason: finish, message: { content } }] });

function mockFetch(t, replies) {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, ...options, body: JSON.parse(options.body) });
    assert.ok(replies.length, "unexpected extra API request");
    return replies.shift()();
  });
  return calls;
}

test("Gemini success never calls Groq", async (t) => {
  const e = environment();
  const calls = mockFetch(t, [geminiOK]);
  assert.deepEqual(await ai(e, "JSON please"), { ok: true });
  assert.equal(calls.length, 1);
  assert.equal(e.used, 1);
});
test("Gemini 429 falls back once to Groq and counts both attempts", async (t) => {
  const e = environment();
  const calls = mockFetch(t, [
    () => new Response("quota", { status: 429 }),
    groqOK,
  ]);
  assert.deepEqual(await ai(e, "JSON please"), { ok: true });
  assert.equal(e.used, 2);
  assert.equal(calls[1].url, "https://api.groq.com/openai/v1/chat/completions");
  assert.equal(calls[1].headers.Authorization, "Bearer test-groq");
  assert.equal(calls[1].body.response_format.type, "json_object");
  assert.equal(calls[1].body.messages[1].content, "JSON please");
});
test("local budget cannot be bypassed with a fallback", async (t) => {
  const e = environment(1);
  const calls = mockFetch(t, [() => new Response("quota", { status: 429 })]);
  await assert.rejects(ai(e, "JSON"), /Cota diária/);
  assert.equal(calls.length, 1);
});
test("authentication errors do not trigger fallback", async (t) => {
  const calls = mockFetch(t, [
    () => new Response("secret must not leak", { status: 401 }),
  ]);
  await assert.rejects(
    ai(environment(), "JSON"),
    /Gemini indisponível \(HTTP 401\)/,
  );
  assert.equal(calls.length, 1);
});
test("unconfigured Groq preserves Gemini quota error", async (t) => {
  const e = environment();
  delete e.GROQ_API_KEY;
  mockFetch(t, [() => new Response("quota", { status: 429 })]);
  await assert.rejects(ai(e, "JSON"), /HTTP 429/);
});
test("Groq exhaustion ends without retrying either provider", async (t) => {
  const calls = mockFetch(t, [
    () => new Response("quota", { status: 429 }),
    () => new Response("quota", { status: 429 }),
  ]);
  await assert.rejects(ai(environment(), "JSON"), /Groq indisponível/);
  assert.equal(calls.length, 2);
});
test("Groq-only mode rejects truncated and malformed JSON", async (t) => {
  const e = environment();
  delete e.GEMINI_API_KEY;
  mockFetch(t, [() => groqOK("length"), () => groqOK("stop", "not JSON")]);
  await assert.rejects(ai(e, "JSON"), /não concluiu/);
  await assert.rejects(ai(e, "JSON"));
});

// Minimal real PDF, generated in-memory without personal data.
function samplePDF(text) {
  const stream = `BT /F1 12 Tf 50 700 Td (${text}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, i) => {
    offsets.push(pdf.length);
    pdf += `${i + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = pdf.length;
  pdf += `xref\n0 6\n0000000000 65535 f \n${offsets
    .slice(1)
    .map((n) => String(n).padStart(10, "0") + " 00000 n \n")
    .join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return btoa(pdf);
}
test("PDF fallback sends extracted text, preserves it and never sends raw PDF to Groq", async (t) => {
  const text = "Test Developer - React and Node experience";
  const pdf = samplePDF(text);
  const calls = mockFetch(t, [
    () => new Response("quota", { status: 429 }),
    () => groqOK("stop", '{"text":"invented","fields":{}}'),
  ]);
  const result = await ai(environment(), "Extract resume as JSON", pdf);
  assert.equal(result.text.trim(), text);
  assert.ok(calls[1].body.messages[1].content.includes(text));
  assert.ok(!JSON.stringify(calls[1].body).includes(pdf));
});
test("PDF without selectable text fails explicitly", async () => {
  await assert.rejects(pdfText(samplePDF("")), /PDF sem texto suficiente/);
});
