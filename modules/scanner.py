"""
Link Scanner Module
Validates that job URLs are real and accessible before saving to logs
"""
import requests
from typing import Optional, Tuple
from playwright.sync_api import Page
import time


class LinkScanner:
    """Validates job URLs are real and accessible"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        self.timeout = 5
    
    def validate_url(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate URL is real and accessible
        Returns: (is_valid, error_message)
        """
        if not url or not url.startswith('http'):
            return (False, "URL does not start with http")
        
        try:
            # Use HEAD request first (faster)
            response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            
            if response.status_code == 200:
                return (True, None)
            elif response.status_code in [301, 302, 303, 307, 308]:
                # Follow redirect and check final URL
                final_url = response.headers.get('Location', url)
                if final_url.startswith('http'):
                    return (True, None)
                else:
                    return (False, f"Redirect to invalid URL: {final_url}")
            else:
                return (False, f"HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            return (False, "Request timeout")
        except requests.exceptions.ConnectionError:
            return (False, "Connection error")
        except requests.exceptions.RequestException as e:
            return (False, f"Request error: {str(e)}")
        except Exception as e:
            return (False, f"Unexpected error: {str(e)}")
    
    def validate_with_playwright(self, page: Page, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate URL using Playwright (more robust, can handle JS)
        Returns: (is_valid, error_message)
        """
        if not url or not url.startswith('http'):
            return (False, "URL does not start with http")
        
        try:
            response = page.goto(url, wait_until='domcontentloaded', timeout=10000)
            
            if response and response.status == 200:
                return (True, None)
            elif response:
                return (False, f"HTTP {response.status}")
            else:
                return (False, "No response from page")
                
        except Exception as e:
            return (False, f"Playwright error: {str(e)}")
    
    def is_real_data(self, url: str, description: str = "") -> bool:
        """
        Check if data appears to be real (not mock/test)
        Validates URL format and content
        """
        # URL must start with http
        if not url.startswith('http'):
            return False
        
        # URL must not contain test/mock keywords
        test_keywords = ['test', 'mock', 'fake', 'demo', 'example', 'localhost']
        url_lower = url.lower()
        if any(keyword in url_lower for keyword in test_keywords):
            return False
        
        # Description should not be empty for real jobs
        if not description or len(description.strip()) < 10:
            return False
        
        return True


if __name__ == "__main__":
    scanner = LinkScanner()
    
    # Test URLs
    test_urls = [
        "https://www.google.com",
        "https://invalid-url-that-does-not-exist-12345.com",
        "not-a-url",
        "https://remoteok.com"
    ]
    
    for url in test_urls:
        is_valid, error = scanner.validate_url(url)
        print(f"{url}: {'✓ Valid' if is_valid else f'✗ Invalid: {error}'}")

