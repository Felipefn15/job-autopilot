import { publicUrl, cleanText, digest, LIMITS } from "./core.js";
import { event } from "./db.js";
import { linkedinUrl, parseLinkedinPost, linkedinJob } from "./linkedin.js";
export function sourceSpec(kind, value) {
  if (!["greenhouse", "lever", "ashby", "page", "linkedin"].includes(kind))
    throw new Error("Fonte não suportada.");
  if (kind === "page") return { kind, value: publicUrl(value) };
  if (kind === "linkedin") return { kind, value: linkedinUrl(value) };
  if (!/^[a-zA-Z0-9_-]{1,100}$/.test(value))
    throw new Error("Use o identificador da empresa no ATS.");
  return { kind, value };
}
export async function fetchText(url, max = 2000000) {
  const u = publicUrl(url);
  const r = await fetch(u, {
    headers: {
      "User-Agent": "JobAutopilot/0.1 (+personal job search)",
      Accept: "application/json,text/html",
    },
    redirect: "manual",
    signal: AbortSignal.timeout(12000),
  });
  if (r.status >= 300 && r.status < 400)
    throw new Error("Redirecionamento: cadastre a URL final da fonte.");
  if (!r.ok) throw new Error(`Fonte retornou HTTP ${r.status}.`);
  const reader = r.body.getReader();
  let chunks = [],
    size = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > max) {
      await reader.cancel();
      throw new Error("Fonte excede limite de tamanho.");
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let off = 0;
  for (const c of chunks) {
    bytes.set(c, off);
    off += c.length;
  }
  return new TextDecoder().decode(bytes);
}
export function parseStructuredJobs(html, base) {
  const jobs = [];
  function walk(x) {
    if (Array.isArray(x)) {
      x.forEach(walk);
      return;
    }
    if (!x || typeof x !== "object") return;
    if (
      x["@type"] === "JobPosting" ||
      (Array.isArray(x["@type"]) && x["@type"].includes("JobPosting"))
    ) {
      const expiration = Date.parse(x.validThrough || "");
      if (Number.isFinite(expiration) && expiration < Date.now()) return;
      const addr = x.jobLocation?.address || {};
      jobs.push({
        title: x.title,
        company: x.hiringOrganization?.name,
        location: [addr.addressLocality, addr.addressCountry, x.jobLocationType]
          .filter(Boolean)
          .join(", "),
        url: x.url ? new URL(x.url, base).href : base,
        description: x.description,
      });
    }
    if (x["@graph"]) walk(x["@graph"]);
    if (x.itemListElement) walk(x.itemListElement);
    if (x.item) walk(x.item);
  }
  for (const m of html.matchAll(
    /<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi,
  )) {
    try {
      walk(JSON.parse(m[1]));
    } catch {}
  }
  return jobs;
}
export async function discover(env, source, config) {
  let jobs = [];
  const slug = encodeURIComponent(source.value);
  if (source.kind === "greenhouse") {
    const d = JSON.parse(
      await fetchText(
        `https://boards-api.greenhouse.io/v1/boards/${slug}/jobs?content=true`,
      ),
    );
    jobs = (d.jobs || []).map((j) => ({
      title: j.title,
      company: source.value,
      location: j.location?.name,
      url: j.absolute_url,
      description: j.content,
    }));
  } else if (source.kind === "lever") {
    const d = JSON.parse(
      await fetchText(`https://api.lever.co/v0/postings/${slug}?mode=json`),
    );
    jobs = d.map((j) => ({
      title: j.text,
      company: source.value,
      location: j.categories?.location,
      url: j.applyUrl || j.hostedUrl,
      description: [
        j.descriptionPlain,
        ...(j.lists || []).map((l) => l.text + " " + cleanText(l.content)),
        j.additionalPlain,
      ].join("\n"),
    }));
  } else if (source.kind === "ashby") {
    const d = JSON.parse(
      await fetchText(`https://api.ashbyhq.com/posting-api/job-board/${slug}`),
    );
    jobs = (d.jobs || [])
      .filter((j) => j.isListed !== false)
      .map((j) => ({
        title: j.title,
        company: source.value,
        location: j.location,
        url: j.applyUrl || j.jobUrl,
        description: j.descriptionPlain || j.descriptionHtml,
      }));
  } else if (source.kind === "linkedin") {
    jobs = [
      linkedinJob(
        { url: source.value },
        parseLinkedinPost(await fetchText(source.value)),
      ),
    ];
  } else {
    const u = new URL(source.value);
    // Conservative robots handling: custom pages require an explicit allow or no robots file.
    const rr = await fetch(u.origin + "/robots.txt", {
      redirect: "manual",
      signal: AbortSignal.timeout(8000),
    });
    if (rr.status !== 404) {
      if (!rr.ok) throw new Error("Não foi possível verificar robots.txt.");
      const robots = await rr.text();
      if (/^\s*Disallow:\s*\S+/im.test(robots))
        throw new Error(
          "Fonte com restrições em robots.txt: utilize conector ATS ou revisão manual.",
        );
    }
    const html = await fetchText(source.value);
    jobs = parseStructuredJobs(html, source.value);
    if (!jobs.length)
      throw new Error(
        "Página sem JobPosting estruturado. Cadastre a página individual da vaga ou um ATS.",
      );
  }
  return saveJobs(env, source, config, jobs);
}

export async function saveJobs(env, source, config, jobs) {
  let saved = 0;
  let pending = [],
    bytes = 2;
  const encoder = new TextEncoder();
  async function flush() {
    if (!pending.length) return;
    const r = await env.DB.prepare(
      "INSERT OR IGNORE INTO jobs(id,source_id,title,company,location,url,description) SELECT json_extract(value,'$.id'),json_extract(value,'$.source_id'),json_extract(value,'$.title'),json_extract(value,'$.company'),json_extract(value,'$.location'),json_extract(value,'$.url'),json_extract(value,'$.description') FROM json_each(?)",
    )
      .bind(JSON.stringify(pending))
      .run();
    saved += r.meta.changes;
    pending = [];
    bytes = 2;
  }
  const keys = config.keywords
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  for (const j of jobs.slice(0, 300)) {
    j.description = cleanText(j.description).slice(0, LIMITS.description);
    j.title = cleanText(j.title).slice(0, 300);
    if (!j.title || j.description.length < 80) continue;
    if (
      keys.length &&
      !keys.some((k) =>
        (j.title + " " + j.description).toLowerCase().includes(k),
      )
    )
      continue;
    try {
      j.url = publicUrl(j.url);
    } catch {
      continue;
    }
    const id = await digest(j.url);
    const row = {
      id,
      source_id: source.id,
      title: j.title,
      company: cleanText(j.company || source.value).slice(0, 200),
      location: cleanText(j.location || "Não informado").slice(0, 300),
      url: j.url,
      description: j.description,
    };
    const size = encoder.encode(JSON.stringify(row)).length + 1;
    if (bytes + size > 1000000) await flush();
    pending.push(row);
    bytes += size;
  }
  await flush();
  await event(
    env,
    "discovery",
    `${source.kind}/${source.value}: ${saved} vagas novas.`,
  );
  return saved;
}
