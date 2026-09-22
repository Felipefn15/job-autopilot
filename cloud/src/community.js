import { cleanText } from "./core.js";
export function githubJobs(items, repo, now = Date.now()) {
  if (!Array.isArray(items))
    throw new Error("Resposta inválida da comunidade GitHub.");
  return items
    .filter(
      (j) =>
        !j.pull_request &&
        j.state === "open" &&
        Date.parse(j.created_at) >= now - 90 * 86400000,
    )
    .map((j) => ({
      title: j.title,
      company: `Comunidade ${repo}`,
      location: j.title,
      url: j.html_url,
      description: j.body || "",
    }));
}
export async function telegramJobs(html, channel) {
  const jobs = [];
  let current = null;
  await new HTMLRewriter()
    .on(".tgme_widget_message[data-post]", {
      element(el) {
        const post = el.getAttribute("data-post");
        current = null;
        if (!new RegExp(`^${channel}/[0-9]+$`, "i").test(post || "")) return;
        current = {
          url: `https://t.me/${post}`,
          description: "",
          title: "",
          company: `Canal ${channel}`,
          location: "Consulte o anúncio",
          date: null,
        };
        jobs.push(current);
      },
    })
    .on(".tgme_widget_message_text", {
      text(chunk) {
        if (current) current.description += chunk.text;
      },
    })
    .on(".tgme_widget_message_text br", {
      element() {
        if (current) current.description += "\n";
      },
    })
    .on(".tgme_widget_message_date time", {
      element(el) {
        if (current) current.date = el.getAttribute("datetime");
      },
    })
    .transform(new Response(html))
    .text();
  if (!jobs.length)
    throw new Error(
      "Canal sem posts públicos legíveis; verifique se o canal continua público.",
    );
  return jobs
    .filter((j) => Date.parse(j.date) >= Date.now() - 90 * 86400000)
    .map((j) => ({ ...j, title: cleanText(j.description).slice(0, 180) }));
}
export function selectSources(rows, focus = "brasil") {
  const sorted = [...rows].sort(
    (a, b) =>
      String(a.checked_at || "").localeCompare(String(b.checked_at || "")) ||
      (a.priority ?? 50) - (b.priority ?? 50) ||
      a.id.localeCompare(b.id),
  );
  if (focus === "global") return sorted.slice(0, 5);
  const selected = [
    ...sorted.filter((s) => s.region === "BR").slice(0, 4),
    ...sorted.filter((s) => s.region !== "BR").slice(0, 1),
  ];
  return [...selected, ...sorted.filter((s) => !selected.includes(s))].slice(
    0,
    5,
  );
}
export function sourceWindow(jobs, cursor = 0, size = 300) {
  const sorted = [...jobs].sort((a, b) =>
    String(a.url).localeCompare(String(b.url)),
  );
  const start = sorted.length
    ? Math.max(0, Number(cursor) || 0) % sorted.length
    : 0;
  return {
    jobs: sorted.slice(start, start + size),
    cursor: start + size >= sorted.length ? 0 : start + size,
  };
}
