"""
Headless ATS Application Module
Applies to jobs via API (Lever, Greenhouse) without opening browser
"""
import requests
import re
from typing import Dict, Optional, Tuple
from pathlib import Path


class HeadlessATSApplier:
    """Applies to jobs via ATS APIs (Lever, Greenhouse) without browser"""
    
    def __init__(self, user_data: Dict[str, str], resume_path: str):
        self.user_data = user_data
        self.resume_path = Path(resume_path)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def apply_to_lever(self, job_url: str) -> Tuple[bool, Optional[str]]:
        """
        Apply to Lever job via API
        
        Args:
            job_url: Lever job posting URL (e.g., https://jobs.lever.co/company/job-id)
            
        Returns:
            (success, error_message)
        """
        try:
            # Extract company and job ID from URL
            # Pattern: https://jobs.lever.co/{company}/{job_id}
            match = re.search(r'jobs\.lever\.co/([^/]+)/([^/?]+)', job_url)
            if not match:
                return (False, "Invalid Lever URL format")
            
            company = match.group(1)
            job_id = match.group(2)
            
            # Lever API endpoint
            api_url = f"https://jobs.lever.co/v0/postings/{company}/{job_id}"
            
            # Get job posting details
            response = self.session.get(api_url, timeout=10)
            if response.status_code != 200:
                return (False, f"Failed to fetch job details: HTTP {response.status_code}")
            
            job_data = response.json()
            
            # Extract application URL
            apply_url = job_data.get('applyUrl', '')
            if not apply_url:
                # Try alternative endpoint
                apply_url = f"https://jobs.lever.co/{company}/{job_id}/apply"
            
            # Prepare application data
            application_data = {
                'name': self.user_data.get('name', ''),
                'email': self.user_data.get('email', ''),
                'phone': self.user_data.get('phone', ''),
                'resume': self.resume_path,
                'urls': {
                    'linkedin': self.user_data.get('linkedin', '')
                }
            }
            
            # Submit application
            apply_response = self.session.post(apply_url, json=application_data, timeout=30)
            
            if apply_response.status_code in [200, 201]:
                print(f"  ✓ Successfully applied via Lever API")
                return (True, None)
            else:
                return (False, f"Lever API returned HTTP {apply_response.status_code}")
                
        except Exception as e:
            return (False, f"Lever application error: {str(e)}")
    
    def apply_to_greenhouse(self, job_url: str) -> Tuple[bool, Optional[str]]:
        """
        Apply to Greenhouse job via API
        
        Args:
            job_url: Greenhouse job posting URL (e.g., https://boards.greenhouse.io/company/jobs/123456)
            
        Returns:
            (success, error_message)
        """
        try:
            # Extract company and job ID from URL
            # Pattern: https://boards.greenhouse.io/{company}/jobs/{job_id}
            match = re.search(r'boards\.greenhouse\.io/([^/]+)/jobs/(\d+)', job_url)
            if not match:
                return (False, "Invalid Greenhouse URL format")
            
            company = match.group(1)
            job_id = match.group(2)
            
            # Greenhouse API endpoint
            api_url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}"
            
            # Get job posting details
            response = self.session.get(api_url, timeout=10)
            if response.status_code != 200:
                return (False, f"Failed to fetch job details: HTTP {response.status_code}")
            
            job_data = response.json()
            
            # Extract application token
            application_token = job_data.get('application_token', '')
            if not application_token:
                return (False, "No application token found")
            
            # Prepare application data
            application_data = {
                'first_name': self.user_data.get('name', '').split()[0] if self.user_data.get('name') else '',
                'last_name': ' '.join(self.user_data.get('name', '').split()[1:]) if len(self.user_data.get('name', '').split()) > 1 else '',
                'email': self.user_data.get('email', ''),
                'phone': self.user_data.get('phone', ''),
                'resume': self.resume_path,
                'linkedin_url': self.user_data.get('linkedin', '')
            }
            
            # Submit application
            apply_url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}/applications"
            apply_response = self.session.post(
                apply_url,
                json=application_data,
                headers={'Authorization': f'Bearer {application_token}'},
                timeout=30
            )
            
            if apply_response.status_code in [200, 201]:
                print(f"  ✓ Successfully applied via Greenhouse API")
                return (True, None)
            else:
                return (False, f"Greenhouse API returned HTTP {apply_response.status_code}")
                
        except Exception as e:
            return (False, f"Greenhouse application error: {str(e)}")
    
    def apply_headless(self, job_url: str) -> Tuple[bool, Optional[str]]:
        """
        Detect ATS type and apply accordingly
        
        Args:
            job_url: Job posting URL
            
        Returns:
            (success, error_message)
        """
        if 'lever.co' in job_url:
            return self.apply_to_lever(job_url)
        elif 'greenhouse.io' in job_url:
            return self.apply_to_greenhouse(job_url)
        else:
            return (False, "Not a supported ATS (Lever/Greenhouse)")


if __name__ == "__main__":
    # Test
    user_data = {
        'name': 'Test User',
        'email': 'test@example.com',
        'phone': '+55 11 99999-9999',
        'linkedin': 'https://linkedin.com/in/testuser'
    }
    
    applier = HeadlessATSApplier(user_data, 'curriculo.pdf')
    # Test URL (replace with real URL)
    # success, error = applier.apply_headless("https://jobs.lever.co/company/job-id")
    # print(f"Success: {success}, Error: {error}")

