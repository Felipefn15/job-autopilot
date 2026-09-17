"""
Google Dorks Sniper (ATS Hunter)
Automatiza buscas com operadores site: (lever.co, greenhouse.io, recruitee.com),
filtra por palavras-chave (Senior, Node.js, Remote) e persiste URLs de candidatura
no jobs.db com score de relevância baseado no título da página.
"""
import os
import re
import time
from typing import List, Optional, Any, Dict
import requests

from .models import JobListing
from .database import DatabaseManager


# Sites ATS comuns para "Trabalhe Conosco" / job boards
DEFAULT_ATS_SITES = [
    "lever.co",
    "greenhouse.io",
    "recruitee.com",
    "workable.com",
    "ashbyhq.com",
]


class GoogleDorksSniper:
    """
    Sniper via Google Dorks para achar páginas de vagas em ATS
    que o LinkedIn não indexa. Usa SerpAPI (engine=google) com site: + keywords.
    """

    def __init__(
        self,
        resume_data: Any = None,
        db: Optional[DatabaseManager] = None,
        api_key: Optional[str] = None,
    ):
        self.resume_data = resume_data
        self.db = db or DatabaseManager("jobs.db")
        self.api_key = api_key or os.getenv("SERPAPI_KEY")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })

    def _build_dork_query(
        self,
        site: str,
        keywords: List[str],
    ) -> str:
        """Monta query estilo Dork: site:lever.co "Senior" "Node.js" "Remote"."""
        site_part = f"site:{site}"
        keyword_parts = [f'"{k}"' for k in keywords if k]
        return " ".join([site_part] + keyword_parts)

    def _search_serp(self, query: str, num: int = 20) -> List[Dict]:
        """Executa busca no Google via SerpAPI e retorna resultados orgânicos."""
        if not self.api_key:
            print("  ⚠ SERPAPI_KEY not set. Add to .env or pass api_key.")
            return []
        url = "https://serpapi.com/search.json"
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            "num": min(num, 100),
        }
        try:
            r = self.session.get(url, params=params, timeout=15)
            if r.status_code != 200:
                print(f"  ⚠ SerpAPI error: {r.status_code}")
                return []
            data = r.json()
            return data.get("organic_results", [])
        except Exception as e:
            print(f"  ⚠ SerpAPI request failed: {e}")
            return []

    def _relevance_score(self, title: str, link: str, keywords: List[str]) -> float:
        """Score 0–1 baseado em quantas keywords aparecem no título (e no link)."""
        text = (title + " " + link).lower()
        score = 0.0
        for k in keywords:
            if k and k.lower() in text:
                score += 0.25
        return min(score, 1.0) if keywords else 0.5

    def run(
        self,
        keywords: Optional[List[str]] = None,
        sites: Optional[List[str]] = None,
        results_per_site: int = 20,
        min_score: float = 0.0,
    ) -> List[JobListing]:
        """
        Executa buscas site: para cada ATS, filtra por keywords (Senior, Node.js, Remote),
        extrai URLs e persiste no jobs.db com score de relevância.

        - keywords: ex. ["Senior", "Node.js", "Remote"]. Se None, usa do resume_data ou default.
        - sites: lista de domínios (site:). Se None, usa DEFAULT_ATS_SITES.
        - results_per_site: máx resultados por site.
        - min_score: só persiste jobs com relevance_score >= min_score.
        """
        sites = sites or DEFAULT_ATS_SITES
        if keywords is None and self.resume_data:
            keywords = getattr(self.resume_data, "stack_tecnico", [])[:5]
        if not keywords:
            keywords = ["Senior", "Node.js", "Remote"]
        keywords = [str(k).strip() for k in keywords if k][:8]

        all_jobs: List[JobListing] = []
        seen_urls = set()

        print("\n🕸️ Google Dorks Sniper (ATS Hunter)")
        print("   Keywords:", " ".join(keywords))
        print("   Sites:", ", ".join(sites))

        for site in sites:
            query = self._build_dork_query(site, keywords)
            results = self._search_serp(query, num=results_per_site)
            time.sleep(1)

            for item in results:
                link = (item.get("link") or "").strip()
                title = (item.get("title") or "").strip()
                snippet = (item.get("snippet") or "").strip()
                if not link or not link.startswith("http"):
                    continue
                if link in seen_urls:
                    continue
                if self.db.is_job_processed(link):
                    continue

                score = self._relevance_score(title, link, keywords)
                if score < min_score:
                    continue

                seen_urls.add(link)
                job = JobListing(
                    title=title or "Job Application",
                    company=site.split(".")[0].capitalize(),
                    location="Remote",
                    url=link,
                    posted_date=None,
                    description=snippet[:1000] if snippet else "",
                    source="google_dorks_sniper",
                )
                job.match_score = score

                job_data = {
                    "url": job.url,
                    "title": job.title,
                    "company": job.company,
                    "match_score": job.match_score,
                    "error_details": [],
                    "source": "google_dorks_sniper",
                }
                self.db.save_job(job_data, status="EASY_APPLY_PENDING")
                all_jobs.append(job)
                print(f"    ✓ EASY_APPLY_PENDING | {job.title[:50]} | score={score:.2f}")

        print(f"\n  🎯 Total: {len(all_jobs)} URLs salvas (EASY_APPLY_PENDING)")
        return all_jobs
