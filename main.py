"""
Main Orchestrator
Coordinates the entire job search and application pipeline with continuous improvement
"""
import sys
import time
import os
import shutil
from pathlib import Path
from typing import List, Dict
import json

# Carregar .env no início para que SERPAPI_KEY, GROQ_API_KEY, etc. estejam disponíveis
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from modules.parser import ResumeParser, ResumeData
from modules.searcher import JobSearcher, JobListing
from modules.logger import ApplicationLogger
from modules.brain import AIBrain
from modules.database import DatabaseManager
from modules.emailer import EmailQuotaExceeded


class JobAutomationEngine:
    """Main engine that orchestrates the entire pipeline with continuous improvement"""
    
    def __init__(self, resume_path: str = "curriculo.pdf", user_data: Dict[str, str] = None, db: DatabaseManager = None):
        self.resume_path = Path(resume_path)
        self.user_data = user_data or {}
        self.resume_data: ResumeData = None
        self.jobs: List[JobListing] = []
        self.logger = ApplicationLogger()
        self.brain = AIBrain(no_ai_fallback=self.user_data.get("no_ai_fallback", False))
        self.db = db  # Database manager for tracking applications
        
    def extract_resume_data(self) -> ResumeData:
        """Step 1: Extract structured data from resume"""
        print("="*60)
        print("STEP 1: Extracting Resume Data")
        print("="*60)
        
        if not self.resume_path.exists():
            raise FileNotFoundError(f"Resume not found: {self.resume_path}")
        
        parser = ResumeParser(str(self.resume_path))
        self.resume_data = parser.parse()
        
        print(f"\nExtracted Resume Data:")
        print(f"  Technical Stack: {', '.join(self.resume_data.stack_tecnico)}")
        print(f"  Years of Experience: {self.resume_data.experiencia_anos}")
        print(f"  Desired Seniority: {self.resume_data.senioridade_pretendida}")
        print(f"  Keywords: {', '.join(self.resume_data.palavras_chave[:10])}")
        print()
        
        return self.resume_data

    def multi_source_discovery(self, iteration: int = 1) -> List[JobListing]:
        """
        Multi-Source Discovery: GitHub Sniper (BR + internacionais) + Google Dorks (1ª iteração).
        Retorna apenas JobListings com e-mail para a fila do EmailApplier.
        Twitter Sniper removido; capacidade de processamento direcionada aos repos GitHub internacionais.
        """
        print("="*60)
        print("MULTI-SOURCE DISCOVERY (Prioridade 2: GitHub | Prioridade 3: Google Dorks)")
        print("="*60)
        sniper_jobs_with_email: List[JobListing] = []

        try:
            from modules.github_sniper import GitHubSniper
            # Twitter Sniper removido do pipeline (import/call comentados ou deletados)

            # GitHub Issues Sniper: varre BR + internacionais (remote-lab/remote-jobs, awesome-jobs, etc.)
            # issues_per_repo=75: espaço que era do Twitter direcionado aos repos internacionais
            try:
                github = GitHubSniper(self.resume_data, db=self.db, user_data=self.user_data)
                github_jobs = github.run(issues_per_repo=75, use_ai_extraction=True, min_score=0.3)
                with_email = [j for j in github_jobs if getattr(j, "email", None)]
                sniper_jobs_with_email.extend(with_email)
                print(f"  🐙 GitHub: {len(with_email)} vagas com e-mail na fila")
            except Exception as e:
                print(f"  ⚠ GitHub Sniper failed: {e}")

            # Google Dorks Sniper – apenas 1ª iteração (evitar consumo excessivo de créditos SerpAPI)
            if iteration == 1:
                try:
                    from modules.google_dorks_sniper import GoogleDorksSniper
                    dorks = GoogleDorksSniper(self.resume_data, db=self.db)
                    dorks.run(results_per_site=15, min_score=0.25)
                    print("  🕸️ Google Dorks: URLs salvas como EASY_APPLY_PENDING (1x nesta sessão)")
                except Exception as e:
                    print(f"  ⚠ Google Dorks Sniper failed: {e}")
        except ImportError as e:
            print(f"  ⚠ Multi-Source Discovery skipped (missing module): {e}")

        print(f"  ✓ Total Multi-Source com e-mail para pipeline: {len(sniper_jobs_with_email)}\n")
        return sniper_jobs_with_email

    def search_jobs(self, location: str = "Brazil", max_per_source: int = 10) -> List[JobListing]:
        """Step 2: Search for matching jobs"""
        print("="*60)
        print("STEP 2: Searching for Jobs")
        print("="*60)
        
        if not self.resume_data:
            raise ValueError("Resume data not extracted. Run extract_resume_data() first.")
        
        searcher = JobSearcher(self.resume_data, user_data=self.user_data)
        # Get query_search and blocked_keys from user_data if available
        query_search = getattr(self, 'query_search', None) or self.user_data.get('query_search')
        blocked_keys = getattr(self, 'blocked_keys', None) or self.user_data.get('blocked_keys', [])
        # Get max_applications to sync with LinkedIn scroll
        # CRITICAL: Use max_applications if available, otherwise use max_per_source
        max_applications = getattr(self, 'max_applications', None)
        if max_applications:
            print(f"  📊 Using max_applications={max_applications} for LinkedIn scroll synchronization")
        else:
            print(f"  ⚠ max_applications not set, using default max_posts_per_skill=100 (max_per_source={max_per_source} ignored for LinkedIn)")
        # If max_applications is set, ignore max_per_source for LinkedIn (it will be calculated proportionally)
        # Otherwise, use max_per_source as fallback (but LinkedIn will use 100 as default)
        all_jobs = searcher.search_all(location=location, max_per_source=max_per_source, 
                                      query_search=query_search, blocked_keys=blocked_keys,
                                      max_applications=max_applications)
        
        print(f"\n  Total jobs found: {len(all_jobs)}")
        
        # Filter out jobs that have already been processed in database
        if self.db:
            original_count = len(all_jobs)
            new_jobs = []
            followup_count = 0
            for j in all_jobs:
                # Check if a follow-up is due (sent > 7 days ago, no follow-up yet)
                followup_info = self.db.get_followup_info(j.url)
                if followup_info:
                    j._is_followup = True
                    new_jobs.append(j)
                    followup_count += 1
                    continue

                # Skip if already processed (and not eligible for follow-up)
                if self.db.is_job_processed(j.url):
                    continue

                # For email jobs, also check if email was already sent
                if hasattr(j, 'email') and j.email:
                    email_url = f"email:{j.email}"
                    if self.db.is_job_processed(email_url):
                        continue

                new_jobs.append(j)
            self.jobs = new_jobs
            skipped_count = original_count - len(self.jobs)

            if skipped_count > 0:
                print(f"  ℹ Skipping {skipped_count} jobs (already processed in database)")
            if followup_count > 0:
                print(f"  ↩ {followup_count} jobs queued as follow-ups (sent >7 days ago)")
            print(f"  ✓ Found {len(self.jobs)} jobs to process ({followup_count} follow-ups)")
        else:
            self.jobs = all_jobs
            print(f"  ⚠ Database not available - processing all {len(self.jobs)} jobs")
        
        print(f"\nFound {len(self.jobs)} new jobs (after filtering)")
        print("\nTop matching jobs:")
        for i, job in enumerate(self.jobs[:5], 1):
            print(f"  {i}. {job.title} at {job.company}")
            print(f"     Match Score: {job.match_score:.2f} | URL: {job.url}")
        print()
        
        return self.jobs

    def load_pending_jobs_from_db(self, max_applications: int) -> List[JobListing]:
        """Carrega vagas com status PENDING do jobs.db (respeitando max_applications na query)."""
        if not self.db:
            return []
        rows = self.db.get_pending_jobs(status="PENDING", limit=max_applications)
        jobs = []
        for row in rows:
            url = row.get("url", "")
            title = row.get("title") or "Unknown"
            company = row.get("company") or "Unknown"
            match_score = float(row.get("match_score") or 0.5)
            email = row.get("email") or None
            if not email and url.startswith("email:"):
                email = url[6:].strip()
            job = JobListing(
                title=title,
                company=company,
                location="Remote",
                url=url,
                posted_date=None,
                description="",
                match_score=match_score,
                email=email,
            )
            jobs.append(job)
        return jobs

    def run_send_only_pipeline(self, max_applications: int = 5, min_match_score: float = 0.3) -> Dict:
        """Executa apenas Step 3 (aplicação) para vagas PENDING no jobs.db. Ignora Step 1 e Step 2."""
        print("\n" + "="*60)
        print("SEND-ONLY MODE (Step 3 only – PENDING jobs from jobs.db)")
        print("="*60 + "\n")
        self.max_applications = max_applications
        # Garantir resume_data para apply_to_jobs (cover letter, subject, etc.)
        if not self.resume_data and self.resume_path.exists():
            parser = ResumeParser(str(self.resume_path))
            self.resume_data = parser.parse()
        self.jobs = self.load_pending_jobs_from_db(max_applications=max_applications)
        if not self.jobs:
            print("  ℹ No PENDING jobs in jobs.db. Nothing to send.")
            return {"jobs_found": 0, "applications": [], "successful_applications": 0}
        print(f"  ✓ Loaded {len(self.jobs)} PENDING jobs from jobs.db (limit {max_applications})\n")
        results = self.apply_to_jobs(max_applications=max_applications, min_match_score=min_match_score)
        return {
            "jobs_found": len(self.jobs),
            "applications": results,
            "successful_applications": sum(1 for r in results if r.get("success")),
        }
    
    def apply_to_jobs(self, max_applications: int = 5, min_match_score: float = 0.3) -> List[Dict]:
        """Step 3: Apply only via EmailApplier (Gmail SMTP). Easy Apply / browser desativado."""
        print("="*60)
        print("STEP 3: Applying to Jobs (Email only – no browser)")
        print("="*60)
        
        if not self.jobs:
            raise ValueError("No jobs found. Run search_jobs() first.")
        
        def _job_email(j):
            e = getattr(j, 'email', None) or (j.url and str(j.url).startswith('email:') and j.url.replace('email:', '').strip())
            return e if e and '@' in str(e) else None
        
        # Force minimum score for GitHub BR jobs
        for job in self.jobs:
            if hasattr(job, 'source') and job.source == 'github_br':
                job.match_score = max(job.match_score, 0.7)
                print(f"  ✓ GitHub BR job: {job.title} - Score ajustado para {job.match_score:.2f}")
        
        # Filtrar apenas vagas com e-mail válido; sem browser/Playwright
        eligible = [job for job in self.jobs if job.match_score >= min_match_score and _job_email(job)]
        filtered_jobs = eligible[:max_applications]
        filtered_set = set(id(j) for j in filtered_jobs)
        
        # Log exato do motivo de cada vaga ignorada (Step 0 PENDING e Step 3)
        for job in self.jobs:
            if id(job) in filtered_set:
                continue
            if not _job_email(job):
                print(f"  Skipping: No email found — {job.title} at {job.company}")
            elif job.match_score < min_match_score:
                print(f"  Skipping: Score below threshold ({job.match_score:.2f} < {min_match_score}) — {job.title} at {job.company}")
            else:
                print(f"  Skipping: Over quota — {job.title} at {job.company}")
        
        if not filtered_jobs:
            print(f"ℹ No jobs with valid email (or none meet min score {min_match_score})")
            print(f"   Total jobs in queue: {len(self.jobs)}")
            return []
        
        print(f"\nApplying to {len(filtered_jobs)} jobs via email only (min score: {min_match_score})")
        
        from modules.emailer import EmailApplier, get_do_not_contact_emails
        emailer = EmailApplier()
        do_not_contact = get_do_not_contact_emails()
        results = []
        
        for i, job in enumerate(filtered_jobs, 1):
            job_email = _job_email(job)
            if job_email and job_email.strip().lower() in do_not_contact:
                print(f"\n  ⏭ Skipping (do not contact - already replied): {job_email}")
                continue
            print(f"\n[{i}/{len(filtered_jobs)}] {job.title} at {job.company} → {job_email}")
            
            _is_followup = getattr(job, '_is_followup', False)
            language = getattr(job, 'language', 'en') or 'en'
            cover_letter = None
            # Skip AI cover letter for follow-ups (not needed; only the ref block matters)
            if hasattr(job, 'source') and job.source == 'linkedin_post' and self.resume_data and not _is_followup:
                try:
                    from modules.linkedin_post_searcher import LinkedInPostSearcher
                    linkedin_searcher = LinkedInPostSearcher(self.resume_data, self.user_data)
                    search_skill = getattr(job, 'search_skill', None)
                    cover_letter = linkedin_searcher.generate_cover_letter(
                        job.description, language, job.title, search_skill=search_skill
                    )
                except Exception as e:
                    print(f"  ⚠ Cover letter skipped: {e}")
            # Always include post URL + job code + external link for linkedin_post jobs
            # (both new applications and follow-ups need the recruiter to identify the post)
            if hasattr(job, 'source') and job.source == 'linkedin_post':
                _lang = language
                _post_url = getattr(job, 'url', None)
                _ext_links = [l for l in (getattr(job, 'external_links', None) or []) if isinstance(l, str) and l.startswith('http')]

                _code = getattr(job, 'job_code', None)
                ref_parts = []
                if _code:
                    if _lang == 'pt':
                        ref_parts.append(f"Identificação da vaga: {_code}")
                    elif _lang == 'es':
                        ref_parts.append(f"Identificación de la vacante: {_code}")
                    else:
                        ref_parts.append(f"Job ID: {_code}")
                if _post_url and _post_url.startswith('http'):
                    if _lang == 'pt':
                        ref_parts.append(f"Post no LinkedIn: {_post_url}")
                    elif _lang == 'es':
                        ref_parts.append(f"Publicación en LinkedIn: {_post_url}")
                    else:
                        ref_parts.append(f"LinkedIn post: {_post_url}")
                if _ext_links:
                    _job_link = _ext_links[0]
                    if _lang == 'pt':
                        ref_parts.append(f"Link da vaga: {_job_link}")
                    elif _lang == 'es':
                        ref_parts.append(f"Link de la vacante: {_job_link}")
                    else:
                        ref_parts.append(f"Job link: {_job_link}")

                if ref_parts:
                    if _is_followup:
                        # For follow-ups the ref block IS the cover_letter (short email, no AI text)
                        cover_letter = "\n".join(ref_parts)
                    else:
                        cover_letter = (cover_letter or "") + "\n\n" + "\n".join(ref_parts)

            resume_data_dict = None
            if self.resume_data:
                resume_data_dict = {
                    'experiencia_anos': getattr(self.resume_data, 'experiencia_anos', 8),
                    'senioridade_pretendida': getattr(self.resume_data, 'senioridade_pretendida', 'senior'),
                    'stack_tecnico': getattr(self.resume_data, 'stack_tecnico', [])
                }
            
            # Snippet: title + company, no hashtags; same logic as searcher
            import re
            def _clean_snippet(s):
                if not s:
                    return s
                s = re.sub(r"hashtag#", "", s, flags=re.I)
                s = re.sub(r"#\w+", "", s).strip()
                s = re.sub(r"\s+", " ", s).strip()
                return s[:100] if s else ""
            _title = (getattr(job, 'title', None) or "").strip()
            _company = (getattr(job, 'company', None) or "").strip()
            _desc = (getattr(job, 'description', None) or "") or ""
            if _title and _company and _company.lower() not in ("unknown", ""):
                job_snippet = _clean_snippet(f"{_title} at {_company}") or f"{_title} at {_company}"[:100]
            elif _title and _title != "Job from LinkedIn Post":
                job_snippet = _clean_snippet(_title) or _title[:100]
            else:
                lines = [ln.strip() for ln in str(_desc).split("\n") if ln.strip()]
                job_snippet = ""
                for ln in lines:
                    if len(ln) >= 25 and not re.search(r"Feed post|Verified|•\s*1st|•\s*2nd|•\s*3rd", ln, re.I):
                        job_snippet = _clean_snippet(ln) or ln[:100]
                        break
                if not job_snippet and lines:
                    job_snippet = _clean_snippet(lines[0]) or lines[0][:100]
            # Prefer the recruiter's own job code as the ref; fall back to URL hash
            _job_code = getattr(job, 'job_code', None)
            job_id_ref = _job_code if _job_code else getattr(job, 'url', None)
            _language = language  # already resolved above

            if not _is_followup and self.db and self.db.is_sent_to_email_for_job(job_email, str(job_id_ref or "")):
                print(f"  ⏭ Skipping (already sent to {job_email} for this job)")
                continue

            if _is_followup:
                print(f"  ↩ Sending follow-up to {job_email} (first email sent >7 days ago)")

            success, smtp_message_id, email_subject = emailer.send_application_email(
                to_email=job_email,
                job_subject=job.title,
                resume_path=str(self.resume_path),
                user_data=self.user_data,
                job_description=job.description,
                cover_letter=cover_letter,
                resume_data=resume_data_dict,
                match_score=getattr(job, 'match_score', None),
                company_name=getattr(job, 'company', None),
                job_id=job_id_ref,
                job_description_snippet=job_snippet or None,
                language=_language,
                is_followup=_is_followup,
            )
            result = {
                'success': success,
                'job_title': job.title,
                'job_company': job.company,
                'match_score': job.match_score,
                'method': 'email_followup' if _is_followup else 'email',
                'errors': [] if success else ['Failed to send email'],
            }
            if success:
                print(f"  ✓ Email sent to {job_email}")
            else:
                print(f"  ✗ Email failed for {job_email}")
            results.append(result)

            if self.db:
                record_url = job.url
                if _is_followup:
                    if success:
                        self.db.mark_followup_sent(record_url)
                        print(f"  ✓ Follow-up recorded in database")
                else:
                    status = "SUCCESS" if success else "FAILED"
                    job_data = {
                        'url': record_url,
                        'title': job.title,
                        'company': job.company,
                        'match_score': job.match_score,
                        'error_details': result.get('errors', []),
                        'source': getattr(job, 'source', None),
                        'email': job_email,
                        'job_id': record_url,
                        'description': (getattr(job, 'description', '') or '')[:1000],
                        'job_code': getattr(job, 'job_code', None),
                        'email_subject': email_subject,
                    }
                    self.db.save_job(job_data, status=status)
                    if success and smtp_message_id:
                        self.db.update_smtp_message_id(record_url, smtp_message_id)
                    print(f"  ✓ Saved to database: {status}")
            time.sleep(2)
        
        print("\n" + "="*60)
        print("APPLICATION SUMMARY")
        print("="*60)
        successful = sum(1 for r in results if r['success'])
        print(f"Total applications: {len(results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {len(results) - successful}")
        for result in results:
            status = "✓" if result['success'] else "✗"
            print(f"  {status} {result['job_title']} at {result['job_company']}")
            if result['errors']:
                for err in result['errors']:
                    print(f"      Error: {err}")
        return results
    
    def analyze_previous_failures(self) -> Dict:
        """Step 0: Analyze previous failures and get AI suggestions for improvement"""
        print("="*60)
        print("STEP 0: Analyzing Previous Failures (Continuous Improvement)")
        print("="*60)
        
        failed_logs = self.logger.get_failed_logs(limit=5)
        
        if not failed_logs:
            print("No previous failures found. Starting fresh.\n")
            return {}
        
        print(f"\nFound {len(failed_logs)} recent failures:")
        for i, log in enumerate(failed_logs, 1):
            print(f"  {i}. {log.get('job_title', 'Unknown')} at {log.get('company', 'Unknown')}")
            print(f"     Error: {log.get('error_details', {}).get('message', 'Unknown error')}")
        
        # Use Gemini to analyze patterns (com timeout para não travar o pipeline)
        try:
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
            failure_summary = json.dumps(failed_logs, indent=2, ensure_ascii=False)
            prompt = f"""Analyze these recent job application failures and suggest improvements:

{failure_summary[:2000]}

Return a JSON object with:
{{"common_errors": ["..."], "suggestions": ["..."], "high_risk_companies": ["..."]}}"""

            def _call_gemini():
                r = self.brain.model.generate_content(prompt)
                return r.text.strip() if r and r.text else ""

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_call_gemini)
                try:
                    response_text = future.result(timeout=45)
                except FuturesTimeoutError:
                    print("  ⚠ Failure analysis timed out (45s). Skipping to avoid blocking pipeline.\n")
                    return {}

            if not response_text:
                return {}
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            analysis = json.loads(response_text)
            print("\nAI Analysis:")
            if analysis.get("common_errors"):
                for err in analysis["common_errors"][:5]:
                    print(f"    - {err}")
            if analysis.get("suggestions"):
                for sug in analysis["suggestions"][:5]:
                    print(f"    - {sug}")
            print()
            return analysis

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str or "rate limit" in error_str:
                print("  ⚠ AI quota exceeded (429). Skipping failure analysis.\n")
            else:
                print(f"  ⚠ Failure analysis skipped: {e}\n")
            return {}
    
    def run_full_pipeline(self, location: str = "Brazil", max_applications: int = 5,
                         min_match_score: float = 0.3, analyze_failures: bool = True,
                         iteration: int = 1) -> Dict:
        """Run the complete pipeline: first apply to PENDING (headless), then discovery + apply to new jobs."""
        print("\n" + "="*60)
        print("JOB AUTOMATION ENGINE - FULL PIPELINE (Continuous Improvement Mode)")
        print("="*60 + "\n")
        
        # CRITICAL: Store max_applications BEFORE calling search_jobs
        self.max_applications = max_applications
        all_results = []
        applied_count = 0

        try:
            remaining_quota = max_applications

            # Step 1: Extract resume data (required for LinkedIn cover letter / subject)
            self.extract_resume_data()

            # --- FOCUS 1: LinkedIn Post Sniper runs first (discovery + apply) ---
            print("="*60)
            print("STEP 2 (Focus 1): LinkedIn Post Sniper (Multi-Stack Boolean Search)")
            print("="*60)
            self.search_jobs(location=location)

            # Step 3a: Apply to LinkedIn jobs first (consumes quota)
            if self.jobs and remaining_quota > 0:
                step3_results = self.apply_to_jobs(max_applications=remaining_quota,
                                                   min_match_score=min_match_score)
                all_results.extend(step3_results)
                remaining_quota = max(0, max_applications - sum(1 for r in all_results if r.get('success')))

            # Step 0: Drain PENDING queue from DB (e-mail only, after LinkedIn)
            pending_jobs = self.load_pending_jobs_from_db(max_applications=remaining_quota)
            if pending_jobs and remaining_quota > 0:
                print("="*60)
                print("STEP 0 (Fila de Envio): Aplicar a vagas PENDING no banco (e-mail apenas, sem browser)")
                print("="*60)
                self.jobs = pending_jobs
                pending_results = self.apply_to_jobs(max_applications=len(pending_jobs),
                                                     min_match_score=min_match_score)
                all_results.extend(pending_results)
                applied_count = sum(1 for r in pending_results if r.get('success'))
                remaining_quota = max(0, remaining_quota - applied_count)
                print(f"  ✓ Enviados para PENDING: {applied_count} | Restante da cota: {remaining_quota}\n")

            if analyze_failures:
                self.analyze_previous_failures()

            # Prioridade 2: GitHub | Prioridade 3: Google Dorks (only if quota left)
            if remaining_quota <= 0:
                print("  ℹ Cota atingida. GitHub/Google Dorks não executados.\n")
            else:
                sniper_jobs = self.multi_source_discovery(iteration=iteration)

                new_sniper: List[JobListing] = []
                if sniper_jobs and self.db:
                    seen = set()
                    for j in self.jobs:
                        key = f"email:{j.email}" if getattr(j, "email", None) else j.url
                        seen.add(key)
                    for j in sniper_jobs:
                        key = f"email:{j.email}" if getattr(j, "email", None) else j.url
                        if key in seen:
                            continue
                        if self.db.is_job_processed(key):
                            continue
                        seen.add(key)
                        new_sniper.append(j)
                    if new_sniper:
                        print(f"  ✓ +{len(new_sniper)} vagas GitHub/Google Dorks para aplicar (cota restante)\n")

                if new_sniper and remaining_quota > 0:
                    self.jobs = new_sniper
                    step3b_results = self.apply_to_jobs(max_applications=remaining_quota,
                                                        min_match_score=min_match_score)
                    all_results.extend(step3b_results)

            return {
                'resume_data': self.resume_data.model_dump() if self.resume_data else {},
                'jobs_found': len(self.jobs),
                'applications': all_results,
                'successful_applications': sum(1 for r in all_results if r.get('success'))
            }

        except Exception as e:
            print(f"\n✗ Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}


def load_user_data(config_path: str = "user_config.json") -> Dict[str, str]:
    """Load user data from JSON and allow deployment-safe environment overrides."""
    config_file = Path(config_path)
    user_data: Dict[str, str] = {}

    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            user_data = json.load(f)

    env_mapping = {
        "name": "USER_NAME",
        "email": "USER_EMAIL",
        "phone": "USER_PHONE",
        "linkedin": "USER_LINKEDIN",
    }
    for key, env_name in env_mapping.items():
        value = os.getenv(env_name)
        if value:
            user_data[key] = value

    return user_data


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Job Automation Engine')
    parser.add_argument('--resume', type=str, default='curriculo.pdf', 
                       help='Path to resume PDF')
    parser.add_argument('--location', type=str, default='Brazil',
                       help='Job search location')
    parser.add_argument('--max-applications', type=int, default=5,
                       help='Maximum number of applications')
    parser.add_argument('--min-score', type=float, default=0.3,
                       help='Minimum match score for applications')
    parser.add_argument('--config', type=str, default='user_config.json',
                       help='Path to user config file')
    parser.add_argument('--query-search', type=str, default=None,
                       help='Custom search query (e.g., \'"USD" OR "EURO" OR "Contractor"\')')
    parser.add_argument('--blocked-keys', type=str, nargs='+', default=None,
                       help='Keywords to exclude using NOT (e.g., --blocked-keys "junior" "estagio" "hibrido")')
    parser.add_argument('--mode', type=str, default='post-sniper',
                       choices=['post-sniper', 'easy-apply'],
                       help='Application mode: post-sniper (LinkedIn posts) or easy-apply (LinkedIn Easy Apply jobs)')
    parser.add_argument('--auto-submit', action='store_true',
                       help='Automatically submit Easy Apply applications without review (use with caution)')
    parser.add_argument('--stats', action='store_true',
                       help='Show analytics dashboard (volume, success rate, avg score by source) and exit')
    parser.add_argument('--no-ai-fallback', action='store_true', dest='no_ai_fallback',
                       help='When Groq and Gemini fail (e.g. 429), use local heuristic scoring instead of default 0.6')
    parser.add_argument('--send-only', action='store_true', dest='send_only',
                       help='Skip Step 1 (Extraction) and Step 2 (Discovery); only run Step 3 (apply) for jobs in jobs.db with status PENDING')
    parser.add_argument('--once', action='store_true',
                       help='Run one pipeline iteration and exit (recommended for cron/systemd deployments)')
    
    args = parser.parse_args()
    
    # Load user data
    user_data = load_user_data(args.config)
    
    # Add query_search and blocked_keys from CLI if provided
    if args.query_search:
        user_data['query_search'] = args.query_search
    if args.blocked_keys:
        user_data['blocked_keys'] = args.blocked_keys
    if getattr(args, 'no_ai_fallback', False):
        user_data['no_ai_fallback'] = True
    if getattr(args, 'send_only', False):
        user_data['send_only'] = True
    
    if not user_data:
        print("WARNING: No user_config.json found. Creating template...")
        template = {
            "name": "Your Name",
            "email": "your.email@example.com",
            "phone": "+55 11 99999-9999",
            "linkedin": "https://linkedin.com/in/yourprofile"
        }
        with open('user_config.json', 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=2)
        print("Please edit user_config.json with your information and run again.")
        sys.exit(1)
    
    # Initialize database manager
    print("\n" + "="*60)
    print("INITIALIZING DATABASE")
    print("="*60)
    db = DatabaseManager(os.getenv("DATABASE_PATH", "jobs.db"))
    print(f"  Persistent database: {db.db_path}")
    
    # Show database statistics
    stats = db.get_statistics()
    if stats:
        print(f"  Total applications in database: {stats.get('total', 0)}")
        print(f"  By status: {stats.get('by_status', {})}")
        print(f"  Recent (24h): {stats.get('recent_24h', 0)}")
    print()

    # --stats: show analytics dashboard and exit
    if args.stats:
        from modules.analytics import run_stats
        run_stats(db_path=str(db.db_path))
        db.close()
        sys.exit(0)

    # --send-only: apenas Step 3 (aplicação) para vagas PENDING no jobs.db
    if getattr(args, 'send_only', False):
        engine = JobAutomationEngine(resume_path=args.resume, user_data=user_data, db=db)
        try:
            results = engine.run_send_only_pipeline(
                max_applications=args.max_applications,
                min_match_score=args.min_score,
            )
            print(f"\n  ✓ Send-only: {results.get('successful_applications', 0)}/{results.get('jobs_found', 0)} applications sent.")
        finally:
            db.close()
        sys.exit(0)
    
    # Run pipeline based on mode
    if args.mode == 'easy-apply':
        # LinkedIn Easy Apply mode
        from modules.linkedin_easy_applier import LinkedInEasyApplier
        
        print("\n" + "="*60)
        print("LINKEDIN EASY APPLY MODE")
        print("="*60)
        print(f"  Mode: Easy Apply")
        print(f"  Location: {args.location}")
        print(f"  Max Applications: {args.max_applications}")
        print(f"  Auto Submit: {args.auto_submit}")
        print()
        
        # Initialize Easy Apply applier
        easy_applier = LinkedInEasyApplier(resume_path=args.resume, user_data=user_data)
        
        if not easy_applier.start_browser(headless=False):
            print("  ✗ Failed to start browser. Exiting.")
            sys.exit(1)
        
        try:
            # Get resume data for AI context
            from modules.parser import ResumeParser
            parser = ResumeParser(args.resume)
            resume_data = parser.parse()
            
            # PRIORIDADE: Verificar se há vagas EASY_APPLY_PENDING no banco
            pending_jobs = db.get_pending_jobs(status="EASY_APPLY_PENDING", limit=args.max_applications)
            
            if pending_jobs:
                print(f"\n  📋 Found {len(pending_jobs)} pending jobs in database (EASY_APPLY_PENDING)")
                print(f"  🚀 [Step 2: The Negotiator] Starting applications for pending jobs...\n")
                
                # Process pending jobs first
                applied_count = 0
                for i, job in enumerate(pending_jobs[:args.max_applications], 1):
                    print(f"\n  [{i}/{len(pending_jobs)}] Applying to: {job['title']} at {job['company']}")
                    
                    # Apply to job using Step 2: The Negotiator (AI-powered form filling)
                    success = easy_applier.process_application_flow(
                        job['url'], 
                        auto_submit=args.auto_submit,
                        resume_data=resume_data.__dict__ if hasattr(resume_data, '__dict__') else {}
                    )
                    
                    if success:
                        applied_count += 1
                        # Update status in database
                        job_data = {
                            'url': job['url'],
                            'title': job['title'],
                            'company': job.get('company', 'Unknown'),
                            'match_score': job.get('match_score', 0.8)
                        }
                        db.save_job(job_data, status="SUCCESS" if args.auto_submit else "PENDING_REVIEW")
                        print(f"  ✓ Application {'submitted' if args.auto_submit else 'ready for review'}")
                    else:
                        job_data = {
                            'url': job['url'],
                            'title': job['title'],
                            'company': job.get('company', 'Unknown'),
                            'match_score': job.get('match_score', 0.0)
                        }
                        db.save_job(job_data, status="FAILED")
                        print(f"  ✗ Application failed")
                    
                    # Small delay between applications
                    time.sleep(3)
                
                print(f"\n  ✓ Completed: {applied_count}/{len(pending_jobs)} pending applications processed")
                
                # If we processed enough pending jobs, skip new scout
                if len(pending_jobs) >= args.max_applications:
                    print(f"\n  ℹ Processed {args.max_applications} pending jobs. Skipping new scout.")
                    # Don't do new scout, just finish
                    easy_applier.close_browser()
                    db.close()
                    print("\n✓ Database connection closed")
                    sys.exit(0)
            
            # Scout Mode: Search for Easy Apply jobs using sidebar list (only if no pending jobs or user wants more)
            # Get technologies from resume data if available
            # Use top 15 technical skills for scouting
            keywords = resume_data.stack_tecnico[:15] if resume_data.stack_tecnico else ["Python", "React", "Node.js"]
            
            print(f"\n  🔍 [Step 1: The Scout] Scouting Easy Apply jobs for {len(keywords)} technologies...")
            
            # NOVA LÓGICA OTIMIZADA: Aplicar imediatamente após escanear cada tecnologia
            # E processar vagas do banco ANTES de buscar novas
            all_jobs_found = []
            total_applied = 0
            
            # PRIMEIRO: Processar vagas pendentes do banco ANTES de buscar novas
            print(f"\n  📋 [Step 2: The Negotiator] Processing pending jobs from database first...")
            pending_from_db = db.get_pending_jobs(status="EASY_APPLY_PENDING", limit=args.max_applications)
            
            if pending_from_db:
                print(f"  → Found {len(pending_from_db)} pending jobs in database")
                for job in pending_from_db:
                    if total_applied >= args.max_applications:
                        break
                    
                    print(f"\n  📄 Applying to pending job: {job['title']} at {job['company']}")
                    
                    # APLICAR AGORA: Step 2 - The Negotiator
                    success = easy_applier.process_application_flow(
                        job['url'], 
                        auto_submit=args.auto_submit,
                        resume_data=resume_data.__dict__ if hasattr(resume_data, '__dict__') else {}
                    )
                    
                    if success:
                        total_applied += 1
                        job_data = {
                            'url': job['url'],
                            'title': job['title'],
                            'company': job.get('company', 'Unknown'),
                            'match_score': job.get('match_score', 0.8)
                        }
                        db.save_job(job_data, status="SUCCESS" if args.auto_submit else "PENDING_REVIEW")
                        print(f"  ✓ Application {'submitted' if args.auto_submit else 'ready for review'}")
                    else:
                        job_data = {
                            'url': job['url'],
                            'title': job['title'],
                            'company': job.get('company', 'Unknown'),
                            'match_score': job.get('match_score', 0.0)
                        }
                        db.save_job(job_data, status="FAILED")
                        print(f"  ✗ Application failed")
                    
                    time.sleep(3)
            
            # Se já atingiu o limite, não precisa buscar novas
            if total_applied >= args.max_applications:
                print(f"\n  ✓ Reached max applications limit ({args.max_applications}) from pending jobs. Skipping new scout.")
            else:
                # SEGUNDO: Buscar novas vagas tecnologia por tecnologia e aplicar imediatamente
                for tech_idx, tech in enumerate(keywords, 1):
                    if total_applied >= args.max_applications:
                        break
                    
                    print(f"\n  📊 [{tech_idx}/{len(keywords)}] Processing technology: {tech}")
                    
                    # Scout jobs for this technology
                    tech_jobs = easy_applier.scout_easy_apply_jobs(
                        location=args.location,
                        keywords=[tech],  # Scout one technology at a time
                        max_jobs_per_tech=25
                    )
                    
                    if not tech_jobs:
                        print(f"  ⚠ No Easy Apply jobs found for {tech}. Continuing...")
                        continue
                    
                    print(f"  ✓ Found {len(tech_jobs)} Easy Apply jobs for {tech}")
                    all_jobs_found.extend(tech_jobs)
                    
                    # APLICAR IMEDIATAMENTE: Process each job found for this technology
                    print(f"  🚀 [Step 2: The Negotiator] Applying to jobs found for {tech}...\n")
                    
                    for job_idx, job in enumerate(tech_jobs, 1):
                        if total_applied >= args.max_applications:
                            print(f"\n  ✓ Reached max applications limit ({args.max_applications}). Stopping.")
                            break
                        
                        if not job.get('has_easy_apply'):
                            print(f"  ⏭ Skipping {job['title']} at {job['company']} (no Easy Apply)")
                            continue
                        
                        # Check if already processed (mas não pular se for EASY_APPLY_PENDING ou FAILED - tentar aplicar)
                        if db.is_job_processed(job['url']):
                            # Verificar status no banco
                            try:
                                if hasattr(db, 'conn') and db.conn:
                                    cursor = db.conn.cursor()
                                    cursor.execute("SELECT status FROM jobs_processed WHERE url = ?", (job['url'],))
                                    result = cursor.fetchone()
                                    if result:
                                        status = result[0]
                                        # Só pular se já foi SUCCESS ou PENDING_REVIEW
                                        if status in ['SUCCESS', 'PENDING_REVIEW']:
                                            print(f"  ⏭ Already successfully processed (status: {status}). Skipping...")
                                            continue
                                        # Se for FAILED ou EASY_APPLY_PENDING, tentar novamente
                                        print(f"  🔄 Retrying job (previous status: {status})...")
                                    else:
                                        # Não encontrou no banco, continuar normalmente
                                        pass
                            except Exception as e:
                                # Se der erro ao verificar, continuar normalmente
                                print(f"  ⚠ Could not check job status, proceeding anyway...")
                                pass
                        
                        print(f"\n  [{job_idx}/{len(tech_jobs)}] Applying to: {job['title']} at {job['company']}")
                        
                        # Salvar no banco primeiro (ou atualizar se já existe)
                        job_data = {
                            'url': job['url'],
                            'title': job['title'],
                            'company': job.get('company', 'Unknown'),
                            'match_score': 0.0
                        }
                        db.save_job(job_data, status="EASY_APPLY_PENDING")
                        job_id_display = job.get('job_id', 'N/A')
                        print(f"  ✅ [Scout] Saved: {job['title']} (ID: {job_id_display}) to database.")
                        
                        # APLICAR AGORA: Step 2 - The Negotiator
                        success = easy_applier.process_application_flow(
                            job['url'], 
                            auto_submit=args.auto_submit,
                            resume_data=resume_data.__dict__ if hasattr(resume_data, '__dict__') else {}
                        )
                        
                        if success:
                            total_applied += 1
                            # Update status in database
                            job_data['match_score'] = 0.8
                            db.save_job(job_data, status="SUCCESS" if args.auto_submit else "PENDING_REVIEW")
                            print(f"  ✓ Application {'submitted' if args.auto_submit else 'ready for review'}")
                        else:
                            db.save_job(job_data, status="FAILED")
                            print(f"  ✗ Application failed")
                        
                        # Small delay between applications
                        time.sleep(3)
                    
                    # Se atingiu o limite, parar de buscar mais tecnologias
                    if total_applied >= args.max_applications:
                        break
            
            print(f"\n  ✓ Completed: {total_applied} applications processed from {len(all_jobs_found)} jobs found")
            
        finally:
            easy_applier.close_browser()
            db.close()
            print("\n✓ Database connection closed")
    
    else:
        # Default: Post Sniper mode
        engine = JobAutomationEngine(resume_path=args.resume, user_data=user_data, db=db)
        
        iteration = 0
        try:
            while True:
                iteration += 1
                print(f"\n{'='*60}")
                print(f"PIPELINE ITERATION #{iteration}")
                print(f"{'='*60}\n")
                
                try:
                    results = engine.run_full_pipeline(
                        location=args.location,
                        max_applications=args.max_applications,
                        min_match_score=args.min_score,
                        iteration=iteration
                    )

                    if args.once and results.get('error'):
                        raise RuntimeError(results['error'])
    
                    # Save results after each iteration
                    data_dir = Path(os.getenv("DATA_DIR", ".")).expanduser()
                    output_file = Path(os.getenv("RESULTS_PATH", str(data_dir / "application_results.json"))).expanduser()
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(results, f, indent=2, ensure_ascii=False)
                    
                    print(f"\nResults saved to: {output_file}")
                    
                    # Show database statistics
                    stats = db.get_statistics()
                    if stats:
                        print(f"\nDatabase Statistics:")
                        print(f"  Total applications: {stats.get('total', 0)}")
                        print(f"  By status: {stats.get('by_status', {})}")
                    
                    if args.once:
                        print("\n✓ Single-run mode complete.")
                        break

                    # Check if no jobs were found or no applications were made
                    jobs_found = results.get('jobs_found', 0)
                    applications = results.get('applications', [])
                    
                    if jobs_found == 0 or len(applications) == 0:
                        print(f"\n⚠ No new jobs found or no applications made in this iteration.")
                        print(f"   Waiting 15 minutes (900 seconds) before retrying...")
                        print(f"   (Press Ctrl+C to stop)")
                        time.sleep(900)  # Wait 15 minutes before retrying
                    else:
                        # Small delay between iterations if jobs were found
                        print(f"\n✓ Iteration complete. Waiting 15 minutes before next iteration...")
                        print(f"   (Press Ctrl+C to stop)")
                        time.sleep(900)  # Wait 15 minutes between iterations
                        
                except KeyboardInterrupt:
                    print(f"\n\n⚠ Pipeline stopped by user (Ctrl+C)")
                    break
                except EmailQuotaExceeded as e:
                    print("\n" + "="*60)
                    print("🛑 EMAIL QUOTA EXCEEDED (Gmail / SMTP limit)")
                    print("="*60)
                    print(f"   {e.message}")
                    print("   State has been saved in jobs.db. Do NOT keep sending or you risk")
                    print("   account reputation / block.")
                    print("   → Pause for at least 2 hours, then run the same command again.")
                    print("="*60 + "\n")
                    sys.exit(1)
                except Exception as e:
                    print(f"\n✗ Error in pipeline iteration: {e}")
                    import traceback
                    traceback.print_exc()
                    if args.once:
                        raise
                    print(f"   Waiting 15 minutes before retrying...")
                    time.sleep(900)  # Wait 15 minutes on error before retrying
        finally:
            # Close database connection
            db.close()
            print("\n✓ Database connection closed")
