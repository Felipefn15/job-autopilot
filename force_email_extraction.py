#!/usr/bin/env python3
"""
Force Email Extraction – caçador de e-mails (só Regex, sem browser e sem IA).
Busca todas as vagas PENDING no jobs.db com email NULL, abre cada URL com requests.get,
aplica o Regex de Elite (EmailApplier) no corpo da página e salva o e-mail no banco.
Assim ./run.sh --send-only pode enviar imediatamente para essas vagas.
"""
import sys
import time
from pathlib import Path
from typing import Optional

# Garantir que o projeto está no path
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

from modules.database import DatabaseManager
from modules.emailer import EmailApplier


def fetch_body(url: str, session: requests.Session) -> Optional[str]:
    """Obtém o corpo de texto: GitHub Issue via API, caso contrário GET na URL (sem browser)."""
    if "github.com" in url and "/issues/" in url:
        api_url = url.replace("https://github.com/", "https://api.github.com/repos/")
        api_url = api_url.replace("http://github.com/", "https://api.github.com/repos/")
        try:
            r = session.get(api_url, timeout=15, headers={"Accept": "application/vnd.github.v3+json"})
            if r.status_code == 200:
                data = r.json()
                return (data.get("body") or "")[:8000]
        except Exception as e:
            print(f"    ⚠ GitHub API: {e}")
        return None
    try:
        r = session.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible; ForceEmailExtraction/1.0)"})
        if r.status_code == 200:
            return (r.text or "")[:8000]
    except Exception as e:
        print(f"    ⚠ GET: {e}")
    return None


def main(db_path: str = "jobs.db", limit: Optional[int] = None) -> None:
    db = DatabaseManager(db_path)
    emailer = EmailApplier()
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ForceEmailExtraction/1.0)"})

    pending = db.get_pending_without_email(limit=limit)
    if not pending:
        print("  ℹ Nenhuma vaga PENDING com email NULL no banco.")
        return

    print(f"\n  📬 Force Email Extraction: {len(pending)} vagas PENDING sem e-mail (só Regex, sem IA)\n")
    updated = 0

    for i, job in enumerate(pending, 1):
        url = job.get("url", "")
        title = (job.get("title") or "Unknown")[:55]
        print(f"  [{i}/{len(pending)}] {title} ... ", end="", flush=True)
        body = fetch_body(url, session)
        if not body:
            print("sem corpo")
            time.sleep(0.4)
            continue
        email = emailer.extract_email_from_text(body)
        if email:
            if db.update_job_email(url, email):
                print(f"✓ {email}")
                updated += 1
            else:
                print("erro ao salvar")
        else:
            print("não encontrado")
        time.sleep(0.4)

    print(f"\n  ✓ Concluído: {updated} e-mails salvos. Rode ./run.sh --send-only para enviar.\n")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Extrai e-mail de vagas PENDING (Regex apenas)")
    p.add_argument("--db", default="jobs.db", help="Caminho do jobs.db")
    p.add_argument("--limit", type=int, default=None, help="Máximo de vagas a processar")
    args = p.parse_args()
    main(db_path=args.db, limit=args.limit)
