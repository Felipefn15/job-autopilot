"""
LinkedIn Post Searcher Module
Searches for hiring posts on LinkedIn and extracts contact information
Uses Playwright to access LinkedIn (requires logged-in Chrome profile or credentials)
"""
import re
import time
import os
import json
import unicodedata
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from playwright.sync_api import sync_playwright, Page
from .models import JobListing
from .brain import AIBrain
from .emailer import EmailApplier


def _canonical_post_url(url: str) -> str:
    """Normalize LinkedIn post URL so same post = same job_id (avoids duplicate sends across runs/skills)."""
    if not url or not isinstance(url, str):
        return (url or "").strip()
    base = url.split("?")[0].strip()
    return base.rstrip("/") if base else url


class LinkedInPostSearcher:
    """Searches for hiring posts on LinkedIn and extracts contact info"""
    
    def __init__(self, resume_data, user_data: Dict[str, str] = None):
        self.resume_data = resume_data
        self.user_data = user_data or {}
        self.brain = AIBrain()
        self.emailer = EmailApplier()
        self.page: Optional[Page] = None
        self.playwright = None
        
    def start_browser(self, headless: bool = False):
        """Start Playwright browser with logged-in Chrome profile"""
        from .session_manager import SessionManager
        
        # Reuse session manager logic
        session_manager = SessionManager()
        context_args = session_manager.get_context_args("chrome")
        
        if not context_args.get('can_use_real_session'):
            print("  ⚠ Cannot use real Chrome session. LinkedIn search requires login.")
            return False
        
        user_data_dir = context_args['user_data_dir']

        # Remove stale singleton lock files left behind by previous crashes.
        # Chrome finds them, assumes another instance is running, and immediately
        # hits an assertion (brk #0 → SIGTRAP) on macOS 26.
        for lock_file in ['SingletonLock', 'SingletonCookie', 'SingletonSocket']:
            lock_path = Path(user_data_dir) / lock_file
            try:
                lock_path.unlink(missing_ok=True)
            except Exception:
                pass

        try:
            self.playwright = sync_playwright().start()
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=headless,
                channel=None,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-gpu',
                    '--disable-features=SyncRequiresConsent,ChromeSignin',
                ],
                viewport={'width': 1920, 'height': 1080},
                permissions=['clipboard-read', 'clipboard-write'],
            )
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            
            print("  ✓ LinkedIn browser started")
            if not headless:
                print("  ✓ Modo Interativo: Navegador visível (headless=False)")

            # Navega para o feed para ativar os cookies do perfil persistente.
            # Se a sessão for válida, o LinkedIn redireciona direto para o feed.
            # Se não, redireciona para /login e o login é feito abaixo.
            try:
                self.page.goto("https://www.linkedin.com/feed", wait_until='domcontentloaded', timeout=30000)
                time.sleep(2)
            except Exception:
                pass

            def _block_media(route):
                if route.request.resource_type in ['image', 'media', 'imageset']:
                    route.abort()
                else:
                    route.continue_()

            if self.is_logged_in():
                print("  ✓ Sessão restaurada do perfil — já logado no LinkedIn")
                self.page.route("**/*", _block_media)
                print("  ✓ Media blocking enabled")
            else:
                print("  ⚠ Sessão expirada ou inexistente. Fazendo login...")
                if self.login_linkedin():
                    print("  ✓ Login realizado com sucesso")
                    if '/feed' not in self.page.url.lower():
                        print("  → Navegando para o Feed após login...")
                        try:
                            self.page.goto("https://www.linkedin.com/feed", wait_until='domcontentloaded', timeout=30000)
                            time.sleep(2)
                        except Exception:
                            pass
                    self.page.route("**/*", _block_media)
                    print("  ✓ Media blocking enabled")
                else:
                    print("  ⚠ Login falhou ou requer 2FA. Continuando com sessão atual...")
            
            return True
        except Exception as e:
            print(f"  ✗ Error starting browser: {e}")
            try:
                if self.context:
                    self.context.close()
            except Exception:
                pass
            try:
                if self.playwright:
                    self.playwright.stop()
            except Exception:
                pass
            self.page = None
            self.context = None
            self.playwright = None
            return False
    
    def is_logged_in(self) -> bool:
        """Check if already logged in by inspecting current URL and cookies — no extra navigation."""
        if not self.page:
            return False
        try:
            current_url = self.page.url.lower()
            # Se ainda está em branco ou na página inicial do Playwright, não navegou ainda
            if not current_url or current_url in ('about:blank', ''):
                return False
            # Se a URL contém indicadores de login, não está logado
            if any(x in current_url for x in ('login', 'signin', 'uas/')):
                return False
            # Se está no feed ou em qualquer página autenticada do LinkedIn, está logado
            if 'linkedin.com' in current_url and any(x in current_url for x in ('/feed', '/in/', '/jobs', '/messaging')):
                return True
            return False
        except Exception:
            return False
    
    def login_linkedin(self) -> bool:
        """Perform automatic login to LinkedIn using credentials from .env"""
        if not self.page:
            return False
        
        # Get credentials from environment variables
        linkedin_email = os.getenv('LINKEDIN_EMAIL')
        linkedin_password = os.getenv('LINKEDIN_PASSWORD')
        
        if not linkedin_email or not linkedin_password:
            print("  ⚠ LinkedIn credentials not found in .env")
            print("  → Please add LINKEDIN_EMAIL and LINKEDIN_PASSWORD to your .env file")
            print("  → Example:")
            print("  →   LINKEDIN_EMAIL=seu_email@exemplo.com")
            print("  →   LINKEDIN_PASSWORD=sua_senha")
            return False
        
        try:
            print(f"  → Credenciais: {linkedin_email[:4]}...@... / {'*' * len(linkedin_password)}")

            # Navega para login — usa domcontentloaded pois LinkedIn carrega scripts
            # de terceiros (reCAPTCHA, Google GSI, Adobe demdex) que nunca fecham
            # e fazem o networkidle nunca disparar, travando o goto silenciosamente.
            self.page.goto("https://www.linkedin.com/login", wait_until='domcontentloaded', timeout=30000)
            time.sleep(2)  # aguarda JS renderizar o formulário após DOM pronto
            print(f"  → URL após goto: {self.page.url}")

            # Aguarda campo de email aparecer no DOM
            try:
                self.page.wait_for_selector(
                    "input[autocomplete='username webauthn'], #username, input[type='email']",
                    timeout=15000, state='attached'
                )
            except Exception:
                time.sleep(3)

            # Preenche email com page.click + page.type (eventos de teclado reais)
            email_sel = None
            for sel in [
                "input[autocomplete='username webauthn']",
                "#username",
                "input[name='session_key']",
                "input[type='email']",
            ]:
                if self.page.locator(sel).count() > 0:
                    email_sel = sel
                    break

            if not email_sel:
                print(f"  ✗ Não encontrou campo de email. URL: {self.page.url}")
                return False

            self.page.click(email_sel)
            self.page.type(email_sel, linkedin_email)
            print(f"  ✓ Email preenchido ({email_sel})")
            time.sleep(0.5)

            # Tab para o campo de senha (evita problemas de seletor com React)
            self.page.keyboard.press("Tab")
            time.sleep(0.4)

            # Verifica se o foco está em um campo de senha
            active_type = self.page.evaluate("() => document.activeElement ? document.activeElement.type : ''")
            print(f"  → Campo ativo após Tab: type='{active_type}'")

            if active_type == 'password':
                self.page.keyboard.type(linkedin_password)
                print("  ✓ Senha preenchida (via Tab)")
            else:
                # Fallback: clica diretamente no campo de senha
                print("  → Tab não chegou ao campo de senha, tentando seletor direto...")
                pass_filled = False
                for sel in [
                    "input[autocomplete='current-password']",
                    "input[type='password']",
                ]:
                    try:
                        count = self.page.locator(sel).count()
                        print(f"  → Seletor '{sel}': {count} elemento(s)")
                        if count > 0:
                            self.page.click(sel)
                            self.page.type(sel, linkedin_password)
                            pass_filled = True
                            print(f"  ✓ Senha preenchida ({sel})")
                            break
                    except Exception as e:
                        print(f"  ✗ Erro no seletor '{sel}': {e}")
                        continue

                if not pass_filled:
                    print("  ✗ Não encontrou campo de senha")
                    return False

            time.sleep(0.5)

            # Submete o formulário via Enter (funciona em qualquer versão da página)
            self.page.keyboard.press("Enter")
            print("  ✓ Formulário submetido (Enter)")
            
            # Wait for navigation/response
            time.sleep(5)
            
            # DETECÇÃO DE CHALLENGE/CAPTCHA: LinkedIn pode pedir validação humana
            # Verificar antes do 2FA para dar prioridade ao Challenge
            current_url = self.page.url.lower()
            page_text = self.page.content().lower()
            page_visible_text = self.page.inner_text('body').lower() if self.page else ""
            
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
            
            has_challenge = any(indicator in page_text or indicator in page_visible_text or indicator in current_url for indicator in challenge_indicators)
            
            # Verificar seletores específicos de Challenge
            if not has_challenge:
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
                            has_challenge = True
                            break
                    except:
                        continue
            
            if has_challenge:
                print("\n" + "="*60)
                print("  ⚠ LinkedIn Challenge/Captcha detectado!")
                print("  → MODO INTERATIVO: O script está pausado para você resolver manualmente.")
                print("  → Se aparecer imagens para selecionar ou bonequinho para girar, faça isso agora na janela do navegador.")
                print("  → Após resolver o desafio e chegar no Feed do LinkedIn, volte aqui e pressione ENTER...")
                print("="*60)
                input("\n  👤 Resolva o Captcha/Challenge no navegador. Quando estiver no Feed, pressione ENTER aqui para continuar... ")
                print("  ✓ Continuando após resolução manual...")
                # Aguardar um pouco após resolução para garantir que a página processou
                time.sleep(2)
                # Re-captura estado da página após captcha para evitar falso-positivo de 2FA
                current_url = self.page.url.lower()
                page_text = self.page.content().lower()
                page_visible_text = self.page.inner_text('body').lower() if self.page else ""

            # Check for 2FA challenge
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
                print("  → Após aprovar o 2FA e chegar no Feed do LinkedIn, volte aqui e pressione ENTER...")
                print("="*60)
                input("\n  👤 Aprove o 2FA no celular. Quando estiver no Feed, pressione ENTER aqui para continuar... ")
                
                # Aguardar um pouco após input para garantir que o 2FA foi processado
                time.sleep(3)
            
            # VERIFICAÇÃO PASSIVA: Verificar URL atual sem navegar (evita interferir com a página)
            # Não chamar is_logged_in() aqui pois ele faz page.goto() que pode interferir
            try:
                final_url = self.page.url.lower()
                final_page_text = self.page.inner_text('body').lower() if self.page else ""
                
                # Verificar se está no Feed (indicador de login bem-sucedido)
                feed_indicators = ['/feed', 'linkedin.com/feed', 'feed-shared-update']
                is_on_feed = any(indicator in final_url for indicator in feed_indicators)
                
                # Verificar se não está mais na página de login/verificação
                login_indicators = ['/login', '/signin', 'verify', 'challenge', '2fa']
                is_not_on_login = not any(indicator in final_url for indicator in login_indicators)
                
                # Verificar elementos do Feed na página atual (sem navegar)
                try:
                    feed_elements = self.page.query_selector('article[class*="feed-shared-update"], .feed-shared-update-v2')
                    has_feed_elements = feed_elements is not None
                except:
                    has_feed_elements = False
                
                if (is_on_feed or (is_not_on_login and has_feed_elements)) and 'linkedin.com' in final_url:
                    print("  ✓ Login bem-sucedido! Detectado Feed do LinkedIn.")
                    return True
                else:
                    print("  ⚠ Verificando status do login...")
                    # Tentar verificação passiva adicional
                    time.sleep(2)
                    final_url_check = self.page.url.lower()
                    if '/feed' in final_url_check or 'linkedin.com/feed' in final_url_check:
                        print("  ✓ Login bem-sucedido! Detectado Feed do LinkedIn.")
                        return True
                    else:
                        print("  ⚠ Não foi possível confirmar automaticamente se o login foi concluído.")
                        print("  → Se você está vendo o Feed do LinkedIn no navegador, o login foi bem-sucedido.")
                        print("  → O robô continuará assumindo que o login foi concluído.")
                        return True  # Assumir sucesso se chegou até aqui após input()
            except Exception as check_error:
                print(f"  ⚠ Erro ao verificar status do login: {check_error}")
                print("  → Assumindo que o login foi concluído (você confirmou via ENTER).")
                return True  # Assumir sucesso se chegou até aqui após input()
                
        except Exception as e:
            print(f"  ✗ Error during login: {e}")
            return False
    
    def close_browser(self):
        """Close browser"""
        if hasattr(self, 'context') and self.context:
            try:
                self.context.close()
            except:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except:
                pass
    
    def detect_language(self, text: str) -> str:
        """Detect if text is Portuguese, English, or Spanish (so email follows post language)"""
        pt_words = ['estamos', 'contratando', 'vaga', 'oportunidade', 'empresa', 'trabalho',
                    'remoto', 'home office', 'salário', 'benefícios', 'candidatar', 'desenvolvedor']
        en_words = ['hiring', 'we are', 'position', 'opportunity', 'company', 'work',
                    'remote', 'salary', 'benefits', 'apply', 'developer']
        es_words = ['estamos', 'buscamos', 'oportunidad', 'empresa', 'trabajo', 'remoto',
                    'envíe', 'envie', 'curriculum', 'cv', 'desarrollador', 'desarrolladora', 'vacante']
        text_lower = text.lower()
        pt_count = sum(1 for word in pt_words if word in text_lower)
        en_count = sum(1 for word in en_words if word in text_lower)
        es_count = sum(1 for word in es_words if word in text_lower)
        if 'desarrollador' in text_lower or 'hashtag#desarrollador' in text_lower:
            es_count += 2
        if pt_count > en_count and pt_count >= es_count:
            return 'pt'
        if es_count > en_count and es_count >= pt_count:
            return 'es'
        if en_count > 0 or not (pt_count or es_count):
            return 'en'
        try:
            prompt = f"Detect the language of this text. Return only 'pt', 'en', or 'es':\n\n{text[:200]}"
            response = self.brain.smart_ai.generate_content(prompt)
            lang = response.strip().lower()[:2]
            return lang if lang in ['pt', 'en', 'es'] else 'en'
        except Exception:
            return 'en'
    
    def extract_job_code(self, text: str) -> Optional[str]:
        """Extract recruiter job identification codes from post text.
        Matches patterns like: IDENTIFICAÇÃO ENGFULLJAVA - 01, ID: REQ-2024, Código: JAVA-SR-01
        """
        patterns = [
            # Explicit label + code (most reliable)
            r'(?:identifica[çc][aã]o|c[oó]digo\s+da\s+vaga|c[oó]digo|identificador|code|c[oó]d\.?|ref\.?|id\.?)\s*[:\-–]?\s*([A-Z][A-Z0-9\-_\.]{2,}(?:\s*[\-–]\s*\d{1,4})?)',
            # Bare code on its own line: uppercase word(s) + dash + number
            r'(?:^|\n)\s*([A-Z]{3,}[A-Z0-9_]*\s*[\-–]\s*\d{1,4})\s*(?:\n|$)',
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                code = m.group(1).strip()
                if code and len(code) >= 4:
                    return code
        return None

    def extract_email_from_post(self, text: str) -> Optional[str]:
        """
        Extract email from post text using robust regex (Deep Scan)
        Supports multiple obfuscation patterns:
        - felipe [at] gmail.com
        - felipe(at)gmail.com
        - felipe arroba gmail.com
        - felipe [at] gmail [dot] com
        """
        if not text:
            return None
        
        # Pré-processamento: Remove caracteres invisíveis e normaliza espaços
        # LinkedIn sometimes inserts invisible characters to hinder scrapers
        # Remove zero-width spaces, non-breaking spaces, and other invisible chars
        text = ''.join(char for char in text if unicodedata.category(char)[0] != 'C' or char in '\n\t')
        # Normaliza quebras de linha e espaços
        text = re.sub(r'\s+', ' ', text)  # Remove quebras de linha excessivas e normaliza espaços
        text = text.strip()
        
        # 1. Normaliza variações comuns de [at], (at), {at}, arroba, @
        # Pattern: felipe [at] gmail.com, felipe(at)gmail.com, felipe arroba gmail.com
        text = re.sub(r'\s*[\[\(\{]at[\]\)\}]\s*', '@', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+arroba\s+', '@', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\{at\}\s*', '@', text, flags=re.IGNORECASE)
        
        # 2. Normaliza variações de [dot], (dot), {dot}, ponto
        # Pattern: felipe [dot] gmail [dot] com
        text = re.sub(r'\s*[\[\(\{]dot[\]\)\}]\s*', '.', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+ponto\s+', '.', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\(dot\)\s*', '.', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\[dot\]\s*', '.', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\{dot\}\s*', '.', text, flags=re.IGNORECASE)
        
        # 3. Regex avançado - Captura e-mails mesmo grudados em emojis, aspas ou pontos
        # Não usa \b no início para capturar emails grudados em caracteres
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        
        emails = re.findall(email_pattern, text)
        
        if emails:
            # Limpa possíveis caracteres de pontuação que o regex capturou no final
            cleaned_emails = [email.strip('.,!?;:()[]{}"\'') for email in emails]
            
            # SANITIZAÇÃO DE SUFIXOS: Remove palavras comuns do LinkedIn coladas no final
            # Exemplos: email@domain.comhashtag, email@domain.comSubject, email@domain.comContact
            linkedin_artifacts = ['hashtag', 'subject', 'contact', 'via', 'post', 'linkedin', 'share', 'comment', 'like', 'follow']
            sanitized_emails = []
            for email in cleaned_emails:
                email_lower = email.lower()
                for artifact in linkedin_artifacts:
                    if email_lower.endswith(artifact):
                        # Remove artefato do final
                        email = email[:len(email) - len(artifact)]
                        break
                sanitized_emails.append(email)
            
            # PÓS-PROCESSAMENTO: Limpeza de rabo de e-mail e validação de TLD
            # Remove qualquer caractere alfanumérico após o TLD válido
            valid_tlds = ['com', 'io', 'net', 'org', 'edu', 'gov', 'br', 'co.uk', 'com.br', 'co', 'in', 'de', 'fr', 'es', 'it', 'au', 'ca', 'mx', 'jp', 'cn', 'ru', 'uk', 'us', 'info', 'biz', 'me', 'tv', 'cc', 'ws', 'name', 'mobi', 'asia', 'tel', 'pro', 'travel', 'jobs', 'xxx', 'aero', 'museum', 'coop', 'mil']
            validated_emails = []
            for email in sanitized_emails:
                email_lower = email.lower()
                parts = email_lower.split('.')
                
                if len(parts) >= 2:
                    tld = parts[-1]
                    tld_compound = None
                    if len(parts) >= 3:
                        tld_compound = f"{parts[-2]}.{parts[-1]}"
                    
                    # Verifica TLD válido (composto primeiro, depois simples)
                    valid_tld = None
                    if tld_compound and tld_compound in valid_tlds:
                        valid_tld = tld_compound
                        # Remove qualquer caractere alfanumérico após o TLD composto
                        # Ex: email@domain.co.ukhashtag -> email@domain.co.uk
                        tld_end_pos = email_lower.rfind(f".{valid_tld}")
                        if tld_end_pos != -1:
                            expected_end = tld_end_pos + len(f".{valid_tld}")
                            if len(email_lower) > expected_end:
                                # Remove caracteres após o TLD
                                email = email[:expected_end]
                    elif tld in valid_tlds:
                        valid_tld = tld
                        # Remove qualquer caractere alfanumérico após o TLD simples
                        # Ex: email@domain.comhashtag -> email@domain.com
                        tld_end_pos = email_lower.rfind(f".{valid_tld}")
                        if tld_end_pos != -1:
                            expected_end = tld_end_pos + len(f".{valid_tld}")
                            if len(email_lower) > expected_end:
                                # Remove caracteres após o TLD
                                email = email[:expected_end]
                    
                    # Só adiciona se encontrou TLD válido
                    if valid_tld:
                        validated_emails.append(email)
            
            # Remove duplicatas mantendo ordem
            seen = set()
            unique_emails = []
            for email in validated_emails:
                email_lower = email.lower()
                if email_lower not in seen:
                    seen.add(email_lower)
                    unique_emails.append(email)
            
            # Filter out common non-contact emails
            valid_emails = [e for e in unique_emails if not any(skip in e.lower() 
                           for skip in ['noreply', 'no-reply', 'linkedin', 'notification', 'example.com', 'test.com', 'sample.com'])]
            
            return valid_emails[0] if valid_emails else None
        
        return None
    
    def extract_emails_robust(self, text: str) -> List[str]:
        """
        Extract multiple emails from text using robust regex (returns list)
        Used for deduplication across posts
        Supports all obfuscation patterns like extract_email_from_post
        Includes sanitization of LinkedIn artifacts (hashtag, Subject, Contact, etc.)
        """
        if not text:
            return []
        
        # Pré-processamento: Remove caracteres invisíveis
        text = ''.join(char for char in text if unicodedata.category(char)[0] != 'C' or char in '\n\t')
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        # Normaliza todas as variações de [at], (at), arroba
        text = re.sub(r'\s*[\[\(\{]at[\]\)\}]\s*', '@', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+arroba\s+', '@', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\{at\}\s*', '@', text, flags=re.IGNORECASE)
        
        # Normaliza todas as variações de [dot], (dot), ponto
        text = re.sub(r'\s*[\[\(\{]dot[\]\)\}]\s*', '.', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+ponto\s+', '.', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\(dot\)\s*', '.', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\[dot\]\s*', '.', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\{dot\}\s*', '.', text, flags=re.IGNORECASE)
        
        # Regex avançado
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, text)
        
        if emails:
            # Limpa pontuação
            cleaned_emails = [email.strip('.,!?;:()[]{}"\'') for email in emails]
            
            # SANITIZAÇÃO DE SUFIXOS: Remove palavras comuns do LinkedIn coladas no final
            # Exemplos: email@domain.comhashtag, email@domain.comSubject, email@domain.comContact
            linkedin_artifacts = ['hashtag', 'subject', 'contact', 'via', 'post', 'linkedin', 'share', 'comment', 'like', 'follow']
            sanitized_emails = []
            for email in cleaned_emails:
                # Remove artefatos do LinkedIn do final do email
                email_lower = email.lower()
                for artifact in linkedin_artifacts:
                    # Remove se estiver colado no final (ex: .comhashtag -> .com)
                    if email_lower.endswith(artifact):
                        # Tenta encontrar o TLD válido antes do artefato
                        # Ex: email@domain.comhashtag -> email@domain.com
                        tld_pattern = r'\.(com|io|net|org|edu|gov|br|co\.uk|com\.br|co|in|de|fr|es|it|au|ca|mx|jp|cn|ru|uk|us)(?:' + artifact + ')?$'
                        match = re.search(tld_pattern, email_lower)
                        if match:
                            # Remove o artefato, mantendo o TLD
                            email = email[:len(email) - len(artifact)]
                            break
                        else:
                            # Se não encontrar TLD válido, tenta remover o artefato diretamente
                            if email_lower.endswith(artifact):
                                email = email[:len(email) - len(artifact)]
                                break
                
                sanitized_emails.append(email)
            
            # PÓS-PROCESSAMENTO: Limpeza de rabo de e-mail e validação de TLD
            # Remove qualquer caractere alfanumérico após o TLD válido
            valid_tlds = ['com', 'io', 'net', 'org', 'edu', 'gov', 'br', 'co.uk', 'com.br', 'co', 'in', 'de', 'fr', 'es', 'it', 'au', 'ca', 'mx', 'jp', 'cn', 'ru', 'uk', 'us', 'info', 'biz', 'me', 'tv', 'cc', 'ws', 'name', 'mobi', 'asia', 'tel', 'pro', 'travel', 'jobs', 'xxx', 'aero', 'museum', 'coop', 'mil']
            validated_emails = []
            for email in sanitized_emails:
                email_lower = email.lower()
                parts = email_lower.split('.')
                
                if len(parts) >= 2:
                    tld = parts[-1]
                    tld_compound = None
                    if len(parts) >= 3:
                        tld_compound = f"{parts[-2]}.{parts[-1]}"
                    
                    # Verifica TLD válido (composto primeiro, depois simples)
                    valid_tld = None
                    if tld_compound and tld_compound in valid_tlds:
                        valid_tld = tld_compound
                        # Remove qualquer caractere alfanumérico após o TLD composto
                        # Ex: email@domain.co.ukhashtag -> email@domain.co.uk
                        tld_end_pos = email_lower.rfind(f".{valid_tld}")
                        if tld_end_pos != -1:
                            expected_end = tld_end_pos + len(f".{valid_tld}")
                            if len(email_lower) > expected_end:
                                # Remove caracteres após o TLD
                                email = email[:expected_end]
                    elif tld in valid_tlds:
                        valid_tld = tld
                        # Remove qualquer caractere alfanumérico após o TLD simples
                        # Ex: email@domain.comhashtag -> email@domain.com
                        tld_end_pos = email_lower.rfind(f".{valid_tld}")
                        if tld_end_pos != -1:
                            expected_end = tld_end_pos + len(f".{valid_tld}")
                            if len(email_lower) > expected_end:
                                # Remove caracteres após o TLD
                                email = email[:expected_end]
                    
                    # Só adiciona se encontrou TLD válido
                    if valid_tld:
                        validated_emails.append(email)
            
            # Remove duplicatas
            seen = set()
            unique_emails = []
            for email in validated_emails:
                email_lower = email.lower()
                if email_lower not in seen:
                    seen.add(email_lower)
                    unique_emails.append(email)
            
            # Filter invalid emails (noreply, linkedin, etc.)
            valid_emails = [e for e in unique_emails if not any(skip in e.lower() 
                           for skip in ['noreply', 'no-reply', 'linkedin', 'notification', 'example.com', 'test.com', 'sample.com'])]
            
            return valid_emails
        
        return []
    
    def extract_external_links(self, text: str) -> List[str]:
        """Extract external application links from post text."""
        link_patterns = [
            # Known ATS / form platforms
            r'https?://(?:docs\.google\.com/forms|forms\.gle|typeform\.com|ashbyhq\.com|greenhouse\.io|lever\.co|workable\.com|breezy\.hr|bamboohr\.com|smartrecruiters\.com|jobvite\.com|icims\.com|recruitee\.com|airtable\.com)[^\s\)\]>]+',
            # LinkedIn short links that appear as text in posts
            r'https?://lnkd\.in/[^\s\)\]>]+',
            # Any URL that contains job/apply/hiring keywords
            r'https?://[^\s\)\]>]+(?:apply|inscreva|aplicar|candidatar|vagas|jobs|careers|hiring|job)[^\s\)\]>]*',
            # Broad catch-all: any https URL that is not a LinkedIn internal URL
            r'https?://(?!(?:www\.)?linkedin\.com)[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}/[^\s\)\]>]{3,}',
        ]

        seen = set()
        links = []
        for pattern in link_patterns:
            for url in re.findall(pattern, text, re.IGNORECASE):
                url = url.rstrip('.,;:')
                if url not in seen:
                    seen.add(url)
                    links.append(url)

        return links
    
    def _get_post_url_via_menu(self, post_card) -> Optional[str]:
        """Click the post's overflow menu → 'Copy link to post' → read clipboard.
        Returns the canonical LinkedIn post URL or None if it can't be obtained."""
        try:
            btn = post_card.query_selector(
                'button[aria-label*="control menu for post"],'
                'button[aria-label*="Open control menu"],'
                'button[aria-label*="More actions for this post"]'
            )
            if not btn:
                return None
            btn.click()
            self.page.wait_for_timeout(400)
            # Find "Copy link to post" (text varies slightly by language)
            item = None
            for sel in [
                '[role="menuitem"]:has(p:text("Copy link to post"))',
                '[role="menuitem"]:has-text("Copy link to post")',
                '[role="menuitem"]:has-text("Copiar link para o post")',
                '[role="menuitem"]:has-text("Copiar enlace del post")',
            ]:
                try:
                    item = self.page.query_selector(sel)
                    if item:
                        break
                except Exception:
                    continue
            if not item:
                self.page.keyboard.press("Escape")
                return None
            item.click()
            self.page.wait_for_timeout(300)
            # Read clipboard (requires clipboard-read permission granted at context level)
            url = self.page.evaluate("async () => { try { return await navigator.clipboard.readText(); } catch(e) { return null; } }")
            if url and isinstance(url, str) and 'linkedin.com' in url:
                return url.strip()
            return None
        except Exception:
            try:
                self.page.keyboard.press("Escape")
            except Exception:
                pass
            return None

    def search_posts_advanced(self, boolean_query: str, max_posts: int = 50, seen_post_ids: set = None) -> List[Dict]:
        """
        Advanced boolean search for LinkedIn posts (SNIPER MODE)
        
        Args:
            boolean_query: Boolean query string (e.g., '("javascript" OR "react") AND "hiring" AND "remoto"')
            max_posts: Maximum posts to extract PER TECHNOLOGY (validated for safety, max 500)
            seen_post_ids: Set of post IDs already processed (for deduplication across queries)
        
        Safety: If max_posts > 500, it's capped at 500 to prevent browser crashes
            
        Returns:
            List of post dictionaries with extracted information
        """
        if not self.page:
            if not self.start_browser(headless=False):
                return []
        
        print(f"\n  🎯 LinkedIn Post Sniper Mode")
        print(f"  🔍 Boolean Query: {boolean_query}")
        
        # Initialize cache in memory for this session (if not provided)
        if seen_post_ids is None:
            seen_post_ids = set()
        
        if max_posts > 1000:
            max_posts = 1000
        
        all_posts = []
        
        # Captura de Performance: Inicia timer para medir tempo total da busca
        import time as time_module
        search_start_time = time_module.time()
        
        # So finally block can always reference these (e.g. when navigation fails before the loop)
        processed_count = 0
        skipped_cache = 0
        skipped_no_contact = 0
        skipped_duplicate_email = 0
        
        try:
            # Navigate to LinkedIn search with boolean query (increased timeout for slow connections)
            # Improved sanitization using urllib.parse.quote for proper URL encoding
            from urllib.parse import quote
            # Encode the query: (technology) AND "hiring" AND (location or user query)
            encoded_query = quote(boolean_query, safe='()"')
            # sortBy must be quoted "date_posted" for Latest to work; sid optional (e.g. sid=9.l)
            search_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&origin=FACETED_SEARCH&sid=9.l&sortBy=%5B%22date_posted%22%5D"
            
            # RETRY LÓGICO: Se page.goto der Timeout, espera 10s e tenta novamente uma vez
            max_retries = 2
            retry_count = 0
            navigation_success = False
            
            while retry_count < max_retries and not navigation_success:
                try:
                    self.page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
                    navigation_success = True
                except Exception as nav_error:
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"    ⚠ Navigation timeout (attempt {retry_count}/{max_retries}). Waiting 10s before retry...")
                        time.sleep(10)  # Wait 10 seconds before retry
                    else:
                        print(f"    ✗ Navigation failed after {max_retries} attempts: {nav_error}")
                        raise
            
            # Patience for boolean query rendering (LinkedIn needs time)
            self.page.wait_for_timeout(5000)  # Wait 5 seconds for boolean query results (increased from 3s)
            time.sleep(2)  # Additional delay
            
            # 1) Filtrar por Posts (não pessoas, jobs, etc.)
            # Scope to the search facets/pills area to avoid accidentally clicking
            # "view all posts" links inside post cards.
            try:
                posts_filter = self.page.query_selector(
                    # SDUI pill selector
                    "li[data-test-pill-name='Posts'], "
                    # scoped to facet containers (search results header area)
                    ".search-reusables__filter-trigger-and-dropdown button:has-text('Posts'), "
                    ".search-reusables__primary-filter button:has-text('Posts'), "
                    # legacy
                    "button[aria-label='Posts filter'], button[aria-label*='Filtrar por Posts']"
                )
                if posts_filter:
                    if posts_filter.is_visible():
                        posts_filter.click()
                    else:
                        parent = posts_filter.evaluate_handle('el => el.closest("button, a, li")')
                        if parent:
                            parent.click()
                    time.sleep(3)
                    print(f"    ✓ Filtered to Posts only")
                else:
                    # Broader fallback — only if nothing else matched
                    posts_filter = self.page.query_selector("button:has-text('Posts'), a:has-text('Posts')")
                    if posts_filter and posts_filter.is_visible():
                        posts_filter.click()
                        time.sleep(3)
                        print(f"    ✓ Filtered to Posts only (fallback)")
            except Exception as e:
                print(f"    ⚠ Could not click Posts filter: {e}")

            # 2) Sort by Latest (abrir Sort by → clicar Latest → Show results)
            try:
                sort_btn = self.page.locator("button:has-text('Sort by')").first
                if not sort_btn.is_visible(timeout=3000):
                    print("    ⚠ Sort by: botão não encontrado")
                else:
                    sort_btn.click()
                    # Esperar dropdown: radio ou label do LinkedIn (id sortBy-date_posted)
                    try:
                        self.page.wait_for_selector("#sortBy-date_posted, label[for='sortBy-date_posted']", state="visible", timeout=6000)
                    except Exception:
                        pass
                    self.page.wait_for_timeout(1000)
                    latest_clicked = False
                    # Clicar no label (associa ao radio) ou no li que contém "Latest"
                    for selector in [
                        "label[for='sortBy-date_posted']",
                        "#sortBy-date_posted",
                        "li.search-reusables__collection-values-item input[value='date_posted']",
                    ]:
                        el = self.page.query_selector(selector)
                        if el:
                            try:
                                el.scroll_into_view_if_needed()
                                self.page.wait_for_timeout(300)
                                el.click(force=True)
                                latest_clicked = True
                                break
                            except Exception:
                                continue
                    if not latest_clicked:
                        # Fallback: locator por texto "Latest" dentro do painel
                        latest_opt = self.page.get_by_text("Latest", exact=True)
                        if latest_opt.is_visible(timeout=2000):
                            latest_opt.click(force=True)
                            latest_clicked = True
                    if latest_clicked:
                        self.page.wait_for_timeout(800)
                        show_btn = self.page.get_by_role("button", name="Show results")
                        if show_btn.count() == 0:
                            show_btn = self.page.locator("button:has-text('Show results'), button:has-text('Aplicar')").first
                        if show_btn.count() > 0 and show_btn.first.is_visible(timeout=2000):
                            show_btn.first.click()
                            time.sleep(2)
                            print("    ✓ Sorted by Latest")
                        else:
                            print("    ✓ Sorted by Latest (opção clicada)")
                    else:
                        print("    ⚠ Sort by Latest: opção não encontrada")
            except Exception as e:
                print(f"    ⚠ Sort by Latest: {e}")
            
            # POST-BY-POST: Scroll to load posts (LIMITED to max_posts to avoid freeze)
            # Scale scroll count with max_posts so 500 requests actually load ~500 posts
            print(f"    📜 Scrolling to load posts (max: {max_posts})...")
            previous_post_count = 0
            scroll_attempts = 0
            # ~1 scroll per 10 posts, capped at 120 for 1000-post runs
            max_scrolls = min(120, max(20, (max_posts // 10) + 10))

            # Press Escape once upfront to close any dialog that may already be open
            try:
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(300)
            except Exception:
                pass

            while scroll_attempts < max_scrolls:
                # Dismiss any open dialog (reposts panel, reactions, etc.) before scrolling
                try:
                    self.page.evaluate("""() => {
                        const dlg = document.querySelector('[role="dialog"]');
                        if (!dlg) return;
                        const btn = dlg.querySelector(
                            'button[aria-label="Dismiss"], button[aria-label="Close"],' +
                            'button[aria-label="Fechar"], button[aria-label="Dispensar"]'
                        );
                        if (btn) { btn.click(); return; }
                        // fallback: press Escape
                        document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
                    }""")
                except Exception:
                    pass

                # Scroll up ~2 viewports so the infinite-scroll sentinel LEAVES the viewport,
                # then jump to the bottom so it RE-ENTERS — this re-fires the IntersectionObserver
                # that LinkedIn uses to trigger loading the next batch of posts.
                self.page.evaluate("""() => {
                    const h = document.body.scrollHeight;
                    const vh = window.innerHeight;
                    window.scrollTo(0, Math.max(0, h - vh * 2));
                }""")
                self.page.wait_for_timeout(400)
                self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                # Also scrollIntoView on the last post so the sentinel right after it is visible
                self.page.evaluate("""() => {
                    const posts = document.querySelectorAll(
                        'div[role="listitem"][componentkey*="FeedType_FLAGSHIP_SEARCH"]'
                    );
                    if (posts.length > 0) posts[posts.length - 1].scrollIntoView({block: 'end'});
                }""")
                self.page.wait_for_timeout(5000)
                time.sleep(0.5)

                # Count unique post containers using multiple strategies.
                # Primary: componentkey*="FeedType_FLAGSHIP_SEARCH" — every LinkedIn SDUI
                # search result has this attribute on its listitem wrapper.
                try:
                    current_post_count = self.page.evaluate("""() => {
                        // 1) Direct SDUI search-result containers (most reliable)
                        let nodes = document.querySelectorAll(
                            'div[role="listitem"][componentkey*="FeedType_FLAGSHIP_SEARCH"]'
                        );
                        if (nodes.length) return nodes.length;

                        // 2) Any SDUI listitem with a componentkey outside a dialog
                        nodes = Array.from(document.querySelectorAll('div[role="listitem"][componentkey]'))
                            .filter(el => !el.closest('[role="dialog"]'));
                        if (nodes.length) return nodes.length;

                        // 3) expandable-text-box anchor (only set on posts with text)
                        const seen = new Set();
                        for (const b of document.querySelectorAll('[data-testid="expandable-text-box"]')) {
                            const c = b.closest('[role="listitem"]');
                            if (c && !c.closest('[role="dialog"]')) seen.add(c);
                        }
                        if (seen.size) return seen.size;

                        // 4) Legacy pre-SDUI class
                        return document.querySelectorAll('div.feed-shared-update-v2').length;
                    }""")
                except Exception:
                    current_post_count = 0
                
                # If no new posts loaded, increment stall counter; exit after 5 stalls
                if current_post_count == previous_post_count:
                    scroll_attempts += 1
                    if scroll_attempts >= 5:
                        break
                else:
                    scroll_attempts = 0  # Reset counter when new posts appear
                
                # OTIMIZAÇÃO: Para se já carregou max_posts (evita freeze do LinkedIn)
                if current_post_count >= max_posts:
                    print(f"      ✓ Reached max_posts limit ({max_posts}). Stopping scroll.")
                    break
                
                previous_post_count = current_post_count
                
                # LOG DE TELEMETRIA DE SCROLL: A cada 10 posts carregados
                if current_post_count % 10 == 0 and current_post_count > 0:
                    print(f"    [LinkedIn] Scroll progress: {current_post_count}/{max_posts} posts loaded...")
                else:
                    print(f"      Loaded {current_post_count} posts so far...")
            
            print(f"    ✓ Finished scrolling. Total posts loaded: {previous_post_count}")
            
            # Dismiss any lingering dialog before tagging posts
            try:
                self.page.evaluate("""() => {
                    const dlg = document.querySelector('[role="dialog"]');
                    if (!dlg) return;
                    const btn = dlg.querySelector(
                        'button[aria-label="Dismiss"], button[aria-label="Close"],' +
                        'button[aria-label="Fechar"], button[aria-label="Dispensar"]'
                    );
                    if (btn) { btn.click(); return; }
                    document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
                }""")
                self.page.wait_for_timeout(500)
            except Exception:
                pass

            # Tag each unique search-result container with data-post-li.
            # Multi-method: primary uses componentkey (reliable SDUI attribute),
            # fallbacks handle edge cases and older LinkedIn layouts.
            try:
                self.page.evaluate("""() => {
                    const seen = new Set();
                    let idx = 0;

                    function tag(el) {
                        if (!seen.has(el) && !el.closest('[role="dialog"]')) {
                            el.setAttribute('data-post-li', String(idx++));
                            seen.add(el);
                        }
                    }

                    // 1) Direct SDUI search-result containers
                    document.querySelectorAll(
                        'div[role="listitem"][componentkey*="FeedType_FLAGSHIP_SEARCH"]'
                    ).forEach(tag);

                    // 2) Any SDUI listitem with componentkey (broader, outside dialogs)
                    if (idx === 0) {
                        document.querySelectorAll('div[role="listitem"][componentkey]')
                            .forEach(el => { if (!el.closest('[role="dialog"]')) tag(el); });
                    }

                    // 3) expandable-text-box anchor
                    if (idx === 0) {
                        for (const b of document.querySelectorAll('[data-testid="expandable-text-box"]')) {
                            const c = b.closest('[role="listitem"]');
                            if (c) tag(c);
                        }
                    }

                    // 4) Legacy pre-SDUI class
                    if (idx === 0) {
                        document.querySelectorAll('div.feed-shared-update-v2').forEach(tag);
                    }
                }""")
                posts_found = self.page.query_selector_all('[data-post-li]')
                print(f"    ✓ Tagged {len(posts_found)} post containers for processing")
            except Exception as tag_err:
                print(f"    ⚠ Tagging failed: {tag_err}")
                posts_found = []

            # Only posts we actually process (not skipped by cache or no contact) count toward the total
            processed_count = 0
            skipped_cache = 0
            skipped_no_contact = 0
            seen_emails_this_run = set()  # Dedupe: same email in multiple posts -> add only once
            skipped_duplicate_email = 0
            # Single DB connection for the whole run (avoids "Database initialized" spam per post)
            _db = None
            try:
                from .database import DatabaseManager
                _db = DatabaseManager("jobs.db")
            except Exception:
                pass
            print(f"    📋 Scanning {len(posts_found)} posts (only processed posts count toward total)...")
            
            # Process each post: Expand + Extract via HTML Deep Scan
            for i, post_card in enumerate(posts_found[:max_posts]):
                try:
                    # STEP 1: Expand truncated text within this post container.
                    # LinkedIn SDUI marks the expand button with data-testid="expandable-text-button"
                    # (lives inside the text-box span). Click all of them, then fall back to
                    # legacy class-based buttons for older post formats.
                    try:
                        post_card.evaluate("""el => {
                            // Primary: SDUI stable selector
                            el.querySelectorAll('[data-testid="expandable-text-button"]').forEach(btn => btn.click());
                            // Legacy fallback
                            const legacy = el.querySelector(
                                '.feed-shared-inline-show-more-text__button, ' +
                                'button[class*="show-more"], .inline-show-more-text__link'
                            );
                            if (legacy) legacy.click();
                        }""")
                        time.sleep(0.5)
                    except Exception as expand_error:
                        pass
                    
                    # STEP 2: Extract text/HTML — post_card is the <li> container.
                    # Combine all expandable-text-box elements inside it so we capture
                    # both the resharer's comment and the embedded original post text.
                    try:
                        raw_html = None
                        raw_text = None

                        # Method 1: concatenate HTML of all text-boxes in this container
                        try:
                            raw_html = post_card.evaluate("""el => {
                                const boxes = el.querySelectorAll('[data-testid="expandable-text-box"]');
                                if (boxes.length) return Array.from(boxes).map(b => b.innerHTML || '').join(' ').trim();
                                return el.innerHTML || '';
                            }""")
                        except:
                            pass

                        # Method 2: concatenate plain text of all text-boxes
                        if not raw_html or len(raw_html) < 10:
                            try:
                                raw_text = post_card.evaluate("""el => {
                                    const boxes = el.querySelectorAll('[data-testid="expandable-text-box"]');
                                    if (boxes.length) return Array.from(boxes).map(b => b.innerText || b.textContent || '').join('\\n\\n').trim();
                                    return el.innerText || el.textContent || '';
                                }""")
                            except:
                                pass

                        # Method 3: full container innerHTML fallback
                        if (not raw_html or len(raw_html) < 10) and (not raw_text or len(raw_text) < 10):
                            try:
                                result = post_card.evaluate('el => ({html: el.innerHTML || "", text: el.innerText || el.textContent || ""})')
                                raw_html = result.get('html') or raw_html
                                raw_text = result.get('text') or raw_text
                            except:
                                pass
                        
                        # Process HTML: Clean email variations BEFORE any AI call
                        if raw_html:
                            # Clean email variations in HTML: [at], (at), arroba, {at} -> @
                            raw_html = re.sub(r'\s*[\[\(\{]at[\]\)\}]\s*', '@', raw_html, flags=re.IGNORECASE)
                            raw_html = re.sub(r'\s+arroba\s+', '@', raw_html, flags=re.IGNORECASE)
                            raw_html = re.sub(r'\s*\(at\)\s*', '@', raw_html, flags=re.IGNORECASE)
                            raw_html = re.sub(r'\s*\[at\]\s*', '@', raw_html, flags=re.IGNORECASE)
                            raw_html = re.sub(r'\s*\{at\}\s*', '@', raw_html, flags=re.IGNORECASE)
                            
                            # Clean dot variations: [dot], (dot), ponto -> .
                            raw_html = re.sub(r'\s*[\[\(\{]dot[\]\)\}]\s*', '.', raw_html, flags=re.IGNORECASE)
                            raw_html = re.sub(r'\s+ponto\s+', '.', raw_html, flags=re.IGNORECASE)
                            raw_html = re.sub(r'\s*\(dot\)\s*', '.', raw_html, flags=re.IGNORECASE)
                            raw_html = re.sub(r'\s*\[dot\]\s*', '.', raw_html, flags=re.IGNORECASE)
                            raw_html = re.sub(r'\s*\{dot\}\s*', '.', raw_html, flags=re.IGNORECASE)

                            # Decode LinkedIn safety redirect URLs so the real URL is visible in text.
                            # href="https://www.linkedin.com/safety/go/?url=ENCODED&..." -> href="DECODED"
                            def _decode_safety_url(m):
                                try:
                                    from urllib.parse import urlparse, parse_qs, unquote
                                    params = parse_qs(urlparse(m.group(0)).query)
                                    decoded = unquote(params.get('url', [''])[0])
                                    return f'href="{decoded}"' if decoded else m.group(0)
                                except Exception:
                                    return m.group(0)
                            raw_html = re.sub(
                                r'href="https?://(?:www\.)?linkedin\.com/safety/go/\?[^"]*url=[^"]*"',
                                _decode_safety_url,
                                raw_html
                            )

                            # Extract text from cleaned HTML
                            try:
                                # Use BeautifulSoup to extract text from HTML (if available)
                                try:
                                    from bs4 import BeautifulSoup
                                    soup = BeautifulSoup(raw_html, 'html.parser')
                                    raw_text = soup.get_text()
                                except ImportError:
                                    # Fallback: simple regex to remove HTML tags
                                    raw_text = re.sub(r'<[^>]+>', ' ', raw_html)
                            except:
                                raw_text = raw_html  # Use HTML as text if extraction fails
                        
                        # Clean invisible characters that LinkedIn inserts
                        if raw_text:
                            # Remove zero-width spaces, non-breaking spaces, and other invisible chars
                            raw_text = ''.join(char for char in raw_text if unicodedata.category(char)[0] != 'C' or char in '\n\t')
                            # Normalize whitespace
                            raw_text = re.sub(r'\s+', ' ', raw_text)
                            raw_text = raw_text.strip()
                        
                        if not raw_text or len(raw_text) < 10:
                            print(f"    ⚠ Post {i+1}: Texto muito curto após limpeza, pulando...")
                            continue
                    except Exception as extract_error:
                        print(f"    ⚠ Post {i+1}: Erro ao extrair texto: {extract_error}")
                        continue
                    
                    # STEP 3: Cache em memória - Evita processar o mesmo post múltiplas vezes
                    # Criar ID único do post baseado no texto (hash dos primeiros 200 chars)
                    post_id = hash(raw_text[:200])
                    post_id_short = str(abs(post_id))[:8]  # Primeiros 8 dígitos para log
                    
                    # RASTREAMENTO DE PROCESSAMENTO: Log detalhado para cada post
                    print(f"    [LinkedIn] Analisando Post ID: {post_id_short}...")
                    
                    if post_id in seen_post_ids:
                        skipped_cache += 1
                        print(f"    ⏭ Skipped (cache): already processed, skipping...")
                        continue
                    seen_post_ids.add(post_id)
                    
                    # STEP 4: Pré-filtro agressivo (economiza 90% dos tokens)
                    # Se o post não contém '@' ou 'http', não tem contato - pula completamente
                    raw_text_lower = raw_text.lower()
                    has_email_indicator = '@' in raw_text_lower
                    has_link_indicator = 'http' in raw_text_lower or 'www.' in raw_text_lower
                    
                    if not has_email_indicator and not has_link_indicator:
                        skipped_no_contact += 1
                        print(f"    [LinkedIn] Status: ⏭ Sem Contato")
                        print(f"    ⏭ Skipped (no @ or http), not counted in total")
                        continue
                    
                    processed_count += 1
                    
                    # STEP 5: Regex como Protagonista - Tenta regex PRIMEIRO (sem IA)
                    email = self.extract_email_from_post(raw_text)
                    external_links = self.extract_external_links(raw_text)
                    language = self.detect_language(raw_text)
                    
                    # Se regex encontrou email ou links, usa e pula IA (economia de tokens)
                    if email or external_links:
                        if email:
                            print(f"    [LinkedIn] Status: ✅ Email Encontrado - {email}")
                            print(f"    ✓ Post {processed_count}: Email encontrado via regex (pulou IA): {email}")
                        if external_links:
                            print(f"    [LinkedIn] Status: 🔗 Link Encontrado - {len(external_links)} link(s)")
                            print(f"    ✓ Post {processed_count}: {len(external_links)} link(s) encontrado(s) via regex (pulou IA)")
                    else:
                        # Regex não encontrou nada - verifica se há palavras-chave antes de tentar IA
                        has_email_keywords = any(keyword in raw_text_lower for keyword in ['email', 'e-mail', 'cv', 'resume', 'curriculum', 'send to', 'contact'])
                        
                        if has_email_keywords:
                            # Post menciona email mas regex não encontrou - tenta Groq (pode estar ofuscado)
                            print(f"    [LinkedIn] Status: 🔍 Mencionou 'email/cv', tentando IA...")
                            print(f"    🔍 Post {processed_count}: Regex não encontrou, mas post menciona 'email/cv'. Tentando Groq para e-mails ofuscados...")
                        else:
                            # Sem palavras-chave e sem contato - provavelmente não tem email
                            print(f"    [LinkedIn] Status: ⏭ Sem Contato")
                            print(f"    ⚠ Post {processed_count}: Regex não encontrou contato e post não menciona 'email/cv'")
                            continue
                        
                        try:
                            # Prompt para Groq extrair tudo de uma vez (apenas se regex falhou)
                            # Foco especial em e-mails ofuscados se post menciona 'email/cv'
                            if has_email_keywords:
                                groq_prompt = f"""Encontre o e-mail de contato neste texto, mesmo que esteja escrito de forma ofuscada (ex: felipe (at) gmail (dot) com).
Se não houver e-mail, responda exatamente: N/A

Post:
{raw_text[:1500]}

Retorne APENAS o e-mail encontrado ou "N/A"."""
                            else:
                                groq_prompt = f"""Abaixo está o conteúdo bruto de um post do LinkedIn. Extraia:

1. O e-mail de contato (se houver) - mesmo que esteja escrito de forma estranha como "felipe (at) gmail . com"
2. O link de inscrição (se houver) - URLs de Google Forms, Typeform, Ashby, Greenhouse, etc.
3. O idioma principal (pt ou en)

Se não houver contato, responda apenas: N/A

Post bruto:
{raw_text[:1500]}

Responda no formato JSON:
{{
  "email": "email@exemplo.com ou N/A",
  "links": ["link1", "link2"] ou [],
  "language": "pt ou en"
}}"""
                            
                            # Try AI first, but catch 429 immediately to fallback to regex
                            try:
                                ai_response = self.brain.smart_ai.generate_content(groq_prompt)
                                ai_response = ai_response.strip()
                                
                                # Check if AI returned empty (429 fallback)
                                if not ai_response or ai_response == "":
                                    # AI failed silently (429), force regex
                                    raise Exception("AI returned empty (likely 429)")
                            except Exception as ai_error:
                                error_str = str(ai_error).lower()
                                is_429 = '429' in error_str or 'rate limit' in error_str or 'quota' in error_str or 'limit' in error_str or 'empty' in error_str
                                
                                if is_429:
                                    # SNIPER MODE 100% OFFLINE: Se IA falhou (429), força regex
                                    print(f"    ⚠ Post {processed_count}: IA indisponível (429). Forçando extração via regex (modo offline)...")
                                    
                                    emails_found = self.extract_emails_robust(raw_text)
                                    if emails_found:
                                        email = emails_found[0]
                                        print(f"    ✓ Post {processed_count}: Email encontrado via regex (modo offline): {email}")
                                    else:
                                        external_links = self.extract_external_links(raw_text)
                                        if external_links:
                                            print(f"    ✓ Post {processed_count}: {len(external_links)} link(s) encontrado(s) via regex (modo offline)")
                                        else:
                                            print(f"    ⚠ Post {processed_count}: Regex offline não encontrou contato")
                                            email = None
                                            external_links = []
                                    
                                    # Skip AI parsing, go directly to post URL extraction (canonical = same job_id)
                                    post_url = post_card.evaluate("""el => {
                                        const feedLinks = Array.from(el.querySelectorAll('a[href*="/feed/update/"]'));
                                        for (const a of feedLinks) {
                                            if ((a.href || '').includes('activity:')) return a.href;
                                        }
                                        const postsLinks = Array.from(el.querySelectorAll('a[href*="/posts/"]'));
                                        for (const a of postsLinks) {
                                            if ((a.href || '').includes('-activity-')) return a.href;
                                        }
                                        const urnEl = el.querySelector('[data-urn],[data-occludable-update-urn]');
                                        if (urnEl) {
                                            const urn = urnEl.getAttribute('data-urn') || urnEl.getAttribute('data-occludable-update-urn');
                                            if (urn && urn.includes('urn:li:activity:')) {
                                                const id = urn.split('urn:li:activity:')[1] || '';
                                                if (/^\\d{10,}$/.test(id)) return 'https://www.linkedin.com/feed/update/' + urn;
                                            }
                                        }
                                        const key = el.getAttribute('componentkey') || '';
                                        const m = key.match(/^expanded(\\d{10,})FeedType/);
                                        if (m) return 'https://www.linkedin.com/feed/update/urn:li:activity:' + m[1];
                                        return null;
                                    }""")
                                    if post_url:
                                        post_url = _canonical_post_url(post_url)

                                    title_match = re.search(r'(?:hiring|contratando|vaga|position)[\s:]*([^\n\.]{10,80})', raw_text, re.IGNORECASE)
                                    job_title = title_match.group(1).strip() if title_match else f"Job from LinkedIn Post"

                                    job_code = self.extract_job_code(raw_text)

                                    company = post_card.evaluate("""el => {
                                        const a = el.querySelector('a[href*="/in/"], a[href*="/company/"]');
                                        if (a) return (a.getAttribute('aria-label') || a.innerText || '').trim();
                                        return 'Unknown';
                                    }""") or "Unknown"

                                    # Only create post if we found contact info
                                    if email or external_links:
                                        post_data = {
                                            'text': raw_text,
                                            'url': post_url,
                                            'email': email,
                                            'external_links': external_links,
                                            'language': language,
                                            'job_title': job_title,
                                            'company': company,
                                            'query': boolean_query,
                                            'job_code': job_code,
                                        }
                                        if email and email.strip().lower() in seen_emails_this_run:
                                            skipped_duplicate_email += 1
                                            print(f"    ⏭ Skipped (duplicate email this run): {email}")
                                        else:
                                            all_posts.append(post_data)
                                            if email:
                                                seen_emails_this_run.add(email.strip().lower())
                                                print(f"    ✅ Post {processed_count}: Adicionado com email (modo offline): {email}")
                                            else:
                                                print(f"    ✅ Post {processed_count}: Adicionado com {len(external_links)} link(s) (modo offline)")
                                    
                                    continue  # Skip to next post
                                else:
                                    raise  # Re-raise if not 429
                            
                            # Try to parse JSON response (only if AI succeeded)
                            try:
                                # Extract JSON from response (might have extra text)
                                json_match = re.search(r'\{[^}]+\}', ai_response, re.DOTALL)
                                if json_match:
                                    parsed = json.loads(json_match.group(0))
                                    
                                    # Extract email
                                    if parsed.get('email') and parsed['email'].lower() != 'n/a':
                                        email_str = parsed['email']
                                        # Clean up email (handle "felipe (at) gmail . com" format)
                                        email_str = email_str.replace(' (at) ', '@').replace(' (at)', '@').replace('(at) ', '@')
                                        email_str = email_str.replace(' . ', '.').replace(' .', '.').replace('. ', '.')
                                        # Extract valid email using regex
                                        email_matches = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', email_str)
                                        if email_matches:
                                            email = email_matches[0]
                                            # Filter invalid emails
                                            if any(skip in email.lower() for skip in ['noreply', 'no-reply', 'linkedin', 'notification', 'example.com']):
                                                email = None
                                    
                                    # Extract links
                                    if parsed.get('links') and isinstance(parsed['links'], list):
                                        external_links = [link for link in parsed['links'] if link and link.startswith('http')]
                                    
                                    # Extract language
                                    if parsed.get('language') in ['pt', 'en']:
                                        language = parsed['language']
                            except:
                                # Fallback: regex já foi tentado, mas tenta de novo
                                pass
                            
                            if email:
                                print(f"    ✓ Post {processed_count}: Email encontrado via IA: {email} ({language.upper()})")
                            elif external_links:
                                print(f"    ✓ Post {processed_count}: {len(external_links)} link(s) encontrado(s) via IA ({language.upper()})")
                            else:
                                print(f"    ⚠ Post {processed_count}: IA também não encontrou contato")
                        
                        except Exception as groq_error:
                            error_str = str(groq_error).lower()
                            # Detect 429 or rate limit errors
                            is_429 = '429' in error_str or 'rate limit' in error_str or 'quota' in error_str or 'limit' in error_str
                            
                            if is_429:
                                # SNIPER MODE 100% OFFLINE: Se IA falhou (429), força regex novamente de forma mais agressiva
                                print(f"    ⚠ Post {processed_count}: Groq Rate Limit 429. Forçando extração via regex (modo offline)...")
                                
                                # Tenta regex novamente com texto completo (não apenas primeira tentativa)
                                # Usa extract_emails_robust que é mais permissivo
                                emails_found = self.extract_emails_robust(raw_text)
                                if emails_found:
                                    email = emails_found[0]  # Pega o primeiro email encontrado
                                    print(f"    ✓ Post {processed_count}: Email encontrado via regex (modo offline): {email}")
                                else:
                                    # Tenta extrair links mesmo sem email
                                    external_links = self.extract_external_links(raw_text)
                                    if external_links:
                                        print(f"    ✓ Post {processed_count}: {len(external_links)} link(s) encontrado(s) via regex (modo offline)")
                                    else:
                                        print(f"    ⚠ Post {processed_count}: Regex offline também não encontrou contato")
                                        email = None
                                        external_links = []
                            else:
                                print(f"    ⚠ Post {processed_count}: Erro no Groq ({groq_error}). Tentando regex como fallback...")
                                
                                # Para outros erros, também tenta regex
                                emails_found = self.extract_emails_robust(raw_text)
                                if emails_found:
                                    email = emails_found[0]
                                    print(f"    ✓ Post {processed_count}: Email encontrado via regex (fallback): {email}")
                                else:
                                    external_links = self.extract_external_links(raw_text)
                                    if not external_links:
                                        email = None
                                        external_links = []
                    
                    # Extract post URL using multiple strategies.
                    # NOTE: a[href*="/activity/"] does NOT match "urn:li:activity:" (colon≠slash).
                    # Use /feed/update/ links and validate numeric activity IDs only.
                    post_url = post_card.evaluate("""el => {
                        // 1) Canonical /feed/update/ link (timestamp element — most reliable)
                        const feedLinks = Array.from(el.querySelectorAll('a[href*="/feed/update/"]'));
                        for (const a of feedLinks) {
                            const href = a.href || '';
                            if (href.includes('activity:')) return href;
                        }
                        // 2) /posts/ format (older LinkedIn URL style)
                        const postsLinks = Array.from(el.querySelectorAll('a[href*="/posts/"]'));
                        for (const a of postsLinks) {
                            const href = a.href || '';
                            if (href.includes('-activity-')) return href;
                        }
                        // 3) data-urn with NUMERIC activity ID only (avoids UUID/base64 garbage)
                        const urnEl = el.querySelector('[data-urn],[data-occludable-update-urn]');
                        if (urnEl) {
                            const urn = urnEl.getAttribute('data-urn') || urnEl.getAttribute('data-occludable-update-urn');
                            if (urn && urn.includes('urn:li:activity:')) {
                                const id = urn.split('urn:li:activity:')[1] || '';
                                if (/^\\d{10,}$/.test(id)) return 'https://www.linkedin.com/feed/update/' + urn;
                            }
                        }
                        // 4) componentkey — ONLY if it contains a numeric activity ID (not UUID/base64)
                        const key = el.getAttribute('componentkey') || '';
                        const m = key.match(/^expanded(\\d{10,})FeedType/);
                        if (m) return 'https://www.linkedin.com/feed/update/urn:li:activity:' + m[1];
                        return null;
                    }""")
                    if post_url:
                        post_url = _canonical_post_url(post_url)
                    # Last resort: click the overflow menu to get the canonical URL
                    if not post_url:
                        post_url = self._get_post_url_via_menu(post_card)
                        if post_url:
                            post_url = _canonical_post_url(post_url)

                    # Extract job title
                    title_match = re.search(r'(?:hiring|contratando|vaga|position)[\s:]*([^\n\.]{10,80})', raw_text, re.IGNORECASE)
                    job_title = title_match.group(1).strip() if title_match else f"Job from LinkedIn Post"

                    # Extract recruiter job identification code (e.g. "ENGFULLJAVA - 01")
                    job_code = self.extract_job_code(raw_text)

                    # Extract company/author — first author link inside the container
                    company = post_card.evaluate("""el => {
                        const a = el.querySelector('a[href*="/in/"], a[href*="/company/"]');
                        if (a) return (a.getAttribute('aria-label') || a.innerText || '').trim();
                        return 'Unknown';
                    }""") or "Unknown"

                    post_data = {
                        'text': raw_text,
                        'url': post_url,
                        'email': email,
                        'external_links': external_links,
                        'language': language,
                        'job_title': job_title,
                        'company': company,
                        'query': boolean_query,
                        'job_code': job_code,
                    }
                    
                    # INTEGRAÇÃO COM jobs.db: Registra tentativa mesmo sem email (reuse single connection)
                    try:
                        if _db and post_url and not email and not external_links:
                            job_data = {
                                'url': post_url,
                                'title': job_title,
                                'company': company,
                                'match_score': 0.0
                            }
                            _db.save_job(job_data, status="SKIPPED")
                            print(f"    [LinkedIn] Post {post_id_short} registrado no jobs.db (SKIPPED - sem contato)")
                    except Exception as db_error:
                        pass
                    
                    # Only append if there's contact info (email or links); dedupe by email in this run
                    if email or external_links:
                        if email and email.strip().lower() in seen_emails_this_run:
                            skipped_duplicate_email += 1
                            print(f"    ⏭ Skipped (duplicate email this run): {email}")
                        else:
                            all_posts.append(post_data)
                            if email:
                                seen_emails_this_run.add(email.strip().lower())
                                print(f"    ✅ Post {processed_count}: Adicionado com email: {email}")
                            else:
                                print(f"    ✅ Post {processed_count}: Adicionado com {len(external_links)} link(s)")
                
                except Exception as e:
                    print(f"    ⚠ Erro processando post {i+1}: {e}")
                    import traceback
                    print(traceback.format_exc()[:200])
                    continue
            
            print(f"    ✓ Extracted {len(all_posts)} posts with contact (processed {processed_count} for contact, {skipped_cache} cache, {skipped_no_contact} no @/http, {skipped_duplicate_email} duplicate email)")
            
        except Exception as e:
            print(f"  ✗ Error in advanced search: {e}")
            import traceback
            print(traceback.format_exc()[:500])
        finally:
            # Captura de Performance: Registra tempo total da busca
            search_elapsed = time_module.time() - search_start_time
            print(f"    [LinkedIn] Busca finalizada em {search_elapsed:.1f}s - {len(all_posts)} posts com contato (total processado na lista: {processed_count})")
        
        return all_posts
    
    @staticmethod
    def _dedup_cover_letter(text: str) -> str:
        """If AI returned multiple cover letter variants separated by blank lines, keep only the first."""
        if not text:
            return text
        parts = re.split(r'\n{2,}', text.strip())
        if len(parts) <= 1:
            return text
        greeting = re.compile(r'^(hola[,\s]|hi[,\s]|hi\s+hiring|olá[,\s]|dear\s)', re.IGNORECASE)
        first_idx = None
        for i, part in enumerate(parts):
            if greeting.match(part.strip()):
                if first_idx is None:
                    first_idx = i
                else:
                    return '\n\n'.join(parts[:i]).strip()
        return text

    def generate_cover_letter(self, post_text: str, language: str, job_title: str, search_skill: str = None) -> str:
        """Generate personalized cover letter using Groq AI"""
        try:
            # Get user info
            user_name = self.user_data.get('name', 'Felipe França Nogueira')
            years_exp = self.resume_data.experiencia_anos if hasattr(self.resume_data, 'experiencia_anos') else 8
            seniority = self.resume_data.senioridade_pretendida if hasattr(self.resume_data, 'senioridade_pretendida') else 'senior'
            skills = ', '.join(self.resume_data.stack_tecnico[:5]) if hasattr(self.resume_data, 'stack_tecnico') else 'Python, React, Ruby on Rails'
            
            # Personalize based on search skill if available
            skill_context = ""
            if search_skill:
                if language == 'pt':
                    skill_context = f"O candidato encontrou este post através de uma busca por '{search_skill}'. "
                elif language == 'es':
                    skill_context = f"El candidato encontró esta publicación buscando '{search_skill}'. "
                else:
                    skill_context = f"The candidate found this post through a search for '{search_skill}'. "
            
            if language == 'pt':
                prompt = f"""Escreva uma carta de apresentação curta e impactante (máximo 80 palavras) em português para esta vaga:

Título: {job_title}
Post: {post_text[:500]}

Candidato: {user_name}
Experiência: {years_exp} anos ({seniority})
Stack: {skills}
{skill_context}Tecnologia específica da busca: {search_skill or 'N/A'}

A carta deve:
- Começar mencionando que você viu o post sobre {search_skill or 'a vaga'} (se tecnologia disponível)
- Ser profissional mas calorosa
- Destacar os {years_exp} anos de experiência como {seniority}
- Mencionar interesse específico na vaga
- Incluir call-to-action para conversa

Retorne APENAS o texto de UMA ÚNICA carta. Não forneça alternativas nem variações."""
            elif language == 'es':
                prompt = f"""Escribe una carta de presentación breve e impactante (máximo 80 palabras) en español para esta vacante:

Título: {job_title}
Publicación: {post_text[:500]}

Candidato: {user_name}
Experiencia: {years_exp} años ({seniority})
Stack: {skills}
{skill_context}Tecnología de la búsqueda: {search_skill or 'N/A'}

La carta debe:
- Empezar mencionando que viste la publicación sobre {search_skill or 'la vacante'}
- Ser profesional pero cercana
- Destacar {years_exp} años de experiencia como {seniority}
- Mencionar interés específico en la posición
- Incluir llamada a la acción para conversar

Devuelve SOLO el texto de UNA ÚNICA carta. No proporciones alternativas ni variaciones."""
            else:
                prompt = f"""Write a short and impactful cover letter (maximum 80 words) in English (C1/C2 level) for this position:

Title: {job_title}
Post: {post_text[:500]}

Candidate: {user_name}
Experience: {years_exp} years ({seniority})
Stack: {skills}
{skill_context}Specific technology from search: {search_skill or 'N/A'}

The letter should:
- Start by mentioning you saw the post about {search_skill or 'the position'} (if technology available)
- Be professional but warm
- Highlight {years_exp} years of experience as {seniority}
- Mention specific interest in the position
- Include call-to-action for conversation

Return ONLY the text of ONE single letter. Do NOT provide alternatives or multiple versions."""

            cover_letter = self.brain.smart_ai.generate_content(prompt)
            cover_letter_clean = cover_letter.strip() if cover_letter else ""

            # If AI returned error message, treat as failure
            error_indicators = ['ai services unavailable', 'ai services', 'unavailable', 'using fallback']
            if cover_letter_clean and any(indicator in cover_letter_clean.lower() for indicator in error_indicators):
                print(f"  ⚠ AI returned error message, using empty body")
                return ""

            # Remove extra variants if AI returned multiple cover letters separated by blank lines
            cover_letter_clean = self._dedup_cover_letter(cover_letter_clean)

            return cover_letter_clean
        
        except Exception as e:
            error_str = str(e).lower()
            is_429 = '429' in error_str or 'quota' in error_str or 'rate limit' in error_str
            
            if is_429:
                print(f"  ⚠ Error generating cover letter (429/quota): {e}")
            else:
                print(f"  ⚠ Error generating cover letter: {e}")
            
            # Return empty string if AI fails (emailer.py will send email with empty body + attachment)
            # This is more professional than sending error messages
            return ""
    
    def convert_posts_to_jobs(self, posts: List[Dict]) -> List[JobListing]:
        """Convert LinkedIn posts to JobListing objects"""
        jobs = []
        
        # Initialize counters BEFORE the loop (BUG FIX)
        emails_found = 0
        links_found = 0
        
        print(f"  📧 Converting {len(posts)} posts to jobs...")
        
        for post in posts:
            # Create job if there's contact info (email or external link)
            # Links are saved to DB for later analysis even without email (prioritize direct contact)
            if not post.get('email') and not post.get('external_links'):
                continue
            
            # Use post URL for persistence (canonical so same post = same job_id, no duplicate sends)
            post_url = _canonical_post_url(post.get('url') or "") or f"linkedin_post_{hash(post['text'][:100])}"
            
            # For job URL, use email format or external link, but keep post_url for DB persistence
            if post.get('email'):
                # For email jobs, use special format but post_url for DB
                job_url = f"email:{post['email']}"
            elif post.get('external_links'):
                job_url = post['external_links'][0]
            else:
                job_url = post_url  # Fallback to post URL
            
            # Use post URL for database persistence (unique identifier to avoid duplicates)
            job_url_for_db = post_url
            
            # Calculate match score based on post content
            post_text_lower = post['text'].lower()
            skills = self.resume_data.stack_tecnico if hasattr(self.resume_data, 'stack_tecnico') else []
            
            match_score = 0.6  # Base score for LinkedIn posts (direct contact)
            for skill in skills:
                if skill.lower() in post_text_lower:
                    match_score += 0.1
            
            match_score = min(match_score, 1.0)
            
            job = JobListing(
                title=post['job_title'],
                company=post['company'],
                url=job_url_for_db,  # Use post URL for database persistence
                location="Remote",
                description=post['text'][:1000],  # First 1000 chars
                posted_date=None,  # LinkedIn posts don't always have dates
                source='linkedin_post',
                match_score=match_score,
                email=post.get('email'),
                language=post.get('language', 'en'),
                external_links=post.get('external_links', []),
                job_code=post.get('job_code'),
            )

            if post.get('email'):
                job.email = post['email']
                emails_found += 1

            if post.get('external_links'):
                links_found += len(post.get('external_links', []))

            if post.get('search_skill'):
                job.search_skill = post['search_skill']
            
            jobs.append(job)
        
        print(f"  ✓ Converted {len(jobs)} posts to jobs ({emails_found} emails, {links_found} links)")
        return jobs

