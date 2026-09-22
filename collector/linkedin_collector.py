"""Local authenticated LinkedIn collector; only posts are sent to the cloud app."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

DEFAULT_URL = "https://job-autopilot.felipenogueira.workers.dev"
DEFAULT_PROFILE = Path.home() / ".job-autopilot" / "linkedin-profile"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class API:
    def __init__(self, url, token):
        u = urlparse(url)
        if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ("", "/"):
            raise ValueError("Use apenas a origem HTTPS do seu painel.")
        if len(token) < 32:
            raise ValueError("APP_TOKEN deve ter pelo menos 32 caracteres.")
        self.url, self.token = url.rstrip("/"), token
        self.opener = build_opener(NoRedirect())

    def call(self, path, data=None):
        req = Request(self.url + "/api/" + path,
                      data=None if data is None else json.dumps(data).encode(),
                      headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=45) as response:
                return json.load(response)
        except HTTPError as error:
            # Never print request headers or credentials.
            raise RuntimeError(f"Painel retornou HTTP {error.code}; verifique acesso e atividade no painel.") from None

    def report(self, state, count=0):
        self.call("linkedin/collector-status", {"state": state, "count": count})


def queries(config):
    terms = [re.sub(r'[^\w .+#-]', '', t).strip() for t in (config.get("targetRoles") or config.get("keywords", "")).split(",")]
    terms = [t[:60] for t in terms if t][:9]
    if not terms:
        raise ValueError("Configure tecnologias nas preferências do painel.")
    country = config.get("country", "global")
    region = "" if country.lower() in ("global", "world", "mundo") else (
        ' (LATAM OR "Latin America" OR "América Latina")' if country.upper() == "LATAM"
        else ' "' + re.sub(r'[^\w .-]', '', country)[:80] + '"')
    remote = " (remote OR remoto)" if config.get("remoteOnly") else ""
    return ['(' + ' OR '.join('"' + t + '"' for t in terms[i:i+3]) + ') (hiring OR vaga OR contratando)' + region + remote for i in range(0, len(terms), 3)]


def canonical_post(url):
    u = urlparse(url)
    if u.scheme != "https" or u.hostname not in ("linkedin.com", "www.linkedin.com"):
        return None
    activity = re.search(r'(?:urn:li:activity:|activity-)(\d+)', u.path)
    if activity:
        return "https://www.linkedin.com/feed/update/urn:li:activity:" + activity[1] + "/"
    if u.path.startswith("/posts/"):
        return "https://www.linkedin.com" + u.path.rstrip("/")
    return None


def require_session(page):
    if any(s in page.url.lower() for s in ("/login", "/checkpoint", "/challenge", "/authwall", "/uas/")):
        raise PermissionError("Sessão ausente ou verificação pendente. Execute o comando login.")
    if page.locator('input[name="session_key"], input[name="session_password"], iframe[src*="captcha"]').count():
        raise PermissionError("Login ou verificação pendente. Resolva no navegador local.")


# Selectors adapted from modules/linkedin_post_searcher.py. No stealth flags,
# credential injection, profile copying or removal of Chromium lock files.
CARDS = 'div.feed-shared-update-v2, div[data-urn*="activity"], div[role="listitem"][componentkey]'
EXTRACT = """el => {
  const box = el.querySelector('[data-testid="expandable-text-box"], .update-components-text, .feed-shared-text, .feed-shared-update-v2__description');
  const anchor = el.querySelector('a[href*="/feed/update/"], a[href*="/posts/"]');
  const urn = el.getAttribute('data-urn') || el.getAttribute('data-occludable-update-urn') || '';
  return {text: box ? box.innerText : '', url: anchor ? anchor.href : (urn.includes('urn:li:activity:') ? 'https://www.linkedin.com/feed/update/' + urn + '/' : '')};
}"""


def collect(page, api, config, limit):
    seen, saved, observed = set(), 0, 0
    for query in queries(config):
        page.goto("https://www.linkedin.com/search/results/content/?" + urlencode({"keywords": query, "sortBy": '"date_posted"'}), wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        require_session(page)
        for _ in range(5):
            require_session(page)
            cards = page.locator(CARDS)
            for index in range(min(cards.count(), 80)):
                card = cards.nth(index)
                more = card.locator('[data-testid="expandable-text-button"], .feed-shared-inline-show-more-text__button')
                if more.count() and more.first.is_visible():
                    more.first.click(timeout=3000)
                    page.wait_for_timeout(200)
                post = card.evaluate(EXTRACT)
                url = canonical_post(post["url"])
                text = post["text"].strip()
                if not url or url in seen or not 80 <= len(text) <= 20000 or text.endswith(("…", "...")):
                    continue
                seen.add(url)
                observed += 1
                result = api.call("linkedin/import", {"url": url, "text": text})
                saved += result.get("saved", 0)
                print(f"Posts processados: {observed}; novos no painel: {saved}", flush=True)
                if observed >= limit:
                    return saved, observed
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(2000)
    return saved, observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["login", "run", "watch"])
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE, help="Pasta persistente da automação antiga, ou perfil dedicado novo")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--max-posts", type=int, default=30)
    parser.add_argument("--interval-minutes", type=int, default=120)
    args = parser.parse_args()
    if not 1 <= args.max_posts <= 100 or args.interval_minutes < 30:
        parser.error("Use 1–100 posts por ciclo e intervalo mínimo de 30 minutos.")
    from playwright.sync_api import sync_playwright
    profile = args.profile_dir.expanduser().resolve()
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    api = None if args.command == "login" else API(args.url, os.getenv("JOB_AUTOPILOT_TOKEN") or getpass.getpass("APP_TOKEN do painel (oculto): "))
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(profile), headless=False, accept_downloads=False, viewport={"width": 1440, "height": 1000})
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(10000)
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
            if args.command == "login":
                input("Faça login no navegador aberto. Quando o feed estiver visível, pressione Enter aqui. ")
                require_session(page)
                if "/feed" not in page.url:
                    raise PermissionError("Abra o feed para confirmar a sessão antes de continuar.")
                print("Perfil persistente salvo localmente. Use a mesma pasta no comando run/watch.")
                return
            while True:
                try:
                    require_session(page)
                    state = api.call("linkedin/collector-config")
                    if not state.get("confirmed"):
                        raise ValueError("Confirme o currículo no painel antes de coletar.")
                    if args.command == "watch" and not state["config"].get("enabled"):
                        print("Agendamento desativado no painel. Coletor encerrado.")
                        api.report("paused")
                        break
                    api.report("running")
                    saved, observed = collect(page, api, state["config"], args.max_posts)
                    api.report("completed" if observed else "no_results", saved)
                    print(f"Ciclo concluído: {saved} novos posts. A análise acontece nos lotes do painel.")
                except Exception as error:
                    try:
                        api.report("login_required" if isinstance(error, PermissionError) else "error")
                    except Exception:
                        pass
                    raise
                if args.command != "watch":
                    break
                print(f"Próximo ciclo em {args.interval_minutes} minutos. Ctrl+C para parar.", flush=True)
                time.sleep(args.interval_minutes * 60)
        finally:
            context.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Coletor encerrado.")
    except Exception as error:
        print(f"Coleta interrompida: {error}")
        raise SystemExit(1)
