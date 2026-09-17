"""
GitHub Issues Sniper
Varre repositórios de vagas (backend-br, frontend-br, react-brasil, etc.),
extrai título, empresa e e-mail das Issues e persiste no jobs.db com status PENDING
para o pipeline de envio por e-mail.
Se o e-mail não estiver na Issue, busca em README.md e CONTRIBUTING.md do repositório.
Mantém a lógica Sniper: mesma interface JobListing + brain + database.
"""
import base64
import re
import time
from typing import List, Dict, Optional, Any

import requests

from .models import JobListing
from .database import DatabaseManager
from .brain import AIBrain
from .emailer import EmailApplier


# Repositórios validados (API GitHub): frontendbr sem hífen; remote-lab 404 → RemoteWLB/remote-jobs
# react-brasil/vagas confirmado; react-jobs/vagas e awesome-jobs/vagas 404 – removidos
DEFAULT_VAGAS_REPOS = [
    "backend-br/vagas",
    "frontendbr/vagas",           # correto: sem hífen (frontend-br/vagas retorna 404)
    "react-brasil/vagas",
    "RemoteWLB/remote-jobs",      # internacional (remote-lab/remote-jobs 404)
]


class GitHubSniper:
    """
    Sniper de vagas em GitHub Issues.
    Usa API do GitHub para capturar Issues, extrai dados (Regex + IA opcional)
    e calcula match score com o currículo. Persiste no jobs.db como PENDING.
    """

    def __init__(
        self,
        resume_data: Any,
        db: Optional[DatabaseManager] = None,
        repo_list: Optional[List[str]] = None,
        user_data: Optional[Dict[str, Any]] = None,
    ):
        self.resume_data = resume_data
        self.db = db or DatabaseManager("jobs.db")
        self.repos = repo_list or DEFAULT_VAGAS_REPOS
        self.user_data = user_data or {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/vnd.github.v3+json",
        })
        self.emailer = EmailApplier()
        self.brain = AIBrain(no_ai_fallback=self.user_data.get("no_ai_fallback", False))

    def _extract_from_body_regex(self, body: str) -> Dict[str, Optional[str]]:
        """Extrai título, empresa e e-mail do corpo da Issue via regex. E-mail via EmailApplier.extract_email_from_text (antes de qualquer IA)."""
        if not body:
            return {"title": None, "company": None, "email": None}

        body_lower = body.lower()
        out = {"title": None, "company": None, "email": None}

        # E-mail: sempre via Regex (EmailApplier.extract_email_from_text) primeiro
        email = self.emailer.extract_email_from_text(body)
        if email:
            out["email"] = email

        # Empresa: padrões comuns em Markdown (Empresa:, Company:, Contratando:)
        company_patterns = [
            r"(?:empresa|company|contratando|hiring)\s*[:\|]\s*([^\n#*]+)",
            r"(?:^|\n)\*\*?(?:empresa|company)\*\*?\s*[:\|]\s*([^\n#*]+)",
        ]
        for pat in company_patterns:
            m = re.search(pat, body, re.IGNORECASE)
            if m:
                out["company"] = m.group(1).strip()
                break
        if not out["company"]:
            # Fallback: primeira linha que pareça nome de empresa (curta, sem markdown)
            first_lines = [ln.strip() for ln in body.split("\n")[:8] if ln.strip() and not ln.strip().startswith("#")]
            for ln in first_lines:
                if 3 <= len(ln) <= 60 and not ln.startswith(("http", "-", "*", "[")):
                    out["company"] = ln
                    break

        return out

    def _extract_with_ai(self, issue_title: str, body: str) -> Dict[str, Optional[str]]:
        """Usa IA (brain) para extrair título da vaga, empresa e e-mail quando regex não basta."""
        try:
            resume_dict = {
                "stack_tecnico": getattr(self.resume_data, "stack_tecnico", []) or [],
                "experiencia_anos": getattr(self.resume_data, "experiencia_anos", 8),
                "senioridade_pretendida": getattr(self.resume_data, "senioridade_pretendida", "senior"),
                "palavras_chave": getattr(self.resume_data, "palavras_chave", []) or [],
            }
            prompt = f"""From this GitHub issue (job posting), extract exactly:
1. job_title: The job position title (e.g. "Desenvolvedor(a) Backend Python")
2. company: Company or organization name
3. contact_email: A single contact email if present (only if clearly an email address)

Issue title: {issue_title}

Body (first 2000 chars):
{(body or '')[:2000]}

Reply with ONLY a JSON object, no markdown, no explanation:
{{"job_title": "...", "company": "...", "contact_email": "..." or null}}
"""
            response = self.brain.model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text).strip()
                text = re.sub(r"\n?```$", "", text).strip()
            import json
            data = json.loads(text)
            email = (data.get("contact_email") or "").strip() or None
            if email and not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
                email = None
            return {
                "title": (data.get("job_title") or "").strip() or issue_title,
                "company": (data.get("company") or "").strip() or "Unknown",
                "email": email,
            }
        except Exception as e:
            print(f"    ⚠ GitHub Sniper AI extraction failed: {e}")
            return {
                "title": issue_title,
                "company": "Unknown",
                "email": self.emailer.extract_email_from_text(body),
            }

    def _repo_from_issue_url(self, issue_url: str) -> Optional[str]:
        """Extrai owner/repo da URL da issue. Ex: https://github.com/backend-br/vagas/issues/123 -> backend-br/vagas"""
        if not issue_url or "github.com" not in issue_url:
            return None
        try:
            parts = issue_url.replace("http://", "").replace("https://", "").split("/")
            if "github.com" in parts[0] and len(parts) >= 3:
                return f"{parts[1]}/{parts[2]}"
        except Exception:
            pass
        return None

    def _fetch_repo_file_content(self, repo: str, path: str) -> Optional[str]:
        """Busca conteúdo de um arquivo no repositório (ex: README.md, CONTRIBUTING.md). API retorna base64."""
        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code != 200:
                return None
            data = r.json()
            content_b64 = data.get("content")
            if not content_b64:
                return None
            raw = base64.b64decode(content_b64).decode("utf-8", errors="replace")
            return raw[:15000]
        except Exception as e:
            print(f"    ⚠ Repo file {path}: {e}")
            return None

    def _find_email_in_repo_docs(self, issue_url: str) -> Optional[str]:
        """Se o e-mail não está na Issue, busca em README.md e CONTRIBUTING.md do repositório (recrutamento centralizado)."""
        repo = self._repo_from_issue_url(issue_url)
        if not repo:
            return None
        for path in ("CONTRIBUTING.md", "README.md"):
            text = self._fetch_repo_file_content(repo, path)
            if text:
                email = self.emailer.extract_email_from_text(text)
                if email:
                    return email
            time.sleep(0.3)
        return None

    def _fetch_issues(self, repo: str, per_page: int = 50) -> List[Dict]:
        """Busca as últimas Issues abertas do repositório via API GitHub."""
        url = f"https://api.github.com/repos/{repo}/issues"
        params = {
            "state": "open",
            "per_page": per_page,
            "sort": "updated",
            "direction": "desc",
        }
        try:
            r = self.session.get(url, params=params, timeout=15)
            if r.status_code != 200:
                print(f"    ⚠ GitHub API {repo}: {r.status_code}")
                return []
            return r.json()
        except Exception as e:
            print(f"    ⚠ Error fetching {repo}: {e}")
            return []

    def _issue_to_job(
        self,
        issue: Dict,
        extracted: Dict[str, Optional[str]],
    ) -> Optional[JobListing]:
        """Converte uma Issue + dados extraídos em JobListing e calcula match score."""
        issue_title = issue.get("title", "")
        body = issue.get("body", "") or ""
        issue_url = issue.get("html_url", "")

        title = extracted.get("title") or issue_title
        company = extracted.get("company") or "Unknown"
        email = extracted.get("email")

        # Sem e-mail: ainda pode ser salvo como PENDING se houver link externo; pipeline pode usar URL
        description = (body or "")[:3000]
        location = "Remote"

        job = JobListing(
            title=title,
            company=company,
            location=location,
            url=issue_url,
            posted_date=issue.get("created_at"),
            description=description,
            email=email,
            source="github_sniper",
        )

        # Match score: brain.evaluate_job (currículo 8 anos, React/Node/Python)
        try:
            resume_dict = {
                "stack_tecnico": getattr(self.resume_data, "stack_tecnico", []) or [],
                "experiencia_anos": getattr(self.resume_data, "experiencia_anos", 8),
                "senioridade_pretendida": getattr(self.resume_data, "senioridade_pretendida", "senior"),
                "palavras_chave": getattr(self.resume_data, "palavras_chave", []) or [],
            }
            job.match_score = self.brain.evaluate_job(description, resume_dict, location)
        except Exception as e:
            print(f"    ⚠ Match score failed for {title}: {e}")
            job.match_score = 0.5

        return job

    def run(
        self,
        issues_per_repo: int = 50,
        use_ai_extraction: bool = True,
        min_score: float = 0.0,
    ) -> List[JobListing]:
        """
        Varre os repositórios configurados, extrai vagas e persiste no jobs.db com status PENDING.

        - issues_per_repo: máximo de Issues por repositório (padrão 50).
        - use_ai_extraction: se True, usa IA para extrair título/empresa/email quando regex não acha e-mail.
        - min_score: só persiste jobs com match_score >= min_score.

        Returns:
            Lista de JobListing encontrados e persistidos (PENDING).
        """
        all_jobs: List[JobListing] = []
        seen_urls = set()

        print("\n🐙 GitHub Issues Sniper")
        print("   Repos:", ", ".join(self.repos[:5]), "..." if len(self.repos) > 5 else "")

        for repo in self.repos:
            print(f"\n  📂 {repo} (até {issues_per_repo} issues)")
            issues = self._fetch_issues(repo, per_page=issues_per_repo)
            time.sleep(1)

            for issue in issues:
                if "pull_request" in issue:
                    continue
                issue_url = issue.get("html_url", "")
                if issue_url in seen_urls:
                    continue
                if self.db.is_job_processed(issue_url):
                    continue

                body = issue.get("body", "") or ""
                issue_title = issue.get("title", "")

                # 1) Extração de e-mail SEMPRE via Regex primeiro (EmailApplier.extract_email_from_text)
                extracted = self._extract_from_body_regex(body)
                if extracted.get("email"):
                    # E-mail encontrado por Regex: IA apenas para match_score (Groq-First no brain)
                    print("    [GitHub Sniper] E-mail via Regex → IA só para match_score (Groq Primary)")
                elif use_ai_extraction and body:
                    # E-mail NÃO encontrado por Regex: usar IA para tentar extrair do corpo da Issue
                    print("    [GitHub Sniper] E-mail não via Regex → IA para extração + match_score")
                    extracted = self._extract_with_ai(issue_title, body)
                if not extracted.get("title"):
                    extracted["title"] = issue_title
                if not extracted.get("company"):
                    extracted["company"] = "Unknown"

                job = self._issue_to_job(issue, extracted)  # match_score via Groq (brain.evaluate_job)
                if not job or job.match_score < min_score:
                    continue

                # E-mail não na Issue: buscar em README.md e CONTRIBUTING.md do repositório (Strider, Botcity, etc.)
                if not job.email:
                    email_from_docs = self._find_email_in_repo_docs(issue_url)
                    if email_from_docs:
                        job.email = email_from_docs
                        print(f"    📧 E-mail do repositório ({repo}): {email_from_docs}")

                seen_urls.add(issue_url)
                all_jobs.append(job)

                job_data = {
                    "url": job.url,
                    "title": job.title,
                    "company": job.company,
                    "match_score": job.match_score,
                    "error_details": [],
                    "source": "github_sniper",
                }
                # Com e-mail (Issue ou README/CONTRIBUTING): PENDING. Sem e-mail e score alto: MANUAL_REVIEW
                if not job.email and job.match_score >= 0.6:
                    self.db.save_job(job_data, status="MANUAL_REVIEW")
                    print(f"    ✓ MANUAL_REVIEW (no email, score {job.match_score:.2f}) | {job.title[:50]} | {job.company}")
                else:
                    self.db.save_job(job_data, status="PENDING")
                    if job.email:
                        self.db.update_job_email(job.url, job.email)
                    print(f"    ✓ PENDING | {job.title[:50]} | {job.company} | score={job.match_score:.2f}")

        print(f"\n  🎯 Total: {len(all_jobs)} vagas salvas como PENDING")
        return all_jobs
