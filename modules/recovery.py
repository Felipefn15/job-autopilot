"""
Recovery script: extrai e-mail de vagas PENDING que foram puladas por "No email found".
Lê do banco as vagas PENDING sem e-mail, faz request na URL (GitHub API ou página),
usa Regex (EmailApplier) + IA (Groq) para extrair e-mail e atualiza o banco.
Assim o Step 0 (apply_to_pending_jobs) consegue enviar para essas vagas.
"""
import re
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import requests


def _fetch_body_from_url(url: str, session: requests.Session) -> Optional[str]:
    """Obtém o corpo de texto: GitHub Issue via API, caso contrário GET na URL."""
    if "github.com" in url and "/issues/" in url:
        # GitHub API: https://github.com/owner/repo/issues/123 -> api.github.com/repos/owner/repo/issues/123
        api_url = url.replace("https://github.com/", "https://api.github.com/repos/")
        api_url = api_url.replace("http://github.com/", "https://api.github.com/repos/")
        try:
            r = session.get(api_url, timeout=15, headers={"Accept": "application/vnd.github.v3+json"})
            if r.status_code == 200:
                data = r.json()
                return (data.get("body") or "")[:8000]
        except Exception as e:
            print(f"    ⚠ GitHub API error for {url}: {e}")
        return None
    try:
        r = session.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible; JobRecovery/1.0)"})
        if r.status_code == 200:
            return (r.text or "")[:8000]
    except Exception as e:
        print(f"    ⚠ GET error for {url}: {e}")
    return None


def _extract_email_with_ai(body: str, issue_title: str = "") -> Optional[str]:
    """Usa Groq (SmartAI) para extrair contact_email do corpo da vaga."""
    try:
        from .ai_handler import SmartAI
        ai = SmartAI()
        if not getattr(ai, "groq_client", None):
            return None
        prompt = f"""From this job posting text, extract exactly one contact email if present.
Reply with ONLY a JSON object: {{"contact_email": "email@example.com"}} or {{"contact_email": null}} if none.

Title: {issue_title[:200]}
Text (first 2500 chars):
{(body or '')[:2500]}
"""
        response = ai.groq_client.chat.completions.create(
            model=ai.groq_model,
            messages=[
                {"role": "system", "content": "You extract contact emails from job postings. Return ONLY valid JSON: {\"contact_email\": \"...\" or null}."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        response_text = (response.choices[0].message.content or "").strip()
        if not response_text:
            return None
        text = response_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text).strip()
            text = re.sub(r"\n?```$", "", text).strip()
        import json
        data = json.loads(text)
        email = (data.get("contact_email") or "").strip() or None
        if email and "@" in email and re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            return email
        return None
    except Exception as e:
        print(f"    ⚠ AI extraction failed: {e}")
        return None


def run_recovery(db_path: str = "jobs.db", limit: Optional[int] = None, use_ai: bool = True) -> dict:
    """
    Lê vagas PENDING sem e-mail, busca corpo na URL, extrai e-mail (Regex + opcionalmente IA) e atualiza o banco.
    """
    from .database import DatabaseManager
    from .emailer import EmailApplier

    load_dotenv()
    db = DatabaseManager(db_path)
    emailer = EmailApplier()
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; JobRecovery/1.0)"})

    pending = db.get_pending_without_email(limit=limit)
    if not pending:
        print("  ℹ Nenhuma vaga PENDING sem e-mail no banco.")
        return {"total": 0, "updated": 0, "failed": 0}

    print(f"\n  📬 Recovery: {len(pending)} vagas PENDING sem e-mail. Tentando extrair...\n")
    updated = 0
    failed = 0

    for i, job in enumerate(pending, 1):
        url = job.get("url", "")
        title = job.get("title", "Unknown")[:60]
        print(f"  [{i}/{len(pending)}] {title} ... ", end="", flush=True)
        body = _fetch_body_from_url(url, session)
        if not body:
            print("no body")
            failed += 1
            time.sleep(0.5)
            continue
        email = emailer.extract_email_from_text(body)
        if not email and use_ai:
            email = _extract_email_with_ai(body, title)
        if email:
            if db.update_job_email(url, email):
                print(f"✓ {email}")
                updated += 1
            else:
                print("update failed")
                failed += 1
        else:
            print("no email found")
            failed += 1
        time.sleep(0.5)

    print(f"\n  ✓ Recovery concluído: {updated} atualizados, {failed} sem e-mail ou falha.\n")
    return {"total": len(pending), "updated": updated, "failed": failed}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Recovery: extrair e-mail de vagas PENDING sem e-mail")
    parser.add_argument("--db", default="jobs.db", help="Caminho do jobs.db")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de vagas a processar")
    parser.add_argument("--no-ai", action="store_true", help="Usar só Regex, sem IA")
    args = parser.parse_args()
    run_recovery(db_path=args.db, limit=args.limit, use_ai=not args.no_ai)
