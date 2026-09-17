"""
ATS (Applicant Tracking System) Drivers
Specific drivers for common ATS systems: Gupy, Lever, Greenhouse
These systems are used by thousands of companies, so having specific drivers
significantly increases success rate
"""
from playwright.sync_api import Page
from typing import Dict, Optional, Tuple, List
import time
import re


class ATSDriver:
    """Base class for ATS drivers"""
    
    def __init__(self, page: Page, user_data: Dict[str, str], resume_path: str):
        self.page = page
        self.user_data = user_data
        self.resume_path = resume_path
    
    def detect_ats_type(self, url: str) -> Optional[str]:
        """Detect which ATS system is being used"""
        url_lower = url.lower()
        
        if 'gupy.io' in url_lower or 'gupy.com.br' in url_lower:
            return 'gupy'
        elif 'lever.co' in url_lower or 'jobs.lever.co' in url_lower:
            return 'lever'
        elif 'greenhouse.io' in url_lower or 'boards.greenhouse.io' in url_lower:
            return 'greenhouse'
        elif 'workday' in url_lower:
            return 'workday'
        elif 'taleo' in url_lower:
            return 'taleo'
        
        return None
    
    def apply(self) -> Tuple[bool, List[str]]:
        """Apply to job - to be implemented by subclasses"""
        raise NotImplementedError


class GupyDriver(ATSDriver):
    """Driver for Gupy ATS (very common in Brazil)"""
    
    def apply(self) -> Tuple[bool, List[str]]:
        """Apply to job via Gupy"""
        errors = []
        steps_completed = []
        
        try:
            # Gupy typically has a long form with multiple steps
            print("  Using Gupy-specific driver...")
            
            # Step 1: Find and fill email
            email_selectors = [
                "input[name='email']",
                "input[type='email']",
                "#email",
                "input[placeholder*='email' i]"
            ]
            
            email_filled = False
            for selector in email_selectors:
                try:
                    email_field = self.page.wait_for_selector(selector, timeout=2000, state='visible')
                    if email_field:
                        email_field.fill(self.user_data.get('email', ''))
                        email_filled = True
                        steps_completed.append('email_filled')
                        break
                except:
                    continue
            
            if not email_filled:
                errors.append("Could not find email field in Gupy form")
            
            # Step 2: Fill name
            name_selectors = [
                "input[name='name']",
                "input[name='fullName']",
                "input[name='nome']",
                "#name",
                "input[placeholder*='nome' i]"
            ]
            
            for selector in name_selectors:
                try:
                    name_field = self.page.wait_for_selector(selector, timeout=2000, state='visible')
                    if name_field:
                        name_field.fill(self.user_data.get('name', ''))
                        steps_completed.append('name_filled')
                        break
                except:
                    continue
            
            # Step 3: Fill phone
            phone_selectors = [
                "input[name='phone']",
                "input[name='telefone']",
                "input[type='tel']",
                "#phone"
            ]
            
            for selector in phone_selectors:
                try:
                    phone_field = self.page.wait_for_selector(selector, timeout=2000, state='visible')
                    if phone_field:
                        phone_field.fill(self.user_data.get('phone', ''))
                        steps_completed.append('phone_filled')
                        break
                except:
                    continue
            
            # Step 4: Upload resume (Gupy usually has file upload)
            file_selectors = [
                "input[type='file']",
                "input[accept*='pdf']",
                "input[name*='curriculo']",
                "input[name*='resume']"
            ]
            
            resume_uploaded = False
            for selector in file_selectors:
                try:
                    file_input = self.page.wait_for_selector(selector, timeout=2000, state='visible')
                    if file_input:
                        file_input.set_input_files(str(self.resume_path))
                        time.sleep(2)  # Wait for upload
                        resume_uploaded = True
                        steps_completed.append('resume_uploaded')
                        break
                except:
                    continue
            
            if not resume_uploaded:
                errors.append("Could not upload resume in Gupy form")
            
            # Step 5: Navigate through Gupy's multi-step form
            # Gupy often has "Next" buttons between steps
            next_button_selectors = [
                "button:has-text('Próximo')",
                "button:has-text('Next')",
                "button:has-text('Continuar')",
                "button[type='submit']:has-text('Próximo')",
                ".gupy-button--primary"
            ]
            
            # Try to find and click "Next" buttons (Gupy can have 3-5 steps)
            for step in range(5):  # Max 5 steps
                next_clicked = False
                for selector in next_button_selectors:
                    try:
                        next_btn = self.page.wait_for_selector(selector, timeout=2000, state='visible')
                        if next_btn:
                            next_btn.scroll_into_view_if_needed()
                            next_btn.click()
                            time.sleep(1)
                            next_clicked = True
                            steps_completed.append(f'step_{step+1}_next')
                            break
                    except:
                        continue
                
                if not next_clicked:
                    break  # No more steps
            
            # Step 6: Final submit
            submit_selectors = [
                "button:has-text('Enviar')",
                "button:has-text('Submit')",
                "button:has-text('Finalizar')",
                "button[type='submit']:not(:has-text('Próximo'))",
                ".gupy-button--submit"
            ]
            
            submitted = False
            for selector in submit_selectors:
                try:
                    submit_btn = self.page.wait_for_selector(selector, timeout=3000, state='visible')
                    if submit_btn:
                        submit_btn.scroll_into_view_if_needed()
                        submit_btn.click()
                        time.sleep(3)
                        submitted = True
                        steps_completed.append('submitted')
                        break
                except:
                    continue
            
            if not submitted:
                errors.append("Could not find submit button in Gupy form")
            
            return (submitted and len(errors) == 0, errors)
            
        except Exception as e:
            errors.append(f"Gupy driver error: {str(e)}")
            return (False, errors)


