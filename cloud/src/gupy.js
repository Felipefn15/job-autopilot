import { publicUrl } from "./core.js";
// Public candidate portal response, checked against live results. No employer API credential.
export function gupyPage(data) {
  if (
    !Array.isArray(data?.data) ||
    !Number.isFinite(Number(data.pagination?.total))
  )
    throw new Error("Gupy: resposta inesperada; nenhuma vaga importada.");
  const jobs = [];
  for (const j of data.data) {
    let url;
    try {
      url = publicUrl(j.jobUrl);
      if (!new URL(url).hostname.endsWith(".gupy.io")) continue;
    } catch {
      continue;
    }
    const mode =
      {
        remote: "Remote",
        hybrid: "Híbrido",
        "on-site": "Presencial",
        onsite: "Presencial",
      }[j.workplaceType] || (j.isRemoteWork === true ? "Remote" : "");
    jobs.push({
      title: j.name,
      company: j.careerPageName,
      url,
      description: j.description,
      location: [j.city, j.state, j.country, mode].filter(Boolean).join(" · "),
      published_at: j.publishedDate,
      valid_through: /^\d{4}-\d{2}-\d{2}$/.test(j.applicationDeadline || "")
        ? j.applicationDeadline + "T23:59:59Z"
        : j.applicationDeadline,
    });
  }
  return {
    jobs,
    total: Number(data.pagination.total),
    count: data.data.length,
  };
}
