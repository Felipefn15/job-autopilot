"""
Brazil Job Sources Module
Searches for jobs in Brazilian GitHub repositories (backend-br, frontend-br, etc)
Most jobs use email applications
"""
import requests
import re
import time
from typing import List
from .models import JobListing
from .emailer import EmailApplier


class BrazilJobSources:
    """Searches for jobs in Brazilian GitHub repositories"""
    
    def __init__(self, resume_data):
        self.resume_data = resume_data
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/vnd.github.v3+json'
        })
        self.emailer = EmailApplier()
    
    def search_github_br_jobs(self, max_results: int = 50) -> List[JobListing]:
        """
        Search jobs in Brazilian GitHub repositories
        Extracts emails from issue bodies
        
        Repositories:
        - backend-br/vagas
        - frontend-br/vagas
        - react-brasil/vagas
        - python-brasil/vagas
        - vuejs-br/vagas
        """
        jobs = []
        
        # Brazilian GitHub repositories with job postings
        repos = [
            'backend-br/vagas',
            'frontend-br/vagas',
            'react-brasil/vagas',
            'python-brasil/vagas',
            'vuejs-br/vagas',
            'qa-brasil/vagas',
            'php-brasil/vagas',
            'dev-brasil/vagas'
        ]
        
        print(f"\n🇧🇷 Searching Brazilian GitHub repositories...")
        
        for repo in repos:
            try:
                print(f"  🇧🇷 Buscando no GitHub Brasil: {repo}...")
                # GitHub API: Get open issues
                url = f"https://api.github.com/repos/{repo}/issues"
                params = {
                    'state': 'open',
                    'per_page': 10,  # 10 issues por repositório
                    'sort': 'updated',
                    'direction': 'desc'
                }
                
                response = self.session.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    issues = response.json()
                    
                    for issue in issues[:max_results // len(repos)]:
                        # Skip pull requests (they have pull_request field)
                        if 'pull_request' in issue:
                            continue
                        
                        title = issue.get('title', '')
                        body = issue.get('body', '')
                        issue_url = issue.get('html_url', '')
                        created_at = issue.get('created_at', '')
                        
                        # SNIPER: Detect if this is a "mural" with multiple jobs (contains "Main Stack" and Strider links)
                        strider_links = re.findall(r'(https?://app\.onstrider\.com/r/[^\s\)]+)', body, re.IGNORECASE)
                        has_main_stack = 'main stack' in body.lower() or 'stack principal' in body.lower()
                        
                        if strider_links and has_main_stack:
                            # This is a MURAL - extract individual jobs
                            print(f"  🎯 Mural detected with {len(strider_links)} Strider links. Extracting individual jobs...")
                            
                            # Split body into sections (each job usually has a title and a link)
                            # Pattern: Job title (often with | separator) followed by Strider link
                            job_sections = re.split(r'(?=\n|^)(?:#{1,3}\s*)?([^\n]+(?:\|[^\n]+)?)', body)
                            
                            for i, strider_link in enumerate(strider_links):
                                # Find the job title associated with this link
                                # Look backwards from the link to find the nearest title
                                link_index = body.find(strider_link)
                                if link_index == -1:
                                    continue
                                
                                # Extract text before the link (likely contains job title)
                                text_before_link = body[max(0, link_index-200):link_index]
                                
                                # Try to find job title pattern: "TITLE | STACK" or "TITLE - STACK"
                                title_match = re.search(r'([A-Z][A-Z\s\-|]+(?:ENGINEER|DEVELOPER|ENGENHEIR[OA]|DESENVOLVEDOR)[A-Z\s\-|]*(?:\|[A-Z\s,\.]+)?)', text_before_link, re.IGNORECASE)
                                if title_match:
                                    job_title = title_match.group(1).strip()
                                else:
                                    # Fallback: use first line before link
                                    lines_before = text_before_link.split('\n')
                                    job_title = lines_before[-1].strip() if lines_before else f"Vaga {i+1}"
                                
                                # Extract stack from title or nearby text
                                stack_match = re.search(r'(?:Main Stack|Stack Principal|Stack|Tech Stack)[\s:]*([^\n]+)', text_before_link, re.IGNORECASE)
                                stack_text = stack_match.group(1).strip() if stack_match else ""
                                
                                # Calculate match score based on stack
                                stack_lower = stack_text.lower()
                                skills = self.resume_data.stack_tecnico if hasattr(self.resume_data, 'stack_tecnico') else []
                                match_score = 0.5  # Base score for Strider jobs
                                
                                # Boost score if stack matches
                                for skill in skills:
                                    if skill.lower() in stack_lower:
                                        match_score += 0.2
                                
                                match_score = min(match_score, 1.0)  # Cap at 1.0
                                
                                # Extract company (usually in title or first part)
                                company = "Unknown"
                                if '|' in job_title:
                                    parts = job_title.split('|')
                                    if len(parts) > 1:
                                        company = parts[-1].strip()
                                        job_title = parts[0].strip()
                                
                                # Create individual job listing
                                job = JobListing(
                                    title=job_title,
                                    company=company,
                                    url=strider_link,  # Direct Strider link, not GitHub issue
                                    location="Remote",
                                    description=f"Stack: {stack_text}\n\n{text_before_link[:500]}",
                                    posted_date=created_at,
                                    source='github_br_strider',
                                    match_score=match_score
                                )
                                
                                jobs.append(job)
                                print(f"    ✓ Extracted: {job_title[:50]} (Score: {match_score:.2f})")
                            
                            # Skip normal processing for mural issues
                            continue
                        
                        # Filter for relevant skills
                        title_lower = title.lower()
                        body_lower = body.lower()
                        full_text = (title_lower + " " + body_lower)
                        
                        # Check if matches resume skills
                        skills = self.resume_data.stack_tecnico if hasattr(self.resume_data, 'stack_tecnico') else []
                        skill_keywords = ['python', 'backend', 'frontend', 'react', 'vue', 'javascript', 'node', 'devops', 'full stack']
                        
                        # Check if job is relevant
                        is_relevant = any(keyword in full_text for keyword in skill_keywords)
                        
                        # Filter: Only remote jobs or jobs that accept remote
                        remote_indicators = ['remoto', 'remote', 'home office', 'trabalho remoto', 'qualquer lugar', 'brasil']
                        has_remote = any(indicator in full_text for indicator in remote_indicators)
                        
                        # Reject on-site only jobs
                        reject_indicators = ['presencial', 'escritório', 'são paulo', 'rio de janeiro', 'curitiba']
                        is_rejected = any(indicator in full_text and 'remoto' not in full_text for indicator in reject_indicators)
                        
                        if is_relevant and has_remote and not is_rejected:
                            # Extract email from issue body
                            email_found = self.emailer.extract_email_from_text(body)
                            
                            # Extract external apply link (inscreva-se, apply here, etc.)
                            apply_link = None
                            # Procurar por links comuns de aplicação
                            apply_patterns = [
                                r'(?:inscreva-se|inscrever|apply|aplicar|candidatar|vagas|jobs|careers)[\s:]*([^\s\n]+(?:bit\.ly|gupy\.io|greenhouse|lever|apply|inscreva|candidatar|vagas|jobs|careers)[^\s\n]*)',
                                r'(?:link|url|site)[\s:]*([^\s\n]+(?:bit\.ly|gupy\.io|greenhouse|lever)[^\s\n]*)',
                                r'(https?://(?:bit\.ly|gupy\.io|greenhouse|lever|.*apply.*|.*inscreva.*|.*vagas.*)[^\s\n\)]+)',
                            ]
                            
                            for pattern in apply_patterns:
                                matches = re.finditer(pattern, body, re.IGNORECASE)
                                for match in matches:
                                    potential_link = match.group(1) if match.groups() else match.group(0)
                                    # Verificar se é um link válido
                                    if 'http' in potential_link or 'bit.ly' in potential_link or 'gupy.io' in potential_link:
                                        apply_link = potential_link.strip()
                                        break
                                if apply_link:
                                    break
                            
                            # Se não encontrou por regex, procurar por links markdown do GitHub
                            if not apply_link:
                                markdown_links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', body)
                                for link_text, link_url in markdown_links:
                                    link_text_lower = link_text.lower()
                                    if any(keyword in link_text_lower for keyword in ['inscreva', 'apply', 'aplicar', 'candidatar', 'vagas', 'jobs']):
                                        if link_url.startswith('http'):
                                            apply_link = link_url
                                            break
                                        elif not link_url.startswith('#'):  # Não é âncora
                                            apply_link = link_url
                                            break
                            
                            # Extract company name (usually in title or first line of body)
                            company = "Unknown"
                            company_match = re.search(r'(?:empresa|company|contratando|hiring):\s*([^\n]+)', body, re.IGNORECASE)
                            if company_match:
                                company = company_match.group(1).strip()
                            else:
                                # Try to extract from title
                                title_parts = title.split('|')
                                if len(title_parts) > 1:
                                    company = title_parts[-1].strip()
                            
                            # Usar link de aplicação externo se encontrado, senão usar URL do GitHub
                            final_url = apply_link if apply_link else issue_url
                            
                            job = JobListing(
                                title=title,
                                company=company,
                                location='Remote (Brazil)',
                                url=final_url,  # URL principal (link externo se encontrado)
                                posted_date=created_at,
                                description=body[:500] if body else '',
                                email=email_found,  # Store email if found
                                source='github_br'  # Mark as GitHub BR source
                            )
                            
                            if apply_link:
                                print(f"    ✓ {repo}: {title[:50]}... | Link externo: {apply_link[:50]}...")
                            elif email_found:
                                print(f"    ✓ {repo}: {title[:50]}... | Email: {email_found}")
                            else:
                                print(f"    ✓ {repo}: {title[:50]}... | (GitHub issue)")
                            
                            jobs.append(job)
                
                time.sleep(1)  # Rate limiting (GitHub allows 60 requests/hour without auth)
                
            except Exception as e:
                print(f"    ✗ Error searching {repo}: {e}")
                continue
        
        print(f"  ✓ Found {len(jobs)} jobs from Brazilian GitHub repositories")
        return jobs


if __name__ == "__main__":
    from modules.parser import ResumeParser, ResumeData
    
    # Mock resume data
    resume_data = ResumeData(
        stack_tecnico=['Python', 'Backend', 'JavaScript'],
        experiencia_anos=5,
        senioridade_pretendida='senior',
        palavras_chave=['automation', 'backend', 'api']
    )
    
    sources = BrazilJobSources(resume_data)
    jobs = sources.search_github_br_jobs(max_results=20)
    
    print(f"\nFound {len(jobs)} jobs:")
    for job in jobs[:5]:
        email_text = f" | Email: {job.email}" if job.email else ""
        print(f"  - {job.title} at {job.company}{email_text}")

