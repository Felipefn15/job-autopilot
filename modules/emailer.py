"""
Email Application Module (envio exclusivo smtplib).
Montagem do e-mail: MIMEMultipart, MIMEText (corpo), MIMEBase (anexo do currículo).
Conexão: SMTP_SERVER + SMTP_PORT, starttls() para criptografia. Sem SendGrid.
Template dinâmico: tecnologias e anos de experiência (ex.: 8 anos) no assunto e no corpo.
"""
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional, Dict, Tuple
from email.utils import make_msgid
from dotenv import load_dotenv

load_dotenv()


def get_do_not_contact_emails() -> set:
    """Load emails that replied / do not contact again (one per line in do_not_contact.txt)."""
    path = Path(__file__).resolve().parent.parent / "do_not_contact.txt"
    if not path.exists():
        return set()
    try:
        emails = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                emails.add(line.lower())
        return emails
    except Exception:
        return set()


class EmailQuotaExceeded(Exception):
    """
    Levantada quando Gmail/SMTP retorna limite de envio (quota ou taxa).
    O orquestrador deve pausar, salvar estado e avisar o usuário.
    """
    def __init__(self, message: str = "Email sending limit reached (quota or rate limit)"):
        self.message = message
        super().__init__(self.message)


class EmailApplier:
    """Envia candidaturas por e-mail via Gmail SMTP (smtplib). Recebe e-mail extraído e dispara imediatamente."""

    def __init__(self):
        # Gmail SMTP: variáveis GMAIL_USER e GMAIL_APP_PASSWORD no .env (fallback: SMTP_USERNAME / SMTP_PASSWORD)
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('GMAIL_USER') or os.getenv('SMTP_USERNAME', '')
        self.smtp_password = os.getenv('GMAIL_APP_PASSWORD') or os.getenv('SMTP_PASSWORD', '')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_username)
        self.dry_run = os.getenv('DRY_RUN', 'False').lower() == 'true'
        
    def send_application_email(self, to_email: str, job_subject: str, resume_path: str,
                              user_data: Dict[str, str], job_description: str = "", cover_letter: str = None,
                              resume_data: Dict = None, match_score: Optional[float] = None,
                              company_name: Optional[str] = None,
                              job_id: Optional[str] = None,
                              job_description_snippet: Optional[str] = None,
                              language: Optional[str] = None,
                              is_followup: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Envio exclusivo via smtplib. Retorna (success, message_id) para rastreio no banco.
        job_id: used in subject (Ref #) so each email opens a new thread.
        job_description_snippet: post reference (title/role) so recruiter identifies the post.
        language: 'pt', 'en', or 'es' - entire email (snippet intro, sign-off) follows post language.
        """
        if not self.smtp_username or not self.smtp_password:
            print(f"  ⚠ SMTP: credenciais não configuradas. Defina GMAIL_USER e GMAIL_APP_PASSWORD no .env")
            return (False, None, None)

        if self.dry_run:
            print(f"  [DRY_RUN] Would send email to {to_email}")
            return (True, make_msgid(), None)

        try:
            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = to_email
            message_id = make_msgid()
            msg['Message-ID'] = message_id
            candidate_name = user_data.get('name', 'Candidate')
            lang = (language or "en").strip().lower()[:2]
            if lang not in ("pt", "es"):
                lang = "en"
            _cn = (company_name or "").strip()
            if lang == "pt":
                company = _cn if _cn and _cn.lower() not in ("unknown", "") else "sua empresa"
            elif lang == "es":
                company = _cn if _cn and _cn.lower() not in ("unknown", "") else "su empresa"
            else:
                company = _cn if _cn and _cn.lower() not in ("unknown", "") else "your company"

            # Snippet intro and sign-off in post language (so email is consistent)
            if lang == "pt":
                snippet_intro = "Escrevo em relação ao seu post"
                sign_off = "Atenciosamente"
            elif lang == "es":
                snippet_intro = "Escribo respecto a tu publicación"
                sign_off = "Saludos cordiales"
            else:
                snippet_intro = "I'm writing regarding your post"
                sign_off = "Best regards"

            # Assunto: dinâmico com Ref #job_id para nova thread por vaga
            ref_suffix = ""
            if job_id and str(job_id).strip():
                ref_suffix = f" (Ref #{str(job_id).strip()[-8:]})"
            if resume_data:
                years_exp = resume_data.get('experiencia_anos', 8)
                seniority = (resume_data.get('senioridade_pretendida') or 'senior').capitalize()
                skills = resume_data.get('stack_tecnico', [])[:3] or ['Full Stack']
                skills_display = ' / '.join(skills)
                subject_sent = f"{seniority} Full Stack Engineer ({years_exp} years exp) - {job_subject[:40]}{ref_suffix}"
            else:
                subject_sent = f"Application for {job_subject[:60]}{ref_suffix} - {candidate_name}"
            msg['Subject'] = subject_sent

            # Snippet: job title/role + company (language from post)
            snippet_line = ""
            if job_description_snippet and str(job_description_snippet).strip():
                snip = str(job_description_snippet).strip()[:100]
                if len(str(job_description_snippet).strip()) > 100:
                    snip += "..."
                snippet_line = f'{snippet_intro}: "{snip}"\n\n'

            # Follow-up: brief reminder instead of full application
            if is_followup:
                if lang == "pt":
                    followup_body = (
                        f"Olá,\n\n"
                        f"Gostaria de acompanhar minha candidatura enviada recentemente para a vaga acima. "
                        f"Sigo muito interessado na oportunidade e fico à disposição para uma conversa.\n\n"
                        f"Segue meu currículo novamente em anexo.\n\n"
                        f"{sign_off},\n{candidate_name}\n"
                        f"{user_data.get('email', '')}\n{user_data.get('phone', '')}\n{user_data.get('linkedin', '')}"
                    )
                elif lang == "es":
                    followup_body = (
                        f"Hola,\n\n"
                        f"Me gustaría hacer un seguimiento de mi candidatura enviada recientemente para la vacante mencionada. "
                        f"Sigo muy interesado en la oportunidad y quedo disponible para conversar.\n\n"
                        f"Adjunto nuevamente mi currículum.\n\n"
                        f"{sign_off},\n{candidate_name}\n"
                        f"{user_data.get('email', '')}\n{user_data.get('phone', '')}\n{user_data.get('linkedin', '')}"
                    )
                else:
                    followup_body = (
                        f"Hi,\n\n"
                        f"I wanted to follow up on my application sent a few days ago for the above position. "
                        f"I remain very interested in the opportunity and am happy to connect at your convenience.\n\n"
                        f"Please find my resume attached again.\n\n"
                        f"{sign_off},\n{candidate_name}\n"
                        f"{user_data.get('email', '')}\n{user_data.get('phone', '')}\n{user_data.get('linkedin', '')}"
                    )
                if snippet_line:
                    followup_body = snippet_line + followup_body
                if cover_letter and cover_letter.strip():
                    followup_body = followup_body + "\n\n---\n" + cover_letter.strip()
                msg.attach(MIMEText(followup_body, 'plain'))
                # Attach resume and send (skip the rest of the body-building block)
                resume_file = Path(resume_path)
                if not resume_file.exists():
                    print(f"  ⚠ Resume file not found: {resume_path}")
                    return (False, None, subject_sent)
                with open(resume_file, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename= {resume_file.name}')
                msg.attach(part)
                try:
                    server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
                    server.starttls()
                    server.login(self.smtp_username, self.smtp_password)
                    server.send_message(msg)
                    server.quit()
                    print(f"  ✓ SMTP Follow-up sent to {to_email}")
                    return (True, message_id, subject_sent)
                except smtplib.SMTPDataError as e:
                    err_str = str(e).lower()
                    if any(x in err_str for x in ('quota', 'limit', 'exceeded', 'daily', 'sending', 'blocked')):
                        raise EmailQuotaExceeded(f"Gmail/SMTP limit reached. {e}")
                    print(f"  ✗ SMTP Error (follow-up): {e}")
                    return (False, None, subject_sent)
                except Exception as e:
                    print(f"  ✗ Error sending follow-up: {e}")
                    return (False, None, subject_sent)

            # Corpo: cover letter válida OU template Senior-to-Senior
            body = ""
            if cover_letter:
                cover_letter_clean = cover_letter.strip()
                error_indicators = ['ai services unavailable', 'ai services', 'unavailable', 'error', 'failed', '429', 'quota', 'rate limit']
                if cover_letter_clean and not any(x in cover_letter_clean.lower() for x in error_indicators):
                    body = f"""{snippet_line}{cover_letter_clean}

{sign_off},
{candidate_name}
{user_data.get('email', '')}
{user_data.get('phone', '')}
{user_data.get('linkedin', '')}
"""
            if not body and resume_data:
                years_exp = resume_data.get('experiencia_anos', 8)
                skills = resume_data.get('stack_tecnico', [])[:5] or ['Python', 'Node.js', 'React']
                skills_str = ', '.join(skills)
                if lang == "pt":
                    intro = "Olá,"
                    msg_body = f"Sou engenheiro de software sênior com {years_exp} anos de experiência, especializado em {skills_str}. Tenho focado em agentes de IA e automação, alinhado ao que vocês buscam na {company}. Segue meu currículo em anexo."
                elif lang == "es":
                    intro = "Hola,"
                    msg_body = f"Soy ingeniero de software sénior con {years_exp} años de experiencia, especializado en {skills_str}. Mi foco reciente ha sido en agentes de IA y automatización, similar a lo que buscan en {company}. Adjunto mi currículum."
                else:
                    intro = "Hi Hiring Team,"
                    msg_body = f"I am a Senior Full Stack Engineer with {years_exp} years of experience, specialized in {skills_str}. My recent focus has been on AI Agents and Automation Engines, similar to what you are looking for at {company}. Please find my resume attached."
                body = f"""{snippet_line}{intro}

{msg_body}

{sign_off},
{candidate_name}
{user_data.get('email', '')}
{user_data.get('phone', '')}
{user_data.get('linkedin', '')}
"""
            if not body:
                if lang == "pt":
                    body = f"{snippet_line}Olá,\n\nSou engenheiro de software sênior com 8 anos de experiência, especializado em Python, Node.js e React. Segue meu currículo em anexo.\n\n{sign_off},\n{candidate_name}"
                elif lang == "es":
                    body = f"{snippet_line}Hola,\n\nSoy ingeniero de software sénior con 8 años de experiencia, especializado en Python, Node.js y React. Adjunto mi currículum.\n\n{sign_off},\n{candidate_name}"
                else:
                    body = f"{snippet_line}Hi Hiring Team,\n\nI am a Senior Full Stack Engineer with 8 years of experience, specialized in Python, Node.js, and React. Please find my resume attached.\n\n{sign_off},\n{candidate_name}"

            msg.attach(MIMEText(body, 'plain'))

            # Anexo do currículo (MIMEBase / PDF)
            resume_file = Path(resume_path)
            if not resume_file.exists():
                print(f"  ⚠ Resume file not found: {resume_path}")
                return (False, None, subject_sent)
            with open(resume_file, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename= {resume_file.name}')
            msg.attach(part)

            # Conexão SMTP exclusiva (smtplib): SMTP_SERVER, SMTP_PORT, starttls() obrigatório
            try:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
                server.quit()
                score_str = f"{match_score:.2f}" if match_score is not None else "N/A"
                print(f"  ✓ SMTP Delivery: [Score {score_str}] Email enviado para {to_email}")
                return (True, message_id, subject_sent)
            except smtplib.SMTPRecipientsRefused as e:
                print(f"  ✗ SMTP Error: Invalid recipient {to_email}: {e}")
                return (False, None, subject_sent)
            except smtplib.SMTPDataError as e:
                # Quota exceeded ou limite de envio (mailer-daemon) -> travar e avisar
                err_str = str(e).lower()
                if any(x in err_str for x in ('quota', 'limit', 'exceeded', 'daily', 'sending', 'blocked')):
                    print(f"  ✗ SMTP Error (quota/limit): {e}")
                    raise EmailQuotaExceeded(
                        f"Gmail/SMTP limit reached. Stop sending to protect reputation. {e}"
                    )
                print(f"  ✗ SMTP Error: Mailbox full or other data error for {to_email}: {e}")
                return (False, None, subject_sent)
            except smtplib.SMTPServerDisconnected as e:
                err_str = str(e).lower()
                if any(x in err_str for x in ('quota', 'limit', 'exceeded')):
                    raise EmailQuotaExceeded(f"SMTP disconnected (possible quota): {e}")
                print(f"  ✗ SMTP Error: Server disconnected: {e}")
                return (False, None, subject_sent)
            except smtplib.SMTPAuthenticationError as e:
                print(f"  ✗ SMTP Error: Authentication failed: {e}")
                return (False, None, subject_sent)
            except smtplib.SMTPException as e:
                err_str = str(e).lower()
                if any(x in err_str for x in ('quota', 'limit', 'exceeded', 'sending')):
                    raise EmailQuotaExceeded(f"SMTP error (quota/limit): {e}")
                print(f"  ✗ SMTP Error: {e}")
                return (False, None, subject_sent)
            except Exception as e:
                err_str = str(e).lower()
                if any(x in err_str for x in ('quota', 'limit', 'exceeded', 'mailer-daemon')):
                    raise EmailQuotaExceeded(f"Email limit/quota: {e}")
                print(f"  ✗ Error sending email: {e}")
                return (False, None, subject_sent)
        except Exception as e:
            # Outer try block - catch any errors in message creation
            print(f"  ✗ Failed to create/send email: {e}")
            return (False, None, None)
    
    def extract_email_from_text(self, text: str) -> Optional[str]:
        """
        Extract email address from text using regex.
        Supports obfuscated forms: contato [at] empresa.com, recrutamento(at)empresa.com, x at dominio.com
        """
        import re
        if not (text and text.strip()):
            return None
        # Normalize obfuscated [at], (at), " at " to @ (case insensitive)
        normalized = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
        normalized = re.sub(r'\s*\(at\)\s*', '@', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\s+at\s+', '@', normalized, flags=re.IGNORECASE)
        # Standard email regex
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, normalized)
        if matches:
            for email in matches:
                email_lower = email.lower()
                if any(domain in email_lower for domain in ['hiring', 'recruiting', 'jobs', 'careers', 'hr']):
                    return email
            return matches[0]
        return None


if __name__ == "__main__":
    # Test
    emailer = EmailApplier()
    test_email = emailer.extract_email_from_text("Contact us at jobs@example.com or hiring@company.com")
    print(f"Extracted email: {test_email}")

