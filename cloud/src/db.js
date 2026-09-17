export async function settings(env) {
  return JSON.parse(
    (await env.DB.prepare("SELECT data FROM settings WHERE id=1").first()).data,
  );
}
export async function profile(env) {
  const p = await env.DB.prepare(
    "SELECT * FROM profiles ORDER BY created_at DESC, rowid DESC LIMIT 1",
  ).first();
  return p ? { ...p, data: JSON.parse(p.data) } : null;
}
export async function event(env, kind, detail, jobId = null) {
  await env.DB.prepare("INSERT INTO events(job_id,kind,detail) VALUES(?,?,?)")
    .bind(jobId, kind, String(detail).slice(0, 4000))
    .run();
}
export async function reserve(env, kind, limit) {
  if (!Number.isInteger(limit) || limit < 1) return false;
  const row = await env.DB.prepare(
    "INSERT INTO usage(day,kind,count) VALUES(date('now'),?,1) ON CONFLICT(day,kind) DO UPDATE SET count=count+1 WHERE count < ? RETURNING count",
  )
    .bind(kind, limit)
    .first();
  return !!row;
}
export async function lock(env, name) {
  const token = crypto.randomUUID(),
    now = Date.now();
  const row = await env.DB.prepare(
    "INSERT INTO locks(name,token,expires) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET token=excluded.token,expires=excluded.expires WHERE locks.expires < ? RETURNING token",
  )
    .bind(name, token, now + 600000, now)
    .first();
  return row?.token === token ? token : null;
}
export async function unlock(env, name, token) {
  await env.DB.prepare("DELETE FROM locks WHERE name=? AND token=?")
    .bind(name, token)
    .run();
}
export async function status(env, id, state, proof = "") {
  await env.DB.prepare(
    "UPDATE jobs SET status=?,proof=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
  )
    .bind(state, proof, id)
    .run();
}
