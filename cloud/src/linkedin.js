import { publicUrl, cleanText } from "./core.js";

export function linkedinUrl(value) {
  const u = new URL(publicUrl(value));
  if (
    !/^(www\.)?linkedin\.com$/.test(u.hostname) ||
    !/^\/(posts\/[^/]+|feed\/update\/urn:li:activity:\d+)\/?$/.test(u.pathname)
  )
    throw new Error(
      "Informe a URL de um post LinkedIn (/posts/ ou /feed/update/urn:li:activity:...).",
    );
  u.search = "";
  return u.href;
}

export function parseLinkedinPost(html) {
  let text = "";
  function walk(x) {
    if (Array.isArray(x)) return x.forEach(walk);
    if (!x || typeof x !== "object") return;
    if (
      ["SocialMediaPosting", "DiscussionForumPosting", "Article"].includes(
        x["@type"],
      )
    ) {
      const candidate = cleanText(x.articleBody || x.text || "");
      if (candidate.length > text.length) text = candidate;
    }
    if (x["@graph"]) walk(x["@graph"]);
  }
  for (const m of html.matchAll(
    /<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi,
  )) {
    try {
      walk(JSON.parse(m[1]));
    } catch {}
  }
  const commentary = html.match(
    /<(?:div|p)\b[^>]*class=["'][^"']*\b(?:attributed-text-segment-list__content|share-update-card__update-text)\b[^"']*["'][^>]*>([\s\S]*?)<\/(?:div|p)>/i,
  );
  const visible = commentary ? cleanText(commentary[1]) : "";
  if (visible.length > text.length) text = visible;
  if (text.length < 80 || /(?:…|\.\.\.)\s*$/.test(text))
    throw new Error(
      "Post não disponível por completo. Abra o LinkedIn e cole o texto integral no campo abaixo.",
    );
  return text;
}

export function linkedinJob(input, text) {
  const url = linkedinUrl(input.url);
  if (
    typeof text !== "string" ||
    text.trim().length < 80 ||
    text.length > 20000
  )
    throw new Error(
      "Informe o texto completo do post, entre 80 e 20.000 caracteres.",
    );
  return {
    title: String(
      input.title || text.split(/[\n.!?]/)[0] || "Oportunidade no LinkedIn",
    ).slice(0, 300),
    company: "Não informada — post LinkedIn",
    location: "Consultar requisitos no post",
    url,
    description: text.trim(),
  };
}
