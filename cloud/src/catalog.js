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
  const where = [],
    args = [];
  if (recommended) {
    where.push(
      "analysis IS NOT NULL AND score >= CAST(json_extract((SELECT data FROM settings WHERE id=1),'$.minScore') AS INTEGER) AND status IN ('matched','needs_input','preparing','sending','submitted','unknown')",
    );
  }
  if (q) {
    where.push(
      "(title LIKE ? ESCAPE '\\' OR company LIKE ? ESCAPE '\\' OR location LIKE ? ESCAPE '\\')",
    );
    const pattern = `%${q.replace(/[\\%_]/g, "\\$&")}%`;
    args.push(pattern, pattern, pattern);
  }
  const condition = where.length ? " WHERE " + where.join(" AND ") : "";
  const total = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM jobs" + condition,
  )
    .bind(...args)
    .first();
  const rows = await env.DB.prepare(
    "SELECT id,title,company,location,url,status,score,proof,created_at FROM jobs" +
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
