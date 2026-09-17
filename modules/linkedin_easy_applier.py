"""
LinkedIn Easy Apply Automation Module
Automates LinkedIn Easy Apply job applications with self-healing AI-powered form filling
"""
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
from typing import Dict, List, Optional, Tuple
import re
import time
import os
from pathlib import Path
from .brain import AIBrain
from .session_manager import SessionManager
from datetime import datetime


class LinkedInEasyApplier:
    """Automated LinkedIn Easy Apply with AI-powered self-healing"""
    
    def __init__(self, resume_path: str, user_data: Dict[str, str]):
        self.resume_path = Path(resume_path)
        self.user_data = user_data  # {name, email, linkedin, phone, etc.}
        self.page: Optional[Page] = None
        self.context = None
        self.playwright = None
        self.brain = AIBrain()
        self.auto_submit = False  # Flag para auto-submit (será setado via --auto-submit)
        
    def start_browser(self, headless: bool = False):
        """
        Start browser with persistent Chrome context
        FORÇA headless=False para evitar detecção e permitir resolução manual de Challenge
        """
        # FORÇA headless=False para vencer Challenge do LinkedIn
        headless = False
        from .session_manager import SessionManager
        session_manager = SessionManager()
        
        context_args = session_manager.get_context_args("chrome")
        
        if not context_args.get('can_use_real_session'):
            print("  ⚠ Cannot use real Chrome session. LinkedIn Easy Apply requires login.")
            return False
        
        self.playwright = sync_playwright().start()
        user_data_dir = context_args['user_data_dir']
        
        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=headless,
                channel="chrome" if session_manager.find_chrome_profile() else None,
                args=['--disable-blink-features=AutomationControlled'],
                viewport={'width': 1920, 'height': 1080}
            )
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            
            print("  ✓ LinkedIn Easy Apply browser started with logged-in profile")
            print("  ✓ Modo Interativo: Navegador visível (headless=False) para resolução manual de Challenge/2FA")
            return True
        except Exception as e:
            print(f"  ✗ Error starting browser: {e}")
            return False
    
    def close_browser(self):
        """Close browser"""
        if self.page:
            try:
                self.page.close()
            except:
                pass
        if self.context:
            try:
                self.context.close()
            except:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except:
                pass
    
    def is_logged_in(self) -> bool:
        """Check if user is logged in to LinkedIn by checking navigation bar"""
        if not self.page:
            return False
        
        try:
            # Check for navigation bar indicator
            nav_check = self.page.query_selector('[data-global-nav-check]')
            if nav_check:
                return True
            
            # Fallback: Check for feed elements
            feed_indicators = [
                'article[class*="feed-shared-update"]',
                '.feed-shared-update-v2',
                '[data-test-id="feed-shared-update"]'
            ]
            
            for indicator in feed_indicators:
                element = self.page.query_selector(indicator)
                if element:
                    return True
            
            # Check URL - if still on login page, not logged in
            current_url = self.page.url.lower()
            if 'login' in current_url or 'signin' in current_url:
                return False
            
            return False
        except:
            return False
    
    def detect_login_wall(self) -> bool:
        """
        Detect if login wall/modal is present
        Checks for .base-search-card or .authwall-base-card
        
        Returns:
            bool: True if login wall is detected
        """
        if not self.page:
            return False
        
        try:
            # Check for login wall modal
            login_wall_selectors = [
                '.authwall-base-card',
                '.base-search-card',
                '[class*="authwall"]',
                '[class*="login-wall"]'
            ]
            
            for selector in login_wall_selectors:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        return True
                except:
                    continue
            
            # Check for "Sign in" buttons that indicate login required
            sign_in_buttons = self.page.query_selector_all(
                'button:has-text("Sign in"), a:has-text("Sign in"), '
                'button:has-text("Entrar"), a:has-text("Entrar"), '
                'button:has-text("Sign in with Email")'
            )
            
            for btn in sign_in_buttons:
                if btn and btn.is_visible():
                    return True
            
            return False
        except:
            return False
    
    def handle_login_wall(self) -> bool:
        """
        Handle login wall by clicking "Sign in with Email" and performing login
        
        Returns:
            bool: True if login was successful
        """
        if not self.page:
            return False
        
        try:
            print("  ✓ Detected login wall. Initiating automatic login...")
            
            # Find and click "Sign in with Email" button
            sign_in_email_selectors = [
                'button:has-text("Sign in with Email")',
                'a:has-text("Sign in with Email")',
                'button:has-text("Entrar com Email")',
                'a:has-text("Entrar com Email")',
                '[data-test-id="sign-in-with-email"]'
            ]
            
            sign_in_clicked = False
            for selector in sign_in_email_selectors:
                try:
                    btn = self.page.query_selector(selector)
                    if btn and btn.is_visible():
                        btn.click()
                        print(f"  ✓ Clicked 'Sign in with Email' using: {selector}")
                        sign_in_clicked = True
                        self.page.wait_for_timeout(2000)
                        break
                except:
                    continue
            
            if not sign_in_clicked:
                # Try to find any sign in button
                sign_in_btn = self.page.query_selector(
                    'button:has-text("Sign in"), a:has-text("Sign in"), '
                    'button:has-text("Entrar"), a:has-text("Entrar")'
                )
                if sign_in_btn and sign_in_btn.is_visible():
                    sign_in_btn.click()
                    print("  ✓ Clicked generic sign in button")
                    self.page.wait_for_timeout(2000)
            
            # Now perform login
            return self.login_linkedin()
            
        except Exception as e:
            print(f"  ✗ Error handling login wall: {e}")
            return False
    
    def login_linkedin(self) -> bool:
        """
        Perform automatic login to LinkedIn using credentials from .env
        Reuses logic from linkedin_post_searcher.py
        
        Returns:
            bool: True if login was successful
        """
        if not self.page:
            return False
        
        # Get credentials from environment variables
        linkedin_email = os.getenv('LINKEDIN_EMAIL')
        linkedin_password = os.getenv('LINKEDIN_PASSWORD')
        
        if not linkedin_email or not linkedin_password:
            print("  ⚠ LinkedIn credentials not found in .env")
            print("  → Please add LINKEDIN_EMAIL and LINKEDIN_PASSWORD to your .env file")
            return False
        
        try:
            # Navigate to LinkedIn login page if not already there
            current_url = self.page.url.lower()
            if 'login' not in current_url and 'signin' not in current_url:
                self.page.goto("https://www.linkedin.com/login", wait_until='domcontentloaded', timeout=60000)
                time.sleep(2)
            
            # Find and fill email field
            email_selectors = [
                "input[id='username']",
                "input[name='session_key']",
                "input[type='email']",
                "input[placeholder*='Email']",
                "input[placeholder*='E-mail']"
            ]
            
            email_filled = False
            for selector in email_selectors:
                try:
                    email_field = self.page.query_selector(selector)
                    if email_field and email_field.is_visible():
                        email_field.click()
                        email_field.fill('')
                        email_field.fill(linkedin_email)
                        email_filled = True
                        print(f"  ✓ Email filled using: {selector}")
                        break
                except:
                    continue
            
            if not email_filled:
                print("  ✗ Could not find email field")
                return False
            
            time.sleep(1)
            
            # Find and fill password field
            password_selectors = [
                "input[id='password']",
                "input[name='session_password']",
                "input[type='password']",
                "input[placeholder*='Password']",
                "input[placeholder*='Senha']"
            ]
            
            password_filled = False
            for selector in password_selectors:
                try:
                    password_field = self.page.query_selector(selector)
                    if password_field and password_field.is_visible():
                        password_field.click()
                        password_field.fill('')
                        password_field.fill(linkedin_password)
                        password_filled = True
                        print(f"  ✓ Password filled using: {selector}")
                        break
                except:
                    continue
            
            if not password_filled:
                print("  ✗ Could not find password field")
                return False
            
            time.sleep(1)
            
            # Find and click sign in button
            sign_in_selectors = [
                "button[type='submit']",
                "button:has-text('Sign in')",
                "button:has-text('Entrar')",
                "input[type='submit'][value*='Sign']",
                "input[type='submit'][value*='Entrar']"
            ]
            
            sign_in_clicked = False
            for selector in sign_in_selectors:
                try:
                    sign_in_button = self.page.query_selector(selector)
                    if sign_in_button and sign_in_button.is_visible():
                        sign_in_button.click()
                        sign_in_clicked = True
                        print(f"  ✓ Sign in button clicked using: {selector}")
                        break
                except:
                    continue
            
            if not sign_in_clicked:
                print("  ✗ Could not find sign in button")
                return False
            
            # Wait for navigation/response
            time.sleep(5)
            
            # DETECÇÃO DE CHALLENGE/CAPTCHA: LinkedIn pode pedir validação humana
            if self._detect_challenge():
                print("\n" + "="*60)
                print("  ⚠ LinkedIn Challenge/Captcha detectado!")
                print("  → MODO INTERATIVO: O script está pausado para você resolver manualmente.")
                print("  → Se aparecer imagens para selecionar ou bonequinho para girar, faça isso agora na janela do navegador.")
                print("  → Após resolver o desafio, volte aqui e pressione ENTER para continuar...")
                print("="*60)
                input("\n  👤 Resolva o Captcha/Challenge no navegador e pressione ENTER aqui para continuar... ")
                print("  ✓ Continuando após resolução manual...")
            
            # Check for 2FA challenge and handle it
            if self._handle_2fa():
                return True
            
            # Check if login was successful
            if self.is_logged_in():
                print("  ✓ Login bem-sucedido!")
                return True
            else:
                print("  ⚠ Login pode ter falhado. Verifique as credenciais.")
                return False
                
        except Exception as e:
            print(f"  ✗ Error during login: {e}")
            return False
    
    def _detect_challenge(self) -> bool:
        """
        Detect if LinkedIn is showing a Challenge/Captcha that requires human interaction
        
        Returns:
            bool: True if challenge/captcha is detected
        """
        if not self.page:
            return False
        
        try:
            current_url = self.page.url.lower()
            page_text = self.page.content().lower()
            page_visible_text = self.page.inner_text('body').lower()
            
            # Indicadores de Challenge/Captcha do LinkedIn
            challenge_indicators = [
                'challenge',
                'captcha',
                'verify you\'re human',
                'prove you\'re human',
                'security check',
                'unusual activity',
                'select all images',
                'rotate the image',
                'click on all',
                'verify your identity',
                'verifique sua identidade',
                'atividade incomum'
            ]
            
            # Verificar se algum indicador está presente
            for indicator in challenge_indicators:
                if indicator in page_text or indicator in page_visible_text or indicator in current_url:
                    return True
            
            # Verificar seletores específicos de Challenge
            challenge_selectors = [
                '[data-test-id="challenge"]',
                '.challenge-container',
                '#challenge',
                '[aria-label*="challenge"]',
                '[aria-label*="captcha"]',
                'img[alt*="captcha"]',
                'img[alt*="challenge"]'
            ]
            
            for selector in challenge_selectors:
                try:
                    challenge_elem = self.page.query_selector(selector)
                    if challenge_elem and challenge_elem.is_visible():
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            # Em caso de erro, assumir que não há challenge (não bloquear o fluxo)
            return False
    
    def _handle_2fa(self) -> bool:
        """
        Handle 2FA (Two-Factor Authentication) challenge
        Reuses 60-second wait logic from Sniper Mode
        
        Returns:
            bool: True if 2FA was approved and login successful
        """
        if not self.page:
            return False
        
        try:
            current_url = self.page.url.lower()
            page_text = self.page.content().lower()
            
            two_fa_indicators = [
                'verify',
                'verification',
                'two-factor',
                'two factor',
                '2fa',
                'verificação',
                'código',
                'code',
                'authenticator',
                'security check'
            ]
            
            if any(indicator in current_url or indicator in page_text for indicator in two_fa_indicators):
                print("\n" + "="*60)
                print("  ⚠ 2FA (Verificação em duas etapas) detectado!")
                print("  → MODO INTERATIVO: O script está pausado para você aprovar o 2FA.")
                print("  → Por favor, aprove o acesso no seu celular/aplicativo autenticador.")
                print("  → Após aprovar o 2FA, volte aqui e pressione ENTER para continuar...")
                print("="*60)
                input("\n  👤 Aprove o 2FA no celular e pressione ENTER aqui para continuar... ")
                
                # Verificar se login foi bem-sucedido após input
                if self.is_logged_in():
                    print("  ✓ 2FA aprovado! Sessão ativa.")
                    return True
                else:
                    print("  ⚠ 2FA pode não ter sido aprovado. Verificando novamente...")
                    # Aguardar mais um pouco e verificar novamente
                    time.sleep(3)
                    if self.is_logged_in():
                        print("  ✓ 2FA aprovado! Sessão ativa.")
                        return True
                    print("  ⚠ Login não confirmado após 2FA. Continuando...")
                    return False
            
            return False
        except:
            return False
    
    def validate_session(self) -> bool:
        """
        Validate session by checking linkedin.com/feed for navigation bar
        If not logged in, force login
        
        Returns:
            bool: True if session is valid
        """
        if not self.page:
            return False
        
        try:
            print("  🔍 Validating session...")
            
            # Try to navigate to feed with multiple strategies
            session_valid = False
            
            # Strategy 1: Try with shorter timeout and load event
            try:
                self.page.goto("https://www.linkedin.com/feed", wait_until='load', timeout=30000)
                self.page.wait_for_timeout(2000)
                session_valid = True
            except Exception as e1:
                print(f"  ⚠ First attempt failed: {str(e1)[:100]}...")
                # Strategy 2: Try with commit (faster, doesn't wait for all resources)
                try:
                    self.page.goto("https://www.linkedin.com/feed", wait_until='commit', timeout=15000)
                    self.page.wait_for_timeout(2000)
                    session_valid = True
                except Exception as e2:
                    print(f"  ⚠ Second attempt failed: {str(e2)[:100]}...")
                    # Strategy 3: Check current URL - if already on LinkedIn, assume valid
                    current_url = self.page.url
                    if 'linkedin.com' in current_url.lower():
                        print("  ⚠ Already on LinkedIn. Assuming session is valid.")
                        session_valid = True
                    else:
                        print("  ⚠ Could not navigate to feed. Will try to proceed anyway...")
                        # Since we're using persistent session, assume it's valid
                        return True
            
            if session_valid:
                # Check for navigation bar indicator
                try:
                    nav_check = self.page.wait_for_selector('[data-global-nav-check]', timeout=5000, state='attached')
                    if nav_check:
                        print("  ✓ Session valid. Navigation bar detected.")
                        return True
                except:
                    pass
                
                # Check for login wall
                if self.detect_login_wall():
                    print("  ⚠ Login wall detected. Attempting login...")
                    return self.handle_login_wall()
                
                # Check URL - if we're on feed, assume valid
                if 'feed' in self.page.url.lower() or 'linkedin.com' in self.page.url.lower():
                    print("  ✓ Session appears valid (on LinkedIn domain).")
                    return True
            
            # If all checks fail but we have a persistent session, assume valid
            print("  ⚠ Could not fully validate session, but using persistent Chrome session - assuming valid.")
            return True
                
        except Exception as e:
            print(f"  ⚠ Error validating session: {str(e)[:100]}...")
            print("  ⚠ Will proceed anyway since we're using persistent Chrome session.")
            # Since we're using persistent Chrome session, assume it's valid
            return True
    
    def scout_easy_apply_jobs(self, location: str = "Brazil", keywords: List[str] = None, max_jobs_per_tech: int = 25):
        """
        Scout Mode: Varrer lista de vagas e identificar quais são Easy Apply
        Usa a lista lateral esquerda (.scaffold-layout__list-container) para identificar vagas
        
        Args:
            location: Job location filter
            keywords: List of technologies to search for
            max_jobs_per_tech: Maximum jobs to process per technology
            
        Returns:
            List[Dict]: List of Easy Apply jobs found
        """
        if not self.page:
            print("  ✗ Browser not started. Call start_browser() first.")
            return []
        
        # FASE 1: Validação de Sessão (Reforço de Cookies)
        print("\n  🔐 [FASE 1] Validating session...")
        session_valid = self.validate_session()
        if not session_valid:
            print("  ⚠ Session validation had issues, but proceeding with persistent Chrome session...")
            # Don't return empty - try to proceed anyway since we have persistent session
        
        if not keywords:
            keywords = ["Python", "React", "Node.js"]
        
        all_easy_apply_jobs = []
        
        for tech in keywords:
            try:
                print(f"\n  🔍 Searching for: \"{tech}\" (Exact Match Mode)")
                
                # Build LinkedIn job search URL with Easy Apply filter and exact match
                # f_AL=true enables Easy Apply filter, sortBy=DD for latest
                # %22 = aspas duplas escapadas para busca exata
                location_encoded = location.replace(" ", "%20")
                tech_encoded = f"%22{tech.replace(' ', '%20')}%22"  # Envolver em aspas duplas para exact match
                
                search_url = f"https://www.linkedin.com/jobs/search/?f_AL=true&keywords={tech_encoded}&location={location_encoded}&sortBy=DD"
                
                print(f"     URL: {search_url}")
                
                self.page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
                self.page.wait_for_timeout(3000)  # Wait for page to load
                
                # Detector de Modal de Login: Verificar se apareceu login wall
                if self.detect_login_wall():
                    print("  ⚠ Login wall detected on job search page. Handling...")
                    if not self.handle_login_wall():
                        print("  ✗ Failed to handle login wall. Skipping this search.")
                        continue
                    # Reload page after login
                    self.page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
                    self.page.wait_for_timeout(3000)
                
                # Verify Easy Apply filter is active
                try:
                    easy_apply_indicator = self.page.query_selector('button[aria-label*="Easy Apply"], button:has-text("Easy Apply"), button:has-text("Candidatura simplificada")')
                    if easy_apply_indicator:
                        print("  ✓ Easy Apply filter is active")
                except:
                    print("  ⚠ Could not verify Easy Apply filter")
                
                # Scout jobs from left sidebar list
                easy_apply_jobs = self._scout_sidebar_jobs(max_jobs_per_tech)
                
                print(f"  ✓ Found {len(easy_apply_jobs)} Easy Apply jobs for {tech}")
                all_easy_apply_jobs.extend(easy_apply_jobs)
                
                # Small delay between technologies
                time.sleep(2)
                
            except Exception as e:
                print(f"  ✗ Error scouting jobs for {tech}: {e}")
                continue
        
        print(f"\n  ✓ Total Easy Apply jobs found: {len(all_easy_apply_jobs)}")
        return all_easy_apply_jobs
    
    def _scout_sidebar_jobs(self, max_jobs: int = 25) -> List[Dict]:
        """
        Scout jobs from left sidebar list with resilient selectors
        Uses multiple fallback selectors to handle LinkedIn layout variations
        
        Args:
            max_jobs: Maximum jobs to process
            
        Returns:
            List[Dict]: List of Easy Apply jobs with job_id, title, company, location, url
        """
        easy_apply_jobs = []
        
        try:
            # Wait a bit for page to fully load
            self.page.wait_for_timeout(2000)
            
            # Check for "No jobs found" message before attempting to find container
            no_jobs_indicators = [
                'text="No jobs found"',
                'text="Nenhuma vaga encontrada"',
                'text="No se encontraron trabajos"',
                '.jobs-search-no-results',
                '[class*="no-results"]',
                '[class*="empty-state"]'
            ]
            
            for indicator in no_jobs_indicators:
                try:
                    no_jobs_elem = self.page.query_selector(indicator)
                    if no_jobs_elem and no_jobs_elem.is_visible():
                        print("  ⚠ No jobs found for this search. Skipping...")
                        return []
                except:
                    continue
            
            # SELETORES ALTERNATIVOS: Lista de fallbacks para encontrar o container
            list_container_selectors = [
                '.scaffold-layout__list-container',
                '.jobs-search-results-list',
                'ul.jobs-search-results__list',
                '[class*="jobs-search-results"]',
                '[class*="scaffold-layout__list"]',
                'ul[class*="list"]',
                '.jobs-search__results-list'
            ]
            
            list_container = None
            used_selector = None
            
            for selector in list_container_selectors:
                try:
                    list_container = self.page.wait_for_selector(selector, timeout=5000, state='visible')
                    if list_container:
                        used_selector = selector
                        print(f"  ✅ [Scout] Sidebar detected using: {selector}")
                        break
                except:
                    continue
            
            if not list_container:
                print("  ⚠ Left sidebar list container not found with any selector")
                print("  → Page may have different layout or no jobs available")
                return []
            
            print(f"  ✅ [Scout] Sidebar detected. Loading {max_jobs} jobs....")
            
            # SELETOR ULTRA-RESILIENTE: Usar data-occludable-job-id como seletor principal
            # Este é o atributo mais estável que o LinkedIn usa para rastreamento
            print("  ✅ [Scout] Container de vagas detectado.")
            
            # PRIORIDADE 1: li[data-occludable-job-id] - Seletor mais estável
            job_cards = self.page.query_selector_all('li[data-occludable-job-id]')
            
            if len(job_cards) == 0:
                # FALLBACK: Tentar outros seletores baseados em estrutura
                fallback_selectors = [
                    'ul.scaffold-layout__list-container > li',
                    'ul.jobs-search-results__list > li',
                    'li[data-job-id]',
                    'li[data-entity-urn*="job"]',
                    'div.job-card-container'
                ]
                
                for selector in fallback_selectors:
                    try:
                        cards = self.page.query_selector_all(selector)
                        if len(cards) > 0:
                            job_cards = cards
                            print(f"  📋 Found {len(job_cards)} job cards using fallback: {selector}")
                            break
                    except:
                        continue
            
            if len(job_cards) == 0:
                print("  ⚠ No job cards found. Page may have different structure.")
                return []
            
            print(f"  📋 Found {len(job_cards)} job cards using data-occludable-job-id")
            
            # MODE SILENCIOSO: Scroll suave na lista lateral para carregar todas as vagas
            scroll_attempts = 0
            max_scrolls = 5
            previous_count = len(job_cards)
            
            while scroll_attempts < max_scrolls and len(easy_apply_jobs) < max_jobs:
                # Smooth scroll within the sidebar
                # Tentar scroll no container se encontrado, senão scroll na página
                if used_selector:
                    try:
                        self.page.evaluate(f"""
                            const container = document.querySelector('{used_selector}');
                            if (container) {{
                        container.scrollTop = container.scrollHeight;
                            }}
                        """)
                    except:
                        # Fallback: scroll the page itself
                        self.page.evaluate("window.scrollBy(0, 500);")
                else:
                    # Fallback: scroll the page itself
                    self.page.evaluate("window.scrollBy(0, 500);")
                
                self.page.wait_for_timeout(2000)  # Wait for new jobs to load
                
                # Re-count job cards usando o seletor principal data-occludable-job-id
                new_cards = self.page.query_selector_all('li[data-occludable-job-id]')
                current_count = len(new_cards)
                
                if current_count != previous_count:
                    job_cards = new_cards
                    scroll_attempts = 0
                    previous_count = current_count
                    print(f"    Loaded {current_count} job cards...")
                else:
                    scroll_attempts += 1
            
            # Process each job card
            processed_count = 0
            for i, card in enumerate(job_cards[:max_jobs], 1):
                if len(easy_apply_jobs) >= max_jobs:
                    break
                
                try:
                    # FOCUS ACTION: Hover e scroll para forçar renderização do LinkedIn
                    card.scroll_into_view_if_needed()
                    card.hover()  # Hover engatilha a renderização do conteúdo
                    self.page.wait_for_timeout(500)  # Wait for lazy loading to complete
                    
                    # EXTRAIR INFORMAÇÕES DO CARD ANTES DE CLICAR (usando data-attributes)
                    job_id = card.get_attribute('data-occludable-job-id')
                    
                    # RETRY DINÂMICO: Extrair título com até 3 tentativas (1500ms entre tentativas)
                    title_from_card = self._extract_title_with_retry(card, max_retries=3, retry_delay=1500)
                    
                    # SELETORES ROBUSTOS: Extrair empresa com fallbacks
                    company_from_card = self._extract_company_with_fallback(card)
                    
                    # Log do ID e título antes de processar
                    if job_id:
                        title_display = title_from_card or "Loading..."
                        company_display = company_from_card or "Unknown"
                        print(f"    [Scout] Processando ID: {job_id} ({title_display} - {company_display})", end="")
                    
                    # Se ainda não conseguiu título após retries, pular este card
                    if not title_from_card or title_from_card == 'Loading...' or len(title_from_card) == 0:
                        print(f" -> ⏭ Skipped (Title not loaded after retries)")
                        continue
                    
                    # IDENTIFICAÇÃO DE SUCESSO: Log quando título e empresa forem extraídos
                    if title_from_card and company_from_card:
                        print(f" -> ✅ [Scout] Vaga identificada: {title_from_card} | {company_from_card}")
                    
                    # BRUTE FORCE HTML: Extrair dados do HTML bruto como fallback/backup
                    html_content = card.evaluate('el => el.outerHTML')
                    title_from_html = self._extract_title_from_html(html_content)
                    company_from_html = self._extract_company_from_html(html_content)
                    
                    # Usar dados do HTML se os do DOM falharam
                    if not title_from_card or title_from_card == 'Loading...':
                        title_from_card = title_from_html
                    if not company_from_card:
                        company_from_card = company_from_html
                    
                    # FORÇAR GRAVAÇÃO: Se título e empresa foram encontrados (mesmo via HTML), criar job_data
                    if title_from_card and title_from_card != 'Loading...' and company_from_card:
                        # Compor URL usando job_id
                        job_url = f'https://www.linkedin.com/jobs/view/{job_id}/' if job_id else None
                        
                        # Criar job_data diretamente dos dados extraídos
                        job_data = {
                            'job_id': job_id,
                            'title': title_from_card,
                            'company': company_from_card,
                            'location': 'Unknown',  # Pode ser extraído depois se necessário
                            'url': job_url,
                            'has_easy_apply': False  # Será verificado abaixo
                        }
                        
                        # Click on card to open detail on the right para verificar Easy Apply
                        try:
                            card.click()
                            self.page.wait_for_timeout(1500)  # Wait for detail panel to load
                            
                            # VALIDAÇÃO: Verificar se o botão jobs-apply-button (Easy Apply) está presente e visível
                            easy_apply_btn = self.page.query_selector('button.jobs-apply-button, button[aria-label*="Easy Apply"], button:has-text("Easy Apply"), button:has-text("Candidatura simplificada")')
                            
                            if easy_apply_btn and easy_apply_btn.is_visible():
                                job_data['has_easy_apply'] = True
                                easy_apply_jobs.append(job_data)
                                processed_count += 1
                                # Log final quando Easy Apply é encontrado
                                print(f" -> ✅ Easy Apply Found! ({title_from_card} | {company_from_card})")
                            else:
                                # Not Easy Apply, skip
                                print(f" -> ⏭ Skipped (No Easy Apply)")
                                continue
                        except Exception as click_error:
                            # Se o click falhar, ainda assim salvar a vaga identificada
                            print(f" -> ⚠ Click failed but job identified: {title_from_card} | {company_from_card}")
                            # Não adicionar à lista se não conseguir verificar Easy Apply
                            continue
                    else:
                        print(f" -> ⏭ Skipped (Could not extract title/company from card or HTML)")
                        continue
                        
                except Exception as e:
                    print(f" -> ⚠ Error: {e}")
                    continue
            
            return easy_apply_jobs
            
        except PlaywrightTimeout:
            print("  ⚠ Timeout waiting for sidebar. Checking if page has 'no jobs' message...")
            # Final check for "no jobs" message
            page_text = self.page.content().lower()
            no_jobs_texts = ['no jobs found', 'nenhuma vaga encontrada', 'no se encontraron trabajos']
            if any(text in page_text for text in no_jobs_texts):
                print("  ⚠ Confirmed: No jobs found for this search.")
                return []
            print("  ⚠ Timeout but page structure unclear. Returning empty list.")
            return []
        except Exception as e:
            print(f"  ✗ Error scouting sidebar jobs: {e}")
            import traceback
            print(traceback.format_exc()[:500])
            return []
    
    def _extract_title_with_retry(self, card, max_retries: int = 3, retry_delay: int = 1500) -> Optional[str]:
        """
        Extract job title from card with dynamic retry mechanism
        Retries up to max_retries times if title is 'Loading...' or empty
        Tries inner_text first, then aria-label as fallback
        
        Args:
            card: Playwright element representing the job card
            max_retries: Maximum number of retry attempts
            retry_delay: Delay in milliseconds between retries
            
        Returns:
            str: Job title or None if not found after retries
        """
        title_selectors = [
            'a.job-card-list__title--link',
            '.job-card-list__title--link',
            'a[class*="job-card-list__title"]',
            'a[class*="title"]'
        ]
        
        for attempt in range(max_retries):
            for selector in title_selectors:
                try:
                    title_elem = card.query_selector(selector)
                    if title_elem:
                        # Tentar inner_text primeiro
                        title_text = title_elem.inner_text().strip()
                        
                        # Se título válido (não 'Loading...' e não vazio), retornar
                        if title_text and title_text != 'Loading...' and len(title_text) > 0:
                            return title_text
                        
                        # EXTRACTION VIA ATTRIBUTE: Se inner_text falhar, tentar aria-label
                        if not title_text or title_text == 'Loading...' or len(title_text) == 0:
                            aria_label = title_elem.get_attribute('aria-label')
                            if aria_label and len(aria_label.strip()) > 0:
                                return aria_label.strip()
                            
                            # Tentar também title attribute
                            title_attr = title_elem.get_attribute('title')
                            if title_attr and len(title_attr.strip()) > 0:
                                return title_attr.strip()
                            
                            # Tentar textContent via evaluate (mais robusto)
                            text_content = title_elem.evaluate('el => el.textContent || ""')
                            if text_content and len(text_content.strip()) > 0:
                                return text_content.strip()
                except:
                    continue
            
            # RETRY DE TEXTO: Se não encontrou título válido e ainda há tentativas, esperar e tentar novamente
            if attempt < max_retries - 1:
                self.page.wait_for_timeout(retry_delay)  # Esperar 1500ms antes de retry
                # Fazer hover novamente para forçar renderização
                try:
                    card.hover()
                except:
                    pass
        
        return None
    
    def _extract_title_from_html(self, html_content: str) -> Optional[str]:
        """
        Extract job title from HTML content using regex (Brute Force method)
        
        Args:
            html_content: Raw HTML content of the job card
            
        Returns:
            str: Job title or None if not found
        """
        try:
            # Regex para encontrar título dentro da classe job-card-list__title--link
            # Padrão 1: <a class="job-card-list__title--link" ...>Título</a>
            pattern1 = r'<a[^>]*class="[^"]*job-card-list__title--link[^"]*"[^>]*>([^<]+)</a>'
            match1 = re.search(pattern1, html_content, re.IGNORECASE | re.DOTALL)
            if match1:
                title = match1.group(1).strip()
                if title and len(title) > 0:
                    return title
            
            # Padrão 2: <a ... class="...job-card-list__title--link..." ...>Título</a>
            pattern2 = r'class="[^"]*job-card-list__title[^"]*"[^>]*>([^<]+)</a>'
            match2 = re.search(pattern2, html_content, re.IGNORECASE | re.DOTALL)
            if match2:
                title = match2.group(1).strip()
                if title and len(title) > 0:
                    return title
            
            # Padrão 3: aria-label no link
            pattern3 = r'aria-label="([^"]+)"[^>]*class="[^"]*job-card-list__title'
            match3 = re.search(pattern3, html_content, re.IGNORECASE)
            if match3:
                title = match3.group(1).strip()
                if title and len(title) > 0:
                    return title
            
            # Padrão 4: Qualquer link com texto dentro de um elemento com classe contendo "title"
            pattern4 = r'<a[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</a>'
            match4 = re.search(pattern4, html_content, re.IGNORECASE | re.DOTALL)
            if match4:
                title = match4.group(1).strip()
                if title and len(title) > 0 and title != 'Loading...':
                    return title
            
            return None
        except Exception as e:
            return None
    
    def _extract_company_from_html(self, html_content: str) -> Optional[str]:
        """
        Extract company name from HTML content using regex (Brute Force method)
        
        Args:
            html_content: Raw HTML content of the job card
            
        Returns:
            str: Company name or None if not found
        """
        try:
            # Regex para encontrar empresa dentro da classe job-card-container__primary-description
            # Padrão 1: <span class="job-card-container__primary-description">Empresa</span>
            pattern1 = r'<[^>]*class="[^"]*job-card-container__primary-description[^"]*"[^>]*>([^<]+)</[^>]+>'
            match1 = re.search(pattern1, html_content, re.IGNORECASE | re.DOTALL)
            if match1:
                company = match1.group(1).strip()
                if company and len(company) > 0:
                    return company
            
            # Padrão 2: artdeco-entity-lockup__subtitle
            pattern2 = r'<[^>]*class="[^"]*artdeco-entity-lockup__subtitle[^"]*"[^>]*>([^<]+)</[^>]+>'
            match2 = re.search(pattern2, html_content, re.IGNORECASE | re.DOTALL)
            if match2:
                company = match2.group(1).strip()
                if company and len(company) > 0:
                    return company
            
            # Padrão 3: Qualquer elemento com classe contendo "company" ou "subtitle"
            pattern3 = r'<[^>]*class="[^"]*(?:company|subtitle)[^"]*"[^>]*>([^<]+)</[^>]+>'
            match3 = re.search(pattern3, html_content, re.IGNORECASE | re.DOTALL)
            if match3:
                company = match3.group(1).strip()
                if company and len(company) > 0:
                    return company
            
            return None
        except Exception as e:
            return None
    
    def _extract_company_with_fallback(self, card) -> Optional[str]:
        """
        Extract company name from card using robust selectors with fallbacks
        
        Args:
            card: Playwright element representing the job card
            
        Returns:
            str: Company name or None if not found
        """
        company_selectors = [
            '.job-card-container__primary-description',
            '.artdeco-entity-lockup__subtitle',
            '[class*="job-card-container__primary"]',
            '[class*="artdeco-entity-lockup"]',
            '[class*="company"]',
            '[class*="subtitle"]'
        ]
        
        for selector in company_selectors:
            try:
                company_elem = card.query_selector(selector)
                if company_elem:
                    company_text = company_elem.inner_text().strip()
                    if company_text and len(company_text) > 0:
                        return company_text
            except:
                continue
        
        return None
    
    def _extract_job_details(self) -> Optional[Dict]:
        """
        Extract job details from the right detail panel
        
        Returns:
            Dict with job_id, title, company, location, url
        """
        try:
            # Extract job ID from URL or data attributes
            current_url = self.page.url
            job_id = None
            if '/jobs/view/' in current_url:
                job_id_match = re.search(r'/jobs/view/(\d+)', current_url)
                if job_id_match:
                    job_id = job_id_match.group(1)
            
            # Extract job title
            title_selectors = [
                '.jobs-details-top-card__job-title',
                'h1.jobs-details-top-card__job-title',
                'h2.jobs-details-top-card__job-title',
                '.job-details-jobs-unified-top-card__job-title',
                'h1[class*="job-title"]'
            ]
            title = None
            for selector in title_selectors:
                try:
                    title_elem = self.page.query_selector(selector)
                    if title_elem:
                        title = title_elem.inner_text().strip()
                        break
                except:
                    continue
            
            # Extract company name
            company_selectors = [
                '.jobs-details-top-card__company-name',
                '.jobs-details-top-card__company-info a',
                '.job-details-jobs-unified-top-card__company-name',
                'a[class*="company-name"]'
            ]
            company = None
            for selector in company_selectors:
                try:
                    company_elem = self.page.query_selector(selector)
                    if company_elem:
                        company = company_elem.inner_text().strip()
                        break
                except:
                    continue
            
            # Extract location
            location_selectors = [
                '.jobs-details-top-card__bullet',
                '.jobs-details-top-card__primary-description-without-tagline',
                '.job-details-jobs-unified-top-card__primary-description',
                'span[class*="location"]'
            ]
            location = None
            for selector in location_selectors:
                try:
                    location_elem = self.page.query_selector(selector)
                    if location_elem:
                        location = location_elem.inner_text().strip()
                        break
                except:
                    continue
            
            # Get job URL
            job_url = current_url if '/jobs/view/' in current_url else None
            
            if title and company and job_url:
                return {
                    'job_id': job_id,
                    'title': title,
                    'company': company,
                    'location': location or "Unknown",
                    'url': job_url,
                    'has_easy_apply': False  # Will be set to True if button is found
                }
            
            return None
            
        except Exception as e:
            print(f"    ⚠ Error extracting job details: {e}")
            return None
    
    def search_easy_apply_jobs(self, location: str = "Brazil", keywords: str = "Python React", max_jobs: int = 50):
        """
        Legacy method: Navigate to LinkedIn job search with Easy Apply filter (f_AL=true)
        Kept for backward compatibility. Use scout_easy_apply_jobs() for new implementations.
        
        Args:
            location: Job location filter
            keywords: Search keywords
            max_jobs: Maximum jobs to process
        """
        # Convert keywords string to list for scout method
        keywords_list = keywords.split() if isinstance(keywords, str) else [keywords]
        return self.scout_easy_apply_jobs(location=location, keywords=keywords_list, max_jobs_per_tech=max_jobs)
    
    def click_easy_apply_button(self, job_url: str) -> bool:
        """
        Navigate to job and click Easy Apply button
        
        Args:
            job_url: URL of the job posting
            
        Returns:
            bool: True if Easy Apply button was clicked successfully
        """
        if not self.page:
            return False
        
        try:
            # Navigate to job page
            print(f"  📄 Navigating to job: {job_url}")
            self.page.goto(job_url, wait_until='domcontentloaded', timeout=60000)
            
            # SCROLL DE SEGURANÇA: Aguardar carregamento completo e fazer scroll
            self.page.wait_for_load_state("networkidle", timeout=10000)
            self.page.wait_for_timeout(2000)
            
            # DETECTOR DE "CANDIDATURA JÁ ENVIADA": Verificar se já se candidatou
            page_text = self.page.inner_text('body').lower()
            if 'applied' in page_text or 'candidatado' in page_text or 'candidatada' in page_text:
                print("  ℹ Already applied to this job. Skipping...")
                return False
            
            # Pequeno scroll para garantir que o botão seja renderizado
            self.page.evaluate("window.scrollTo(0, 300);")
            self.page.wait_for_timeout(1000)
            
            # PRIORIDADE MÁXIMA: ID Real identificado no HTML
            # REFORÇO DE SELETORES "CASCA GROSSA": Lista expandida e ordenada por prioridade
            # Seletores resilientes que funcionam mesmo quando o LinkedIn muda IDs dinâmicos
            easy_apply_selectors = [
                'button#jobs-apply-button-id',  # PRIORIDADE MÁXIMA: ID fixo identificado no HTML
                'button.jobs-apply-button',  # O clássico - classe mais estável
                'button[data-job-id]',  # Seletor via ID da vaga (muito estável)
                'div.jobs-s-apply button',  # Container de aplicação
                'button:has-text("Candidatura simplificada")',  # PT-BR
                'button:has-text("Easy Apply")',  # EN
                '.jobs-s-apply button',  # Container alternativo
                'button[aria-label*="Easy Apply"]',
                'button[aria-label*="Candidatura simplificada"]',
                'button[data-control-name="jobdetails_topcard_inapply"]',
                'button[class*="jobs-apply"]',  # Qualquer classe contendo jobs-apply
                'button[class*="apply-button"]',  # Qualquer classe contendo apply-button
                'a[href*="easyApply"]',  # Link de Easy Apply (fallback)
                'button[data-test-id*="apply"]'  # Test ID (se disponível)
            ]
            
            # ESTRATÉGIA DE 3 NÍVEIS: Engenharia de Resiliência para vencer sobreposições
            easy_apply_clicked = False
            max_retries = 5
            
            for attempt in range(max_retries):
                if attempt > 0:
                    print(f"  🔄 Retry attempt {attempt + 1}/{max_retries}...")
                    self.page.wait_for_timeout(1000)  # Espera 1s entre tentativas
                    # Scroll adicional para forçar renderização
                    self.page.evaluate("window.scrollTo(0, 300);")
                
                # NÍVEL 1: Tentar seletores padrão com clique Playwright
                for selector in easy_apply_selectors:
                    try:
                        easy_apply_btn = self.page.query_selector(selector)
                        if easy_apply_btn and easy_apply_btn.is_visible():
                            # Scroll into view to ensure button is clickable
                            easy_apply_btn.scroll_into_view_if_needed()
                            self.page.wait_for_timeout(500)
                            easy_apply_btn.click()
                            print(f"  ✓ Clicked Easy Apply button using: {selector} (attempt {attempt + 1})")
                            easy_apply_clicked = True
                            self.page.wait_for_timeout(2000)  # Wait for modal to open
                            break
                    except Exception as e:
                        continue
                
                if easy_apply_clicked:
                    break
                
                # NÍVEL 2: JavaScript Click (fura sobreposições CSS e pointer events)
                if not easy_apply_clicked and attempt >= 2:  # Só tenta JS após 2 tentativas normais
                    print(f"  🔧 Nível 2: Tentando clique via JavaScript (fura sobreposições)...")
                    try:
                        # Tentar com ID específico primeiro
                        js_click_success = self.page.evaluate("""
                            () => {
                                const btn = document.querySelector('button#jobs-apply-button-id') || 
                                           document.querySelector('button.jobs-apply-button') ||
                                           document.querySelector('button[data-job-id]');
                                if (btn) {
                                    btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                    btn.click();
                                    return true;
                                }
                                return false;
                            }
                        """)
                        
                        if js_click_success:
                            print(f"  ✓ Clicked Easy Apply button via JavaScript (attempt {attempt + 1})")
                            easy_apply_clicked = True
                            self.page.wait_for_timeout(2000)
                            break
                    except Exception as js_error:
                        print(f"  ⚠ JavaScript click failed: {js_error}")
                        continue
                
                # NÍVEL 3: Refresh de Segurança (última tentativa)
                if not easy_apply_clicked and attempt == max_retries - 1:
                    print(f"  🔄 Nível 3: Refresh de segurança (última tentativa)...")
                    try:
                        self.page.reload(wait_until='domcontentloaded', timeout=30000)
                        self.page.wait_for_load_state("networkidle", timeout=10000)
                        self.page.wait_for_timeout(2000)
                        
                        # Tentar novamente após refresh
                        for selector in easy_apply_selectors[:3]:  # Apenas os 3 primeiros (mais confiáveis)
                            try:
                                easy_apply_btn = self.page.wait_for_selector(selector, timeout=5000, state='attached')
                                if easy_apply_btn:
                                    # Clique via JavaScript após refresh
                                    self.page.evaluate(f"""
                                        () => {{
                                            const btn = document.querySelector('{selector}');
                                            if (btn) {{
                                                btn.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                                btn.click();
                                                return true;
                                            }}
                                            return false;
                                        }}
                                    """)
                                    print(f"  ✓ Clicked Easy Apply button after refresh using: {selector}")
                                    easy_apply_clicked = True
                                    self.page.wait_for_timeout(2000)
                                    break
                            except:
                                continue
                    except Exception as refresh_error:
                        print(f"  ⚠ Refresh failed: {refresh_error}")
                        continue
            
            # FALLBACK DE IA OTIMIZADO: Só usar se todos os seletores manuais falharem
            if not easy_apply_clicked:
                print("  🔍 Easy Apply button not found with standard selectors.")
                print("  → Trying AI-powered detection (optimized - only relevant HTML)...")
                
                # Extrair apenas o trecho do HTML que contém "Apply" para economizar tokens
                html_snippet = self.page.evaluate("""
                    () => {
                        const buttons = document.querySelectorAll('button, a');
                        let relevantHTML = '';
                        for (let btn of buttons) {
                            const text = btn.textContent || btn.innerText || '';
                            const ariaLabel = btn.getAttribute('aria-label') || '';
                            if (text.toLowerCase().includes('apply') || 
                                text.toLowerCase().includes('candidatura') ||
                                ariaLabel.toLowerCase().includes('apply') ||
                                ariaLabel.toLowerCase().includes('candidatura')) {
                                relevantHTML += btn.outerHTML + '\\n';
                            }
                        }
                        return relevantHTML || document.body.innerHTML.substring(0, 5000);
                    }
                """)
                
                if html_snippet:
                    ai_suggestion = self.brain.find_submit_button(html_snippet)
                    
                    if ai_suggestion:
                        try:
                            ai_btn = self.page.query_selector(ai_suggestion)
                            if ai_btn:
                                ai_btn.scroll_into_view_if_needed()
                                self.page.wait_for_timeout(500)
                                ai_btn.click()
                                print(f"  ✓ Clicked Easy Apply button using AI suggestion: {ai_suggestion}")
                                easy_apply_clicked = True
                                self.page.wait_for_timeout(2000)
                        except Exception as ai_error:
                            print(f"  ⚠ AI suggestion failed: {ai_error}")
                    else:
                        print("  ⚠ AI could not find Easy Apply button selector.")
                else:
                    print("  ⚠ Could not extract relevant HTML for AI analysis.")
            
            return easy_apply_clicked
            
        except Exception as e:
            print(f"  ✗ Error clicking Easy Apply button: {e}")
            return False
    
    def fill_easy_apply_form(self) -> bool:
        """
        Fill Easy Apply form with self-healing AI-powered field detection
        
        Returns:
            bool: True if form was filled successfully
        """
        if not self.page:
            return False
        
        try:
            max_steps = 10  # Maximum number of "Next" clicks
            step = 0
            
            while step < max_steps:
                step += 1
                print(f"  📝 Step {step}/{max_steps}: Processing form...")
                
                # Wait for form to be visible
                self.page.wait_for_timeout(2000)
                
                # Get current form HTML for AI analysis
                try:
                    modal = self.page.query_selector('div[role="dialog"], .jobs-easy-apply-modal, .artdeco-modal')
                    if not modal:
                        print("  ⚠ Modal not found. Form may have closed.")
                        return False
                    
                    html_content = modal.inner_html()
                except:
                    html_content = self.page.content()
                
                # Check for unfilled required fields using AI
                required_fields = self.brain.resolve_form_fields(html_content, ['name', 'email', 'phone', 'resume', 'cover_letter'])
                
                # Fill fields based on AI suggestions
                fields_filled = 0
                for field_name, selector in required_fields.items():
                    if selector:
                        try:
                            field_elem = self.page.query_selector(selector)
                            if field_elem:
                                # Determine field type and fill accordingly
                                tag_name = field_elem.evaluate('el => el.tagName.toLowerCase()')
                                
                                if tag_name == 'INPUT':
                                    input_type = field_elem.get_attribute('type') or 'text'
                                    
                                    if input_type == 'file':
                                        # Resume upload
                                        if self.resume_path.exists():
                                            field_elem.set_input_files(str(self.resume_path))
                                            print(f"  ✓ Uploaded resume: {self.resume_path}")
                                            fields_filled += 1
                                    elif input_type in ['text', 'email', 'tel']:
                                        # Text input
                                        value = self._get_field_value(field_name)
                                        if value:
                                            field_elem.fill(value)
                                            print(f"  ✓ Filled {field_name}: {value}")
                                            fields_filled += 1
                                elif tag_name == 'TEXTAREA':
                                    # Textarea (cover letter, etc.)
                                    if 'cover' in field_name.lower() or 'letter' in field_name.lower():
                                        # Skip cover letter for now (can be added later)
                                        pass
                                    else:
                                        value = self._get_field_value(field_name)
                                        if value:
                                            field_elem.fill(value)
                                            print(f"  ✓ Filled {field_name}: {value}")
                                            fields_filled += 1
                                elif tag_name in ['SELECT', 'DIV']:
                                    # Dropdown or custom select
                                    self._handle_dropdown(field_elem, field_name)
                                    fields_filled += 1
                        except Exception as e:
                            print(f"  ⚠ Error filling {field_name}: {e}")
                            continue
                
                # STEP 2: Form Negotiator - Extract and answer questions from modal
                self._extract_and_answer_modal_questions()
                
                # Handle qualification questions and profile matching
                self._handle_qualification_questions()
                
                # Handle custom questions (dropdowns, checkboxes, radio buttons)
                self._handle_custom_questions()
                
                # Check for "Next" or "Review" button
                next_btn = self._find_next_button()
                submit_btn = self._find_submit_button()
                
                if submit_btn:
                    print(f"  ✓ Found Submit button at step {step}")
                    if self.auto_submit:
                        print("  🚀 Auto-submit enabled. Submitting application...")
                        submit_btn.click()
                        self.page.wait_for_timeout(3000)
                        return True
                    else:
                        print("  ⚠ Submit button found but --auto-submit not enabled.")
                        print("  📋 Review Required: Please review the application before submitting.")
                        return False
                
                if next_btn:
                    print(f"  ➡️ Clicking Next button (step {step})...")
                    next_btn.click()
                    self.page.wait_for_timeout(2000)
                else:
                    print(f"  ⚠ No Next or Submit button found at step {step}. Form may be complete.")
                    break
            
            return True
            
        except Exception as e:
            print(f"  ✗ Error filling Easy Apply form: {e}")
            import traceback
            print(traceback.format_exc()[:500])
            return False
    
    def _get_field_value(self, field_name: str) -> Optional[str]:
        """Get value for a form field from user_data"""
        field_lower = field_name.lower()
        
        if 'name' in field_lower or 'nome' in field_lower:
            return self.user_data.get('name') or self.user_data.get('nome')
        elif 'email' in field_lower or 'e-mail' in field_lower:
            return self.user_data.get('email')
        elif 'phone' in field_lower or 'telefone' in field_lower or 'mobile' in field_lower or 'celular' in field_lower:
            # Mobile Phone: Puxar do user_config.json
            return self.user_data.get('phone') or self.user_data.get('telefone') or self.user_data.get('mobile')
        elif 'linkedin' in field_lower:
            return self.user_data.get('linkedin') or self.user_data.get('linkedin_url')
        elif 'website' in field_lower or 'site' in field_lower:
            return self.user_data.get('website') or self.user_data.get('site')
        
        return None
    
    def _handle_dropdown(self, element, field_name: str):
        """Handle dropdown/select fields"""
        try:
            tag_name = element.evaluate('el => el.tagName')
            
            if tag_name == 'SELECT':
                # Standard select dropdown
                # Try to select first non-empty option
                options = element.query_selector_all('option')
                for option in options[1:]:  # Skip first (usually empty)
                    value = option.get_attribute('value')
                    if value:
                        element.select_option(value)
                        print(f"  ✓ Selected dropdown option for {field_name}")
                        return
            else:
                # Custom dropdown (div with role="listbox")
                element.click()
                self.page.wait_for_timeout(500)
                
                # Try to select first option
                first_option = self.page.query_selector('li[role="option"]:first-child, div[role="option"]:first-child')
                if first_option:
                    first_option.click()
                    print(f"  ✓ Selected custom dropdown option for {field_name}")
                    return
        except Exception as e:
            print(f"  ⚠ Error handling dropdown for {field_name}: {e}")
    
    def _extract_and_answer_modal_questions(self):
        """
        STEP 2: Form Negotiator - Extract all questions from Easy Apply modal and answer with AI
        This method extracts questions like "Do you have experience with Next.js?" 
        and uses AI to answer based on resume data
        
        Returns:
            int: Number of questions answered
        """
        try:
            # Get modal element
            modal = self.page.query_selector('div[role="dialog"], .jobs-easy-apply-modal, .artdeco-modal')
            if not modal:
                return 0
            
            # Extract all text from modal to find questions
            modal_text = modal.inner_text()
            
            # Find all question patterns (labels, placeholders, aria-labels)
            questions_answered = 0
            
            # Find all input fields, textareas, and select elements
            form_elements = modal.query_selector_all(
                'input[type="text"], input[type="number"], textarea, select, '
                'div[contenteditable="true"], [role="textbox"], [role="combobox"]'
            )
            
            for elem in form_elements[:10]:  # Limit to first 10 elements
                try:
                    # Get question text from various sources
                    question_text = None
                    
                    # Try to get label associated with field
                    label_elem = elem.evaluate('''el => {
                        const id = el.id;
                        if (id) {
                            const label = document.querySelector(`label[for="${id}"]`);
                            if (label) return label.textContent || "";
                        }
                        const parent = el.closest("label, div, li");
                        if (parent) {
                            const labelText = parent.querySelector("label, span, p");
                            if (labelText) return labelText.textContent || "";
                        }
                        return "";
                    }''')
                    
                    if label_elem and len(label_elem.strip()) > 0:
                        question_text = label_elem.strip()
                    
                    # Try aria-label as fallback
                    if not question_text:
                        aria_label = elem.get_attribute('aria-label')
                        if aria_label:
                            question_text = aria_label
                    
                    # Try placeholder as fallback
                    if not question_text:
                        placeholder = elem.get_attribute('placeholder')
                        if placeholder:
                            question_text = placeholder
                    
                    # If we found a question, answer it with AI
                    if question_text and len(question_text) > 5:  # Minimum question length
                        # Determine question type
                        question_lower = question_text.lower()
                        question_type = "general"
                        
                        if any(word in question_lower for word in ['experience', 'anos', 'years', 'tempo']):
                            question_type = "experience"
                        elif any(word in question_lower for word in ['qualification', 'qualificação', 'skill', 'habilidade']):
                            question_type = "qualification"
                        elif any(word in question_lower for word in ['have', 'tem', 'possui', 'você']):
                            question_type = "yes_no"
                        
                        # Get resume data (basic - can be enhanced later)
                        resume_data = {}
                        if 'experience' in self.user_data or 'experiencia' in self.user_data:
                            resume_data['experiencia_anos'] = self.user_data.get('experience') or self.user_data.get('experiencia', 8)
                        
                        # Use AI to answer
                        answer = self.brain.answer_form_question(
                            question_text=question_text[:300],
                            question_type=question_type,
                            user_data=self.user_data,
                            resume_data=resume_data
                        )
                        
                        # Fill the field
                        tag_name = elem.evaluate('el => el.tagName.toLowerCase()')
                        if tag_name in ['input', 'textarea']:
                            elem.fill(answer)
                            questions_answered += 1
                            print(f"  ✓ [Form Negotiator] Answered: \"{question_text[:50]}...\" -> {answer[:50]}...")
                            self.page.wait_for_timeout(300)
                        elif tag_name == 'div' and elem.get_attribute('contenteditable') == 'true':
                            elem.fill(answer)
                            questions_answered += 1
                            print(f"  ✓ [Form Negotiator] Answered: \"{question_text[:50]}...\" -> {answer[:50]}...")
                            self.page.wait_for_timeout(300)
                            
                except Exception as e:
                    # Continue to next element if this one fails
                    continue
            
            if questions_answered > 0:
                print(f"  ✅ [Form Negotiator] Answered {questions_answered} questions from modal")
            
            return questions_answered
            
        except Exception as e:
            print(f"  ⚠ Error extracting modal questions: {e}")
            return 0
    
    def _handle_qualification_questions(self):
        """
        STEP 2: Form Negotiator - Handle qualification questions using AI
        Detects questions like "Your profile matches some required qualifications" 
        and answers them based on user identity and resume data
        """
        try:
            # Get form text to detect qualification questions
            modal = self.page.query_selector('div[role="dialog"], .jobs-easy-apply-modal, .artdeco-modal')
            if not modal:
                return
            
            form_text = modal.inner_text().lower()
            
            # Detect qualification-related questions
            qualification_keywords = [
                'your profile matches',
                'required qualifications',
                'years of experience',
                'anos de experiência',
                'qualifications',
                'qualificações',
                'experience level',
                'nível de experiência'
            ]
            
            has_qualification_question = any(keyword in form_text for keyword in qualification_keywords)
            
            if not has_qualification_question:
                return
            
            print("  🤖 [Form Negotiator] Detected qualification questions. Using AI to answer...")
            
            # Find text areas or input fields that might need qualification answers
            # Look for questions about experience, qualifications, etc.
            question_elements = self.page.query_selector_all(
                'textarea, input[type="text"], input[type="number"], '
                'div[contenteditable="true"], [role="textbox"]'
            )
            
            for elem in question_elements[:5]:  # Limit to first 5
                try:
                    # Get surrounding context to understand the question
                    # Use evaluate to get parent text
                    context_text = elem.evaluate('''el => {
                        const parent = el.closest("div, li, fieldset");
                        if (parent) {
                            return parent.textContent || "";
                        }
                        return el.textContent || "";
                    }''')
                    context_lower = context_text.lower()
                    
                    # Check if this is a qualification-related question
                    if any(keyword in context_lower for keyword in qualification_keywords):
                        # Determine question type
                        question_type = "experience"
                        if 'years' in context_lower or 'anos' in context_lower:
                            question_type = "experience"
                        elif 'qualification' in context_lower or 'qualificação' in context_lower:
                            question_type = "qualification"
                        elif 'match' in context_lower:
                            question_type = "qualification_match"
                        
                        # Get resume data if available (from user_data or parse from resume)
                        resume_data = {}
                        # Try to extract experience from user_data if available
                        if 'experience' in self.user_data or 'experiencia' in self.user_data:
                            resume_data['experiencia_anos'] = self.user_data.get('experience') or self.user_data.get('experiencia', 8)
                        
                        # Use AI to answer the question
                        answer = self.brain.answer_form_question(
                            question_text=context_text[:200],  # Limit length
                            question_type=question_type,
                            user_data=self.user_data,
                            resume_data=resume_data
                        )
                        
                        # Fill the field with the answer
                        tag_name = elem.evaluate('el => el.tagName.toLowerCase()')
                        if tag_name == 'textarea' or tag_name == 'input':
                            elem.fill(answer)
                            print(f"  ✓ [Form Negotiator] Answered qualification question: {answer[:50]}...")
                            self.page.wait_for_timeout(500)
                        elif tag_name == 'div' and elem.get_attribute('contenteditable') == 'true':
                            elem.fill(answer)
                            print(f"  ✓ [Form Negotiator] Answered qualification question: {answer[:50]}...")
                            self.page.wait_for_timeout(500)
                            
                except Exception as e:
                    print(f"  ⚠ Error handling qualification question: {e}")
                    continue
            
            # Also handle radio buttons for "Yes/No" qualification questions
            qualification_radios = self.page.query_selector_all('input[type="radio"]')
            for radio in qualification_radios[:10]:  # Limit to first 10
                try:
                    # Get label text using evaluate
                    label_text = radio.evaluate('el => { const label = el.closest("label") || el.parentElement; return label ? label.textContent || "" : ""; }')
                    label_lower = label_text.lower()
                    
                    # If it's a "Yes" option for qualification questions
                    if any(keyword in label_lower for keyword in qualification_keywords):
                        if 'yes' in label_lower or 'sim' in label_lower or 'match' in label_lower:
                            radio.click()
                            print(f"  ✓ [Form Negotiator] Selected 'Yes' for qualification: {label_text[:50]}...")
                            self.page.wait_for_timeout(300)
                            break
                except:
                    continue
                    
        except Exception as e:
            print(f"  ⚠ Error handling qualification questions: {e}")
    
    def _handle_custom_questions(self):
        """Handle custom questions (radio buttons, checkboxes)"""
        try:
            # Find all radio buttons and checkboxes
            radios = self.page.query_selector_all('input[type="radio"]:not(:checked)')
            checkboxes = self.page.query_selector_all('input[type="checkbox"]:not(:checked)')
            
            # For radio buttons, select the first option (usually "No" or "LinkedIn")
            for radio in radios[:5]:  # Limit to first 5 to avoid over-selection
                try:
                    # Check if it's a "No" option (safe default)
                    label = self.page.evaluate('el => el.closest("label")?.textContent || ""', radio)
                    if 'não' in label.lower() or 'no' in label.lower() or 'linkedin' in label.lower():
                        radio.click()
                        print(f"  ✓ Selected radio option: {label.strip()}")
                        self.page.wait_for_timeout(300)
                except:
                    continue
            
            # For checkboxes, only check if it's clearly a consent/authorization checkbox
            for checkbox in checkboxes[:3]:  # Limit to first 3
                try:
                    label = self.page.evaluate('el => el.closest("label")?.textContent || ""', checkbox)
                    if 'authoriz' in label.lower() or 'consent' in label.lower() or 'agree' in label.lower():
                        checkbox.click()
                        print(f"  ✓ Checked checkbox: {label.strip()}")
                        self.page.wait_for_timeout(300)
                except:
                    continue
        except Exception as e:
            print(f"  ⚠ Error handling custom questions: {e}")
    
    def _find_next_button(self) -> Optional[any]:
        """Find Next/Continue button"""
        next_selectors = [
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button:has-text("Avançar")',
            'button:has-text("Continuar")',
            'button[aria-label*="Next"]',
            'button[aria-label*="Continue"]',
            'button.jobs-easy-apply-footer__button--next',
            'button[data-control-name="continue_unify"]'
        ]
        
        for selector in next_selectors:
            try:
                btn = self.page.query_selector(selector)
                if btn and btn.is_visible():
                    return btn
            except:
                continue
        
        return None
    
    def _find_submit_button(self) -> Optional[any]:
        """Find Submit button"""
        submit_selectors = [
            'button:has-text("Submit")',
            'button:has-text("Submit application")',
            'button:has-text("Enviar")',
            'button:has-text("Enviar candidatura")',
            'button[aria-label*="Submit"]',
            'button.jobs-easy-apply-footer__button--submit',
            'button[data-control-name="submit_unify"]'
        ]
        
        for selector in submit_selectors:
            try:
                btn = self.page.query_selector(selector)
                if btn and btn.is_visible():
                    return btn
            except:
                continue
        
        return None
    
    def process_application_flow(self, job_url: str, auto_submit: bool = False, resume_data: Dict = None) -> bool:
        """
        STEP 2: The Negotiator - AI-Powered Form Filling
        Main method that processes the entire Easy Apply flow with AI assistance
        
        Args:
            job_url: URL of the job posting
            auto_submit: If True, automatically submit without review
            resume_data: Resume data for AI context (optional)
            
        Returns:
            bool: True if application was processed successfully
        """
        if not self.page:
            return False
        
        try:
            print(f"\n  🧠 [Step 2: The Negotiator] Starting AI-powered application flow...")
            print(f"  📄 Job URL: {job_url}")
            
            # 1. O GATILHO DO MODAL: Abrir URL e clicar no botão Easy Apply
            print(f"\n  [1/4] Opening job page and clicking Easy Apply...")
            if not self.click_easy_apply_button(job_url):
                print("  ✗ Failed to click Easy Apply button")
                return False
            
            # 2. DETECTAR MODAL: Verificar se modal foi aberto
            print(f"  [2/4] Detecting Easy Apply modal...")
            modal = self.page.wait_for_selector('.jobs-easy-apply-modal, div[role="dialog"], .artdeco-modal', timeout=10000, state='visible')
            if not modal:
                print("  ✗ Modal not detected. Easy Apply may not be available.")
                return False
            print("  ✓ Modal detected. Starting form processing...")
            
            # 3. PROCESSAR ETAPAS: Loop de preenchimento com IA
            print(f"  [3/4] Processing form steps with AI...")
            max_steps = 15  # Increased limit for complex forms
            step = 0
            resume_data_for_ai = resume_data or {}
            
            while step < max_steps:
                step += 1
                print(f"\n    📝 Form Step {step}/{max_steps}:")
                
                # Wait for form to be visible
                self.page.wait_for_timeout(2000)
                
                # Check if modal still exists
                modal = self.page.query_selector('div[role="dialog"], .jobs-easy-apply-modal, .artdeco-modal')
                if not modal:
                    print("    ⚠ Modal closed. Form may have been submitted or closed.")
                    break
                
                # CAPTURE CONTEXTO: Pegar HTML do formulário atual
                try:
                    html_content = modal.inner_html()
                except:
                    html_content = self.page.content()
                
                # Fill standard fields (name, email, phone, resume)
                self._fill_standard_fields(html_content)
                
                # EXTRACTION DE PERGUNTAS E RESPOSTAS VIA IA: Processar perguntas complexas
                questions_answered = self._process_form_questions_with_ai(html_content, resume_data_for_ai)
                if questions_answered > 0:
                    print(f"    ✓ Processed {questions_answered} question(s) with AI")
                
                # 4. NAVEGAÇÃO DE ETAPAS: Verificar botões Next/Review/Submit
                print(f"  [4/4] Checking navigation buttons...")
                next_btn = self._find_next_button()
                review_btn = self._find_review_button()
                submit_btn = self._find_submit_button()
                
                # Se encontrou Review ou Submit
                if review_btn or submit_btn:
                    if not auto_submit:
                        print(f"\n  ⚠ [ACTION REQUIRED] Application ready for review.")
                        print(f"  → Modal is open and waiting for manual review.")
                        print(f"  → Use --auto-submit flag to enable automatic submission.")
                        print(f"  → Review the application and click Submit manually.")
                        return True  # Successfully reached review stage
                    else:
                        # Auto-submit enabled
                        if submit_btn:
                            print(f"  🚀 Auto-submit enabled. Submitting application...")
                            submit_btn.click()
                            self.page.wait_for_timeout(3000)
                            print(f"  ✅ Application submitted successfully!")
                            return True
                
                # Se encontrou Next, continuar
                if next_btn:
                    print(f"    ➡️ Clicking Next button...")
                    next_btn.click()
                    self.page.wait_for_timeout(2000)
                else:
                    print(f"    ⚠ No Next/Review/Submit button found. Form may be complete.")
                    break
            
            print(f"\n  ✅ Form processing completed!")
            return True
            
        except Exception as e:
            print(f"  ✗ Error in application flow: {e}")
            import traceback
            print(traceback.format_exc()[:500])
            return False
    
    def _fill_standard_fields(self, html_content: str):
        """Fill standard fields (name, email, phone, resume)"""
        try:
            # Get selectors for standard fields
            required_fields = self.brain.resolve_form_fields(html_content, ['name', 'email', 'phone', 'resume'])
            
            for field_name, selector in required_fields.items():
                if selector:
                    try:
                        field_elem = self.page.query_selector(selector)
                        if field_elem:
                            tag_name = field_elem.evaluate('el => el.tagName.toLowerCase()')
                            
                            if tag_name == 'INPUT':
                                input_type = field_elem.get_attribute('type') or 'text'
                                
                                if input_type == 'file':
                                    # Resume upload
                                    if self.resume_path.exists():
                                        field_elem.set_input_files(str(self.resume_path))
                                        print(f"    ✓ Uploaded resume")
                                elif input_type in ['text', 'email', 'tel']:
                                    value = self._get_field_value(field_name)
                                    if value:
                                        field_elem.fill(value)
                                        print(f"    ✓ Filled {field_name}")
                            elif tag_name == 'TEXTAREA':
                                value = self._get_field_value(field_name)
                                if value:
                                    field_elem.fill(value)
                                    print(f"    ✓ Filled {field_name}")
                    except:
                        continue
        except Exception as e:
            print(f"    ⚠ Error filling standard fields: {e}")
    
    def _process_form_questions_with_ai(self, html_content: str, resume_data: Dict) -> int:
        """
        Process form questions using AI (The Negotiator)
        Extracts questions from HTML and answers them using AI with Felipe's profile
        
        Returns:
            int: Number of questions answered
        """
        questions_answered = 0
        
        try:
            # Find all input fields, textareas, selects, and radio buttons
            form_elements = self.page.query_selector_all(
                'input[type="text"], input[type="number"], textarea, select, '
                'input[type="radio"]:not(:checked), div[contenteditable="true"]'
            )
            
            for elem in form_elements[:15]:  # Limit to first 15 elements
                try:
                    # Get question text from label, aria-label, or placeholder
                    question_text = None
                    
                    # Try to get associated label
                    label_text = elem.evaluate('''el => {
                        const id = el.id;
                        if (id) {
                            const label = document.querySelector(`label[for="${id}"]`);
                            if (label) return label.textContent || "";
                        }
                        const parent = el.closest("div, li, fieldset");
                        if (parent) {
                            const label = parent.querySelector("label, span, p");
                            if (label) return label.textContent || "";
                        }
                        return "";
                    }''')
                    
                    if label_text and len(label_text.strip()) > 5:
                        question_text = label_text.strip()
                    
                    # Try aria-label
                    if not question_text:
                        aria_label = elem.get_attribute('aria-label')
                        if aria_label and len(aria_label.strip()) > 5:
                            question_text = aria_label.strip()
                    
                    # Try placeholder
                    if not question_text:
                        placeholder = elem.get_attribute('placeholder')
                        if placeholder and len(placeholder.strip()) > 5:
                            question_text = placeholder.strip()
                    
                    # If we found a question, answer it with AI
                    if question_text and len(question_text) > 5:
                        # Determine question type
                        question_lower = question_text.lower()
                        question_type = "general"
                        
                        if any(word in question_lower for word in ['experience', 'anos', 'years', 'tempo', 'experiência']):
                            question_type = "experience"
                        elif any(word in question_lower for word in ['qualification', 'qualificação', 'skill', 'habilidade', 'tecnologia']):
                            question_type = "qualification"
                        elif any(word in question_lower for word in ['visa', 'visto', 'work authorization', 'autorização']):
                            question_type = "visa"
                        elif any(word in question_lower for word in ['salary', 'salário', 'compensation', 'remuneração']):
                            question_type = "salary"
                        elif any(word in question_lower for word in ['have', 'tem', 'possui', 'você', 'do you']):
                            question_type = "yes_no"
                        
                        # Use AI to answer
                        answer = self.brain.answer_form_question(
                            question_text=question_text[:300],
                            question_type=question_type,
                            user_data=self.user_data,
                            resume_data=resume_data
                        )
                        
                        # Fill the field based on type
                        tag_name = elem.evaluate('el => el.tagName.toLowerCase()')
                        input_type = elem.get_attribute('type') if tag_name == 'input' else None
                        
                        if tag_name == 'input' and input_type == 'radio':
                            # For radio buttons, find the option that matches the answer
                            radio_group = self.page.query_selector_all(f'input[type="radio"][name="{elem.get_attribute("name")}"]')
                            for radio in radio_group:
                                label = radio.evaluate('el => el.closest("label")?.textContent || ""')
                                if answer.lower() in label.lower() or label.lower() in answer.lower():
                                    radio.click()
                                    questions_answered += 1
                                    print(f"    ✓ [AI] Selected: {label.strip()[:50]}...")
                                    break
                        elif tag_name in ['input', 'textarea']:
                            elem.fill(answer)
                            questions_answered += 1
                            print(f"    ✓ [AI] Answered: \"{question_text[:50]}...\" -> {answer[:50]}...")
                            self.page.wait_for_timeout(300)
                        elif tag_name == 'div' and elem.get_attribute('contenteditable') == 'true':
                            elem.fill(answer)
                            questions_answered += 1
                            print(f"    ✓ [AI] Answered: \"{question_text[:50]}...\" -> {answer[:50]}...")
                            self.page.wait_for_timeout(300)
                            
                except Exception as e:
                    continue
            
            return questions_answered
            
        except Exception as e:
            print(f"    ⚠ Error processing questions with AI: {e}")
            return 0
    
    def _find_review_button(self) -> Optional[any]:
        """Find Review button"""
        review_selectors = [
            'button:has-text("Review")',
            'button:has-text("Revisar")',
            'button:has-text("Review application")',
            'button[aria-label*="Review"]',
            'button.jobs-easy-apply-footer__button--review'
        ]
        
        for selector in review_selectors:
            try:
                btn = self.page.query_selector(selector)
                if btn and btn.is_visible():
                    return btn
            except:
                continue
        
        return None
    
    def apply_to_job(self, job_url: str, auto_submit: bool = False) -> bool:
        """
        Complete Easy Apply process for a single job
        
        Args:
            job_url: URL of the job posting
            auto_submit: If True, automatically submit without review
            
        Returns:
            bool: True if application was successful
        """
        self.auto_submit = auto_submit
        
        try:
            # Step 1: Click Easy Apply button
            if not self.click_easy_apply_button(job_url):
                print("  ✗ Failed to click Easy Apply button")
                return False
            
            # Step 2: Fill form
            if not self.fill_easy_apply_form():
                print("  ✗ Failed to fill Easy Apply form")
                return False
            
            # Step 3: If auto_submit is False, log review required
            if not auto_submit:
                print("  📋 Review Required: Application ready for manual review.")
                print("  💡 Tip: Use --auto-submit flag to enable automatic submission.")
            
            return True
            
        except Exception as e:
            print(f"  ✗ Error applying to job: {e}")
            import traceback
            print(traceback.format_exc()[:500])
            return False

