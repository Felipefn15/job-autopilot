"""
Real Job Sources - No Mock Data
Only uses real APIs and scrapable sources
"""
import requests
import feedparser
from typing import List, Optional
from .models import JobListing
from datetime import datetime
import time
import os
import json


class RealJobSources:
    """Real job sources - NO MOCK DATA"""
    
    def __init__(self, resume_data):
        self.resume_data = resume_data
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def search_remoteok_api(self, max_results: int = 50) -> List[JobListing]:
        """Search RemoteOK API - Real data only"""
        jobs = []
        
        try:
            url = "https://remoteok.com/api"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Skip first item (header)
                for item in data[1:max_results+1]:
                    if not isinstance(item, dict):
                        continue
                    
                    # Filter for Python/Backend/DevOps
                    tags = str(item.get('tags', [])).lower()
                    description_raw = item.get('description', '')
                    description = str(description_raw).lower()
                    
                    # Verificar se tem as skills técnicas
                    has_tech_skills = any(term in tags for term in ['python', 'backend', 'devops', 'full stack', 'javascript', 'react'])
                    
                    # FILTRO WORLDWIDE: Só aceitar vagas que mencionam "worldwide", "anywhere", "latam", "latin america"
                    # Rejeitar vagas que mencionam "US only", "US citizen", "authorized to work in US"
                    location_text = (tags + " " + description).lower()
                    worldwide_indicators = ['worldwide', 'anywhere', 'latam', 'latin america', 'brazil', 'global', 'international']
                    rejection_indicators = ['us only', 'us citizen', 'authorized to work in us', 'must be us', 'united states only', 'no remote outside us']
                    
                    has_worldwide = any(indicator in location_text for indicator in worldwide_indicators)
                    has_rejection = any(indicator in location_text for indicator in rejection_indicators)
                    
                    if has_tech_skills and (has_worldwide or not has_rejection):
                        job_url = item.get('url', '')
                        if not job_url.startswith('http'):
                            job_url = f"https://remoteok.com{job_url}" if job_url.startswith('/') else f"https://remoteok.com/remote-jobs/{item.get('id', '')}"
                        
                        job = JobListing(
                            title=item.get('position', 'Unknown'),
                            company=item.get('company', 'Unknown'),
                            location='Remote',
                            url=job_url,
                            posted_date=item.get('date', ''),
                            description=description_raw  # Manter descrição original para extração de email
                        )
                        
                        # EXTRAIR EMAIL DA DESCRIÇÃO DO REMOTEOK
                        from modules.emailer import EmailApplier
                        emailer = EmailApplier()
                        email_found = emailer.extract_email_from_text(description_raw)
                        
                        if email_found:
                            job.email = email_found
                            print(f"   ℹ Email found in RemoteOK job: {email_found}")
                        
                        jobs.append(job)
            
            time.sleep(1)  # Rate limiting
            
        except Exception as e:
            print(f"  Error searching RemoteOK API: {e}")
        
        return jobs
    
    def search_weworkremotely_rss(self, max_results: int = 50) -> List[JobListing]:
        """Search We Work Remotely via RSS - Real data only"""
        jobs = []
        
        try:
            # WWR RSS feed
            rss_url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:max_results]:
                # Filter for Python/Backend
                title = entry.get('title', '')
                title_lower = title.lower()
                description_lower = entry.get('summary', '').lower()
                full_text = (title_lower + " " + description_lower)
                
                # FILTRO ANTI-USA: Ignorar vagas explicitamente dos EUA
                # Se o título ou região contiver "USA", "United States", "North America" ou "US Only", pular
                usa_indicators = ['usa', 'united states', 'north america', 'us only']
                has_usa_indicator = any(indicator in title_lower or indicator in full_text.lower() for indicator in usa_indicators)
                
                # Focar em vagas "Anywhere", "Latin America" ou "Global"
                global_indicators = ['anywhere', 'latin america', 'global', 'worldwide', 'latam', 'south america']
                has_global_indicator = any(indicator in full_text.lower() for indicator in global_indicators)
                
                # Se tem indicador USA e não é global, pular
                if has_usa_indicator and not has_global_indicator:
                    continue  # Pular vagas dos EUA
                
                # Verificar se tem as skills técnicas
                has_tech_skills = any(term in full_text for term in ['python', 'backend', 'devops', 'full stack'])
                
                # FILTRO WORLDWIDE: Priorizar vagas que mencionam "worldwide", "anywhere", "latam", "latin america"
                # Rejeitar vagas que mencionam "US only", "US citizen", "authorized to work in US"
                worldwide_indicators = ['worldwide', 'anywhere', 'latam', 'latin america', 'brazil', 'global', 'international', 'south america']
                rejection_indicators = ['us only', 'us citizen', 'authorized to work in us', 'must be us', 'united states only', 'no remote outside us', 'north america only']
                
                has_worldwide = any(indicator in full_text for indicator in worldwide_indicators)
                has_rejection = any(indicator in full_text for indicator in rejection_indicators)
                
                # Rejeitar se tem indicadores de rejeição (exceto se também for worldwide)
                if has_rejection and not has_worldwide:
                    continue  # Pular vagas com restrições dos EUA
                
                # Aceitar apenas se tem skills técnicas e (é worldwide OU não tem rejeição)
                if has_tech_skills and (has_worldwide or not has_rejection):
                    # Usar entry.link (não entry.id) - garantir que seja entry.link diretamente
                    job_url = entry.link if hasattr(entry, 'link') else entry.get('link', '')
                    print(f"DEBUG URL: {job_url}")
                    
                    if not job_url or not job_url.startswith('http'):
                        print(f"  ⚠ URL inválida para vaga: {entry.get('title', 'Unknown')}")
                        continue
                    
                    job = JobListing(
                        title=entry.get('title', 'Unknown'),
                        company=entry.get('author', 'Unknown'),
                        location='Remote',
                        url=job_url,
                        posted_date=entry.get('published', ''),
                        description=entry.get('summary', '')
                    )
                    jobs.append(job)
            
            time.sleep(1)
            
        except Exception as e:
            print(f"  Error searching We Work Remotely RSS: {e}")
        
        return jobs
    
    def search_arbeitnow_api(self, max_results: int = 50) -> List[JobListing]:
        """Search Arbeitnow API - Real remote jobs"""
        jobs = []
        
        try:
            # Arbeitnow API endpoint
            url = "https://www.arbeitnow.com/api/job-board-api"
            params = {
                'limit': max_results,
                'offset': 0,
                'remote': 'true'
            }
            
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                for item in data.get('data', [])[:max_results]:
                    # Filter for tech jobs
                    title_lower = item.get('title', '').lower()
                    if any(term in title_lower for term in ['python', 'backend', 'developer', 'engineer', 'devops']):
                        job = JobListing(
                            title=item.get('title', 'Unknown'),
                            company=item.get('company_name', 'Unknown'),
                            location='Remote',
                            url=item.get('url', ''),
                            posted_date=item.get('created_at', ''),
                            description=item.get('description', '')
                        )
                        jobs.append(job)
            
            time.sleep(1)
            
        except Exception as e:
            print(f"  Error searching Arbeitnow API: {e}")
        
        return jobs
    
    def search_hackernews_jobs(self, max_results: int = 50) -> List[JobListing]:
        """Search Hacker News Jobs via Algolia API (FREE, no key required) - Extract emails"""
        jobs = []
        import re
        
        try:
            # Hacker News Jobs uses Algolia public API
            url = "https://hn.algolia.com/api/v1/search_by_date"
            params = {
                'query': '',  # Query vazia para pegar todos os posts "Who is Hiring"
                'tags': 'story,author_whoishiring',
                # Removido filtro de data para pegar thread mensal "Who is Hiring" completo
                'hitsPerPage': max_results,
                'numericFilters': 'created_at_i>{}'.format(int(time.time()) - 2592000)  # Últimos 30 dias
            }
            
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                for item in data.get('hits', [])[:max_results]:
                    title = item.get('title', '')
                    comment_text = item.get('comment_text', '') or item.get('story_text', '') or ''
                    url_link = item.get('url', '') or f"https://news.ycombinator.com/item?id={item.get('objectID', '')}"
                    
                    # Filter for remote Python jobs
                    title_lower = title.lower()
                    text_lower = (title + " " + comment_text).lower()
                    
                    # FILTRO ANTI-USA: Ignorar vagas dos EUA
                    usa_indicators = ['usa', 'united states', 'north america', 'us only', 'united states only']
                    has_usa_indicator = any(indicator in text_lower for indicator in usa_indicators)
                    global_indicators = ['anywhere', 'latin america', 'global', 'worldwide', 'latam', 'south america']
                    has_global_indicator = any(indicator in text_lower for indicator in global_indicators)
                    
                    # Se tem indicador USA e não é global, pular
                    if has_usa_indicator and not has_global_indicator:
                        continue  # Pular vagas dos EUA
                    
                    if 'python' in text_lower and ('remote' in text_lower or 'anywhere' in text_lower):
                        # Extract email from text
                        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                        email_matches = re.findall(email_pattern, comment_text)
                        
                        # Prefer hiring/recruiting emails
                        job_email = None
                        if email_matches:
                            for email in email_matches:
                                email_lower = email.lower()
                                if any(domain in email_lower for domain in ['hiring', 'recruiting', 'jobs', 'careers', 'hr']):
                                    job_email = email
                                    break
                            if not job_email:
                                job_email = email_matches[0]  # Use first email if no hiring domain
                        
                        job = JobListing(
                            title=title,
                            company='Hacker News',
                            location='Remote',
                            url=url_link,
                            posted_date=item.get('created_at', ''),
                            description=comment_text[:500] if comment_text else ''
                        )
                        
                        # Store email in job metadata if available
                        if job_email:
                            job.email = job_email
                            print(f"  ✓ Found email in Hacker News job: {job_email}")
                        
                        jobs.append(job)
            
            time.sleep(1)
            
        except Exception as e:
            print(f"  Error searching Hacker News Jobs: {e}")
        
        return jobs
    
    def search_berlin_startup_jobs_rss(self, max_results: int = 50) -> List[JobListing]:
        """Search Berlin Startup Jobs RSS (FREE, no key required)"""
        jobs = []
        
        try:
            # Berlin Startup Jobs RSS feed
            rss_url = "https://berlinstartupjobs.com/feed/"
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:max_results]:
                # Filter for remote Python jobs
                title_lower = entry.get('title', '').lower()
                description_lower = entry.get('summary', '').lower()
                
                if any(term in title_lower or term in description_lower for term in ['python', 'backend', 'developer', 'remote']):
                    job = JobListing(
                        title=entry.get('title', 'Unknown'),
                        company=entry.get('author', 'Unknown'),
                        location='Remote',
                        url=entry.get('link', ''),
                        posted_date=entry.get('published', ''),
                        description=entry.get('summary', '')
                    )
                    jobs.append(job)
            
            time.sleep(1)
            
        except Exception as e:
            print(f"  Error searching Berlin Startup Jobs RSS: {e}")
        
        return jobs
    
    def search_all_real_sources(self, target_count: int = 100) -> List[JobListing]:
        """Search all FREE real sources until target_count is reached (NO API KEYS REQUIRED)"""
        all_jobs = []
        
        # ESTRATÉGIA "EMAIL FIRST": Priorizar fontes com emails primeiro
        # Priority sources (com emails ou APIs rápidas)
        priority_sources = [
            ('Hacker News Jobs', self.search_hackernews_jobs, 50),  # PRIORIDADE 1 - Vagas com email
            ('RemoteOK API', self.search_remoteok_api, 50),  # PRIORIDADE 2 - API rápida
            ('We Work Remotely RSS', self.search_weworkremotely_rss, 50),  # PRIORIDADE 3 - RSS
        ]
        
        # Secondary sources
        secondary_sources = [
            ('Arbeitnow API', self.search_arbeitnow_api, 50),
            ('Berlin Startup Jobs RSS', self.search_berlin_startup_jobs_rss, 50),
        ]
        
        print(f"\nSearching real job sources to reach {target_count} jobs...")
        print("  Priority: Hacker News (emails) → RemoteOK API → WWR RSS")
        
        # Search priority sources first
        for source_name, search_func, max_per_source in priority_sources:
            if len(all_jobs) >= target_count:
                break
            
            try:
                print(f"  Searching {source_name}...")
                jobs = search_func(max_per_source)
                
                if jobs:
                    all_jobs.extend(jobs)
                    print(f"    ✓ {source_name}: {len(jobs)} jobs found (Total: {len(all_jobs)})")
                else:
                    print(f"    ✗ {source_name}: No jobs found")
                    
            except Exception as e:
                print(f"    ✗ {source_name}: Error - {str(e)}")
                import traceback
                print(f"      Details: {traceback.format_exc()[:200]}")
                continue
        
        # If we have enough from priority sources, return early
        if len(all_jobs) >= target_count:
            print(f"\n  ✓ Found {len(all_jobs)} jobs from priority sources (enough for batch)")
            return all_jobs[:target_count]
        
        # Search secondary sources if needed
        print(f"\n  Only {len(all_jobs)} jobs from priority sources. Trying secondary sources...")
        for source_name, search_func, max_per_source in secondary_sources:
            if len(all_jobs) >= target_count:
                break
            
            try:
                print(f"  Searching {source_name}...")
                jobs = search_func(max_per_source)
                
                if jobs:
                    all_jobs.extend(jobs)
                    print(f"    ✓ {source_name}: {len(jobs)} jobs found (Total: {len(all_jobs)})")
                else:
                    print(f"    ✗ {source_name}: No jobs found")
                    
            except Exception as e:
                print(f"    ✗ {source_name}: Error - {str(e)}")
                continue
        
        print(f"\n  Total real jobs found: {len(all_jobs)}")
        return all_jobs[:target_count]


if __name__ == "__main__":
    from modules.parser import ResumeParser
    
    parser = ResumeParser("curriculo.pdf", use_ai=False)
    resume_data = parser.parse()
    
    sources = RealJobSources(resume_data)
    jobs = sources.search_all_real_sources(20)
    
    print(f"\nFound {len(jobs)} real jobs:")
    for job in jobs[:5]:
        print(f"  - {job.title} at {job.company} ({job.url})")

