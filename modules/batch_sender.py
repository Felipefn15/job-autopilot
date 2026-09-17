"""
Batch Launcher (Wait & Send): envia e-mails PENDING em blocos com pausas
para evitar alerta de spam do Gmail e manter alta taxa de entrega.
"""
import json
import random
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from modules.database import DatabaseManager
from modules.emailer import EmailApplier, EmailQuotaExceeded, get_do_not_contact_emails


def _load_user_data(config_path: str = "user_config.json"):
    path = Path(config_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def run_batch_send(
    limit: int = 57,
    batch_size: int = 5,
    delay_between_batches: int = 60,
    db_path: str = "jobs.db",
    resume_path: str = None,
    config_path: str = "user_config.json",
):
    resume_path = resume_path or Path(__file__).resolve().parent.parent / "curriculo.pdf"
    resume_path = str(Path(resume_path))

    db = DatabaseManager(db_path)
    rows = db.get_pending_jobs(status="PENDING", limit=limit)

    # Apenas vagas com e-mail; job_id = url (post url) para unique (email, job_id)
    pending = []
    for row in rows:
        url = row.get("url", "")
        email = row.get("email") or (url[6:].strip() if (url and str(url).startswith("email:")) else None)
        job_id = row.get("job_id") or url
        if email and "@" in str(email):
            pending.append({
                "url": url or f"email:{email}",
                "email": email,
                "job_id": job_id,
                "title": row.get("title") or "Unknown",
                "company": row.get("company") or "Unknown",
                "match_score": float(row.get("match_score") or 0),
            })
    pending.sort(key=lambda r: r["match_score"], reverse=True)
    pending = pending[:limit]

    if not pending:
        print("📭 Nenhuma vaga PENDING com e-mail encontrada no banco.")
        return

    print(f"🚀 Iniciando envio de {len(pending)} e-mails em blocos de {batch_size}...")

    user_data = _load_user_data(config_path)
    if not user_data.get("name"):
        user_data["name"] = "Candidate"
    if not user_data.get("email"):
        user_data["email"] = __import__("os").getenv("GMAIL_USER", "")

    resume_data_dict = None
    if Path(resume_path).exists():
        try:
            from modules.parser import ResumeParser
            parser = ResumeParser(resume_path)
            rd = parser.parse()
            resume_data_dict = {
                "experiencia_anos": getattr(rd, "experiencia_anos", 8),
                "senioridade_pretendida": getattr(rd, "senioridade_pretendida", "senior"),
                "stack_tecnico": getattr(rd, "stack_tecnico", []),
            }
        except Exception as e:
            print(f"  ⚠ Resume parse skipped: {e}")
            resume_data_dict = {"experiencia_anos": 8, "senioridade_pretendida": "senior", "stack_tecnico": ["Python", "Node.js", "React"]}

    applier = EmailApplier()
    sent_count = 0
    do_not_contact = get_do_not_contact_emails()

    for i, job in enumerate(pending):
        to_email = job["email"]
        if (to_email or "").strip().lower() in do_not_contact:
            print(f"⏭ Pulando (do not contact - já respondeu): {to_email}")
            continue
        title = job["title"]
        company = job["company"]
        score = job["match_score"]
        job_url = job["url"]
        job_id = job.get("job_id") or job_url

        try:
            if getattr(db, "is_sent_to_email_for_job", None) and db.is_sent_to_email_for_job(to_email, job_id):
                print(f"⏭ Pulando: já enviamos para {to_email} para esta vaga (Ref #{str(job_id)[-8:]})")
                continue

            print(f"📧 [{i+1}/{len(pending)}] Enviando para: {title} ({to_email}) | Score: {score}")

            success, smtp_message_id, _email_subject = applier.send_application_email(
                to_email=to_email,
                job_subject=title,
                resume_path=resume_path,
                user_data=user_data,
                job_description="",
                cover_letter=None,
                resume_data=resume_data_dict,
                match_score=score,
                company_name=company,
                job_id=job_id,
                job_description_snippet=None,
            )

            if success:
                sent_count += 1
                db.save_job(
                    {"url": job_url, "title": title, "company": company, "match_score": score, "email": to_email, "job_id": job_id},
                    status="SUCCESS",
                )
                if smtp_message_id:
                    db.update_smtp_message_id(job_url, smtp_message_id)

            # Lógica de lote: a cada batch_size envios, pausa maior
            if sent_count > 0 and sent_count % batch_size == 0 and sent_count < len(pending):
                wait_time = delay_between_batches + random.randint(10, 30)
                print(f"☕ Bloco finalizado. Pausando {wait_time}s para evitar SPAM...")
                time.sleep(wait_time)
            else:
                time.sleep(random.randint(5, 15))

        except EmailQuotaExceeded as e:
            print(f"🛑 Quota SMTP atingida: {e.message}. Interrompendo envio.")
            break
        except Exception as e:
            print(f"❌ Erro ao processar {job_url}: {e}")

    print(f"🏁 Finalizado! {sent_count} e-mails enviados com sucesso.")


if __name__ == "__main__":
    import os
    limit = int(os.getenv("BATCH_SEND_LIMIT", "57"))
    batch_size = int(os.getenv("BATCH_SIZE", "5"))
    delay = int(os.getenv("BATCH_DELAY_SEC", "60"))
    run_batch_send(limit=limit, batch_size=batch_size, delay_between_batches=delay)
