import { areas, levels } from "./job-insights.js";
import {
  areaSql,
  senioritySql,
  foldSql,
  queryGroups,
  escapeLike,
  profileRoles,
} from "./search.js";
import { settings } from "./db.js";
// Bound every catalog request and parameterize all user-provided filters.
export async function catalog(env, params) {
  const page = Math.max(
    1,
    Math.min(100000, Math.floor(Number(params.get("page")) || 1)),
  );
  const q = String(params.get("q") || "")
    .slice(0, 150)
    .trim();
  const recommended = params.get("view") === "recommended";
  const prefix = `WITH normalized AS (SELECT jobs.*, ${foldSql("title")} AS folded_title, COALESCE(search_normalized, ${foldSql("title || ' ' || COALESCE(company,'') || ' ' || COALESCE(location,'') || ' ' || COALESCE(description,'')")}) AS search_text FROM jobs), catalog_jobs AS (SELECT normalized.*, COALESCE(area, ${areaSql("folded_title")}) AS effective_area, COALESCE(seniority, ${senioritySql("folded_title")}) AS effective_seniority FROM normalized) `;
  const where = [],
    args = [];
  for (const [field, values] of [
    ["area", areas],
    ["seniority", levels],
  ]) {
    const value = params.get(field);
    if (Object.hasOwn(values, value || "")) {
      where.push(
        `${field === "area" ? "effective_area" : "effective_seniority"}=?`,
      );
      args.push(value);
    }
  }
  const availability = params.get("availability");
  if (["open", "closed", "not_listed", "unknown"].includes(availability)) {
    where.push(
      "(CASE WHEN datetime(valid_through)<CURRENT_TIMESTAMP THEN 'closed' ELSE availability END)=?",
    );
    args.push(availability);
  }
  const source = params.get("source");
  if (
    [
      "greenhouse",
      "lever",
      "ashby",
      "smartrecruiters",
      "remotive",
      "remoteok",
      "github",
      "telegram",
      "linkedin",
      "page",
    ].includes(source)
  ) {
    where.push("source_id IN (SELECT id FROM sources WHERE kind=?)");
    args.push(source);
  }
  const days = Number(params.get("days"));
  if ([1, 7, 30].includes(days)) {
    where.push("created_at >= datetime('now', ?)");
    args.push(`-${days} days`);
  }
  if (recommended) {
    where.push(
      "availability NOT IN ('closed','not_listed') AND (valid_through IS NULL OR datetime(valid_through)>=CURRENT_TIMESTAMP)",
    );
    where.push(
      "analysis IS NOT NULL AND score >= CAST(json_extract((SELECT data FROM settings WHERE id=1),'$.minScore') AS INTEGER) AND status IN ('matched','needs_input','preparing','sending','submitted','unknown')",
    );
  }
  for (const group of queryGroups(q)) {
    where.push(
      "(" +
        group.map(() => "search_text LIKE ? ESCAPE '\\'").join(" OR ") +
        ")",
    );
    args.push(...group.map((term) => `%${escapeLike(term)}%`));
  }
  if (params.get("profile") === "1") {
    const terms = profileRoles(await settings(env));
    if (terms.length) {
      where.push(
        "(" +
          terms.map(() => "folded_title LIKE ? ESCAPE '\\'").join(" OR ") +
          ")",
      );
      args.push(...terms.map((term) => `%${escapeLike(term)}%`));
    }
  }
  const condition = where.length ? " WHERE " + where.join(" AND ") : "";
  const total = await env.DB.prepare(
    prefix + "SELECT COUNT(*) AS n FROM catalog_jobs" + condition,
  )
    .bind(...args)
    .first();
  const rows = await env.DB.prepare(
    prefix +
      "SELECT id,title,company,location,url,status,score,proof,created_at,effective_area AS area,effective_seniority AS seniority,CASE WHEN datetime(valid_through)<CURRENT_TIMESTAMP THEN 'closed' ELSE availability END AS availability,published_at,last_seen_at,substr(description,1,240) AS excerpt,(SELECT kind FROM sources WHERE sources.id=catalog_jobs.source_id) AS source_kind FROM catalog_jobs" +
      condition +
      (recommended
        ? " ORDER BY score DESC,created_at DESC,id"
        : " ORDER BY created_at DESC,id") +
      " LIMIT 50 OFFSET ?",
  )
    .bind(...args, (page - 1) * 50)
    .all();
  return { jobs: rows.results, total: total.n, page, pageSize: 50 };
}
