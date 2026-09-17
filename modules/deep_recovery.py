"""
Deep Recovery: recuperação profunda de e-mail ou link de formulário para vagas MANUAL_REVIEW/PENDING sem e-mail.
Filtra por maior match_score, faz scraping do conteúdo da URL (texto limpo de HTML),
envia para IA (Groq/Gemini) para extrair e-mail ou link (Lever, Greenhouse, Typeform).
Atualiza: se e-mail -> email + status PENDING; se link -> apply_link.

Uso: python3 modules/deep_recovery.py   ou   python -m modules.deep_recovery
"""
import re
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any

# Permite execução direta: python3 modules/deep_recovery.py
if __name__ == "__main__":
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from dotenv import load_dotenv

load_dotenv()

import requests


def _strip_html(html: str) -> str:
    """Extrai texto limpo do HTML (remove tags, normaliza espaços)."""
    if not html:
        return ""
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:12000]


def _fetch_page_text(url: str, session: requests.Session) -> Optional[str]:
    """Obtém o texto da página: GitHub Issue via API (body) ou GET + strip HTML."""
    if "github.com" in url and "/issues/" in url:
        api_url = url.replace("https://github.com/", "https://api.github.com/repos/")
        api_url = api_url.replace("http://github.com/", "https://api.github.com/repos/")
        try:
            r = session.get(api_url, timeout=15, headers={"Accept": "application/vnd.github.v3+json"})
            if r.status_code == 200:
                data = r.json()
                body = (data.get("body") or "")[:12000]
                return body
        except Exception as e:
            print(f"    ⚠ GitHub API: {e}")
        return None
    try:
        r = session.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible; DeepRecovery/1.0)"})
        if r.status_code == 200:
            return _strip_html(r.text or "")
    except Exception as e:
        print(f"    ⚠ GET: {e}")
    return None


def _call_ai_extract(text: str) -> Optional[str]:
    """Envia texto para IA (Groq/Gemini): extrair e-mail de contato ou link de formulário. Retorna dado bruto."""
    prompt = """Extraia apenas o e-mail de contato para candidatura deste texto. Se não houver e-mail, mas houver um link de formulário (ex: Lever, Greenhouse, Typeform), retorne esse link. Responda apenas com o dado bruto (um e-mail ou uma URL, nada mais)."""
    full_prompt = f"{prompt}\n\nTexto:\n{(text or '')[:6000]}"
    try:
        from modules.ai_handler import SmartAI
        ai = SmartAI()
        raw = ai.generate_content(full_prompt)
        if not raw:
            return None
        raw = raw.strip()
        if not raw or len(raw) > 500:
            return None
        return raw
    except Exception as e:
        print(f"    ⚠ IA: {e}")
        return None


def _is_email(s: str) -> bool:
    return "@" in s and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s.strip())


def _is_url(s: str) -> bool:
    s = s.strip()
    return s.startswith("http://") or s.startswith("https://")


def run_deep_recovery(db_path: str = "jobs.db", limit: Optional[int] = None) -> Dict[str, int]:
    """
    Busca vagas MANUAL_REVIEW/PENDING com email NULL (prioridade por match_score),
    faz scraping da URL, envia para IA e atualiza: email+status PENDING ou apply_link.
    """
    from modules.database import DatabaseManager

    db = DatabaseManager(db_path)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; DeepRecovery/1.0)"})

    targets = db.get_recovery_targets(limit=limit)
    if not targets:
        print("  ℹ Nenhuma vaga MANUAL_REVIEW/PENDING com email NULL.")
        return {"total": 0, "email_updated": 0, "link_updated": 0, "skipped": 0}

    print(f"\n  🔬 Deep Recovery: {len(targets)} vagas (prioridade por score)\n")
    email_updated = 0
    link_updated = 0
    skipped = 0

    for i, job in enumerate(targets, 1):
        url = job.get("url", "")
        title = (job.get("title") or "Unknown")[:50]
        score = job.get("match_score", 0)
        print(f"  [{i}/{len(targets)}] score={score:.2f} {title} ... ", end="", flush=True)

        text = _fetch_page_text(url, session)
        if not text or len(text) < 50:
            print("sem conteúdo")
            skipped += 1
            time.sleep(0.5)
            continue

        raw = _call_ai_extract(text)
        if not raw:
            print("IA sem retorno")
            skipped += 1
            time.sleep(0.8)
            continue

        if _is_email(raw):
            if db.update_job_email(url, raw) and db.update_job_status(url, "PENDING"):
                print(f"✓ e-mail → PENDING: {raw}")
                email_updated += 1
            else:
                print("erro ao atualizar e-mail")
                skipped += 1
        elif _is_url(raw):
            if db.update_job_apply_link(url, raw):
                print(f"✓ apply_link: {raw[:60]}...")
                link_updated += 1
            else:
                print("erro ao salvar link")
                skipped += 1
        else:
            print(f"resposta não reconhecida: {raw[:50]}")
            skipped += 1

        time.sleep(0.6)

    print(f"\n  ✓ Deep Recovery: {email_updated} e-mails (→ PENDING), {link_updated} links (apply_link), {skipped} ignorados.\n")
    return {"total": len(targets), "email_updated": email_updated, "link_updated": link_updated, "skipped": skipped}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Recuperação profunda: IA extrai e-mail ou link de formulário")
    p.add_argument("--db", default="jobs.db", help="Caminho do jobs.db")
    p.add_argument("--limit", type=int, default=None, help="Máximo de vagas a processar")
    args = p.parse_args()
    run_deep_recovery(db_path=args.db, limit=args.limit)
