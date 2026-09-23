export function boardJobs(kind, data) {
  const items = kind === "remotive" ? data.jobs : data;
  if (!Array.isArray(items)) throw new Error("Resposta inválida do agregador.");
  return items
    .filter((j) => (kind === "remotive" ? j.title : j.position))
    .map((j) => ({
      title: j.title || j.position,
      company: j.company_name || j.company,
      location: `${j.candidate_required_location || j.location || "Localização não informada"} · Remote`,
      // Keep the board URL for attribution; do not replace it with a third-party application URL.
      url: j.url,
      description: j.description,
      published_at: j.publication_date || j.date,
    }))
    .filter((j) => {
      try {
        return (
          new URL(j.url).hostname.toLowerCase() ===
          (kind === "remotive" ? "remotive.com" : "remoteok.com")
        );
      } catch {
        return false;
      }
    });
}
