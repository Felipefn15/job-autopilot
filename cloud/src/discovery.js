import { publicUrl, cleanText, digest, LIMITS } from "./core.js";
import { event } from "./db.js";
import { triageJob, triageKey } from "./triage.js";
import { workplaceLocation } from "./roles.js";
import { githubJobs, telegramJobs, sourceWindow } from "./community.js";
import { linkedinUrl, parseLinkedinPost, linkedinJob } from "./linkedin.js";
import { boardJobs } from "./boards.js";
import { classifyTitle, searchPlan } from "./job-insights.js";
export function sourceSpec(kind, value) {
  if (
    ![
      "greenhouse",
      "lever",
      "ashby",
      "smartrecruiters",
      "remotive",
      "remoteok",
      "page",
      "linkedin",
      "github",
      "telegram",
    ].includes(kind)
  )
    throw new Error("Fonte não suportada.");
  if (kind === "page") return { kind, value: publicUrl(value) };
  if (["remotive", "remoteok"].includes(kind)) return { kind, value: kind };
  if (kind === "linkedin") return { kind, value: linkedinUrl(value) };
  if (kind === "github") {
    if (!/^[a-zA-Z0-9_-]+\/[a-zA-Z0-9_.-]+$/.test(value))
      throw new Error("Use organização/repositório do GitHub.");
    return { kind, value: value.toLowerCase() };
  }
  if (kind === "telegram" && !/^[a-zA-Z][a-zA-Z0-9_]{4,31}$/.test(value))
    throw new Error("Use o nome de um canal público do Telegram.");
  if (!/^[a-zA-Z0-9_-]{1,100}$/.test(value))
    throw new Error("Use o identificador da empresa no ATS.");
  return { kind, value };
}
export async function fetchText(url, max = 12000000) {
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
  if (!r.ok) {
    if (
      new URL(u).hostname === "api.github.com" &&
      [403, 429].includes(r.status)
    ) {
      const limited =
        r.status === 429 ||
        r.headers.get("x-ratelimit-remaining") === "0" ||
        r.headers.has("retry-after");
      if (limited) {
        const retry = r.headers.get("retry-after");
        const retryMs = retry
          ? /^\d+$/.test(retry)
            ? Date.now() + Number(retry) * 1000
            : Date.parse(retry)
          : Number(r.headers.get("x-ratelimit-reset")) * 1000;
        const until = Math.max(
          Date.now() + 60000,
          Number.isFinite(retryMs) && retryMs > Date.now()
            ? retryMs
            : Date.now() + 3600000,
        );
        const error = new Error(
          `GitHub: limite de consultas atingido (HTTP ${r.status}). Consultas pausadas até ${new Date(until).toISOString()}.`,
        );
        error.code = "GITHUB_RATE_LIMIT";
        error.retryAt = new Date(until)
          .toISOString()
          .replace("T", " ")
          .slice(0, 19);
        throw error;
      }
      throw new Error(
        "GitHub recusou acesso (HTTP 403), sem confirmação de limite nos cabeçalhos. Nova tentativa após seis horas.",
      );
    }
    throw new Error(`Fonte retornou HTTP ${r.status}.`);
  }
  const reader = r.body.getReader();
  let chunks = [],
    size = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > max) {
      await reader.cancel();
      throw new Error(
        `Fonte excede o limite de ${Math.round(max / 1000000)} MB. A consulta foi interrompida sem perder as vagas já salvas.`,
      );
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
        published_at: x.datePosted,
        valid_through: x.validThrough,
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
  let nextCursor = 0;
  const slug = encodeURIComponent(source.value);
  const plan = searchPlan(source, config);
  let directed = false;
  if (["remotive", "remoteok"].includes(source.kind)) {
    const endpoint =
      source.kind === "remotive"
        ? "https://remotive.com/api/remote-jobs"
        : "https://remoteok.com/api";
    directed = source.kind === "remotive" && plan.targeted;
    jobs = boardJobs(
      source.kind,
      JSON.parse(
        await fetchText(
          endpoint +
            (directed ? `?search=${encodeURIComponent(plan.term)}` : ""),
        ),
      ),
    );
    if (directed) plan.state.index = (plan.state.index || 0) + 1;
  } else if (source.kind === "smartrecruiters") {
    directed = plan.targeted;
    const offset = Math.max(
      0,
      Number(directed ? plan.state.offset : source.cursor) || 0,
    );
    const query = new URLSearchParams({ limit: "5", offset: String(offset) });
    if (source.location_filter) query.set("country", source.location_filter);
    if (directed) query.set("q", plan.term);
    const base = `https://api.smartrecruiters.com/v1/companies/${slug}/postings`;
    const list = JSON.parse(await fetchText(`${base}?${query}`, 2000000));
    if (!Array.isArray(list.content))
      throw new Error("Catálogo SmartRecruiters inválido.");
    // Bound requests per run. Advance only after every detail was fetched successfully.
    for (const item of list.content.slice(0, 5)) {
      const d = JSON.parse(
        await fetchText(`${base}/${encodeURIComponent(item.id)}`, 2000000),
      );
      jobs.push({
        title: d.name,
        company: d.company?.name || source.value,
        location: [
          d.location?.city,
          d.location?.region,
          d.location?.country,
          d.location?.remote ? "Remote" : "",
        ]
          .filter(Boolean)
          .join(" · "),
        url:
          d.applyUrl ||
          `https://jobs.smartrecruiters.com/${slug}/${encodeURIComponent(d.id)}`,
        description: Object.values(d.jobAd?.sections || {})
          .map((s) => s.text || "")
          .join("\n"),
        published_at: d.releasedDate,
      });
    }
    nextCursor =
      offset + list.content.length < Number(list.totalFound)
        ? offset + list.content.length
        : 0;
    if (directed) {
      plan.state.offset = nextCursor;
      if (!nextCursor) plan.state.index = (plan.state.index || 0) + 1;
      nextCursor = Number(source.cursor) || 0;
    }
  } else if (source.kind === "github") {
    const repo = sourceSpec("github", source.value).value;
    const page = Math.max(1, Math.min(10, Number(source.cursor) || 1));
    const fetchPage = async (p) =>
      JSON.parse(
        await fetchText(
          `https://api.github.com/repos/${repo}/issues?state=open&sort=created&direction=desc&per_page=50&page=${p}`,
          4000000,
        ),
      );
    const newest = await fetchPage(1);
    const older = page > 1 ? await fetchPage(page) : newest;
    jobs = githubJobs(page > 1 ? [...newest, ...older] : newest, repo);
    jobs = [...new Map(jobs.map((j) => [j.url, j])).values()];
    nextCursor = older.length === 50 && page < 10 ? page + 1 : 1;
  } else if (source.kind === "telegram") {
    jobs = await telegramJobs(
      await fetchText(`https://t.me/s/${source.value}`, 4000000),
      source.value,
    );
  } else if (source.kind === "greenhouse") {
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
      published_at: j.first_published,
    }));
  } else if (source.kind === "lever") {
    const skip = Math.max(0, Number(source.cursor) || 0);
    const query = new URLSearchParams({
      mode: "json",
      skip: String(skip),
      limit: "100",
    });
    if (source.location_filter) query.set("location", source.location_filter);
    const d = JSON.parse(
      await fetchText(`https://api.lever.co/v0/postings/${slug}?${query}`),
    );
    nextCursor = d.length === 100 ? skip + 100 : 0;
    jobs = d.map((j) => ({
      title: j.text,
      company: source.value,
      location: workplaceLocation(j, j.categories?.location),
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
        location: workplaceLocation(j, j.location),
        url: j.applyUrl || j.jobUrl,
        description: j.descriptionPlain || j.descriptionHtml,
        published_at: j.publishedAt,
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
  // These endpoints return a complete, unfiltered public board before local slicing.
  // Missing from this snapshot is NOT treated as confirmed closure.
  if (["greenhouse", "ashby"].includes(source.kind) && jobs.length) {
    const urls = jobs
      .map((j) => {
        try {
          return publicUrl(j.url);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
    if (urls.length)
      await env.DB.prepare(
        "UPDATE jobs SET availability=CASE WHEN url IN (SELECT value FROM json_each(?)) THEN 'open' ELSE 'not_listed' END,last_seen_at=CASE WHEN url IN (SELECT value FROM json_each(?)) THEN CURRENT_TIMESTAMP ELSE last_seen_at END WHERE source_id=? AND (valid_through IS NULL OR datetime(valid_through)>=CURRENT_TIMESTAMP)",
      )
        .bind(JSON.stringify(urls), JSON.stringify(urls), source.id)
        .run();
  }
  const stats = { received: jobs.length, query: directed ? plan.term : null };
  if (["greenhouse", "ashby", "remotive", "remoteok"].includes(source.kind)) {
    const window = sourceWindow(jobs, directed ? 0 : source.cursor);
    jobs = window.jobs;
    nextCursor = directed ? Number(source.cursor) || 0 : window.cursor;
  }
  const saved = await saveJobs(env, source, config, jobs, stats);
  if (["remotive", "smartrecruiters"].includes(source.kind)) {
    plan.state.turn = (plan.state.turn || 0) + 1;
    await env.DB.prepare("UPDATE sources SET search_state=? WHERE id=?")
      .bind(JSON.stringify(plan.state), source.id)
      .run();
  }
  await env.DB.prepare("UPDATE sources SET cursor=?,last_stats=? WHERE id=?")
    .bind(nextCursor, JSON.stringify(stats), source.id)
    .run();
  return saved;
}

export async function saveJobs(env, source, config, jobs, stats = {}) {
  const key = await triageKey(config);
  let saved = 0;
  let pending = [],
    bytes = 2;
  const encoder = new TextEncoder();
  async function flush() {
    if (!pending.length) return;
    const r = await env.DB.prepare(
      "INSERT OR IGNORE INTO jobs(id,source_id,title,company,location,url,description,status,proof,triage_key) SELECT json_extract(value,'$.id'),json_extract(value,'$.source_id'),json_extract(value,'$.title'),json_extract(value,'$.company'),json_extract(value,'$.location'),json_extract(value,'$.url'),json_extract(value,'$.description'),json_extract(value,'$.status'),json_extract(value,'$.proof'),json_extract(value,'$.triage_key') FROM json_each(?)",
    )
      .bind(JSON.stringify(pending))
      .run();
    saved += r.meta.changes;
    await env.DB.prepare(
      "UPDATE jobs SET area=COALESCE(jobs.area,json_extract(j.value,'$.area')),seniority=COALESCE(jobs.seniority,json_extract(j.value,'$.seniority')),published_at=COALESCE(jobs.published_at,json_extract(j.value,'$.published_at')),valid_through=COALESCE(json_extract(j.value,'$.valid_through'),jobs.valid_through),last_seen_at=CURRENT_TIMESTAMP,availability=CASE WHEN datetime(COALESCE(json_extract(j.value,'$.valid_through'),jobs.valid_through))<CURRENT_TIMESTAMP THEN 'closed' ELSE 'open' END FROM json_each(?) AS j WHERE jobs.id=json_extract(j.value,'$.id')",
    )
      .bind(JSON.stringify(pending))
      .run();
    pending = [];
    bytes = 2;
  }
  Object.assign(stats, {
    received: stats.received ?? jobs.length,
    scanned: 0,
    invalid: 0,
    filtered: 0,
    matched: 0,
    reasons: {},
  });
  for (const j of jobs.slice(0, 300)) {
    stats.scanned++;
    j.description = cleanText(j.description).slice(0, LIMITS.description);
    j.title = cleanText(j.title).slice(0, 300);
    if (!j.title || j.description.length < 80) {
      stats.invalid++;
      continue;
    }
    const verdict = triageJob(j, config);
    if (!verdict.pass) {
      stats.filtered++;
      stats.reasons[verdict.reason] = (stats.reasons[verdict.reason] || 0) + 1;
    }
    try {
      j.url = publicUrl(j.url);
    } catch {
      stats.invalid++;
      continue;
    }
    if (verdict.pass) stats.matched++;
    const id = await digest(j.url);
    const row = {
      id,
      source_id: source.id,
      title: j.title,
      company: cleanText(j.company || source.value).slice(0, 200),
      location: cleanText(j.location || "Não informado").slice(0, 300),
      url: j.url,
      description: j.description,
      status: verdict.pass ? "discovered" : "filtered",
      proof: verdict.reason,
      triage_key: key,
      ...classifyTitle(j.title),
      published_at: Number.isFinite(Date.parse(j.published_at))
        ? new Date(j.published_at).toISOString()
        : null,
      valid_through: Number.isFinite(Date.parse(j.valid_through))
        ? new Date(j.valid_through).toISOString()
        : null,
    };
    const size = encoder.encode(JSON.stringify(row)).length + 1;
    if (bytes + size > 1000000) await flush();
    pending.push(row);
    bytes += size;
  }
  await flush();
  stats.saved = saved;
  stats.duplicates = stats.scanned - stats.invalid - saved;
  await event(
    env,
    "discovery",
    `${source.kind}/${source.value}${stats.query ? ` (busca: ${stats.query})` : ""}: ${stats.received} recebidas, ${stats.scanned} examinadas, ${stats.filtered} fora das preferências, ${stats.invalid} incompletas, ${stats.duplicates} já cadastradas, ${saved} novas. ${Object.entries(
      stats.reasons,
    )
      .map(([reason, n]) => `${n}: ${reason}`)
      .join(" ")}`,
  );
  return saved;
}
