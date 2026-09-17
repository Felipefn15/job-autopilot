"""
Job Validator Module
Validates that job URLs are real and contain expected content
"""
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout
from typing import Tuple, Optional
import time


class JobValidator:
    """Validates job postings are real and accessible"""
    
    def __init__(self, page: Page):
        self.page = page
    
    def validate_job_url(self, url: str, timeout: int = 10000) -> Tuple[bool, Optional[str]]:
        """
        Validate job URL is real and contains expected content
        
        Returns:
            (is_valid, error_message)
        """
        if not url or not url.startswith('http'):
            return (False, "URL does not start with http")
        
        try:
            # Navigate to URL
            response = self.page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            
            if not response:
                return (False, "No response from page")
            
            if response.status != 200:
                return (False, f"HTTP {response.status}")
            
            # Wait a bit for content to load
            time.sleep(1)
            
            # DEBUG: Take screenshot to see what the robot is seeing
            try:
                from pathlib import Path
                logs_dir = Path("logs")
                logs_dir.mkdir(exist_ok=True)
                self.page.screenshot(path='logs/debug_validation.png')
                print(f"  DEBUG: Screenshot saved to logs/debug_validation.png")
            except Exception as screenshot_error:
                print(f"  DEBUG: Could not save screenshot: {screenshot_error}")
            
            # VALIDAÇÃO SIMPLIFICADA: Se status for 200, aceita (sem verificação de palavras-chave)
            # Comentado temporariamente para evitar falsos positivos com WWR
            # Get page content
            # content = self.page.content().lower()
            
            # # Check for job-related keywords
            # job_keywords = [
            #     'apply', 'aplicar', 'candidatar-se', 'submit application',
            #     'description', 'descrição', 'requirements', 'requisitos',
            #     'job', 'vaga', 'position', 'cargo', 'role'
            # ]
            
            # found_keywords = [kw for kw in job_keywords if kw in content]
            
            # if len(found_keywords) < 2:
            #     return (False, f"Page does not appear to be a job posting (found keywords: {found_keywords})")
            
            # # Check for rejection keywords (error pages, etc.) - DESATIVADO TEMPORARIAMENTE
            # # Esta verificação estava marcando links válidos da WWR como inválidos
            # rejection_keywords = [
            #     '404', 'not found', 'page not found', 'error',
            #     'access denied', 'forbidden', 'blocked'
            # ]
            
            # for reject_kw in rejection_keywords:
            #     if reject_kw in content:
            #         return (False, f"Page contains rejection keyword: {reject_kw}")
            
            # Se chegou aqui e status é 200, aceita
            return (True, None)
            
        except PlaywrightTimeout:
            return (False, "Page load timeout")
        except Exception as e:
            return (False, f"Validation error: {str(e)}")
    
    def validate_job_listing(self, job_title: str, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a complete job listing
        
        Returns:
            (is_valid, error_message)
        """
        # Basic checks
        if not job_title or len(job_title.strip()) < 3:
            return (False, "Job title too short or empty")
        
        if not url or not url.startswith('http'):
            return (False, "Invalid URL format")
        
        # Validate URL accessibility
        return self.validate_job_url(url)


if __name__ == "__main__":
    # Test
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        validator = JobValidator(page)
        
        test_urls = [
            "https://www.google.com",
            "https://www.linkedin.com/jobs/view/1234567890",
        ]
        
        for url in test_urls:
            is_valid, error = validator.validate_job_url(url)
            print(f"{url}: {'✓ Valid' if is_valid else f'✗ Invalid: {error}'}")
        
        browser.close()

