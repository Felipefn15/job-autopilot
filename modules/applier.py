"""
Self-Healing Job Application Module
Uses Playwright with AI-powered (Gemini) DOM navigation for intelligent form filling
"""
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
# Stealth - SIMPLIFICADO com fallback
STEALTH_AVAILABLE = False
stealth_sync = None

try:
    # playwright-stealth v2 API: Stealth().apply_stealth_sync(page)
    from playwright_stealth import Stealth as _Stealth
    def stealth_sync(page):
        _Stealth().apply_stealth_sync(page)
    STEALTH_AVAILABLE = True
except ImportError:
    try:
        # v1 fallback
        from playwright_stealth import stealth_sync  # noqa: F811
        STEALTH_AVAILABLE = True
    except ImportError:
        def stealth_sync(page):
            pass
        STEALTH_AVAILABLE = False
        print("⚠ playwright-stealth não disponível, usando função dummy")
except Exception as e:
    def stealth_sync(page):
        pass
    STEALTH_AVAILABLE = False
    print(f"⚠ playwright-stealth import failed: {e}, usando função dummy")
from typing import Dict, List, Optional, Tuple
import re
import time
from pathlib import Path
from .brain import AIBrain
from .logger import ApplicationLogger, ApplicationStatus
from .ats_drivers import get_ats_driver, ATSDriver
from .session_manager import SessionManager
from datetime import datetime


