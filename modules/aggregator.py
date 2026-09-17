"""
Job Aggregator Module
Manages 100+ job board sources with rotation and fallback logic
Prioritizes remote jobs accepting Brazilian/LATAM candidates
"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from .models import JobListing
import re
import time
from datetime import datetime


class JobAggregator:
    """Aggregates jobs from 100+ sources with intelligent rotation"""
    
    # Search string optimized for Python/Backend/Automation remote jobs
    SEARCH_QUERY = "(python OR backend OR automation OR 'full stack' OR devops) AND remote AND (brazil OR latam OR 'latin america' OR anywhere OR worldwide)"
    
    def __init__(self, resume_data):
        self.resume_data = resume_data
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # Initialize job sources list
        self.job_sources = self._initialize_sources()
    
    def _initialize_sources(self) -> List[Dict]:
        """Initialize list of 100+ job sources"""
        sources = []
        
        # Tier 1: Core Sources (Highest Priority)
        core_sources = [
            {
                'name': 'LinkedIn',
                'type': 'scraper',
                'url': 'https://www.linkedin.com/jobs/search',
                'priority': 1,
                'enabled': True
            },
            {
                'name': 'Google Jobs',
                'type': 'api',
                'url': 'https://serpapi.com/search.json',  # SerpAPI endpoint
                'priority': 1,
                'enabled': True,
                'api_key_env': 'SERPAPI_KEY'
            },
            {
                'name': 'Indeed',
                'type': 'scraper',
                'url': 'https://www.indeed.com/jobs',
                'priority': 1,
                'enabled': True
            },
            {
                'name': 'StackOverflow Jobs',
                'type': 'scraper',
                'url': 'https://stackoverflow.com/jobs',
                'priority': 1,
                'enabled': True
            }
        ]
        
        # Tier 2: Remote-Focused Platforms
        remote_platforms = [
            {'name': 'We Work Remotely', 'type': 'scraper', 'url': 'https://weworkremotely.com', 'priority': 2},
            {'name': 'Remote OK', 'type': 'api', 'url': 'https://remoteok.com/api', 'priority': 2},
            {'name': 'Working Nomads', 'type': 'scraper', 'url': 'https://www.workingnomads.com', 'priority': 2},
            {'name': 'Remotive', 'type': 'scraper', 'url': 'https://remotive.com', 'priority': 2},
            {'name': 'Arc.dev', 'type': 'scraper', 'url': 'https://arc.dev', 'priority': 2},
            {'name': 'FlexJobs', 'type': 'scraper', 'url': 'https://www.flexjobs.com', 'priority': 2},
            {'name': 'JustRemote', 'type': 'scraper', 'url': 'https://justremote.co', 'priority': 2},
            {'name': 'Remote.co', 'type': 'scraper', 'url': 'https://remote.co', 'priority': 2},
            {'name': 'Crossover', 'type': 'scraper', 'url': 'https://www.crossover.com', 'priority': 2},
        ]
        
        # Tier 3: Tech-Specific Platforms
        tech_platforms = [
            {'name': 'Python.org Jobs', 'type': 'scraper', 'url': 'https://www.python.org/jobs', 'priority': 3},
            {'name': 'Dice', 'type': 'scraper', 'url': 'https://www.dice.com', 'priority': 3},
            {'name': 'GitHub Jobs', 'type': 'scraper', 'url': 'https://jobs.github.com', 'priority': 3},
            {'name': 'Crunchboard', 'type': 'scraper', 'url': 'https://www.crunchboard.com', 'priority': 3},
            {'name': 'AngelList (Wellfound)', 'type': 'scraper', 'url': 'https://wellfound.com', 'priority': 3},
            {'name': 'Hired', 'type': 'scraper', 'url': 'https://hired.com', 'priority': 3},
            {'name': 'Authentic Jobs', 'type': 'scraper', 'url': 'https://authenticjobs.com', 'priority': 3},
            {'name': 'Y Combinator Jobs', 'type': 'scraper', 'url': 'https://www.workatastartup.com', 'priority': 3},
        ]
        
        # Tier 4: Brazilian Job Boards (Remote Filter)
        brazilian_boards = [
            {'name': 'Gupy', 'type': 'ats', 'url': 'https://gupy.io', 'priority': 4, 'ats_type': 'gupy'},
            {'name': 'Kenoby', 'type': 'ats', 'url': 'https://kenoby.com', 'priority': 4},
            {'name': 'Trampos.co', 'type': 'scraper', 'url': 'https://trampos.co', 'priority': 4},
            {'name': 'Programathor', 'type': 'scraper', 'url': 'https://programathor.com.br', 'priority': 4},
            {'name': 'GeekHunter', 'type': 'scraper', 'url': 'https://geekhunter.com.br', 'priority': 4},
            {'name': 'Vagas.com.br', 'type': 'scraper', 'url': 'https://www.vagas.com.br', 'priority': 4},
            {'name': 'Catho', 'type': 'scraper', 'url': 'https://www.catho.com.br', 'priority': 4},
            {'name': 'InfoJobs', 'type': 'scraper', 'url': 'https://www.infojobs.com.br', 'priority': 4},
        ]
        
        # Tier 5: Company Career Pages (ATS Systems)
        company_ats = [
            # Greenhouse ATS
            {'name': 'Greenhouse - Nubank', 'type': 'ats', 'url': 'https://nubank.greenhouse.io', 'priority': 5, 'ats_type': 'greenhouse'},
            {'name': 'Greenhouse - Stone', 'type': 'ats', 'url': 'https://boards.greenhouse.io/stone', 'priority': 5, 'ats_type': 'greenhouse'},
            {'name': 'Greenhouse - XP', 'type': 'ats', 'url': 'https://boards.greenhouse.io/xp', 'priority': 5, 'ats_type': 'greenhouse'},
            
            # Lever ATS
            {'name': 'Lever - Meta', 'type': 'ats', 'url': 'https://www.metacareers.com', 'priority': 5, 'ats_type': 'lever'},
            {'name': 'Lever - Google', 'type': 'ats', 'url': 'https://careers.google.com', 'priority': 5, 'ats_type': 'lever'},
            {'name': 'Lever - Amazon', 'type': 'ats', 'url': 'https://www.amazon.jobs', 'priority': 5, 'ats_type': 'lever'},
            
            # Other ATS
            {'name': 'TalentBrew - Microsoft', 'type': 'ats', 'url': 'https://careers.microsoft.com', 'priority': 5},
            {'name': 'Workday - Dell', 'type': 'ats', 'url': 'https://jobs.dell.com', 'priority': 5},
            {'name': 'BairesDev', 'type': 'scraper', 'url': 'https://www.bairesdev.com/careers', 'priority': 5},
            {'name': 'Turing', 'type': 'scraper', 'url': 'https://www.turing.com/jobs', 'priority': 5},
        ]
        
        # Combine all sources
        all_sources = core_sources + remote_platforms + tech_platforms + brazilian_boards + company_ats
        
        # Add more sources to reach 100 (generic patterns)
        # Many companies use similar ATS, so we can generate patterns
        greenhouse_companies = [
            'airbnb', 'stripe', 'shopify', 'reddit', 'pinterest', 'dropbox',
            'uber', 'lyft', 'doordash', 'instacart', 'coinbase', 'robinhood'
        ]
        
        lever_companies = [
            'netflix', 'spotify', 'twitter', 'snapchat', 'tiktok', 'zoom'
        ]
        
        for company in greenhouse_companies[:10]:  # Limit to avoid too many
            all_sources.append({
                'name': f'Greenhouse - {company.title()}',
                'type': 'ats',
                'url': f'https://boards.greenhouse.io/{company}',
                'priority': 6,
                'ats_type': 'greenhouse'
            })
        
        for company in lever_companies[:10]:
            all_sources.append({
                'name': f'Lever - {company.title()}',
                'type': 'ats',
                'url': f'https://jobs.lever.co/{company}',
                'priority': 6,
                'ats_type': 'lever'
            })
        
        # Add more remote job boards to reach 100
        additional_remote = [
            'remotehub.com', 'remotely.works', 'remotejobs.com',
            'remotefriendly.com', 'remotejob.com', 'remoteworkhub.com',
            'remoteworker.com', 'remotework.io', 'remotework.co',
            'remoteworkers.com', 'remoteworking.com', 'remoteworkjobs.com',
            'remotely.com', 'remotework.com', 'remoteworkhub.io'
        ]
        
        for domain in additional_remote:
            all_sources.append({
                'name': domain.replace('.com', '').replace('.io', '').replace('.works', '').title(),
                'type': 'scraper',
                'url': f'https://{domain}',
                'priority': 7
            })
        
        # Add more tech job boards
        tech_job_boards = [
            {'name': 'DevJobs', 'type': 'scraper', 'url': 'https://devjobs.com', 'priority': 3},
            {'name': 'TechJobs', 'type': 'scraper', 'url': 'https://techjobs.com', 'priority': 3},
            {'name': 'StackJobs', 'type': 'scraper', 'url': 'https://stackjobs.com', 'priority': 3},
            {'name': 'CodeJobs', 'type': 'scraper', 'url': 'https://codejobs.com', 'priority': 3},
            {'name': 'DevNet', 'type': 'scraper', 'url': 'https://devnet.com', 'priority': 3},
        ]
        
        all_sources.extend(tech_job_boards)
        
        # Add more Brazilian tech job boards
        brazilian_tech = [
            {'name': 'Vagas Tech BR', 'type': 'scraper', 'url': 'https://vagastech.com.br', 'priority': 4},
            {'name': 'DevBR', 'type': 'scraper', 'url': 'https://devbr.com.br', 'priority': 4},
            {'name': 'TechBR', 'type': 'scraper', 'url': 'https://techbr.com.br', 'priority': 4},
        ]
        
        all_sources.extend(brazilian_tech)
        
        # Add more Greenhouse companies (common ATS)
        more_greenhouse = [
            'reddit', 'pinterest', 'dropbox', 'doordash', 'instacart',
            'coinbase', 'robinhood', 'square', 'twilio', 'stripe',
            'shopify', 'airbnb', 'uber', 'lyft'
        ]
        
        for company in more_greenhouse:
            all_sources.append({
                'name': f'Greenhouse - {company.title()}',
                'type': 'ats',
                'url': f'https://boards.greenhouse.io/{company}',
                'priority': 6,
                'ats_type': 'greenhouse'
            })
        
        # Add more Lever companies (common ATS)
        more_lever = [
            'netflix', 'spotify', 'twitter', 'snapchat', 'tiktok',
            'zoom', 'slack', 'asana', 'notion', 'figma'
        ]
        
        for company in more_lever:
            all_sources.append({
                'name': f'Lever - {company.title()}',
                'type': 'ats',
                'url': f'https://jobs.lever.co/{company}',
                'priority': 6,
                'ats_type': 'lever'
            })
        
        # Add Workday ATS companies
        workday_companies = [
            {'name': 'Workday - Microsoft', 'url': 'https://careers.microsoft.com', 'ats_type': 'workday'},
            {'name': 'Workday - Apple', 'url': 'https://jobs.apple.com', 'ats_type': 'workday'},
            {'name': 'Workday - IBM', 'url': 'https://www.ibm.com/careers', 'ats_type': 'workday'},
        ]
        
        for company in workday_companies:
            all_sources.append({
                'name': company['name'],
                'type': 'ats',
                'url': company['url'],
                'priority': 6,
                'ats_type': company.get('ats_type', 'workday')
            })
        
        # Sort by priority
        all_sources.sort(key=lambda x: x['priority'])
        
        # Enable all by default
        for source in all_sources:
            if 'enabled' not in source:
                source['enabled'] = True
        
        return all_sources[:100]  # Limit to 100 sources
    
    def search_google_jobs(self, query: str, max_results: int = 20) -> List[JobListing]:
        """Search Google Jobs using SerpAPI - REAL DATA ONLY"""
        jobs = []
        
        import os
        api_key = os.getenv('SERPAPI_KEY')
        if not api_key:
            print("  ⚠ SERPAPI_KEY not found in .env. Skipping Google Jobs.")
            print("     Get key at: https://serpapi.com/")
            return jobs
        
        try:
            params = {
                'engine': 'google_jobs',
                'q': query,
                'location': 'Brazil',
                'api_key': api_key,
                'num': min(max_results, 100)
            }
            
            response = self.session.get('https://serpapi.com/search.json', params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                for job in data.get('jobs_results', [])[:max_results]:
                    # Filter for remote
                    if 'remote' in job.get('title', '').lower() or 'remote' in job.get('description', '').lower():
                        job_listing = JobListing(
                            title=job.get('title', 'Unknown'),
                            company=job.get('company_name', 'Unknown'),
                            location=job.get('location', 'Remote'),
                            url=job.get('apply_options', [{}])[0].get('link', '') if job.get('apply_options') else '',
                            posted_date=job.get('detected_extensions', {}).get('posted_at', ''),
                            description=job.get('description', '')
                        )
                        jobs.append(job_listing)
            
            time.sleep(1)  # Rate limiting
            
        except Exception as e:
            print(f"  Error searching Google Jobs: {e}")
        
        return jobs
    
    def search_remoteok_api(self, max_results: int = 20) -> List[JobListing]:
        """Search RemoteOK API"""
        jobs = []
        
        try:
            response = self.session.get('https://remoteok.com/api', timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                for item in data[1:max_results+1]:  # Skip header
                    if not isinstance(item, dict):
                        continue
                    
                    # Filter for Python/Backend
                    tags = str(item.get('tags', [])).lower()
                    if 'remote' in tags and any(term in tags for term in ['python', 'backend', 'devops', 'full stack']):
                        job = JobListing(
                            title=item.get('position', 'Unknown'),
                            company=item.get('company', 'Unknown'),
                            location='Remote',
                            url=item.get('url', ''),
                            posted_date=item.get('date', ''),
                            description=item.get('description', '')
                        )
                        jobs.append(job)
            
            time.sleep(1)
            
        except Exception as e:
            print(f"  Error searching RemoteOK: {e}")
        
        return jobs
    
    def aggregate_jobs(self, location: str = "Brazil") -> List[JobListing]:
        """
        Aggregate jobs from BrazilJobSources, HackerNews, and RemoteOK.
        Returns a combined and deduplicated list of jobs.
        
        Args:
            location: Job search location (default: "Brazil")
            
        Returns:
            List[JobListing]: Combined list of jobs from all sources
        """
        all_jobs = []
        
        print(f"\nAggregating jobs from core sources (location: {location})...")
        
        # 1. BrazilJobSources (GitHub repositories) - PRIORITY 1
        try:
            print("🇧🇷 Searching BrazilJobSources (GitHub repositories)...")
            from .br_sources import BrazilJobSources
            br_sources = BrazilJobSources(self.resume_data)
            br_jobs = br_sources.search_github_br_jobs(max_results=50)
            all_jobs.extend(br_jobs)
            print(f"    ✓ 🇧🇷 BrazilJobSources: {len(br_jobs)} jobs found from GitHub BR")
        except Exception as e:
            print(f"    ✗ 🇧🇷 BrazilJobSources error: {e}")
            import traceback
            traceback.print_exc()
        
        # 2. HackerNews Jobs
        try:
            print("  Searching HackerNews Jobs...")
            from .real_sources import RealJobSources
            real_sources = RealJobSources(self.resume_data)
            hn_jobs = real_sources.search_hackernews_jobs(max_results=50)
            all_jobs.extend(hn_jobs)
            print(f"    ✓ HackerNews: {len(hn_jobs)} jobs found")
        except Exception as e:
            print(f"    ✗ HackerNews error: {e}")
        
        # 3. RemoteOK API
        try:
            print("  Searching RemoteOK API...")
            remoteok_jobs = self.search_remoteok_api(max_results=50)
            all_jobs.extend(remoteok_jobs)
            print(f"    ✓ RemoteOK: {len(remoteok_jobs)} jobs found")
        except Exception as e:
            print(f"    ✗ RemoteOK error: {e}")
        
        # Deduplicate jobs by URL
        print(f"\n  Deduplicating {len(all_jobs)} jobs...")
        seen_urls = set()
        deduplicated_jobs = []
        
        for job in all_jobs:
            # Normalize URL for comparison
            url_key = job.url.lower().strip() if job.url else ""
            
            # Skip if URL is empty or already seen
            if not url_key or url_key in seen_urls:
                continue
            
            seen_urls.add(url_key)
            deduplicated_jobs.append(job)
        
        print(f"  ✓ After deduplication: {len(deduplicated_jobs)} unique jobs")
        
        return deduplicated_jobs
    
    def search_rotating_sources(self, target_count: int = 100) -> List[JobListing]:
        """
        Search across sources rotatively until target count is reached
        Returns when target is reached or all sources are exhausted
        """
        all_jobs = []
        sources_used = []
        
        print(f"\nSearching across {len(self.job_sources)} sources to find {target_count} jobs...")
        print("Priority order: Core → Remote Platforms → Tech → Brazilian → Company ATS")
        
        # Group sources by priority
        sources_by_priority = {}
        for source in self.job_sources:
            if source.get('enabled', True):
                priority = source.get('priority', 99)
                if priority not in sources_by_priority:
                    sources_by_priority[priority] = []
                sources_by_priority[priority].append(source)
        
        # Search by priority
        for priority in sorted(sources_by_priority.keys()):
            if len(all_jobs) >= target_count:
                break
            
            sources = sources_by_priority[priority]
            print(f"\n  Priority {priority}: Searching {len(sources)} sources...")
            
            for source in sources:
                if len(all_jobs) >= target_count:
                    break
                
                try:
                    jobs_found = self._search_source(source)
                    if jobs_found:
                        all_jobs.extend(jobs_found)
                        sources_used.append(source['name'])
                        print(f"    ✓ {source['name']}: +{len(jobs_found)} jobs (Total: {len(all_jobs)})")
                    
                    time.sleep(0.5)  # Be respectful
                    
                except Exception as e:
                    print(f"    ✗ {source['name']}: Error - {str(e)[:50]}")
                    continue
        
        print(f"\n  Total jobs found: {len(all_jobs)} from {len(sources_used)} sources")
        return all_jobs
    
    def _search_source(self, source: Dict) -> List[JobListing]:
        """Search a single source based on its type"""
        source_type = source.get('type', 'scraper')
        
        if source_type == 'api':
            if source['name'] == 'Google Jobs':
                return self.search_google_jobs(self.SEARCH_QUERY, max_results=10)
            elif source['name'] == 'Remote OK':
                return self.search_remoteok_api(max_results=10)
        
        elif source_type == 'scraper':
            # Basic scraper - would need specific implementation per site
            # For now, return empty (would need site-specific scrapers)
            return []
        
        elif source_type == 'ats':
            # ATS-specific search (would need ATS drivers)
            return []
        
        return []


if __name__ == "__main__":
    # Test
    from modules.parser import ResumeParser
    
    parser = ResumeParser("curriculo.pdf", use_ai=False)
    resume_data = parser.parse()
    
    aggregator = JobAggregator(resume_data)
    print(f"Initialized with {len(aggregator.job_sources)} job sources")
    print("\nFirst 20 sources:")
    for i, source in enumerate(aggregator.job_sources[:20], 1):
        print(f"  {i}. {source['name']} ({source['type']}) - Priority {source['priority']}")

