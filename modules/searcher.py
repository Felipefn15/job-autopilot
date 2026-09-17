"""
Job Search Module
Searches for real jobs on LinkedIn and Indeed using web scraping
Uses AI (Gemini) for intelligent job matching
"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import re
import time
from .brain import AIBrain
from .models import JobListing
from .aggregator import JobAggregator


class JobSearcher:
    """Searches for jobs on LinkedIn and Indeed"""

    def __init__(self, resume_data, user_data=None):
        self.resume_data = resume_data
        self.user_data = user_data or {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.brain = AIBrain(no_ai_fallback=self.user_data.get("no_ai_fallback", False))
    
    def search_indeed(self, location: str = "Brazil", max_results: int = 20) -> List[JobListing]:
        """Search REMOTE jobs on Indeed that accept LATAM candidates"""
        jobs = []
        
        # Build search query with REMOTE keywords (mandatory)
        keywords = " ".join(self.resume_data.stack_tecnico[:5])  # Top 5 skills
        # Add remote keywords to ensure we only get remote jobs
        remote_keywords = "Remote OR Remoto OR 'Work from Home' OR 'Anywhere' OR 'LATAM' OR 'Latin America'"
        query = f"{keywords} {self.resume_data.senioridade_pretendida} ({remote_keywords})"
        
        # Indeed search URL with remote filter
        base_url = "https://www.indeed.com/jobs"
        params = {
            'q': query,
            'l': 'Remote',  # Force remote location
            'radius': '0',  # No radius for remote
            'fromage': '1',  # Last 24 hours
            'sort': 'date',
            'remotejob': 'true'  # Indeed remote filter
        }
        
        try:
            response = self.session.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find job cards (Indeed structure may vary)
            job_cards = soup.find_all('div', class_=re.compile(r'job_seen_beacon|jobCard'))
            
            for card in job_cards[:max_results]:
                try:
                    # Extract job title
                    title_elem = card.find('h2', class_=re.compile(r'jobTitle|title'))
                    if not title_elem:
                        title_elem = card.find('a', {'data-jk': True})
                    
                    title = title_elem.get_text(strip=True) if title_elem else "N/A"
                    
                    # Extract company
                    company_elem = card.find('span', class_=re.compile(r'companyName'))
                    if not company_elem:
                        company_elem = card.find('a', {'data-testid': 'company-name'})
                    company = company_elem.get_text(strip=True) if company_elem else "N/A"
                    
                    # Extract location
                    location_elem = card.find('div', class_=re.compile(r'companyLocation'))
                    location_text = location_elem.get_text(strip=True) if location_elem else "Remote"
                    
                    # Filter: Only accept remote locations
                    location_lower = location_text.lower()
                    remote_indicators = ['remote', 'remoto', 'anywhere', 'work from home', 'wfh', 
                                        'latam', 'latin america', 'brazil', 'worldwide', 'global']
                    is_remote = any(indicator in location_lower for indicator in remote_indicators)
                    
                    # Reject hybrid or on-site
                    reject_indicators = ['hybrid', 'on-site', 'onsite', 'office', 'local only']
                    is_rejected = any(indicator in location_lower for indicator in reject_indicators)
                    
                    if is_rejected or not is_remote:
                        continue  # Skip non-remote jobs
                    
                    # Extract URL
                    link_elem = card.find('a', href=True)
                    if link_elem:
                        job_url = link_elem['href']
                        if not job_url.startswith('http'):
                            job_url = f"https://www.indeed.com{job_url}"
                    else:
                        continue
                    
                    # Extract posted date
                    date_elem = card.find('span', class_=re.compile(r'date'))
                    posted_date = date_elem.get_text(strip=True) if date_elem else None
                    
                    # Filter by last 24 hours
                    if posted_date and 'hour' not in posted_date.lower() and 'just now' not in posted_date.lower():
                        if 'day' in posted_date.lower():
                            continue
                    
                    job = JobListing(
                        title=title,
                        company=company,
                        location=location_text,
                        url=job_url,
                        posted_date=posted_date,
                        description=""
                    )
                    
                    # Calculate match score
                    job.match_score = self._calculate_match_score(job)
                    
                    # CRITICAL: Only add real jobs (no validation here, will validate later with Playwright)
                    # Basic URL validation
                    if job_url and job_url.startswith('http'):
                        jobs.append(job)
                    
                except Exception as e:
                    print(f"Error parsing job card: {e}")
                    continue
            
            time.sleep(1)  # Be respectful with requests
            
        except Exception as e:
            print(f"Error searching Indeed: {e}")
        
        return jobs
    
    def search_linkedin(self, location: str = "Brazil", max_results: int = 20) -> List[JobListing]:
        """Search REMOTE jobs on LinkedIn that accept LATAM candidates"""
        jobs = []
        
        # Build search query with REMOTE keywords
        keywords = " ".join(self.resume_data.stack_tecnico[:5])
        remote_keywords = "Remote Remoto 'Work from Home' Anywhere LATAM"
        query = f"{keywords} {self.resume_data.senioridade_pretendida} {remote_keywords}"
        
        # LinkedIn job search URL with remote filter
        base_url = "https://www.linkedin.com/jobs/search"
        params = {
            'keywords': query,
            'location': 'Worldwide',  # Focus on worldwide remote
            'f_TPR': 'r86400',  # Last 24 hours
            'f_WT': '2',  # Remote filter (2 = Remote)
            'f_CR': '103105917',  # Brazil location code (optional)
            'sortBy': 'DD'
        }
        
        try:
            response = self.session.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # LinkedIn structure (may require login for full access)
            job_cards = soup.find_all('div', class_=re.compile(r'job-search-card|base-card'))
            
            for card in job_cards[:max_results]:
                try:
                    # Extract job title
                    title_elem = card.find('h3', class_=re.compile(r'base-search-card__title'))
                    if not title_elem:
                        title_elem = card.find('a', class_=re.compile(r'job-card-list__title'))
                    title = title_elem.get_text(strip=True) if title_elem else "N/A"
                    
                    # Extract company
                    company_elem = card.find('h4', class_=re.compile(r'base-search-card__subtitle'))
                    if not company_elem:
                        company_elem = card.find('a', class_=re.compile(r'job-card-container__company-name'))
                    company = company_elem.get_text(strip=True) if company_elem else "N/A"
                    
                    # Extract location
                    location_elem = card.find('span', class_=re.compile(r'job-search-card__location'))
                    location_text = location_elem.get_text(strip=True) if location_elem else "Remote"
                    
                    # Filter: Only accept remote locations
                    location_lower = location_text.lower()
                    remote_indicators = ['remote', 'remoto', 'anywhere', 'work from home', 'wfh', 
                                        'latam', 'latin america', 'brazil', 'worldwide', 'global']
                    is_remote = any(indicator in location_lower for indicator in remote_indicators)
                    
                    # Reject hybrid or on-site
                    reject_indicators = ['hybrid', 'on-site', 'onsite', 'office', 'local only', 'united states only']
                    is_rejected = any(indicator in location_lower for indicator in reject_indicators)
                    
                    if is_rejected or not is_remote:
                        continue  # Skip non-remote jobs
                    
                    # Extract URL
                    link_elem = card.find('a', href=True, class_=re.compile(r'base-card__full-link|job-card-list__title'))
                    if link_elem:
                        job_url = link_elem['href']
                        if not job_url.startswith('http'):
                            job_url = f"https://www.linkedin.com{job_url}"
                    else:
                        continue
                    
                    # Extract posted date
                    date_elem = card.find('time', class_=re.compile(r'job-search-card__listdate'))
                    posted_date = date_elem.get('datetime') if date_elem else None
                    
                    job = JobListing(
                        title=title,
                        company=company,
                        location=location_text,
                        url=job_url,
                        posted_date=posted_date,
                        description=""
                    )
                    
                    job.match_score = self._calculate_match_score(job)
                    jobs.append(job)
                    
                except Exception as e:
                    print(f"Error parsing LinkedIn job card: {e}")
                    continue
            
            time.sleep(2)  # Be respectful with LinkedIn
            
        except Exception as e:
            print(f"Error searching LinkedIn: {e}")
            print("Note: LinkedIn may require authentication or have anti-scraping measures")
        
        return jobs
    
    def _calculate_match_score(self, job: JobListing) -> float:
        """Calculate how well a job matches the resume using AI (Gemini) with remote eligibility check"""
        # Force minimum score for GitHub BR jobs (curated by devs, high quality)
        if hasattr(job, 'source') and job.source == 'github_br':
            print(f"  🇧🇷 GitHub BR job detected: {job.title} - Will apply minimum score of 0.7")
        
        # Try AI-based evaluation first
        if self.brain and job.description:
            try:
                resume_dict = {
                    "stack_tecnico": self.resume_data.stack_tecnico,
                    "experiencia_anos": self.resume_data.experiencia_anos,
                    "senioridade_pretendida": self.resume_data.senioridade_pretendida,
                    "palavras_chave": self.resume_data.palavras_chave
                }
                # Pass job location for remote eligibility validation
                ai_score = self.brain.evaluate_job(job.description, resume_dict, job.location)
                
                # Force minimum score for GitHub BR jobs
                if hasattr(job, 'source') and job.source == 'github_br':
                    ai_score = max(ai_score, 0.7)
                    print(f"  ✓ GitHub BR score adjusted to: {ai_score:.2f}")
                
                return ai_score
            except Exception as e:
                print(f"AI job evaluation failed, using fallback: {e}")
                
                # Fallback: check for common technologies
                candidate_skills = self.resume_data.stack_tecnico
                job_text_lower = (job.description or "").lower()
                
                common_techs = [skill for skill in candidate_skills if str(skill).lower() in job_text_lower]
                
                if common_techs:
                    fallback_score = 0.5
                    # REMOVED: GitHub BR logic (LinkedIn Only Mode)
                    # if hasattr(job, 'source') and job.source == 'github_br':
                    #     fallback_score = 0.7
                    print(f"  ✓ Fallback: {len(common_techs)} technologies match. Score: {fallback_score}")
                    return fallback_score
        
        # Fallback to rule-based scoring
        score = 0.0
        max_score = 0.0
        
        # Check title match
        title_lower = job.title.lower()
        for skill in self.resume_data.stack_tecnico:
            if skill.lower() in title_lower:
                score += 2.0
                max_score += 2.0
        
        # Check seniority match
        seniority_lower = self.resume_data.senioridade_pretendida.lower()
        if seniority_lower in title_lower or seniority_lower in job.description.lower():
            score += 3.0
            max_score += 3.0
        
        # Check keywords match
        for keyword in self.resume_data.palavras_chave[:10]:
            if keyword.lower() in job.description.lower():
                score += 1.0
                max_score += 1.0
        
        # Normalize score
        if max_score > 0:
            return min(score / max_score, 1.0)
        return 0.0
    
    def search_all(self, location: str = "Brazil", max_per_source: int = 10, 
                 target_count: int = 100, query_search: str = None, blocked_keys: List[str] = None,
                 max_applications: int = None) -> List[JobListing]:
        """
        LinkedIn Only Mode - Focuses exclusively on LinkedIn Posts
        All other sources (RemoteOK, WWR, Arbeitnow, GitHub BR) are disabled
        
        Args:
            location: Região para remoto (Brazil, Latam, Worldwide). Usado na query para remoto/latam/anywhere.
            max_per_source: Maximum jobs per source (not used in LinkedIn Only Mode)
            target_count: Target number of jobs (not used in LinkedIn Only Mode)
            query_search: Custom search query (e.g., '"USD" OR "EURO" OR "Contractor"')
            blocked_keys: List of keywords to exclude using NOT (e.g., ['presencial', 'hibrido', 'estagio'])
        """
        all_jobs = []
        
        # DISABLED: Other sources (RemoteOK, WWR, Arbeitnow, GitHub BR, Indeed, LinkedIn Jobs)
        # Focus exclusively on LinkedIn Posts for direct email contact
        # print("Searching real job sources (APIs first)...")
        # from .real_sources import RealJobSources
        # real_sources = RealJobSources(self.resume_data)
        # api_jobs = real_sources.search_all_real_sources(target_count=target_count)
        # all_jobs.extend(api_jobs)
        
        # DISABLED: Core scrapers (Indeed, LinkedIn Jobs)
        # if len(all_jobs) < target_count:
        #     print(f"\nOnly {len(all_jobs)} jobs from APIs. Trying core scrapers...")
        #     print("  (Note: LinkedIn/Indeed may return 403 - this is expected)")
        #     
        #     indeed_jobs = self.search_indeed("Remote", max_per_source)
        #     all_jobs.extend(indeed_jobs)
        #     print(f"  Found {len(indeed_jobs)} remote jobs on Indeed")
        #     
        #     linkedin_jobs = self.search_linkedin("Worldwide", max_per_source)
        #     all_jobs.extend(linkedin_jobs)
        #     print(f"  Found {len(linkedin_jobs)} remote jobs on LinkedIn")
        
        # LinkedIn Post Searcher (SNIPER MODE - Multi-Stack Boolean Search)
        # THIS IS THE ONLY SOURCE NOW
        try:
            print(f"\n🎯 LinkedIn Post Sniper Mode (Multi-Stack Boolean Search)")
            from .linkedin_post_searcher import LinkedInPostSearcher
            from .database import DatabaseManager
            
            linkedin_searcher = LinkedInPostSearcher(self.resume_data, self.user_data if hasattr(self, 'user_data') else None)
            
            # Get skills from resume data
            skills = self.resume_data.stack_tecnico if hasattr(self.resume_data, 'stack_tecnico') else []
            
            # Fallback to hardcoded skills if empty (mesmas skills do parser.py)
            if not skills:
                skills = [
                    'React', 'Next.js', 'React Native', 'Node.js', 'Python', 
                    'Ruby on Rails', 'Go', 'AWS', 'OpenAI', 'LangChain', 
                    'TypeScript', 'SQL'
                ]
                print(f"  ⚠ No skills found in resume. Using hardcoded skills: {skills[:5]}...")
            
            # PRIORIZAÇÃO: Foca em tecnologias de AI & Automation com métricas de impacto
            # Prioriza: OpenAI, LangChain, React, Python, Node.js, TypeScript, AWS
            priority_skills = ['React', 'Python', 'Node.js', 'TypeScript', 'AWS', 'Next.js', 'React Native', 'Go', 'Ruby on Rails', 'SQL','OpenAI', 'LangChain']
            
            # Reordena skills: prioriza as tecnologias de AI & Automation primeiro
            prioritized_skills = []
            seen_priority = set()
            
            # Adiciona skills prioritárias primeiro (se estiverem na lista)
            for priority_skill in priority_skills:
                for skill in skills:
                    if skill.lower() == priority_skill.lower() and skill.lower() not in seen_priority:
                        prioritized_skills.append(skill)
                        seen_priority.add(skill.lower())
                        break
            
            # Adiciona skills restantes (que não são prioritárias)
            for skill in skills:
                if skill.lower() not in seen_priority:
                    prioritized_skills.append(skill)
                    seen_priority.add(skill.lower())
            
            # Limit to top 15 skills to avoid too many queries
            top_skills = prioritized_skills[:15]
            print(f"  📋 Searching for {len(top_skills)} technologies (prioritized: AI & Automation): {', '.join(top_skills[:5])}...")
            print(f"  📍 Query remoto: {location or 'Brazil'} → ex: (tech) AND \"hiring\" AND \"Latam\" (presencial/híbrido filtrados após busca)")
            
            # Initialize database for deduplication (if available)
            db = None
            try:
                # Try to get database from parent if available
                if hasattr(self, 'db'):
                    db = self.db
                else:
                    # Create temporary database connection for deduplication
                    db = DatabaseManager("jobs.db")
            except:
                print("  ⚠ Database not available for deduplication. Continuing without it...")
            
            all_posts = []
            seen_post_urls = set()  # In-memory deduplication for this session (by URL)
            seen_post_ids = set()  # In-memory deduplication for this session (by content hash)
            seen_emails = set()  # Deduplicação de emails (evita enviar para mesmo email múltiplas vezes)
            total_emails_sent = 0  # Track total emails sent across all skills
            
            # Helper function to process and send emails immediately
            def process_and_send_emails(posts_for_skill, skill_name):
                """Process posts and send emails immediately for a specific skill"""
                nonlocal total_emails_sent, seen_emails
                
                if not posts_for_skill:
                    return 0
                
                # Convert posts to jobs
                jobs_for_skill = linkedin_searcher.convert_posts_to_jobs(posts_for_skill)
                
                if not jobs_for_skill:
                    return 0
                
                # Filter jobs with emails
                email_jobs = [j for j in jobs_for_skill if hasattr(j, 'email') and j.email]
                
                if not email_jobs:
                    return 0
                
                # Import emailer (EmailQuotaExceeded propagates so main can pause 2h)
                from .emailer import EmailApplier, EmailQuotaExceeded
                emailer = EmailApplier()
                
                # Get resume path (try multiple sources)
                resume_path = "curriculo.pdf"
                if hasattr(self, 'resume_path'):
                    resume_path = self.resume_path
                elif hasattr(linkedin_searcher, 'user_data') and linkedin_searcher.user_data and 'resume_path' in linkedin_searcher.user_data:
                    resume_path = linkedin_searcher.user_data['resume_path']
                elif hasattr(self, 'user_data') and self.user_data and 'resume_path' in self.user_data:
                    resume_path = self.user_data['resume_path']
                
                # Verify resume file exists
                from pathlib import Path
                resume_file = Path(resume_path)
                if not resume_file.exists():
                    print(f"     ⚠ Resume file not found: {resume_path}. Skipping email sends.")
                    return 0
                
                emails_sent_count = 0
                
                # Get user data from linkedin_searcher (it has the user_data)
                user_data = linkedin_searcher.user_data if hasattr(linkedin_searcher, 'user_data') and linkedin_searcher.user_data else {}
                if not user_data and hasattr(self, 'user_data'):
                    user_data = self.user_data
                
                # Do-not-contact list (recruiters who already replied)
                try:
                    from .emailer import get_do_not_contact_emails
                    do_not_contact = get_do_not_contact_emails()
                except Exception:
                    do_not_contact = set()

                # Send emails immediately
                for job in email_jobs:
                    try:
                        if (job.email or "").strip().lower() in do_not_contact:
                            print(f"     ⏭ Skipping (do not contact - already replied): {job.email}")
                            continue
                        # Dedupe: same (email, job) in this session
                        job_id = getattr(job, 'url', None) or (job.email and f"email:{job.email}")
                        session_key = (job.email or "", job_id)
                        if session_key in seen_emails:
                            print(f"     ⏭ Skipping {job.email} (already sent in this session for this job)")
                            continue
                        
                        # Already sent to this (email, job_id)? Skip so we can send to same email for different jobs
                        if db and job.email and job_id:
                            if getattr(db, 'is_sent_to_email_for_job', None) and db.is_sent_to_email_for_job(job.email, job_id):
                                print(f"     ⏭ Skipping: already sent to {job.email} for this job (Ref #{str(job_id)[-8:]})")
                                continue
                        
                        seen_emails.add(session_key)
                        
                        # Generate personalized cover letter with skill context
                        language = getattr(job, 'language', 'en') or 'en'
                        search_skill = getattr(job, 'search_skill', skill_name)
                        cover_letter = linkedin_searcher.generate_cover_letter(
                            job.description, language, job.title, search_skill=search_skill
                        )

                        # Append post URL + job code + external links so recruiter can match the email
                        # to the specific post/vacancy (critical when post has an ID code)
                        _post_url = getattr(job, 'url', None)
                        _ext_links = [l for l in (getattr(job, 'external_links', None) or []) if isinstance(l, str) and l.startswith('http')]
                        _code = getattr(job, 'job_code', None)
                        _lang = language
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
                            if _lang == 'pt':
                                ref_parts.append(f"Link da vaga: {_ext_links[0]}")
                            elif _lang == 'es':
                                ref_parts.append(f"Link de la vacante: {_ext_links[0]}")
                            else:
                                ref_parts.append(f"Job link: {_ext_links[0]}")
                        if ref_parts:
                            cover_letter = (cover_letter or "") + "\n\n" + "\n".join(ref_parts)

                        # Get resume_data for enhanced subject line
                        resume_data_dict = None
                        if hasattr(linkedin_searcher, 'resume_data'):
                            resume_data = linkedin_searcher.resume_data
                            resume_data_dict = {
                                'experiencia_anos': getattr(resume_data, 'experiencia_anos', 8),
                                'senioridade_pretendida': getattr(resume_data, 'senioridade_pretendida', 'senior'),
                                'stack_tecnico': getattr(resume_data, 'stack_tecnico', [])
                            }
                        
                        # Snippet: job title + company so recruiter identifies which post (readable, no hashtags)
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

                        _language = getattr(job, 'language', 'en') or 'en'

                        _job_code = getattr(job, 'job_code', None)
                        _job_id_ref = _job_code if _job_code else getattr(job, 'url', None)

                        success, smtp_message_id, _email_subject = emailer.send_application_email(
                            to_email=job.email,
                            job_subject=job.title,
                            resume_path=str(resume_path),
                            user_data=user_data,
                            job_description=job.description,
                            cover_letter=cover_letter,
                            resume_data=resume_data_dict,
                            match_score=job.match_score,
                            company_name=getattr(job, 'company', None),
                            job_id=_job_id_ref,
                            job_description_snippet=job_snippet or None,
                            language=_language,
                        )
                        
                        if success:
                            emails_sent_count += 1
                            total_emails_sent += 1
                            
                            # Save by (url=post_url, email, job_id) so same email can get another send for different job
                            if db:
                                job_url = getattr(job, 'url', None) or f"email:{job.email}"
                                job_data = {
                                    'url': job_url,
                                    'title': job.title,
                                    'company': job.company,
                                    'match_score': job.match_score,
                                    'error_details': [],
                                    'source': 'linkedin_post',
                                    'email': job.email,
                                    'job_id': job_url,
                                }
                                db.save_job(job_data, status="SUCCESS")
                                if smtp_message_id:
                                    db.update_smtp_message_id(job_url, smtp_message_id)
                            
                            print(f"     ✅ Sent to {job.email}")
                        else:
                            print(f"     ⚠ Failed: {job.email}")
                        
                        # Small delay between emails
                        time.sleep(1)
                        
                    except EmailQuotaExceeded:
                        # Trava: não continuar enviando; estado já está no jobs.db
                        raise
                    except Exception as email_error:
                        # Resiliência SMTP: Log erro e continua sem interromper busca
                        error_str = str(email_error).lower()
                        
                        # Categorize common SMTP errors
                        if 'smtp' in error_str or 'connection' in error_str:
                            print(f"     ⚠ SMTP Error sending to {job.email}: {email_error}")
                        elif 'quota' in error_str or 'limit' in error_str or 'exceeded' in error_str:
                            print(f"     ⚠ SMTP Quota/Limit exceeded for {job.email}: {email_error}")
                        elif 'mailbox' in error_str or 'full' in error_str or '550' in error_str:
                            print(f"     ⚠ Mailbox full or invalid for {job.email}: {email_error}")
                        else:
                            print(f"     ⚠ Error sending email to {job.email}: {email_error}")
                        
                        # Continue to next email without interrupting the search
                        continue
                
                return emails_sent_count
            
            # LinkedIn post search structure: (technology) AND "hiring" AND "remoto" AND (LATAM/Brazil)
            # "remoto" is mandatory to exclude on-site Spain/Europe jobs that appear in LATAM searches.
            loc_lower = (location or "Brazil").strip().lower()
            if "latam" in loc_lower or "latin" in loc_lower or "brazil" in loc_lower or "brasil" in loc_lower:
                remote_term = '"LATAM" OR "Brazil"'
            else:
                remote_term = '"remote"'

            merged_blocked = list(blocked_keys) if blocked_keys else []

            def build_clean_query(tech, custom_query="", blocked_keys=[]):
                """Build query: (tech) AND "hiring" AND "remoto" AND (LATAM/Brazil)."""
                base = f'("{tech}")'
                if custom_query and custom_query.strip():
                    # User-provided query: use as-is (no "remoto" injection)
                    core = f' AND "hiring" AND ({custom_query.strip()})'
                else:
                    # Default: require "remoto" AND geographic focus (LATAM/Brazil)
                    core = f' AND "hiring" AND "remoto" AND ({remote_term})'
                negatives = ""
                for key in (blocked_keys or []):
                    if key and str(key).strip():
                        negatives += f' NOT "{str(key).strip()}"'
                return f"{base}{core}{negatives}"
            
            # Iterate over each skill individually
            for skill in top_skills:
                try:
                    # Build clean query (com remote obrigatório e bloqueio hibrido/presencial)
                    boolean_query = build_clean_query(skill, query_search, merged_blocked)
                    
                    print(f"\n  🔍 Searching for: {skill}")
                    
                    # Captura de Performance: Inicia timer para medir tempo da busca desta tecnologia
                    tech_search_start_time = time.time()
                    
                    # NOVA SEMÂNTICA: --max-applications representa o limite POR TECNOLOGIA
                    # Atribuição direta: max_posts_per_skill recebe o valor integral de max_applications
                    if max_applications and max_applications > 0:
                        # Usa o valor diretamente (sem divisão)
                        max_posts_per_skill = max_applications
                        print(f"    🎯 Sniper Mode: Analisando até {max_applications} posts específicos para {skill}")
                    else:
                        # Fallback: usa max_per_source ou 100 (limite padrão)
                        # IMPORTANTE: Se max_per_source for 10 (padrão), usa 100 para LinkedIn (não 10)
                        max_posts_per_skill = 100 if max_per_source <= 10 else max_per_source
                        max_posts_per_skill = min(max_posts_per_skill, 200)  # Limite máximo para fallback
                        print(f"    📊 max_applications not set, using default: max_posts_per_skill={max_posts_per_skill}")
                    
                    # Search with this skill-specific query (pass cache to avoid duplicates)
                    posts = linkedin_searcher.search_posts_advanced(boolean_query, max_posts=max_posts_per_skill, seen_post_ids=seen_post_ids)
                    
                    # Captura de Performance: Registra tempo total da busca
                    tech_search_elapsed = time.time() - tech_search_start_time
                    print(f"    [LinkedIn] Busca para {skill} finalizada em {tech_search_elapsed:.1f}s")
                    
                    # FILTRO DE DUPLICATAS REFORÇADO: Com aumento do volume, verifica jobs.db
                    # Se um post aparecer em 'Python' e 'Django', só será processado uma vez
                    new_posts = []
                    duplicates_skipped = 0
                    for post in posts:
                        post_url = post.get('url') or f"linkedin_post_{hash(post.get('text', '')[:100])}"
                        
                        # Check in-memory deduplication (dentro da mesma sessão)
                        if post_url in seen_post_urls:
                            duplicates_skipped += 1
                            continue
                        
                        # Check database deduplication (CRÍTICO: evita reprocessar posts de outras tecnologias)
                        if db and db.is_job_processed(post_url):
                            duplicates_skipped += 1
                            continue
                        
                        # Mark as seen and add
                        seen_post_urls.add(post_url)
                        
                        # Add skill context to post for personalized cover letter
                        post['search_skill'] = skill
                        new_posts.append(post)
                    
                    if duplicates_skipped > 0:
                        print(f"     ⏭ Skipped {duplicates_skipped} duplicate posts (already processed in jobs.db or this session)")
                    
                    all_posts.extend(new_posts)
                    print(f"     ✓ Found {len(new_posts)} new posts (total: {len(all_posts)} unique posts)")
                    
                    # DISPARO IMEDIATO: Process and send emails for this skill
                    if new_posts:
                        emails_sent = process_and_send_emails(new_posts, skill)
                        if emails_sent > 0:
                            print(f"     🚀 Total de {emails_sent} e-mails disparados para a tecnologia {skill}")
                    
                    # Small delay between queries to avoid rate limiting
                    time.sleep(2)
                    
                except Exception as skill_error:
                    print(f"  ⚠ Error searching for {skill}: {skill_error}")
                    continue
            
            # Also do email-specific queries for top skills
            print(f"\n  📧 Running email-specific queries for top skills...")
            top_email_skills = top_skills[:5]  # Top 5 for email queries
            
            for skill in top_email_skills:
                try:
                    skill_quoted = f'"{skill}"' if ' ' in skill else skill
                    
                    # Email query mirrors the main query: require "remoto" + LATAM/Brazil when no custom query
                    if query_search and query_search.strip():
                        email_query_parts = [f'({skill_quoted})', 'AND "hiring"', f'AND ({query_search.strip()})', 'AND "email"']
                    else:
                        email_query_parts = [f'({skill_quoted})', 'AND "hiring"', 'AND "remoto"', f'AND ({remote_term})', 'AND "email"']
                    if merged_blocked:
                        for blocked_key in merged_blocked:
                            if blocked_key and blocked_key.strip():
                                blocked_quoted = f'"{blocked_key.strip()}"' if ' ' in blocked_key.strip() else f'"{blocked_key.strip()}"'
                                email_query_parts.append(f'NOT {blocked_quoted}')
                    
                    email_query = ' '.join(email_query_parts)
                    
                    print(f"  🔍 Email query for: {skill}")
                    print(f"     Query: {email_query}")
                    # Email queries: usa o mesmo max_posts_per_skill (nova semântica: por tecnologia)
                    # Se max_applications não estiver definido, usa 50 como padrão para email queries
                    email_max_posts = max_posts_per_skill if max_applications else 50
                    posts = linkedin_searcher.search_posts_advanced(email_query, max_posts=email_max_posts, seen_post_ids=seen_post_ids)
                    
                    # FILTRO DE DUPLICATAS REFORÇADO: Verifica jobs.db para evitar reprocessar
                    new_posts = []
                    duplicates_skipped = 0
                    for post in posts:
                        post_url = post.get('url') or f"linkedin_post_{hash(post.get('text', '')[:100])}"
                        
                        # Check in-memory deduplication
                        if post_url in seen_post_urls:
                            duplicates_skipped += 1
                            continue
                        
                        # Check database deduplication (CRÍTICO: evita reprocessar posts de outras tecnologias)
                        if db and db.is_job_processed(post_url):
                            duplicates_skipped += 1
                            continue
                        
                        seen_post_urls.add(post_url)
                        post['search_skill'] = skill
                        new_posts.append(post)
                    
                    if duplicates_skipped > 0:
                        print(f"     ⏭ Skipped {duplicates_skipped} duplicate posts (already processed in jobs.db or this session)")
                    
                    all_posts.extend(new_posts)
                    if new_posts:
                        print(f"     ✅ Found {len(new_posts)} new posts with emails")
                    
                    # DISPARO IMEDIATO: Process and send emails for this skill
                    if new_posts:
                        emails_sent = process_and_send_emails(new_posts, skill)
                        if emails_sent > 0:
                            print(f"     📧 Sent {emails_sent} emails for {skill}")
                    
                    time.sleep(2)
                    
                except Exception as email_error:
                    print(f"  ⚠ Error in email query for {skill}: {email_error}")
                    continue
            
            # Convert remaining posts to jobs (for jobs without emails - external links, etc.)
            # Note: Jobs with emails were already processed and sent above
            posts_without_emails = [p for p in all_posts if not p.get('email')]
            
            if posts_without_emails:
                print(f"\n  📋 Converting {len(posts_without_emails)} posts without emails to jobs...")
                linkedin_jobs = linkedin_searcher.convert_posts_to_jobs(posts_without_emails)
                
                if linkedin_jobs:
                    all_jobs.extend(linkedin_jobs)
                    print(f"  ✓ Added {len(linkedin_jobs)} jobs from LinkedIn posts (external links, etc.)")
            
            # Summary
            print(f"\n  🎯 Multi-Stack Sniper Summary:")
            print(f"     - Total unique posts found: {len(all_posts)}")
            print(f"     - Total emails sent: {total_emails_sent}")
            print(f"     - Jobs with external links: {len(posts_without_emails)}")
            
            linkedin_searcher.close_browser()
            
        except Exception as e:
            print(f"  ⚠ LinkedIn Post Sniper failed: {e}")
            import traceback
            print(traceback.format_exc()[:300])
        
        # DISABLED: Aggregator (GitHub BR, HackerNews, RemoteOK)
        # LinkedIn Posts is the only source now - no fallback to other sources
        # DISABLED: Rotating sources
        # if len(all_jobs) < target_count:
        #     print(f"\nStill only {len(all_jobs)} jobs. Expanding to 100+ rotating sources...")
        #     more_jobs = aggregator.search_rotating_sources(target_count=target_count - len(all_jobs))
        #     all_jobs.extend(more_jobs)
        #     print(f"  Added {len(more_jobs)} jobs from rotating sources")
        
        # CRITICAL: If no real jobs found, STOP - do not generate mock data
        if len(all_jobs) == 0:
            print("\n⚠⚠⚠ CRITICAL: No real jobs found from any source!")
            print("   The system will NOT generate mock data.")
            print("   Please check:")
            print("   1. Network connectivity")
            print("   2. API keys (JOOBLE_API_KEY, SERPAPI_KEY)")
            print("   3. Firewall/proxy settings")
            print("   4. Source availability")
            return []
        
        # Additional validation: Use AI to verify remote eligibility
        if all_jobs:
            print("\nValidating remote eligibility with AI...")
            validated_jobs = []
            for job in all_jobs:
                # AI will validate in _calculate_match_score, but we also check here
                if self._is_remote_eligible(job):
                    validated_jobs.append(job)
                else:
                    print(f"  Rejected (not remote eligible): {job.title} at {job.company}")
            
            # Sort by match score and posted date (safe: convert to string to handle int/str mix)
            validated_jobs.sort(key=lambda x: (x.match_score, str(x.posted_date or "")), reverse=True)
            
            print(f"\nTotal REMOTE jobs found: {len(validated_jobs)}")
            return validated_jobs
        else:
            print(f"\nTotal REMOTE jobs found: 0")
            return []
    
    def _is_remote_eligible(self, job: JobListing) -> bool:
        """Rejeita vagas presencial/híbrido; só aceita remoto (qualquer lugar, Latam, Brasil)."""
        location_lower = (job.location or "").lower()
        description_lower = (job.description or "").lower()
        full_text = f"{location_lower} {description_lower}"

        # Rejeitar presencial, híbrido, escritório obrigatório
        reject_indicators = [
            'hibrido', 'híbrido', 'presencial', 'on-site', 'onsite', 'escritório',
            'office based', 'no remote', 'not remote', 'must be us citizen',
            'authorized to work in us', 'eu only', 'uk only', 'us only'
        ]
        has_rejection = any(indicator in full_text for indicator in reject_indicators)
        if has_rejection:
            return False

        # Deve ter indicador de remoto (qualquer lugar, Latam, Brasil, worldwide)
        remote_indicators = [
            'remote', 'remoto', 'anywhere', 'work from home', 'wfh',
            'latam', 'latin america', 'brazil', 'brasil', 'worldwide', 'global'
        ]
        has_remote = any(indicator in full_text for indicator in remote_indicators)
        return has_remote


if __name__ == "__main__":
    # Test the searcher
    from parser import ResumeParser, ResumeData
    
    # Mock resume data for testing
    test_data = ResumeData(
        stack_tecnico=["Python", "Playwright", "Pydantic"],
        experiencia_anos=5,
        senioridade_pretendida="senior",
        palavras_chave=["automation", "backend", "api"]
    )
    
    searcher = JobSearcher(test_data)
    jobs = searcher.search_all(max_per_source=5)
    
    for job in jobs:
        print(f"{job.title} at {job.company} - Score: {job.match_score:.2f}")
        print(f"  URL: {job.url}\n")