class SelfHealingApplier:
    """Automated job application with AI-powered self-healing"""
    
    def __init__(self, resume_path: str, user_data: Dict[str, str]):
        self.resume_path = Path(resume_path)
        self.user_data = user_data  # {name, email, linkedin, phone, etc.}
        self.page: Optional[Page] = None
        self.playwright = None
        self.browser = None
        self.context = None
        self.brain = AIBrain()  # AI brain for intelligent selector resolution
        self.logger = ApplicationLogger()  # Logger for learning from past attempts
        self.current_log_id: Optional[str] = None
        self.current_job_info: Optional[Dict] = None
        self.selectors_used: Dict[str, str] = {}  # Track selectors used in current application
        self.session_manager = SessionManager()  # Real session manager
        
    def start_browser(self, headless: bool = False, use_real_session: bool = True):
        """
        Start Playwright browser with real session integration (NO API KEYS REQUIRED)
        
        Args:
            headless: Run browser in headless mode (False recommended for 2FA)
            use_real_session: Use real Chrome/Edge profile (recommended to avoid 403)
        """
        self.playwright = sync_playwright().start()
        
        if use_real_session:
            # Get context args from session manager
            try:
                context_args = self.session_manager.get_context_args("chrome")
                
                if context_args.get('can_use_real_session') and context_args.get('user_data_dir'):
                    user_data_dir = context_args['user_data_dir']
                    message = context_args.get('message', '')
                    chrome_running = context_args.get('chrome_running', False)
                    
                    print(f"  {message}")
                    
                    if chrome_running:
                        print("  ⚠ Chrome is running. Using isolated session (may need to login again).")
                        print("     💡 RECOMMENDATION: Close Chrome completely to use your real profile")
                        print("     This ensures Google login works automatically with your saved session.")
                    else:
                        print("  ✓ Using REAL Chrome Profile (Chrome is closed)")
                        print("  ✓ Google login should work automatically with your saved session")
                    
                    # Use persistent context with isolated session
                    print(f"  Attempting to launch persistent context: {user_data_dir}")
                    try:
                        # Add remote debugging port for stability
                        args = [
                            '--disable-blink-features=AutomationControlled',
                            '--disable-dev-shm-usage',
                            '--remote-debugging-port=9222',
                            '--no-first-run',
                            '--no-default-browser-check',
                        ]
                        
                        self.context = self.playwright.chromium.launch_persistent_context(
                            user_data_dir=user_data_dir,
                            headless=headless,
                            channel="chrome" if self.session_manager.find_chrome_profile() else None,
                            args=args,
                            viewport={'width': 1920, 'height': 1080},
                            locale='en-US',
                            timezone_id='America/Sao_Paulo',
                            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                        )
                        
                        # Get first page from persistent context
                        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
                        
                        # Apply stealth mode if available - SIMPLIFICADO
                        if STEALTH_AVAILABLE:
                            try:
                                stealth_sync(self.page)
                                print("  ✓ Stealth mode enabled")
                            except Exception as e:
                                print(f"  ⚠ Stealth mode failed: {e}")
                                print("  Continuing without stealth mode...")
                        
                        print("  ✓ Browser started with real session (NO API KEYS REQUIRED)")
                        return
                    except Exception as browser_error:
                        print(f"\n  ✗ ERROR: Could not launch browser with persistent context")
                        print(f"     Error details: {str(browser_error)}")
                        print(f"     Error type: {type(browser_error).__name__}")
                        print(f"\n     Possible causes:")
                        print(f"     1. Chrome is still running - Please close Chrome completely")
                        print(f"     2. Profile path is incorrect - Check: {user_data_dir}")
                        print(f"     3. Permission issues - Check file permissions")
                        print(f"\n     ⚠ PAUSING LOOP - Please fix the issue and restart")
                        print(f"     Waiting 60 seconds before retry...")
                        time.sleep(60)
                        raise  # Re-raise to trigger recovery
                else:
                    print(f"  ⚠ {context_args.get('message', 'Real profile not available')}")
                    print("     Using temporary profile (may get 403).")
            except Exception as session_error:
                print(f"\n  ✗ ERROR in session management: {str(session_error)}")
                print(f"     Error type: {type(session_error).__name__}")
                print(f"     ⚠ PAUSING LOOP - Please check Chrome and restart")
                time.sleep(60)
                raise  # Re-raise to trigger recovery
        
        # Fallback: Use temporary profile (may get 403)
        import random
        user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        user_agent = random.choice(user_agents)
        
        self.browser = self.playwright.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
            ]
        )
        
        self.context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=user_agent,
            locale='en-US',
            timezone_id='America/Sao_Paulo'
        )
        
        self.page = self.context.new_page()
        
        if STEALTH_AVAILABLE:
            try:
                stealth_sync(self.page)
                print("  ✓ Stealth mode enabled (temporary profile)")
            except Exception as e:
                print(f"  ⚠ Stealth mode failed: {e}")
                print("  Continuing without stealth mode...")
    
    def close_browser(self):
        """Close browser and cleanup"""
        if self.context:
            # For persistent context, use close()
            if hasattr(self.context, 'pages'):
                # Persistent context
                self.context.close()
            else:
                # Regular context
                self.context.close()
        
        if hasattr(self, 'browser') and self.browser:
            self.browser.close()
        
        if self.playwright:
            self.playwright.stop()
    
    def find_element_with_fallback(self, selectors: List[str], timeout: int = 5000, use_ai: bool = True) -> Optional[Tuple[str, any]]:
        """Try multiple selectors until one works, fallback to AI if all fail"""
        for selector in selectors:
            try:
                element = self.page.wait_for_selector(selector, timeout=timeout, state='visible')
                if element:
                    return (selector, element)
            except PlaywrightTimeout:
                continue
            except Exception as e:
                print(f"Selector '{selector}' failed: {e}")
                continue
        
        # All selectors failed - use AI to find the element
        if use_ai and self.page:
            try:
                print("  All selectors failed, using AI to analyze page...")
                html_content = self.page.content()
                # Try to find a generic selector using AI
                # This is a fallback - we'll use resolve_form_fields for specific fields
                return None
            except Exception as e:
                print(f"  AI fallback failed: {e}")
        
        return None
    
    def find_elements_with_fallback(self, selectors: List[str], timeout: int = 5000) -> Optional[Tuple[str, List]]:
        """Try multiple selectors to find multiple elements"""
        for selector in selectors:
            try:
                elements = self.page.wait_for_selector(selector, timeout=timeout, state='visible')
                if elements:
                    all_elements = self.page.query_selector_all(selector)
                    if all_elements:
                        return (selector, all_elements)
            except PlaywrightTimeout:
                continue
            except Exception as e:
                print(f"Selector '{selector}' failed: {e}")
                continue
        return None
    
    def find_field_by_label(self, label_text: str, field_type: str = "input") -> Optional[Tuple[str, any]]:
        """Find form field by label text using multiple strategies"""
        label_lower = label_text.lower()
        
        # Strategy 1: Find label element and get associated input
        label_selectors = [
            f"label:has-text('{label_text}')",
            f"label:has-text('{label_lower}')",
            f"//label[contains(text(), '{label_text}')]",
            f"//label[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{label_lower}')]"
        ]
        
        for label_sel in label_selectors:
            try:
                label = self.page.wait_for_selector(label_sel, timeout=2000, state='visible')
                if label:
                    # Get the 'for' attribute
                    for_attr = label.get_attribute('for')
                    if for_attr:
                        input_sel = f"#{for_attr}"
                        input_elem = self.page.query_selector(input_sel)
                        if input_elem:
                            return (input_sel, input_elem)
                    
                    # Try to find input near the label
                    parent = label.evaluate_handle('el => el.parentElement')
                    if parent:
                        input_elem = self.page.query_selector(f"{label_sel} + input, {label_sel} ~ input")
                        if input_elem:
                            return (f"{label_sel} + input", input_elem)
            except:
                continue
        
        # Strategy 2: Find by placeholder
        placeholder_selectors = [
            f"input[placeholder*='{label_text}']",
            f"input[placeholder*='{label_lower}']",
            f"textarea[placeholder*='{label_text}']",
            f"textarea[placeholder*='{label_lower}']"
        ]
        
        for sel in placeholder_selectors:
            try:
                elem = self.page.wait_for_selector(sel, timeout=2000, state='visible')
                if elem:
                    return (sel, elem)
            except:
                continue
        
        # Strategy 3: Find by name or id attribute
        name_selectors = [
            f"input[name*='{label_lower}']",
            f"input[id*='{label_lower}']",
            f"textarea[name*='{label_lower}']",
            f"textarea[id*='{label_lower}']"
        ]
        
        for sel in name_selectors:
            try:
                elem = self.page.wait_for_selector(sel, timeout=2000, state='visible')
                if elem:
                    return (sel, elem)
            except:
                continue
        
        # Strategy 4: Generic field type search
        generic_selectors = [
            f"{field_type}[type='text']",
            f"{field_type}[type='email']",
            f"{field_type}:not([type='hidden'])"
        ]
        
        # Get all visible fields and try to match by context
        try:
            all_fields = self.page.query_selector_all(f"{field_type}:visible")
            for field in all_fields:
                # Check nearby text
                nearby_text = field.evaluate('el => el.parentElement?.textContent || ""').lower()
                if label_lower in nearby_text:
                    return (f"{field_type}:visible", field)
        except:
            pass
        
        return None
    
    def check_visa_eligibility(self) -> Tuple[bool, Optional[str]]:
        """
        Check if form asks about visa/work authorization that would disqualify LATAM candidates
        Returns: (is_eligible, reason_if_not)
        """
        if not self.page:
            return (True, None)
        
        try:
            page_text = self.page.content().lower()
            page_title = self.page.title().lower()
            
            # Check for visa/work authorization questions that would reject LATAM candidates
            rejection_patterns = [
                r'are you authorized to work in (?:the )?(?:united states|us|usa|eu|europe|uk|united kingdom)',
                r'must be (?:a )?(?:us|united states|eu|european) (?:citizen|resident)',
                r'work authorization.*(?:us|united states|eu|europe)',
                r'eligible to work.*(?:us|united states|eu|europe)',
                r'visa.*(?:sponsorship|required).*(?:us|united states)',
                r'local candidates only',
                r'no remote.*(?:outside|international)',
                r'not accepting.*(?:international|remote.*outside)'
            ]
            
            for pattern in rejection_patterns:
                if re.search(pattern, page_text, re.IGNORECASE) or re.search(pattern, page_title, re.IGNORECASE):
                    match = re.search(pattern, page_text + " " + page_title, re.IGNORECASE)
                    reason = f"Visa/work authorization requirement detected: {match.group(0) if match else pattern}"
                    return (False, reason)
            
            # Check for fields that might ask about work authorization
            auth_field_selectors = [
                "input[name*='authorized']",
                "input[name*='visa']",
                "input[name*='work_permit']",
                "select[name*='authorized']",
                "select[name*='visa']",
                "select[name*='work_permit']",
                "input[id*='authorized']",
                "input[id*='visa']"
            ]
            
            for selector in auth_field_selectors:
                try:
                    element = self.page.query_selector(selector)
                    if element:
                        # Check if it's visible and might be asking about US/EU authorization
                        if element.is_visible():
                            label_text = ""
                            # Try to find associated label
                            label = self.page.query_selector(f"label[for='{element.get_attribute('id')}']")
                            if label:
                                label_text = label.inner_text().lower()
                            
                            # Check if it's asking about US/EU specifically
                            if any(term in label_text for term in ['us', 'united states', 'eu', 'europe']):
                                reason = f"Work authorization field detected: {selector}"
                                return (False, reason)
                except:
                    continue
            
            return (True, None)
            
        except Exception as e:
            print(f"  Error checking visa eligibility: {e}")
            return (True, None)  # On error, assume eligible
    
    def fill_field(self, field_name: str, value: str) -> bool:
        """Fill a form field using self-healing strategies with AI fallback"""
        print(f"Attempting to fill field: {field_name}")
        
        # LÓGICA DE NOME DIVIDIDO: Detectar campos de sobrenome
        if field_name.lower() == 'name':
            # Primeiro, tentar detectar se há campo de sobrenome na página
            last_name_selectors = [
                "input[name='last_name']",
                "input[name='lastName']",
                "input[name='surname']",
                "input[name='family_name']",
                "input[id='last_name']",
                "input[id='lastName']",
                "input[id='surname']",
                "input[id='sobrenome']",
                "input[placeholder*='last name' i]",
                "input[placeholder*='sobrenome' i]",
                "input[placeholder*='surname' i]"
            ]
            
            last_name_field = None
            for selector in last_name_selectors:
                try:
                    last_name_field = self.page.query_selector(selector)
                    if last_name_field:
                        print(f"  ✓ Detected last name field: {selector}")
                        break
                except:
                    continue
            
            # Se não encontrou por seletor, tentar por label
            if not last_name_field:
                last_name_labels = ['last name', 'sobrenome', 'surname', 'family name', 'apellido']
                for label_text in last_name_labels:
                    try:
                        # Procurar label e pegar o input associado
                        label = self.page.query_selector(f"label:has-text('{label_text}')")
                        if label:
                            # Tentar pegar o input associado ao label
                            input_id = label.get_attribute('for')
                            if input_id:
                                last_name_field = self.page.query_selector(f"input#{input_id}")
                            else:
                                # Tentar encontrar input dentro do label
                                last_name_field = label.query_selector("input")
                            
                            if last_name_field:
                                print(f"  ✓ Detected last name field by label: '{label_text}'")
                                break
                    except:
                        continue
            
            # Se encontrou campo de sobrenome, dividir o nome
            if last_name_field:
                full_name = value
                parts = full_name.split(' ', 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else '.'
                
                print(f"  → Splitting name: '{first_name}' (first) + '{last_name}' (last)")
                
                # Preencher primeiro nome no campo "name"
                # (continuar com a lógica normal abaixo, mas usar first_name)
                value = first_name
                
                # Preencher sobrenome no campo de sobrenome
                try:
                    last_name_field.click()
                    last_name_field.fill('')
                    last_name_field.fill(last_name)
                    print(f"  ✓ Filled last name field: '{last_name}'")
                    time.sleep(0.3)
                except Exception as e:
                    print(f"  ⚠ Failed to fill last name field: {e}")
        
        # Common field name mappings
        field_mappings = {
            'name': ['name', 'nome', 'full name', 'nome completo', 'first name', 'primeiro nome'],
            'email': ['email', 'e-mail', 'correo', 'mail'],
            'phone': ['phone', 'telefone', 'tel', 'mobile', 'celular'],
            'linkedin': ['linkedin', 'linkedin url', 'linkedin profile', 'perfil linkedin'],
            'resume': ['resume', 'cv', 'curriculum', 'curriculo', 'upload', 'attach']
        }
        
        search_terms = field_mappings.get(field_name.lower(), [field_name])
        
        for term in search_terms:
            result = self.find_field_by_label(term)
            if result:
                selector, element = result
                try:
                    # Clear and fill
                    element.click()
                    element.fill('')
                    element.fill(value)
                    print(f"  Successfully filled '{field_name}' using selector: {selector}")
                    
                    # Log successful field fill and store selector
                    self.logger.log_action(
                        action_type="fill_field",
                        description=f"Filled field: {field_name}",
                        selector=selector,
                        success=True
                    )
                    self.selectors_used[field_name] = selector
                    time.sleep(0.5)
                    return True
                except Exception as e:
                    print(f"  Failed to fill field: {e}")
                    continue
        
        # Fallback: try direct selectors (including common Brazilian ATS selectors)
        direct_selectors = [
            f"input[name='{field_name}']",
            f"input[id='{field_name}']",
            f"input[name*='{field_name}']",
            f"input[id*='{field_name}']"
        ]
        
        # Add common Brazilian ATS selectors (Strider, Ashby, Gupy, etc.)
        if field_name.lower() == 'name':
            direct_selectors.extend([
                "input[name*='first']",
                "input[id*='first']",
                "input[name*='nome']",
                "input[id*='nome']",
                "[aria-label*='nome' i]",
                "[aria-label*='name' i]",
                "input[placeholder*='nome' i]",
                "input[placeholder*='name' i]"
            ])
        elif field_name.lower() == 'email':
            direct_selectors.extend([
                "input[type='email']",
                "input[name*='email']",
                "input[id*='email']",
                "[aria-label*='email' i]",
                "input[placeholder*='email' i]"
            ])
        elif field_name.lower() == 'phone':
            direct_selectors.extend([
                "input[type='tel']",
                "input[name*='phone']",
                "input[name*='telefone']",
                "input[id*='phone']",
                "[aria-label*='telefone' i]",
                "input[placeholder*='telefone' i]"
            ])
        
        result = self.find_element_with_fallback(direct_selectors, use_ai=False)
        if result:
            selector, element = result
            try:
                element.fill(value)
                print(f"  Successfully filled '{field_name}' using direct selector: {selector}")
                return True
            except Exception as e:
                print(f"  Failed to fill with direct selector: {e}")
        
        # HARDCODED FALLBACK: Try most common selectors immediately (before AI)
        # This prevents wasting AI quota on basic fields
        hardcoded_selectors = {
            'name': [
                "input[name*='name']",
                "#name",
                "[aria-label*='nome' i]",
                "[aria-label*='name' i]",
                "input[placeholder*='name' i]",
                "input[placeholder*='nome' i]"
            ],
            'email': [
                "input[type='email']",
                "#email",
                "[name*='email']",
                "input[placeholder*='email' i]",
                "[aria-label*='email' i]"
            ],
            'phone': [
                "input[type='tel']",
                "#phone",
                "[name*='phone']",
                "[name*='telefone']",
                "[aria-label*='telefone' i]"
            ],
            'linkedin': [
                "input[name*='linkedin']",
                "#linkedin",
                "[aria-label*='linkedin' i]"
            ]
        }
        
        if field_name.lower() in hardcoded_selectors:
            print(f"  Trying hardcoded fallback selectors for '{field_name}'...")
            for hc_selector in hardcoded_selectors[field_name.lower()]:
                try:
                    element = self.page.query_selector(hc_selector)
                    if element and element.is_visible():
                        element.click()
                        element.fill('')
                        element.fill(value)
                        print(f"  ✓ Successfully filled '{field_name}' using hardcoded selector: {hc_selector}")
                        self.selectors_used[field_name] = hc_selector
                        time.sleep(0.3)
                        return True
                except:
                    continue
        
        # AI Fallback with Intelligent Retry: Check logs for previous suggestions
        if self.page and self.brain:
            try:
                print(f"  Traditional methods failed, checking logs for previous suggestions...")
                
                # Check if we have previous failures for this company with suggestions
                if self.current_job_info and self.current_job_info.get('company'):
                    company_logs = self.logger.get_logs_by_company(self.current_job_info['company'])
                    failed_logs = [log for log in company_logs if log.get('status') == 'failed']
                    
                    # Look for previous suggestions for this field
                    for log in failed_logs:
                        error_details = log.get('error_details', {})
                        if error_details.get('field') == field_name and log.get('gemini_suggestion'):
                            suggestion = log['gemini_suggestion']
                            print(f"  Found previous Gemini suggestion: {suggestion}")
                            
                            # Try to extract selector from suggestion
                            # Example: "Try using input[data-testid='candidate-email']"
                            import re
                            selector_match = re.search(r"(input|button|select)\[[^\]]+\]", suggestion)
                            if selector_match:
                                suggested_selector = selector_match.group(0)
                                print(f"  Trying previous suggestion: {suggested_selector}")
                                try:
                                    element = self.page.wait_for_selector(suggested_selector, timeout=3000, state='visible')
                                    if element:
                                        element.click()
                                        element.fill('')
                                        element.fill(value)
                                        print(f"  ✓ Successfully filled '{field_name}' using previous suggestion: {suggested_selector}")
                                        
                                        self.logger.log_action(
                                            action_type="fill_field_retry",
                                            description=f"Filled field: {field_name} using previous suggestion",
                                            selector=suggested_selector,
                                            success=True
                                        )
                                        self.selectors_used[field_name] = suggested_selector
                                        time.sleep(0.5)
                                        return True
                                except Exception as e:
                                    print(f"  Previous suggestion failed: {e}")
                            
                            # If suggestion mentions label, try finding by label text
                            if 'label' in suggestion.lower() or 'text' in suggestion.lower():
                                # Extract label text from suggestion
                                label_match = re.search(r"label.*?['\"]([^'\"]+)['\"]", suggestion, re.IGNORECASE)
                                if label_match:
                                    label_text = label_match.group(1)
                                    print(f"  Trying to find field by label text: '{label_text}'")
                                    result = self.find_field_by_label(label_text)
                                    if result:
                                        selector, element = result
                                        try:
                                            element.click()
                                            element.fill('')
                                            element.fill(value)
                                            print(f"  ✓ Successfully filled '{field_name}' using label: {label_text}")
                                            self.selectors_used[field_name] = selector
                                            time.sleep(0.5)
                                            return True
                                        except Exception as e:
                                            print(f"  Label-based fill failed: {e}")
                
                # If no previous suggestions worked, get new AI suggestion (with SmartAI fallback)
                print(f"  Getting new AI suggestion for '{field_name}' field (Gemini -> Groq fallback)...")
                html_content = self.page.content()
                
                # Get AI-suggested selector (uses SmartAI: Gemini -> Groq -> Manual)
                try:
                    ai_selectors = self.brain.resolve_form_fields(html_content, [field_name])
                    ai_selector = ai_selectors.get(field_name)
                    
                    if ai_selector:
                        try:
                            # Try the AI-suggested selector
                            element = self.page.wait_for_selector(ai_selector, timeout=3000, state='visible')
                            if element:
                                element.click()
                                element.fill('')
                                element.fill(value)
                                print(f"  ✓ Successfully filled '{field_name}' using AI-suggested selector: {ai_selector}")
                                
                                # Log AI-suggested selector success
                                self.logger.log_action(
                                    action_type="fill_field_ai",
                                    description=f"Filled field: {field_name} using AI",
                                    selector=ai_selector,
                                    success=True
                                )
                                self.selectors_used[field_name] = ai_selector
                                time.sleep(0.5)
                                return True
                        except Exception as e:
                            print(f"  AI-suggested selector '{ai_selector}' failed: {e}")
                    else:
                        print(f"  ⚠ AI did not return a selector for '{field_name}'. Trying manual selectors...")
                except Exception as e:
                    error_str = str(e).lower()
                    is_429 = '429' in error_str or 'quota' in error_str or 'rate limit' in error_str
                    if is_429:
                        print(f"  ⚠ AI Quota Exceeded (429). SmartAI should have switched to Groq, but failed. Using manual selectors...")
                    else:
                        print(f"  ⚠ AI resolution failed: {e}. Using manual selectors...")
                
            except Exception as e:
                print(f"  AI fallback error: {e}")
        
        print(f"  ✗ WARNING: Could not find field '{field_name}'")
        return False
    
    def upload_resume(self) -> bool:
        """Upload resume file with self-healing"""
        print("Attempting to upload resume...")
        
        # Try multiple strategies to find file input
        # Priority: Specific selectors first, then generic
        file_selectors = [
            "input[type='file']",  # Most common
            "[data-test='file-upload-input']",  # Greenhouse/Lever specific
            "input[accept*='pdf']",
            "input[accept*='.pdf']",
            "input[name*='resume']",
            "input[name*='cv']",
            "input[name*='curriculum']",
            "input[id*='resume']",
            "input[id*='cv']",
            "input[id*='file']",
            "input[id*='upload']",
            "[data-testid*='file']",  # React testing library
            "[data-testid*='upload']"
        ]
        
        result = self.find_element_with_fallback(file_selectors, timeout=3000)
        if result:
            selector, element = result
            try:
                element.set_input_files(str(self.resume_path))
                print(f"  Successfully uploaded resume using selector: {selector}")
                
                # Wait for upload to process and network to be idle
                time.sleep(1)
                try:
                    self.page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    pass  # Continue even if networkidle times out
                
                return True
            except Exception as e:
                print(f"  Failed to upload resume: {e}")
                return False
        
        print("  WARNING: Could not find file upload field")
        return False
    
    def check_for_modals(self) -> bool:
        """Detect and close modals, cookie banners, and pop-ups that block interactions"""
        if not self.page:
            return False
        
        try:
            # Common modal/cookie banner selectors
            modal_selectors = [
                # Cookie banners
                "button:has-text('Accept')",
                "button:has-text('Aceitar')",
                "button:has-text('Accept All')",
                "button:has-text('I Accept')",
                "button[id*='cookie']",
                "button[class*='cookie']",
                ".cookie-banner button",
                "#cookie-consent button",
                
                # Newsletter popups
                "button:has-text('No Thanks')",
                "button:has-text('Not Now')",
                "button:has-text('Close')",
                "button:has-text('Fechar')",
                ".modal-close",
                ".popup-close",
                "[aria-label='Close']",
                "[aria-label='Fechar']",
                
                # Generic close buttons
                "button.close",
                ".close-button",
                "[data-dismiss='modal']"
            ]
            
            closed_any = False
            for selector in modal_selectors:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        element.click()
                        print(f"  Closed modal/banner: {selector}")
                        time.sleep(0.5)
                        closed_any = True
                except:
                    continue
            
            return closed_any
            
        except Exception as e:
            print(f"  Error checking for modals: {e}")
        return False
    
    def handle_social_login(self, page: Page) -> bool:
        """
        Detect and handle social login (Google SSO, LinkedIn) before form filling.
        Since we're using a persistent Chrome session, we just need to click the login button
        and select the user's account if a popup appears.
        
        Args:
            page: Playwright Page object
            
        Returns:
            bool: True if login was handled, False otherwise
        """
        if not page:
            return False
        
        print("  Checking for social login requirements...")
        
        try:
            # Wait a bit for page to fully load
            time.sleep(2)
            
            # Common SSO button selectors (Google, LinkedIn)
            sso_button_selectors = [
                "button:has-text('Sign in with Google')",
                "button:has-text('Continue with Google')",
                "button:has-text('Log in with Google')",
                "button:has-text('Login with Google')",
                "a:has-text('Sign in with Google')",
                "a:has-text('Continue with Google')",
                "a:has-text('Log in with Google')",
                "a:has-text('Login with Google')",
                "[aria-label*='Google']",
                "[data-provider='google']",
                "[data-provider='google-oauth2']",
                "button[class*='google']",
                "a[class*='google']",
                # LinkedIn variants
                "button:has-text('Sign in with LinkedIn')",
                "button:has-text('Continue with LinkedIn')",
                "a:has-text('Sign in with LinkedIn')",
                "[data-provider='linkedin']",
                "button[class*='linkedin']",
                "a[class*='linkedin']"
            ]
            
            sso_button = None
            for selector in sso_button_selectors:
                try:
                    element = page.query_selector(selector)
                    if element and element.is_visible():
                        sso_button = element
                        print(f"  ✓ Found SSO button: {selector}")
                        break
                except:
                    continue
            
            # If no button found with common selectors, try AI-powered detection
            if not sso_button:
                print("  Trying AI-powered SSO button detection...")
                try:
                    html_content = page.content()
                    prompt = f"""Analyze this HTML and find the button or link for social login (Google SSO, LinkedIn).
                    Return ONLY a CSS selector for the login button, nothing else.
                    Look for buttons/links containing: "Sign in with Google", "Continue with Google", "Login with Google", "Sign in with LinkedIn".
                    
                    HTML:
                    {html_content[:5000]}
                    
                    Return ONLY the CSS selector, example: button[class*='google'] or a:has-text('Sign in with Google')"""
                    
                    if hasattr(self, 'brain') and self.brain:
                        ai_selector = self.brain.smart_ai.generate_content(prompt)
                        # Clean up AI response (remove quotes, extra text)
                        ai_selector = ai_selector.strip().strip('"').strip("'")
                        if ai_selector and len(ai_selector) < 200:  # Reasonable selector length
                            try:
                                element = page.query_selector(ai_selector)
                                if element and element.is_visible():
                                    sso_button = element
                                    print(f"  ✓ Found SSO button via AI: {ai_selector}")
                            except:
                                pass
                except Exception as ai_error:
                    print(f"  ⚠ AI detection failed: {ai_error}")
            
            if not sso_button:
                print("  No SSO login button found, proceeding with form")
                return False
            
            # Click the SSO button
            print("  Clicking SSO login button...")
            sso_button.click()
            time.sleep(3)  # Wait for popup/redirect
            
            # Check if a new page/popup opened (Google account selection)
            # Wait a bit for popup to open
            time.sleep(2)
            
            all_pages = self.context.pages if hasattr(self, 'context') and self.context else [page]
            
            account_selected = False
            
            # User's email and name for account selection
            user_email = self.user_data.get('email', 'felipefrancanogueira@gmail.com')
            user_name = self.user_data.get('name', 'Felipe')
            
            # Try to find and click user's account in popup/new page
            for p in all_pages:
                try:
                    if p.is_closed():
                        continue
                    
                    # Wait for account selection page to load
                    p.wait_for_load_state('domcontentloaded', timeout=5000)
                    
                    # Check if we're on a Google accounts page
                    current_url = p.url.lower()
                    is_google_accounts = 'accounts.google.com' in current_url or 'google.com/accounts' in current_url
                    
                    # PRIORITY 1: Detect if Google already shows the logged-in profile (like in the image)
                    # Look for profile elements that show the user's name or email directly
                    profile_selectors = [
                        # Profile card/modal with name and email visible
                        f"div:has-text('{user_name}'):has-text('{user_email}')",
                        f"div:has-text('{user_name}'):near(div:has-text('{user_email}'))",
                        # Profile picture with name/email nearby
                        f"img[alt*='{user_name}']",
                        f"img[alt*='profile']:near(div:has-text('{user_email}'))",
                        # Direct email text in profile
                        f"div:has-text('{user_email}')",
                        f"span:has-text('{user_email}')",
                        f"p:has-text('{user_email}')",
                        # Name text
                        f"div:has-text('{user_name}')",
                        f"span:has-text('{user_name}')",
                        # Profile container elements
                        "div[role='dialog']:has-text('@gmail.com')",
                        "div[class*='profile']:has-text('@gmail.com')",
                        "div[class*='account']:has-text('@gmail.com')",
                    ]
                    
                    # Try to find the profile element first
                    profile_element = None
                    for profile_sel in profile_selectors:
                        try:
                            elements = p.query_selector_all(profile_sel)
                            for elem in elements:
                                if elem and elem.is_visible():
                                    # Check if it contains the email or name
                                    text = elem.inner_text().lower()
                                    if user_email.lower() in text or user_name.lower() in text:
                                        profile_element = elem
                                        print(f"  ✓ Found logged-in profile: {profile_sel}")
                                        break
                            if profile_element:
                                break
                        except:
                            continue
                    
                    # If profile found, click on it or look for a "Continue" button
                    if profile_element:
                        try:
                            # Try to find a "Continue", "Confirm", or "Allow" button near the profile
                            continue_button_selectors = [
                                "button:has-text('Continue')",
                                "button:has-text('Continuar')",
                                "button:has-text('Confirm')",
                                "button:has-text('Confirmar')",
                                "button:has-text('Allow')",
                                "button:has-text('Permitir')",
                                "button:has-text('Sign in')",
                                "button:has-text('Entrar')",
                                "button[id*='confirm']",
                                "button[id*='continue']",
                                "button[type='submit']",
                                # Google-specific buttons
                                "button[jsname]:has-text('Continue')",
                                "div[role='button']:has-text('Continue')",
                            ]
                            
                            continue_clicked = False
                            for btn_sel in continue_button_selectors:
                                try:
                                    btn = p.query_selector(btn_sel)
                                    if btn and btn.is_visible():
                                        print(f"  ✓ Found continue button: {btn_sel}")
                                        btn.click()
                                        continue_clicked = True
                                        account_selected = True
                                        time.sleep(2)
                                        break
                                except:
                                    continue
                            
                            # If no continue button, click the profile itself
                            if not continue_clicked:
                                print("  ✓ Clicking on profile element...")
                                profile_element.click()
                                account_selected = True
                                time.sleep(2)
                        except Exception as profile_error:
                            print(f"  ⚠ Error clicking profile: {profile_error}")
                    
                    # PRIORITY 2: Specific account identifier selectors (MOST SPECIFIC FIRST)
                    if not account_selected:
                        # Check for password prompt first (Google asking for password)
                        password_indicators = [
                            "input[type='password']",
                            "input[name='password']",
                            "input[id*='password']",
                            "input[aria-label*='password']",
                            "input[aria-label*='senha']",
                            ":has-text('Enter your password')",
                            ":has-text('Digite sua senha')",
                            ":has-text('Password')",
                            ":has-text('Senha')"
                        ]
                        
                        password_required = False
                        for pwd_indicator in password_indicators:
                            try:
                                pwd_element = p.query_selector(pwd_indicator)
                                if pwd_element and pwd_element.is_visible():
                                    password_required = True
                                    print(f"  ⚠ Google SSO exigiu senha manual (detected: {pwd_indicator})")
                                    
                                    # Take screenshot for debugging
                                    try:
                                        screenshot_path = Path("logs") / f"google_password_required_{int(time.time())}.png"
                                        screenshot_path.parent.mkdir(exist_ok=True)
                                        p.screenshot(path=str(screenshot_path))
                                        print(f"  📸 Screenshot saved: {screenshot_path}")
                                    except Exception as screenshot_error:
                                        print(f"  ⚠ Could not save screenshot: {screenshot_error}")
                                    
                                    # Log the issue
                                    self.logger.log_action(
                                        action_type="social_login_password_required",
                                        description="Google SSO required password - manual intervention needed",
                                        success=False
                                    )
                                    
                                    print("  🛑 PARANDO PARA INTERVENÇÃO MANUAL")
                                    print("  → O Google pediu senha. Por favor, faça login manualmente.")
                                    print("  → Após fazer login, o robô continuará automaticamente.")
                                    
                                    # Wait for manual intervention (user can login manually)
                                    print("  ⏳ Aguardando 30 segundos para login manual...")
                                    time.sleep(30)
                                    
                                    # Check if user logged in manually
                                    current_url_after = p.url.lower()
                                    if 'accounts.google.com' not in current_url_after or 'signin' not in current_url_after:
                                        print("  ✓ Login manual detectado - continuando...")
                                        account_selected = True
                                        break
                                    else:
                                        print("  ⚠ Ainda na página de login. Tentando continuar...")
                                    break
                            except:
                                continue
                        
                        if password_required:
                            # Skip account selection if password was required and handled
                            continue
                        
                        # PRIORITY: Specific selectors for felipefrancanogueira@gmail.com
                        account_selectors = [
                            # MOST SPECIFIC: data-identifier attribute (Google account list)
                            f"div[data-identifier='{user_email}']",
                            f"[data-identifier='{user_email}']",
                            f"div[data-email='{user_email}']",
                            f"[data-email='{user_email}']",
                            # Email in aria-label
                            f"[aria-label='{user_email}']",
                            f"[aria-label*='{user_email}']",
                            # Email in text content (exact match)
                            f"div:has-text('{user_email}')",
                            f"span:has-text('{user_email}')",
                            f"p:has-text('{user_email}')",
                            # Email with data-authuser
                            f"[data-authuser]:has-text('{user_email}')",
                            # Username part only
                            f"div:has-text('{user_email.split('@')[0]}')",
                            # Name
                            f"div:has-text('{user_name}')",
                            # Generic account selection (LAST RESORT)
                            "div[data-authuser]",
                            "div[role='button']:has-text('@')",
                            "div[jsname]:has-text('@')",
                            # Click first account if email not found
                            "div[data-authuser='0']",
                            "div[jsname='YRMmle']",  # Google account list item
                        ]
                    
                        for acc_selector in account_selectors:
                            try:
                                # Try to find element
                                account_element = p.query_selector(acc_selector)
                                if account_element and account_element.is_visible():
                                    # Verify it's the correct account by checking text content
                                    element_text = account_element.inner_text().lower()
                                    if user_email.lower() in element_text or user_name.lower() in element_text or 'data-identifier' in acc_selector or 'data-email' in acc_selector:
                                        print(f"  ✓ Found account selection (Felipe): {acc_selector}")
                                        account_element.click()
                                        account_selected = True
                                        time.sleep(2)
                                        break
                                    else:
                                        # Element found but doesn't match our account, skip
                                        print(f"  ⚠ Found element but doesn't match account: {acc_selector}")
                                        continue
                            except Exception as selector_error:
                                # Continue to next selector
                                continue
                    
                    if account_selected:
                        break
                except:
                    continue
            
            # If account selection failed, try AI-powered detection
            if not account_selected:
                print("  Trying AI-powered account selection...")
                for p in all_pages:
                    if p.is_closed():
                        continue
                    try:
                        html_content = p.content()
                        user_email = self.user_data.get('email', 'felipefrancanogueira@gmail.com')
                        prompt = f"""Analyze this HTML from a Google account selection page.
                        Find the element that represents the account with email: {user_email}
                        Return ONLY a CSS selector for that account element.
                        
                        HTML:
                        {html_content[:5000]}
                        
                        Return ONLY the CSS selector."""
                        
                        if hasattr(self, 'brain') and self.brain:
                            ai_selector = self.brain.smart_ai.generate_content(prompt)
                            ai_selector = ai_selector.strip().strip('"').strip("'")
                            if ai_selector and len(ai_selector) < 200:
                                try:
                                    account_element = p.query_selector(ai_selector)
                                    if account_element and account_element.is_visible():
                                        print(f"  ✓ Found account via AI: {ai_selector}")
                                        account_element.click()
                                        account_selected = True
                                        time.sleep(2)
                                        break
                                except:
                                    pass
                    except:
                        continue
            
            # Check if we're already redirected (Google might auto-redirect if already logged in)
            current_url = page.url.lower()
            if 'accounts.google.com' not in current_url and 'google.com/accounts' not in current_url:
                print("  ✓ Already redirected to form page (auto-login detected)")
                account_selected = True
            
            # Wait for redirect back to form page
            print("  Waiting for redirect after login...")
            try:
                page.wait_for_load_state('networkidle', timeout=15000)
            except:
                # If timeout, check if we're already on the form page
                if 'accounts.google.com' not in page.url.lower():
                    print("  ✓ Redirect completed (timeout but not on Google accounts page)")
            time.sleep(2)
            
            # Close any remaining popup windows
            if hasattr(self, 'context') and self.context:
                all_pages = self.context.pages
                for p in all_pages:
                    if p != page and not p.is_closed():
                        try:
                            # If popup is still open after 5 seconds, close it
                            if 'accounts.google.com' in p.url or 'google.com/accounts' in p.url:
                                p.close()
                                print("  ✓ Closed Google account selection popup")
                        except:
                            pass
            
            if account_selected or sso_button:
                print("  ✓ Social login handled successfully")
                self.logger.log_action(
                    action_type="social_login",
                    description="Handled social login (SSO)",
                    success=True
                )
                return True
            else:
                print("  ⚠ SSO button clicked but account selection unclear, proceeding anyway")
                return True  # Return True anyway since we clicked the button
                
        except Exception as e:
            print(f"  ⚠ Error in handle_social_login: {e}")
            # Don't fail the whole application if login detection fails
            return False
    
    def handle_custom_questions(self, page: Page) -> bool:
        """
        Handle custom dropdown questions (select elements) before submitting form.
        Selects appropriate options based on question type and content.
        
        Args:
            page: Playwright Page object
            
        Returns:
            bool: True if any questions were handled, False otherwise
        """
        if not page:
            return False
        
        print("  Handling custom dropdown questions...")
        handled_count = 0
        
        try:
            # Greenhouse Fix: Wait for dynamic content and scroll to force lazy-loaded fields
            print("  Waiting for dynamic content to load...")
            page.wait_for_timeout(3000)  # Wait 3 seconds for lazy-loaded fields
            
            # Scroll to bottom to force loading of all fields
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            time.sleep(1)
            
            # Scroll back to top
            page.evaluate('window.scrollTo(0, 0)')
            time.sleep(1)
            
            # Find all visible select elements
            select_elements = page.query_selector_all("select:visible")
            
            # Also find div[role='listbox'] elements (custom dropdowns)
            listbox_elements = page.query_selector_all("div[role='listbox']:visible")
            
            all_dropdowns = list(select_elements) + list(listbox_elements)
            
            if not all_dropdowns:
                print("  No dropdown questions found")
                return False
            
            print(f"  Found {len(all_dropdowns)} dropdown(s) to process")
            
            for dropdown in all_dropdowns:
                try:
                    # Skip if not visible
                    if not dropdown.is_visible():
                        continue
                    
                    # Get label text for context (for Yes/No questions)
                    label_text = ""
                    try:
                        # Try to find associated label
                        dropdown_id = dropdown.get_attribute('id')
                        if dropdown_id:
                            label = page.query_selector(f"label[for='{dropdown_id}']")
                            if label:
                                label_text = label.inner_text().lower()
                        
                        # If no label found by 'for', try to find nearby label
                        if not label_text:
                            # Get parent container and search for label
                            parent = dropdown.evaluate_handle('el => el.closest("div, form, fieldset")')
                            if parent:
                                # Try to find label in parent
                                nearby_labels = page.query_selector_all(f"label")
                                for lbl in nearby_labels:
                                    if lbl.is_visible():
                                        # Check if label is near the dropdown (same parent or adjacent)
                                        try:
                                            lbl_text = lbl.inner_text().lower()
                                            if lbl_text:
                                                label_text = lbl_text
                                                break
                                        except:
                                            continue
                    except Exception as e:
                        print(f"    ⚠ Could not get label text: {e}")
                    
                    # Check current value
                    current_value = ""
                    try:
                        # Fix: Use evaluate instead of tag_name() to avoid ElementHandle error
                        tag_name = dropdown.evaluate('el => el.tagName')
                        if tag_name.lower() == 'select':
                            current_value = dropdown.evaluate('el => el.value')
                        else:
                            # For custom dropdowns, try to get selected text
                            selected = dropdown.query_selector('[aria-selected="true"]')
                            if selected:
                                current_value = selected.inner_text().lower()
                    except:
                        pass
                    
                    # Skip if already has a value (not default/empty)
                    if current_value and current_value not in ['', '0', '-1', 'selecione', 'select', 'choose', 'escolha']:
                        print(f"    ✓ Dropdown already has value: '{current_value}'")
                        continue
                    
                    # Determine what to select based on label/question type
                    option_to_select = None
                    select_reason = ""
                    is_source_question = False
                    
                    # Source/Conheceu questions logic - prioritize LinkedIn
                    if any(term in label_text for term in ['source', 'conheceu', 'como ficou sabendo', 'onde viu', 'onde soube', 'referral', 'indicação']):
                        is_source_question = True
                        option_to_select = "LinkedIn"  # Priority for source questions
                        select_reason = "source question"
                    
                    # Yes/No questions logic
                    elif any(term in label_text for term in ['trabalha atualmente', 'trabalha na', 'vínculo', 'parente', 'familiar', 'conflito', 'conflict']):
                        option_to_select = "Não"
                        select_reason = "conflict of interest question"
                    elif any(term in label_text for term in ['autorização', 'legalmente', 'authorized', 'legally', 'permit']):
                        option_to_select = "Sim"
                        select_reason = "authorization question"
                    
                    # For select elements
                    # Fix: Use evaluate instead of tag_name() to avoid ElementHandle error
                    tag_name = dropdown.evaluate('el => el.tagName')
                    if tag_name.lower() == 'select':
                        options = dropdown.query_selector_all("option")
                        
                        if not options or len(options) <= 1:
                            print(f"    ⚠ Select has no valid options")
                            continue
                        
                        # Skip first option if it's a placeholder (index 0)
                        start_index = 1 if len(options) > 1 else 0
                        
                        selected_option = None
                        
                        # If we have a specific option to select (Yes/No)
                        if option_to_select:
                            for i in range(start_index, len(options)):
                                opt_text = options[i].inner_text().lower()
                                opt_value = options[i].get_attribute('value') or ""
                                
                                if option_to_select.lower() in opt_text or option_to_select.lower() in opt_value.lower():
                                    selected_option = options[i]
                                    break
                        
                        # If no specific option found, try to find source-related options
                        # For source questions, prioritize LinkedIn
                        if not selected_option:
                            if is_source_question:
                                # First try to find LinkedIn specifically
                                for i in range(start_index, len(options)):
                                    opt_text = options[i].inner_text().lower()
                                    opt_value = options[i].get_attribute('value') or ""
                                    
                                    if 'linkedin' in opt_text or 'linkedin' in opt_value.lower():
                                        selected_option = options[i]
                                        select_reason = "source question (LinkedIn)"
                                        break
                                
                                # If LinkedIn not found, try other source keywords
                                if not selected_option:
                                    source_keywords = ['indicação', 'glassdoor', 'indication', 'referral', 'outros', 'other']
                                    for i in range(start_index, len(options)):
                                        opt_text = options[i].inner_text().lower()
                                        opt_value = options[i].get_attribute('value') or ""
                                        
                                        if any(keyword in opt_text or keyword in opt_value.lower() for keyword in source_keywords):
                                            selected_option = options[i]
                                            select_reason = "source question (fallback)"
                                            break
                            else:
                                # For non-source questions, try generic source keywords
                                source_keywords = ['linkedin', 'indicação', 'glassdoor', 'indication', 'referral']
                                for i in range(start_index, len(options)):
                                    opt_text = options[i].inner_text().lower()
                                    opt_value = options[i].get_attribute('value') or ""
                                    
                                    if any(keyword in opt_text or keyword in opt_value.lower() for keyword in source_keywords):
                                        selected_option = options[i]
                                        select_reason = "source question"
                                        break
                        
                        # Fallback: select second option (index 1) if available
                        if not selected_option and len(options) > 1:
                            selected_option = options[1]
                            select_reason = "fallback to second option"
                        
                        # Select the option
                        if selected_option:
                            try:
                                opt_value = selected_option.get_attribute('value')
                                opt_text = selected_option.inner_text()
                                
                                # Use select_option for select elements
                                dropdown.select_option(value=opt_value if opt_value else opt_text)
                                
                                print(f"    ✓ Selected '{opt_text}' ({select_reason})")
                                handled_count += 1
                                time.sleep(0.3)
                            except Exception as e:
                                print(f"    ⚠ Failed to select option: {e}")
                    
                    # For custom dropdowns (div[role='listbox'])
                    else:
                        # First, try to find the trigger element (button/input that opens the dropdown)
                        trigger_element = None
                        try:
                            # Look for common trigger patterns near the listbox
                            parent = dropdown.evaluate_handle('el => el.parentElement')
                            if parent:
                                # Try to find button or input that might trigger the dropdown
                                trigger_selectors = [
                                    "button[aria-haspopup='listbox']",
                                    "input[role='combobox']",
                                    "button[aria-expanded]",
                                    ".dropdown-toggle",
                                    "[data-toggle='dropdown']"
                                ]
                                
                                for sel in trigger_selectors:
                                    try:
                                        trigger = page.query_selector(sel)
                                        if trigger and trigger.is_visible():
                                            trigger_element = trigger
                                            break
                                    except:
                                        continue
                        except:
                            pass
                        
                        # Try to find options within the listbox
                        options = dropdown.query_selector_all('[role="option"]')
                        
                        # If no options found and listbox might be closed, try to open it
                        if not options or len(options) == 0:
                            try:
                                # Click trigger if found, or click the listbox itself
                                if trigger_element:
                                    trigger_element.click()
                                    time.sleep(0.5)
                                else:
                                    dropdown.click()
                                    time.sleep(0.5)
                                
                                # Try to find options again after opening
                                options = dropdown.query_selector_all('[role="option"]')
                            except:
                                pass
                        
                        if not options:
                            # Try alternative selectors
                            options = dropdown.query_selector_all("div, li, span")
                            options = [opt for opt in options if opt.is_visible() and opt.inner_text().strip()]
                        
                        if not options or len(options) <= 1:
                            print(f"    ⚠ Custom dropdown has no valid options")
                            continue
                        
                        selected_option = None
                        
                        # If we have a specific option to select (Yes/No)
                        if option_to_select:
                            for opt in options:
                                try:
                                    opt_text = opt.inner_text().lower().strip()
                                    if opt_text and option_to_select.lower() in opt_text:
                                        selected_option = opt
                                        break
                                except:
                                    continue
                        
                        # If no specific option found, try to find source-related options
                        # For source questions, prioritize LinkedIn
                        if not selected_option:
                            if is_source_question:
                                # First try to find LinkedIn specifically
                                for opt in options:
                                    try:
                                        opt_text = opt.inner_text().lower().strip()
                                        if opt_text and 'linkedin' in opt_text:
                                            selected_option = opt
                                            select_reason = "source question (LinkedIn)"
                                            break
                                    except:
                                        continue
                                
                                # If LinkedIn not found, try other source keywords
                                if not selected_option:
                                    source_keywords = ['indicação', 'glassdoor', 'indication', 'referral', 'outros', 'other']
                                    for opt in options:
                                        try:
                                            opt_text = opt.inner_text().lower().strip()
                                            if opt_text and any(keyword in opt_text for keyword in source_keywords):
                                                selected_option = opt
                                                select_reason = "source question (fallback)"
                                                break
                                        except:
                                            continue
                            else:
                                # For non-source questions, try generic source keywords
                                source_keywords = ['linkedin', 'indicação', 'glassdoor', 'indication', 'referral']
                                for opt in options:
                                    try:
                                        opt_text = opt.inner_text().lower().strip()
                                        if opt_text and any(keyword in opt_text for keyword in source_keywords):
                                            selected_option = opt
                                            select_reason = "source question"
                                            break
                                    except:
                                        continue
                        
                        # Fallback: select second option if available
                        if not selected_option and len(options) > 1:
                            selected_option = options[1]
                            select_reason = "fallback to second option"
                        
                        # Click the option
                        if selected_option:
                            try:
                                # Make sure dropdown is open (click trigger or dropdown if needed)
                                if trigger_element:
                                    if not trigger_element.get_attribute('aria-expanded') == 'true':
                                        trigger_element.click()
                                        time.sleep(0.5)
                                else:
                                    # Try clicking the dropdown to ensure it's open
                                    dropdown.click()
                                    time.sleep(0.5)
                                
                                # Scroll option into view and click
                                selected_option.scroll_into_view_if_needed()
                                time.sleep(0.2)
                                selected_option.click()
                                
                                opt_text = selected_option.inner_text().strip()
                                print(f"    ✓ Selected '{opt_text}' ({select_reason})")
                                handled_count += 1
                                time.sleep(0.3)
                            except Exception as e:
                                print(f"    ⚠ Failed to select option in custom dropdown: {e}")
                
                except Exception as e:
                    print(f"    ⚠ Error processing dropdown: {e}")
                    continue
            
            if handled_count > 0:
                print(f"  ✓ Handled {handled_count} dropdown question(s)")
                return True
            else:
                print("  No dropdowns needed handling")
                return False
                
        except Exception as e:
            print(f"  ⚠ Error in handle_custom_questions: {e}")
            return False
    
    def find_and_click_submit(self) -> bool:
        """Find and click submit/apply button with robust self-healing"""
        print("Looking for submit/apply button...")
        
        # First, check for and close any modals/cookie banners
        self.check_for_modals()
        
        # HARDCODED FALLBACK: Try most common submit selectors immediately (before AI)
        hardcoded_submit_selectors = [
            "button[type='submit']",
            ".button-apply",
            "#submit-button",
            "[data-test*='submit']",
            "[data-test='submit-button']",  # Greenhouse
            "#submit_app",  # Lever
            ".submit-button"
        ]
        
        print("  Trying hardcoded submit selectors first...")
        for hc_selector in hardcoded_submit_selectors:
            try:
                element = self.page.query_selector(hc_selector)
                if element and element.is_visible():
                    element.scroll_into_view_if_needed()
                    time.sleep(0.5)
                    element.click()
                    print(f"  ✓ Successfully clicked submit using hardcoded selector: {hc_selector}")
                    time.sleep(2)
                    return True
            except:
                continue
        
        button_selectors = [
            # Greenhouse/Lever specific selectors (HIGHEST PRIORITY)
            "[data-test='submit-button']",  # Greenhouse
            "#submit_app",  # Lever
            ".submit-button",  # Generic but common
            # Standard HTML selectors
            "button[type='submit']",
            "input[type='submit']",
            # Text-based selectors
            "button:has-text('Apply')",
            "button:has-text('Aplicar')",
            "button:has-text('Submit')",
            "button:has-text('Enviar')",
            "button:has-text('Send')",
            "a:has-text('Apply')",
            "a:has-text('Aplicar')",
            # XPath selectors
            "//button[contains(text(), 'Apply')]",
            "//button[contains(text(), 'Aplicar')]",
            "//button[contains(text(), 'Submit')]",
            # Class-based selectors
            "button.submit",
            "button.apply",
            ".apply-button"
        ]
        
        result = self.find_element_with_fallback(button_selectors, timeout=5000, use_ai=False)
        if result:
            selector, element = result
            try:
                # Strategy 1: Scroll into view and normal click
                element.scroll_into_view_if_needed()
                time.sleep(0.5)
                
                # Check if element is actually visible
                if not element.is_visible():
                    print("  Element not visible, trying force click...")
                    element.click(force=True)
                else:
                    element.click()
                
                print(f"  Successfully clicked submit button using selector: {selector}")
                time.sleep(2)  # Wait for form submission
                return True
                
            except Exception as e:
                print(f"  Normal click failed: {e}, trying JavaScript click...")
                try:
                    # Strategy 2: JavaScript click (bypasses visibility checks)
                    self.page.evaluate(f"""
                        const btn = document.querySelector('{selector}');
                        if (btn) {{
                            btn.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                            btn.click();
                        }}
                    """)
                    print(f"  Successfully clicked submit button using JavaScript: {selector}")
                    time.sleep(2)
                    return True
                except Exception as js_error:
                    print(f"  JavaScript click also failed: {js_error}")
        
        # AI Fallback: Use Gemini to find submit button
        if self.page and self.brain:
            try:
                print("  Traditional methods failed, using AI to find submit button...")
                html_content = self.page.content()
                ai_selector = self.brain.find_submit_button(html_content)
                
                if ai_selector:
                    try:
                        element = self.page.wait_for_selector(ai_selector, timeout=3000, state='visible')
                        if element:
                            element.scroll_into_view_if_needed()
                            time.sleep(0.5)
                            element.click()
                            print(f"  ✓ Successfully clicked submit button using AI-suggested selector: {ai_selector}")
                            time.sleep(2)
                            return True
                    except Exception as e:
                        print(f"  AI-suggested selector '{ai_selector}' failed: {e}")
            except Exception as e:
                print(f"  AI fallback error: {e}")
        
        print("  ✗ WARNING: Could not find submit button")
        return False
    
    def check_success(self) -> Tuple[bool, str]:
        """Check if application was successful"""
        
        # PRIMEIRO: Verificar se há erros de validação na tela
        print("  Checking for validation errors...")
        error_indicators = [
            "required",
            "obrigatório",
            "campo obrigatório",
            "this field is required",
            "preencha este campo",
            "please fill",
            "invalid",
            "inválido",
            "error",
            "erro"
        ]
        
        # Procurar por elementos de erro visíveis
        error_selectors = [
            ".error",
            ".field-error",
            ".invalid",
            ".error-message",
            ".validation-error",
            "[class*='error']",
            "[class*='invalid']",
            "[aria-invalid='true']",
            ".required",
            "[class*='required']"
        ]
        
        # Verificar elementos de erro visíveis
        for selector in error_selectors:
            try:
                error_elements = self.page.query_selector_all(selector)
                for element in error_elements:
                    # Verificar se o elemento está visível
                    if element.is_visible():
                        error_text = element.inner_text().lower()
                        # Verificar se contém palavras-chave de erro
                        if any(indicator in error_text for indicator in error_indicators):
                            print(f"  ✗ Form validation failed: Found error element '{selector}' with text: '{error_text[:100]}'")
                            return (False, f"Form validation failed: {error_text[:100]}")
            except:
                continue
        
        # Verificar texto da página por erros
        page_text = self.page.content().lower()
        page_title = self.page.title().lower()
        
        # Verificar se há mensagens de erro comuns
        error_patterns = [
            r'required.*field',
            r'campo.*obrigatório',
            r'please.*fill',
            r'preencha.*campo',
            r'this.*required',
            r'invalid.*email',
            r'email.*invalid'
        ]
        
        import re
        for pattern in error_patterns:
            if re.search(pattern, page_text, re.IGNORECASE):
                print(f"  ✗ Form validation failed: Found error pattern '{pattern}' in page")
                return (False, f"Form validation failed: error pattern detected")
        
        # IMPROVED SUCCESS CHECK: Consider success if error disappeared and URL changed
        # Store initial state for comparison
        initial_url = getattr(self, '_initial_url', None)
        current_url = self.page.url.lower()
        
        # If URL changed significantly (not just query params), likely redirected after submit
        if initial_url and initial_url != current_url:
            # Check if we're no longer on the form page
            form_indicators = ['apply', 'application', 'candidatura', 'form', 'submit']
            was_form_page = any(ind in initial_url for ind in form_indicators)
            is_still_form = any(ind in current_url for ind in form_indicators)
            
            if was_form_page and not is_still_form:
                # URL changed from form page to different page = likely success
                print(f"  ✓ URL changed from form page (likely success): {initial_url[:50]} → {current_url[:50]}")
                return (True, f"URL changed after submission (likely success)")
        
        # Check if error elements disappeared (were present before, now gone)
        error_elements_present = False
        for selector in error_selectors:
            try:
                error_elements = self.page.query_selector_all(selector)
                for element in error_elements:
                    if element.is_visible():
                        error_elements_present = True
                        break
                if error_elements_present:
                    break
            except:
                continue
        
        # If no errors visible and URL changed, consider success
        if not error_elements_present and initial_url and current_url != initial_url:
            print(f"  ✓ No errors visible and URL changed (likely success)")
            return (True, "No errors visible and URL changed after submission")
        
        # Se não encontrou erros, verificar indicadores de sucesso
        success_indicators = [
            "success",
            "sucesso",
            "thank you",
            "obrigado",
            "application received",
            "candidatura recebida",
            "submitted",
            "enviado"
        ]
        
        for indicator in success_indicators:
            if indicator in page_text or indicator in page_title:
                return (True, f"Success indicator found: '{indicator}'")
        
        # Check URL for success indicators
        for indicator in success_indicators:
            if indicator in current_url:
                return (True, f"Success indicator in URL: '{indicator}'")
        
        return (False, "No success indicators found")
    
    def apply_to_job(self, job_url: str, job_title: str = "", company: str = "", match_score: float = 0.0, max_retries: int = 3) -> Dict[str, any]:
        """Main method to apply to a job with self-healing and logging"""
        if not self.page:
            self.start_browser(headless=False)
        
        # Store job info for logging
        self.current_job_info = {
            'url': job_url,
            'title': job_title or "Unknown",
            'company': company or "Unknown",
            'match_score': match_score
        }
        self.selectors_used = {}
        
        # Check previous attempts for this URL
        previous_logs = self.logger.get_logs_by_url(job_url)
        if previous_logs:
            last_attempt = previous_logs[-1]
            print(f"\n⚠ Previous attempt found: {last_attempt.get('status')} at {last_attempt.get('timestamp')}")
            if last_attempt.get('error_details'):
                print(f"  Last error: {last_attempt['error_details'].get('message', 'Unknown')}")
                if last_attempt.get('gemini_suggestion'):
                    print(f"  Gemini suggestion: {last_attempt['gemini_suggestion']}")
        
        result = {
            'success': False,
            'url': job_url,
            'job_title': job_title,
            'company': company,
            'errors': [],
            'steps_completed': [],
            'gemini_suggestion': None
        }
        
        try:
            print(f"\n{'='*60}")
            print(f"Applying to: {job_title} at {company}")
            print(f"URL: {job_url}")
            print(f"Match Score: {match_score:.2f}")
            print(f"{'='*60}\n")
            
            # Log action: starting application
            self.logger.log_action(
                action_type="application_start",
                description=f"Starting application to {job_title} at {company}",
                success=True
            )
            
            # SNIPER: Check if URL is direct Strider link (skip GitHub)
            if "app.onstrider.com/r/" in job_url:
                print("  🎯 Direct Strider link detected - navigating directly (skipping GitHub)...")
                self.page.goto(job_url, wait_until='domcontentloaded', timeout=60000)
                time.sleep(2)
                self._initial_url = self.page.url.lower()
                result['steps_completed'].append('direct_strider_navigation')
            else:
                # Navigate to job page
                print("Step 1: Navigating to job page...")
                self.logger.log_action("navigation", "Navigating to job page", success=True)
                # Usar 'domcontentloaded' em vez de 'networkidle' para acelerar (não espera trackers/anúncios)
                self.page.goto(job_url, wait_until='domcontentloaded', timeout=60000)
                time.sleep(2)
                # Store initial URL for success checking
                self._initial_url = self.page.url.lower()
                result['steps_completed'].append('navigation')
            
            # LINK HUNTER: Se estiver em uma página do GitHub, procurar links externos
            # (Skip if we already navigated to Strider directly)
            if "github.com" in self.page.url and "/issues/" in self.page.url and "app.onstrider.com" not in job_url:
                print("  ℹ Detected GitHub Issue. Hunting for external apply link...")
                try:
                    # Tentar pegar o corpo da issue (vários seletores possíveis)
                    issue_body_selectors = [
                        ".comment-body",
                        ".markdown-body",
                        "[itemprop='text']",
                        ".js-comment-body",
                        ".comment-body.markdown-body"
                    ]
                    
                    issue_body = None
                    for selector in issue_body_selectors:
                        try:
                            issue_body = self.page.locator(selector).first
                            if issue_body.count() > 0:
                                break
                        except:
                            continue
                    
                    if issue_body and issue_body.count() > 0:
                        # Procurar links comuns de aplicação
                        links = issue_body.locator("a").all()
                        external_link_found = None
                        
                        for link in links:
                            try:
                                href = link.get_attribute("href")
                                if href:
                                    href_lower = href.lower()
                                    # Procurar por links de aplicação comuns
                                    apply_keywords = ['bit.ly', 'gupy.io', 'greenhouse', 'lever', 'apply', 'inscreva', 'candidatar', 'vagas', 'jobs', 'careers']
                                    if any(keyword in href_lower for keyword in apply_keywords):
                                        # Verificar se é link absoluto ou relativo
                                        if href.startswith('http'):
                                            external_link_found = href
                                        elif href.startswith('/'):
                                            # Link relativo do GitHub, pular
                                            continue
                                        else:
                                            # Link relativo, construir URL completa
                                            external_link_found = href
                                        
                                        print(f"  ✓ Found external apply link: {external_link_found}")
                                        print(f"  → Navigating to external application page...")
                                        
                                        # Navegar para o link externo
                                        self.page.goto(external_link_found, wait_until='domcontentloaded', timeout=60000)
                                        time.sleep(2)
                                        result['steps_completed'].append('github_link_hunt')
                                        break
                            except Exception as e:
                                continue
                        
                        if not external_link_found:
                            # GitHub Issue Email Extraction: Look for email in issue body
                            print("  ⚠ No external apply link found. Searching for email in issue body...")
                            try:
                                issue_text = issue_body.inner_text()
                                # Extract email using regex
                                import re
                                email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                                emails_found = re.findall(email_pattern, issue_text)
                                
                                if emails_found:
                                    # Filter out common non-contact emails
                                    valid_emails = [e for e in emails_found if not any(skip in e.lower() 
                                                   for skip in ['noreply', 'no-reply', 'github', 'notification'])]
                                    
                                    if valid_emails:
                                        contact_email = valid_emails[0]
                                        print(f"  ✉️ Found email in GitHub issue: {contact_email}")
                                        print(f"  → Aborting browser automation, using emailer.py instead...")
                                        
                                        # Return special result to trigger email sending
                                        result['github_email_found'] = contact_email
                                        result['steps_completed'].append('github_email_extracted')
                                        return result  # Exit early, main.py will handle email
                            except Exception as email_error:
                                print(f"  ⚠ Error extracting email: {email_error}")
                            
                            print("  ⚠ No email found. Continuing with GitHub page...")
                    else:
                        print("  ⚠ Could not find issue body. Continuing with GitHub page...")
                except Exception as e:
                    print(f"  ⚠ Error hunting for external link: {e}. Continuing with GitHub page...")
            
            # Check visa eligibility BEFORE proceeding
            print("Step 1.5: Checking visa/work authorization requirements...")
            is_eligible, reason = self.check_visa_eligibility()
            if not is_eligible:
                error_msg = f"Visa/work authorization incompatibility: {reason}"
                result['errors'].append(error_msg)
                result['status'] = 'visa_incompatible'
                print(f"  ✗ {error_msg}")
                
                # Log as incompatible
                screenshot_path = None
                try:
                    screenshot_bytes = self.page.screenshot()
                    screenshot_path = self.logger.save_screenshot(screenshot_bytes, datetime.now().isoformat())
                except:
                    pass
                
                self.current_log_id = self.logger.log_application(
                    job_title=job_title or "Unknown",
                    company=company or "Unknown",
                    url=job_url,
                    match_score=match_score,
                    status=ApplicationStatus.FAILED,
                    error_details={
                        'type': 'visa_incompatibility',
                        'message': reason,
                        'errors': [error_msg]
                    },
                    gemini_suggestion="Job requires work authorization outside LATAM. Skip this application.",
                    steps_completed=result['steps_completed'],
                    selectors_used={},
                    screenshot_path=screenshot_path
                )
                
                return result
            
            print("  ✓ No visa restrictions detected, proceeding...")
            
            # Check if this is an ATS system and use specific driver
            ats_driver = get_ats_driver(self.page, job_url, self.user_data, str(self.resume_path))
            
            if ats_driver:
                print(f"  Detected ATS system, using specialized driver...")
                ats_success, ats_errors = ats_driver.apply()
                
                if ats_success:
                    result['success'] = True
                    result['steps_completed'].extend(['ats_form_filled', 'ats_submitted'])
                    result['message'] = "Application submitted via ATS driver"
                    print(f"\n✓ SUCCESS: Application submitted via ATS driver")
                    
                    # Log successful application
                    self.current_log_id = self.logger.log_application(
                        job_title=job_title or "Unknown",
                        company=company or "Unknown",
                        url=job_url,
                        match_score=match_score,
                        status=ApplicationStatus.SUCCESS,
                        steps_completed=result['steps_completed'],
                        selectors_used=self.selectors_used
                    )
                    return result
                else:
                    result['errors'].extend(ats_errors)
                    print(f"  ATS driver encountered errors: {ats_errors}")
                    # Continue with standard flow as fallback
            
            # Try to find and click "Apply" button if needed
            apply_link_selectors = [
                "a:has-text('Apply')",
                "a:has-text('Aplicar')",
                "button:has-text('Apply Now')",
                "button:has-text('Apply for this job')",
                ".apply-button",
                "#apply-button"
            ]
            
            apply_result = self.find_element_with_fallback(apply_link_selectors, timeout=5000, use_ai=False)
            if apply_result:
                selector, element = apply_result
                print(f"Found apply link, clicking...")
                
                # Suporte para nova aba: esperar possível nova aba após clicar
                try:
                    # Tentar esperar por nova aba (Playwright sync API)
                    if self.context:
                        with self.context.expect_page(timeout=5000) as new_page_info:
                            element.click()
                        # Se abriu nova aba, muda o foco para ela
                        try:
                            new_page = new_page_info.value
                            new_page.wait_for_load_state('domcontentloaded', timeout=10000)
                            
                            # Close old pages to avoid tab clutter (Silent Mode)
                            if self.context and hasattr(self.context, 'pages'):
                                old_pages = [p for p in self.context.pages if p != new_page]
                                for old_page in old_pages:
                                    try:
                                        if not old_page.is_closed():
                                            old_page.close()
                                            print(f"  ✓ Closed old tab (silent mode)")
                                    except:
                                        pass
                            
                            self.page = new_page  # Atualiza a referência
                            # Reaplica stealth na nova aba
                            if STEALTH_AVAILABLE and stealth_sync:
                                try:
                                    stealth_sync(self.page)
                                    print("  ✓ Stealth reaplicado na nova aba")
                                except:
                                    pass
                            print("  ✓ Nova aba aberta, foco mudado")
                            result['steps_completed'].append('apply_link_clicked_new_tab')
                        except Exception as tab_error:
                            print(f"  ⚠ Erro ao mudar para nova aba: {tab_error}, continuando na mesma aba")
                            time.sleep(3)  # Wait for form to load
                            result['steps_completed'].append('apply_link_clicked')
                    else:
                        # Se não tem context, comportamento normal
                        element.click()
                        time.sleep(3)
                        result['steps_completed'].append('apply_link_clicked')
                except Exception as e:
                    # Se não abriu nova aba ou erro, comportamento normal
                    element.click()
                    time.sleep(3)  # Wait for form to load
                    result['steps_completed'].append('apply_link_clicked')
            
            # Handle social login (SSO) if required
            print("\nStep 1.5: Checking for social login (SSO)...")
            self.logger.log_action("social_login_check", "Checking for social login requirement", success=True)
            if self.handle_social_login(self.page):
                result['steps_completed'].append('social_login_handled')
                # Wait a bit more for form to load after login
                time.sleep(2)
            
            # Fill form fields
            print("\nStep 2: Filling form fields...")
            self.logger.log_action("form_filling", "Starting form field filling", success=True)
            
            if 'name' in self.user_data:
                if self.fill_field('name', self.user_data['name']):
                    result['steps_completed'].append('name_filled')
            
            if 'email' in self.user_data:
                if self.fill_field('email', self.user_data['email']):
                    result['steps_completed'].append('email_filled')
            
            if 'phone' in self.user_data:
                if self.fill_field('phone', self.user_data['phone']):
                    result['steps_completed'].append('phone_filled')
            
            if 'linkedin' in self.user_data:
                if self.fill_field('linkedin', self.user_data['linkedin']):
                    result['steps_completed'].append('linkedin_filled')
            
            # Upload resume
            print("\nStep 3: Uploading resume...")
            self.logger.log_action("resume_upload", "Attempting to upload resume", success=True)
            if self.upload_resume():
                result['steps_completed'].append('resume_uploaded')
            else:
                result['errors'].append("Failed to upload resume")
            
            # Handle custom dropdown questions before submitting
            print("\nStep 3.5: Handling custom dropdown questions...")
            self.logger.log_action("custom_questions", "Handling custom dropdown questions", success=True)
            if self.handle_custom_questions(self.page):
                result['steps_completed'].append('custom_questions_handled')
            
            # Submit form
            print("\nStep 4: Submitting application...")
            self.logger.log_action("form_submit", "Attempting to submit form", success=True)
            if self.find_and_click_submit():
                result['steps_completed'].append('form_submitted')
            else:
                result['errors'].append("Failed to submit form")
            
            # Check for success
            print("\nStep 5: Checking for success...")
            time.sleep(3)  # Wait for redirect/confirmation
            success, message = self.check_success()
            
            if success:
                result['success'] = True
                result['message'] = message
                print(f"\n✓ SUCCESS: {message}")
                
                # Log successful application
                self.current_log_id = self.logger.log_application(
                    job_title=job_title or "Unknown",
                    company=company or "Unknown",
                    url=job_url,
                    match_score=match_score,
                    status=ApplicationStatus.SUCCESS,
                    steps_completed=result['steps_completed'],
                    selectors_used=self.selectors_used
                )
            else:
                result['errors'].append(f"Application status unclear: {message}")
                print(f"\n⚠ WARNING: {message}")
                
                # Log as failed with screenshot
                screenshot_path = None
                try:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_bytes = self.page.screenshot(full_page=True)
                    screenshot_path = self.logger.save_screenshot(screenshot_bytes, timestamp)
                    print(f"  Screenshot saved: {screenshot_path}")
                except Exception as e:
                    print(f"  Could not save screenshot: {e}")
                
                # Try to get AI suggestion for the error
                gemini_suggestion = None
                try:
                    html_content = self.page.content()[:3000]
                    # Ask Gemini what might be wrong
                    gemini_suggestion = "Application status unclear - manual review needed"
                except:
                    pass
                
                self.current_log_id = self.logger.log_application(
                    job_title=job_title or "Unknown",
                    company=company or "Unknown",
                    url=job_url,
                    match_score=match_score,
                    status=ApplicationStatus.FAILED,
                    error_details={
                        'type': 'status_unclear',
                        'message': message,
                        'errors': result['errors']
                    },
                    gemini_suggestion=gemini_suggestion,
                    steps_completed=result['steps_completed'],
                    selectors_used=self.selectors_used,
                    screenshot_path=screenshot_path
                )
            
        except Exception as e:
            error_msg = f"Error during application: {str(e)}"
            result['errors'].append(error_msg)
            print(f"\n✗ ERROR: {error_msg}")
            
            # Capture screenshot on error (ALWAYS)
            screenshot_path = None
            try:
                if self.page:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_bytes = self.page.screenshot(full_page=True)
                    screenshot_path = self.logger.save_screenshot(screenshot_bytes, timestamp)
                    print(f"  Screenshot saved: {screenshot_path}")
            except Exception as screenshot_error:
                print(f"  Could not save screenshot: {screenshot_error}")
            
            # Try to capture page HTML for debugging
            html_snippet = None
            try:
                if self.page:
                    html_snippet = self.page.content()[:2000]
            except:
                pass
            
            # Get AI suggestion for the error
            gemini_suggestion = None
            if html_snippet and self.brain:
                try:
                    # Analyze the error with Gemini
                    error_analysis = f"Error: {error_msg}. HTML snippet available for analysis."
                    gemini_suggestion = "Error occurred - check screenshot and HTML for details"
                except:
                    pass
            
            # Log failed application
            self.current_log_id = self.logger.log_application(
                job_title=job_title or "Unknown",
                company=company or "Unknown",
                url=job_url,
                match_score=match_score,
                status=ApplicationStatus.FAILED,
                error_details={
                    'type': 'exception',
                    'message': str(e),
                    'errors': result['errors'],
                    'html_snippet': html_snippet[:500] if html_snippet else None
                },
                gemini_suggestion=gemini_suggestion,
                steps_completed=result['steps_completed'],
                selectors_used=self.selectors_used,
                screenshot_path=screenshot_path
            )
            
            # Log the error action
            self.logger.log_action(
                action_type="error",
                description=error_msg,
                success=False,
                error=str(e),
                html_snippet=html_snippet[:500] if html_snippet else None
            )
        
        return result


if __name__ == "__main__":
    # Test the applier
    user_data = {
        'name': 'Test User',
        'email': 'test@example.com',
        'phone': '+55 11 99999-9999',
        'linkedin': 'https://linkedin.com/in/testuser'
    }
    
    applier = SelfHealingApplier('curriculo.pdf', user_data)
    applier.start_browser(headless=False)
    
    # Test with a sample job URL (replace with real URL)
    # result = applier.apply_to_job("https://example.com/job")
    # print(result)
    
    applier.close_browser()

