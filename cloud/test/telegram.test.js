import test from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
import { Miniflare } from "miniflare";

test("Telegram public preview is parsed by the actual Worker HTMLRewriter", async () => {
  const bundle = await build({
    stdin: {
      contents: `import { telegramJobs } from './src/community.js'; export default {async fetch(request) {return Response.json(await telegramJobs(await request.text(),'frontendbrasilvagas'));}};`,
      resolveDir: process.cwd(),
    },
    bundle: true,
    write: false,
    format: "esm",
    platform: "browser",
  });
  const mf = new Miniflare({
    workers: [
      {
        config: {
          name: "telegram-test",
          type: "worker",
          compatibilityDate: "2026-09-17",
          manifest: {
            mainModule: "index.js",
            modules: {
              "index.js": { type: "esm", contents: bundle.outputFiles[0].text },
            },
          },
        },
      },
    ],
  });
  try {
    const message = (channel, id, date, text) =>
      `<div class="tgme_widget_message" data-post="${channel}/${id}"><div class="tgme_widget_message_text">${text}<br>Detalhes &amp; contato</div><a class="tgme_widget_message_date"><time datetime="${date}"></time></a></div>`;
    const html =
      message(
        "frontendbrasilvagas",
        42,
        new Date().toISOString(),
        "Vaga <b>React</b>",
      ) +
      message("frontendbrasilvagas", 41, "2020-01-01T00:00:00Z", "Antiga") +
      message("otherchannel", 999, new Date().toISOString(), "Ignorar");
    const result = await mf.dispatchFetch("https://example.com", {
      method: "POST",
      body: html,
    });
    assert.equal(result.status, 200);
    const jobs = await result.json();
    assert.equal(jobs.length, 1);
    assert.equal(jobs[0].url, "https://t.me/frontendbrasilvagas/42");
    // HTMLRewriter keeps entities in text chunks; saveJobs normalizes the body.
    assert.equal(jobs[0].description, "Vaga React\nDetalhes &amp; contato");
    assert.equal(jobs[0].title, "Vaga React Detalhes & contato");
  } finally {
    await mf.dispose();
  }
});