class LeverDriver(ATSDriver):
    """Driver for Lever ATS (used by Meta, Google, Amazon, etc.)"""
    
    def apply(self) -> Tuple[bool, List[str]]:
        """Apply to job via Lever"""
        errors = []
        steps_completed = []
        
        try:
            print("  Using Lever-specific driver...")
            
            # Lever has a simpler form structure
            # Step 1: Fill basic info
            fields = {
                'email': ["input[name='email']", "input[type='email']"],
                'name': ["input[name='name']", "input[name='fullName']"],
                'phone': ["input[name='phone']", "input[type='tel']"]
            }
            
            for field_name, selectors in fields.items():
                value = self.user_data.get(field_name, '')
                if not value:
                    continue
                
                for selector in selectors:
                    try:
                        field = self.page.wait_for_selector(selector, timeout=2000, state='visible')
                        if field:
                            field.fill(value)
                            steps_completed.append(f'{field_name}_filled')
                            break
                    except:
                        continue
            
            # Step 2: Upload resume
            file_input = self.page.wait_for_selector("input[type='file']", timeout=3000)
            if file_input:
                file_input.set_input_files(str(self.resume_path))
                time.sleep(2)
                steps_completed.append('resume_uploaded')
            else:
                errors.append("Could not find file upload in Lever form")
            
            # Step 3: Submit (Lever usually has a single submit)
            submit_btn = self.page.wait_for_selector("button[type='submit']", timeout=3000)
            if submit_btn:
                submit_btn.scroll_into_view_if_needed()
                submit_btn.click()
                time.sleep(3)
                steps_completed.append('submitted')
                return (True, errors)
            else:
                errors.append("Could not find submit button in Lever form")
                return (False, errors)
            
        except Exception as e:
            errors.append(f"Lever driver error: {str(e)}")
            return (False, errors)


class GreenhouseDriver(ATSDriver):
    """Driver for Greenhouse ATS (used by Nubank, Stone, XP, etc.)"""
    
    def apply(self) -> Tuple[bool, List[str]]:
        """Apply to job via Greenhouse"""
        errors = []
        steps_completed = []
        
        try:
            print("  Using Greenhouse-specific driver...")
            
            # Greenhouse forms are usually straightforward
            # Step 1: Fill email
            email_field = self.page.wait_for_selector("input#email, input[name='email']", timeout=3000)
            if email_field:
                email_field.fill(self.user_data.get('email', ''))
                steps_completed.append('email_filled')
            else:
                errors.append("Could not find email field in Greenhouse form")
            
            # Step 2: Fill name (sometimes split into first/last)
            first_name = self.page.query_selector("input#first_name, input[name='first_name']")
            last_name = self.page.query_selector("input#last_name, input[name='last_name']")
            
            if first_name and last_name:
                name_parts = self.user_data.get('name', '').split(' ', 1)
                first_name.fill(name_parts[0] if name_parts else '')
                if len(name_parts) > 1:
                    last_name.fill(name_parts[1])
                steps_completed.append('name_filled')
            
            # Step 3: Phone (optional in Greenhouse)
            phone_field = self.page.query_selector("input#phone, input[name='phone']")
            if phone_field:
                phone_field.fill(self.user_data.get('phone', ''))
                steps_completed.append('phone_filled')
            
            # Step 4: Resume upload
            resume_field = self.page.wait_for_selector("input[type='file']", timeout=3000)
            if resume_field:
                resume_field.set_input_files(str(self.resume_path))
                time.sleep(2)
                steps_completed.append('resume_uploaded')
            else:
                errors.append("Could not find resume upload in Greenhouse form")
            
            # Step 5: Submit
            submit_btn = self.page.wait_for_selector("input[type='submit'], button[type='submit']", timeout=3000)
            if submit_btn:
                submit_btn.scroll_into_view_if_needed()
                submit_btn.click()
                time.sleep(3)
                steps_completed.append('submitted')
                return (True, errors)
            else:
                errors.append("Could not find submit button in Greenhouse form")
                return (False, errors)
            
        except Exception as e:
            errors.append(f"Greenhouse driver error: {str(e)}")
            return (False, errors)


def get_ats_driver(page: Page, url: str, user_data: Dict[str, str], resume_path: str) -> Optional[ATSDriver]:
    """Factory function to get appropriate ATS driver"""
    url_lower = url.lower()
    
    if 'gupy' in url_lower:
        return GupyDriver(page, user_data, resume_path)
    elif 'lever' in url_lower:
        return LeverDriver(page, user_data, resume_path)
    elif 'greenhouse' in url_lower:
        return GreenhouseDriver(page, user_data, resume_path)
    
    return None

