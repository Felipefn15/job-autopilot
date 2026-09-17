"""
X (Twitter) Sniper
Busca posts de fundadores/CTOs com ofertas de emprego (hiring, Senior React, IA, OpenAI),
usa IA para classificar oferta e extrair e-mail, link ou DM. Envia para pipeline de e-mail
ou salva como EASY_APPLY_PENDING para o Easy Applier.
"""
import re
import time
import json
from typing import List, Dict, Optional, Any

from playwright.sync_api import sync_playwright, Page

from .models import JobListing
from .database import DatabaseManager
from .brain import AIBrain
from .emailer import EmailApplier
from .session_manager import SessionManager


class TwitterSniper:
    """
    Sniper de vagas no X (Twitter).
    Executa buscas por URL, captura texto dos tweets, usa Groq/Gemini para
    identificar oferta de emprego e extrair e-mail, link ou DM.
    """

    def __init__(
        self,
        resume_data: Any,
        db: Optional[DatabaseManager] = None,
        user_data: Optional[Dict[str, str]] = None,
    ):
        self.resume_data = resume_data
        self.db = db or DatabaseManager("jobs.db")
        self.user_data = user_data or {}
        self.brain = AIBrain()
        self.emailer = EmailApplier()
        self.playwright = None
        self.context = None
        self.page: Optional[Page] = None

    def start_browser(self, headless: bool = False) -> bool:
        """Inicia Playwright com perfil Chrome (login no X opcional)."""
        import tempfile
        session = SessionManager()
        ctx_args = session.get_context_args("chrome")
        if not ctx_args.get("can_use_real_session"):
            print("  ⚠ Twitter Sniper: Chrome profile not found. Using temp profile (X may require login).")
        try:
            self.playwright = sync_playwright().start()
            user_data_dir = ctx_args.get("user_data_dir") or tempfile.mkdtemp(prefix="twitter_sniper_")
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=headless,
                channel="chrome" if session.find_chrome_profile() else None,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1920, "height": 1080},
            )
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            print("  ✓ Twitter Sniper: browser started")
            return True
        except Exception as e:
            print(f"  ✗ Twitter Sniper browser failed: {e}")
            return False

    def close_browser(self):
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass

    def _build_search_url(self, query: str, live: bool = True) -> str:
        """Monta URL de busca do X. query já pode ser algo como '("hiring" AND "Senior React")'."""
        from urllib.parse import quote
        base = "https://x.com/search"
        qs = f"q={quote(query)}"
        if live:
            qs += "&f=live"
        return f"{base}?{qs}"

    def _collect_tweets(self, search_url: str, max_tweets: int = 30) -> List[Dict[str, str]]:
        """Navega para a busca e coleta texto e link de cada tweet visível."""
        if not self.page:
            return []
        tweets = []
        try:
            self.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            for _ in range(5):
                # Seletores comuns do X (podem mudar com o tempo)
                articles = self.page.query_selector_all('article[data-testid="tweet"]')
                if not articles:
                    articles = self.page.query_selector_all("article")
                for art in articles:
                    if len(tweets) >= max_tweets:
                        break
                    try:
                        text_el = art.query_selector('[data-testid="tweetText"]')
                        if not text_el:
                            text_el = art.query_selector(".tweet-text, [lang]")
                        text = text_el.inner_text() if text_el else ""
                        if not text or len(text) < 20:
                            continue
                        link_el = art.query_selector('a[href*="/status/"]')
                        tweet_url = link_el.get_attribute("href") if link_el else ""
                        if tweet_url and not tweet_url.startswith("http"):
                            tweet_url = "https://x.com" + tweet_url
                        tweets.append({"text": text, "url": tweet_url})
                    except Exception:
                        continue
                if len(tweets) >= max_tweets:
                    break
                self.page.evaluate("window.scrollBy(0, 800)")
                time.sleep(1.5)
        except Exception as e:
            print(f"  ⚠ Twitter collect error: {e}")
        return tweets[:max_tweets]

    def _parse_tweet_with_ai(self, text: str, tweet_url: str) -> Dict[str, Any]:
        """
        Usa IA para: (1) é oferta de emprego? (2) e-mail, link de formulário ou "DM"?
        Retorno: is_job_offer, email, apply_link, asks_dm.
        """
        try:
            prompt = f"""Analyze this tweet and determine:
1. Is it a real job/hiring offer (someone recruiting for a role)? Answer yes or no.
2. If yes, extract: contact_email (if visible), apply_link (URL to apply, e.g. greenhouse, lever, form), or whether it says to reply by DM/Direct Message.

Tweet text:
{text[:1500]}

Reply with ONLY a JSON object, no markdown:
{{"is_job_offer": true/false, "contact_email": "email or null", "apply_link": "url or null", "asks_dm": true/false}}
"""
            response = self.brain.model.generate_content(prompt)
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```\w*\n?", "", raw).strip()
                raw = re.sub(r"\n?```$", "", raw).strip()
            data = json.loads(raw)
            email = (data.get("contact_email") or "").strip() or None
            if email and not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
                email = None
            link = (data.get("apply_link") or "").strip() or None
            if link and not link.startswith("http"):
                link = None
            return {
                "is_job_offer": bool(data.get("is_job_offer")),
                "email": email,
                "apply_link": link,
                "asks_dm": bool(data.get("asks_dm")),
            }
        except Exception as e:
            print(f"    ⚠ AI parse tweet failed: {e}")
            return {"is_job_offer": False, "email": None, "apply_link": None, "asks_dm": False}

    def _extract_email_regex(self, text: str) -> Optional[str]:
        return self.emailer.extract_email_from_text(text)

    def run(
        self,
        query: str = '("hiring" AND "Senior React")',
        max_tweets: int = 30,
        live: bool = True,
    ) -> List[JobListing]:
        """
        Executa busca no X, classifica tweets com IA e persiste:
        - Se tiver e-mail -> status PENDING (pipeline de envio).
        - Se tiver link de candidatura -> status EASY_APPLY_PENDING (Easy Applier).
        - DM apenas: salva com url = tweet e status PENDING (contato manual).
        """
        jobs: List[JobListing] = []
        search_url = self._build_search_url(query, live=live)

        print("\n🐦 X (Twitter) Sniper")
        print("   Query:", query[:60], "..." if len(query) > 60 else "")

        if not self.start_browser(headless=False):
            return jobs

        try:
            tweets = self._collect_tweets(search_url, max_tweets=max_tweets)
            print(f"  📋 Collected {len(tweets)} tweets")

            for i, tw in enumerate(tweets):
                text = tw.get("text", "")
                tweet_url = tw.get("url", "") or f"https://x.com/search?q={query}"
                if self.db.is_job_processed(tweet_url):
                    continue

                parsed = self._parse_tweet_with_ai(text, tweet_url)
                if not parsed.get("is_job_offer"):
                    continue

                email = parsed.get("email") or self._extract_email_regex(text)
                apply_link = parsed.get("apply_link")
                asks_dm = parsed.get("asks_dm")

                title = "Job offer (X)" if not re.search(r"\b(senior|engineer|developer|hiring)\b", text, re.I) else text[:80]
                company = "Unknown"
                if email and "@" in email:
                    company = email.split("@")[-1].split(".")[0].capitalize()

                if email:
                    url_for_db = f"email:{email}"
                    status = "PENDING"
                    job_url = tweet_url
                elif apply_link:
                    url_for_db = apply_link
                    status = "EASY_APPLY_PENDING"
                    job_url = apply_link
                else:
                    url_for_db = tweet_url
                    status = "PENDING"
                    job_url = tweet_url

                if self.db.is_job_processed(url_for_db):
                    continue

                job = JobListing(
                    title=title,
                    company=company,
                    location="Remote",
                    url=job_url,
                    posted_date=None,
                    description=text[:2000],
                    email=email,
                    source="twitter_sniper",
                )
                job.match_score = 0.6 if email else 0.5

                job_data = {
                    "url": url_for_db,
                    "title": job.title,
                    "company": job.company,
                    "match_score": job.match_score,
                    "error_details": [],
                    "source": "twitter_sniper",
                }
                self.db.save_job(job_data, status=status)
                jobs.append(job)
                print(f"    ✓ {status} | {job.title[:40]} | email={bool(email)} link={bool(apply_link)} dm={asks_dm}")

        finally:
            self.close_browser()

        print(f"\n  🎯 Total: {len(jobs)} vagas (PENDING ou EASY_APPLY_PENDING)")
        return jobs
