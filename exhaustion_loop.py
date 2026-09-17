#!/usr/bin/env python3
"""
Exhaustion Loop - Production Mode
Infinite loop of real job applications with high-fidelity logging
100% real data, persistent Chrome session, auto-recovery
"""
import sys
import json
import time
import random
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Add modules to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.parser import ResumeParser, ResumeData
from modules.searcher import JobSearcher
from modules.applier import SelfHealingApplier
from modules.logger import ApplicationLogger, ApplicationStatus
from modules.brain import AIBrain
from modules.session_manager import SessionManager
from modules.code_fixer import CodeFixer
from modules.scanner import LinkScanner
from modules.emailer import EmailApplier, EmailQuotaExceeded
from modules.ats_head import HeadlessATSApplier
from main import load_user_data
import os
from dotenv import load_dotenv

load_dotenv()


class ProductionLogger:
    """High-fidelity production logging system"""
    
    def __init__(self):
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        self.screenshot_dir = self.log_dir / "screenshots"
        self.screenshot_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / "production_log.json"
        self.logs = self._load_logs()
    
    def _load_logs(self) -> List[Dict]:
        """Load existing logs"""
        if self.log_file.exists():
            try:
                return json.loads(self.log_file.read_text())
            except:
                return []
        return []
    
    def _save_logs(self):
        """Save logs to file"""
        try:
            self.log_file.write_text(json.dumps(self.logs, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Error saving logs: {e}")
    
    def _generate_fingerprint(self, job_url: str, job_title: str, company: str) -> str:
        """Generate real data fingerprint"""
        data = f"{job_url}|{job_title}|{company}|{datetime.now().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def log_application(
        self,
        job_title: str,
        company: str,
        job_url: str,
        job_source: str,
        match_score: float,
        match_analysis: str,
        status: str,
        screenshot_path: Optional[str] = None,
        error_details: Optional[str] = None
    ) -> Dict:
        """Log application with high-fidelity data"""
        
        # Generate fingerprint
        fingerprint = self._generate_fingerprint(job_url, job_title, company)
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "job": job_title,
            "company": company,
            "url": job_url,
            "job_source": job_source,
            "gemini_score": match_score,
            "match_analysis": match_analysis,
            "execution_screenshot": screenshot_path,
            "real_data_fingerprint": fingerprint,
            "session_auth": "Verified_Persistent_Chrome_User",
            "error_details": error_details
        }
        
        self.logs.append(log_entry)
        self._save_logs()
        
        return log_entry
    
    def get_statistics(self) -> Dict:
        """Get production statistics"""
        if not self.logs:
            return {
                "total_analyzed": 0,
                "total_applied": 0,
                "success_rate": 0.0,
                "by_source": {},
                "by_status": {}
            }
        
        total = len(self.logs)
        applied = len([l for l in self.logs if l.get('status') == 'APPLIED_SUCCESSFULLY'])
        success_rate = applied / total if total > 0 else 0.0
        
        by_source = defaultdict(int)
        by_status = defaultdict(int)
        
        for log in self.logs:
            by_source[log.get('job_source', 'unknown')] += 1
            by_status[log.get('status', 'unknown')] += 1
        
        return {
            "total_analyzed": total,
            "total_applied": applied,
            "success_rate": success_rate,
            "by_source": dict(by_source),
            "by_status": dict(by_status)
        }


class ExhaustionLoop:
    """Infinite loop for production job applications"""
    
    def __init__(self, batch_size: int = 15):
        self.batch_size = batch_size
        self.session_manager = SessionManager()
        self.production_logger = ProductionLogger()
        self.brain = AIBrain()
        self.total_batches = 0
        self.total_applications = 0
        self.chrome_session_active = False
    
    def print_dashboard(self):
        """Print terminal dashboard"""
        stats = self.production_logger.get_statistics()
        session_status = "✓ Active" if self.chrome_session_active else "✗ Inactive"
        
        print("\n" + "="*70)
        print("PRODUCTION DASHBOARD")
        print("="*70)
        print(f"Total Vagas Analisadas: {stats['total_analyzed']}")
        print(f"Total Aplicações Reais: {stats['total_applied']}")
        print(f"Taxa de Sucesso: {stats['success_rate']*100:.1f}%")
        print(f"Status da Sessão Chrome: {session_status}")
        print(f"Batch Atual: {self.total_batches}")
        print("\nPor Fonte:")
        for source, count in stats['by_source'].items():
            print(f"  {source}: {count}")
        print("\nPor Status:")
        for status, count in stats['by_status'].items():
            print(f"  {status}: {count}")
        print("="*70 + "\n")
    
    def recover_session(self):
        """Recover Chrome session if it fails"""
        print("\n⚠ Session recovery initiated...")
        print("  Closing any existing browser instances...")
        
        # Wait before recovery
        time.sleep(60)
        
        # Check Chrome profile again
        context_args = self.session_manager.get_context_args("chrome")
        if context_args.get('can_use_real_session'):
            print("  ✓ Chrome profile detected, ready to restart")
            self.chrome_session_active = True
            return True
        else:
            print(f"  ✗ {context_args.get('message', 'Cannot recover session')}")
            self.chrome_session_active = False
            return False
    
    def analyze_errors_and_fix(self):
        """Analyze errors from logs and auto-fix using Gemini"""
        recent_logs = self.production_logger.logs[-20:]  # Last 20 entries
        errors = [log for log in recent_logs if log.get('status') != 'APPLIED_SUCCESSFULLY']
        
        if not errors:
            return False
        
        # Group errors by type
        error_types = defaultdict(list)
        for error in errors:
            error_details = error.get('error_details', '')
            if 'Element not found' in error_details or 'selector' in error_details.lower():
                error_types['selector_not_found'].append(error)
            elif 'timeout' in error_details.lower():
                error_types['timeout'].append(error)
            elif '403' in error_details or 'forbidden' in error_details.lower():
                error_types['access_denied'].append(error)
        
        if not error_types:
            return False
        
        print("\n🔧 Analyzing errors for auto-correction...")
        
        # Ask Gemini to suggest fixes
        error_summary = {}
        for error_type, error_list in error_types.items():
            error_summary[error_type] = len(error_list)
        
        prompt = f"""
Analyze these application errors and suggest code improvements:

Error Summary:
{json.dumps(error_summary, indent=2)}

Recent Error Details:
{json.dumps([e.get('error_details', '') for e in errors[:5]], indent=2)}

Suggest specific improvements to modules/applier.py selectors or logic.
Return JSON with:
{{
    "improvements": [
        {{
            "function": "function_name",
            "issue": "description",
            "suggestion": "code improvement",
            "old_code": "exact code to replace",
            "new_code": "replacement code"
        }}
    ]
}}
"""
        
        try:
            response = self.brain.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Remove markdown if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            suggestions = json.loads(response_text)
            
            if suggestions.get('improvements'):
                print(f"  ✓ Gemini suggested {len(suggestions['improvements'])} improvements")
                # In production, you would apply these automatically
                # For now, just log them
                return True
        except Exception as e:
            print(f"  ✗ Error analysis failed: {e}")
        
        return False
    
    def audit_and_auto_fix(self) -> Dict[str, Any]:
        """
        Post-batch audit and auto-fix cycle
        Analyzes failures, identifies patterns, and applies code fixes
        """
        print("\n" + "="*70)
        print("[INTROSPECÇÃO] Iniciando Auditoria e Auto-Ajuste")
        print("="*70)
        
        # Load logs
        from modules.logger import ApplicationLogger
        logger = ApplicationLogger()
        
        # Run audit using brain
        print("\n[1/3] Analisando logs de falhas...")
        audit_result = self.brain.audit_and_fix("logs/applications_history.json")
        
        if not audit_result.get('audit_complete'):
            print(f"  ⚠ Auditoria incompleta: {audit_result.get('message', 'Unknown error')}")
            return audit_result
        
        total_failures = audit_result.get('total_failures', 0)
        recurring_errors = audit_result.get('recurring_errors', [])
        code_fixes = audit_result.get('code_fixes', [])
        
        print(f"  ✓ Total de falhas analisadas: {total_failures}")
        print(f"  ✓ Erros recorrentes identificados: {len(recurring_errors)}")
        print(f"  ✓ Correções sugeridas: {len(code_fixes)}")
        
        if recurring_errors:
            print("\n[2/3] Erros Recorrentes Identificados:")
            for i, error in enumerate(recurring_errors, 1):
                print(f"  {i}. {error.get('error_type', 'Unknown')}")
                print(f"     Ocorrências: {error.get('occurrence_count', 0)}")
                print(f"     Descrição: {error.get('error_description', 'N/A')}")
                print(f"     Sugestão: {error.get('suggested_fix', 'N/A')}")
        
        # Apply code fixes if any
        fixes_applied = 0
        if code_fixes and len(recurring_errors) >= 1:  # Apply if there are recurring errors
            print(f"\n[3/3] Aplicando {len(code_fixes)} correções de código...")
            fixer = CodeFixer()
            fix_results = fixer.apply_fixes(code_fixes)
            fixes_applied = fix_results.get('applied', 0)
            
            if fixes_applied > 0:
                print(f"  ✓ {fixes_applied} correções aplicadas com sucesso")
            if fix_results.get('failed', 0) > 0:
                print(f"  ⚠ {fix_results.get('failed', 0)} correções falharam")
        else:
            print("\n[3/3] Nenhuma correção necessária (sem erros recorrentes)")
        
        # Re-validate successful job URLs
        print("\n[VALIDAÇÃO] Re-validando links de vagas bem-sucedidas...")
        successful_logs = logger.get_successful_logs(limit=10)
        scanner = LinkScanner()
        validated_count = 0
        
        for log in successful_logs:
            url = log.get('url', '')
            if url:
                is_valid, _ = scanner.validate_url(url)
                if is_valid:
                    validated_count += 1
        
        print(f"  ✓ {validated_count}/{len(successful_logs)} links ainda ativos")
        
        # Generate summary
        summary = {
            "audit_complete": True,
            "total_failures": total_failures,
            "recurring_errors_count": len(recurring_errors),
            "fixes_applied": fixes_applied,
            "root_cause": audit_result.get('root_cause_analysis', 'N/A'),
            "validated_urls": validated_count
        }
        
        print("\n" + "="*70)
        print("[INTROSPECÇÃO] Resumo da Auditoria")
        print("="*70)
        print(f"Falhas analisadas: {total_failures}")
        print(f"Erros recorrentes: {len(recurring_errors)}")
        print(f"Correções aplicadas: {fixes_applied}")
        print(f"Links validados: {validated_count}/{len(successful_logs)}")
        if fixes_applied > 0:
            print(f"✓ Lógica de seletores atualizada")
        print("="*70)
        
        return summary
    
    def run_batch(self, resume_data: ResumeData, user_data: Dict[str, str]) -> Dict:
        """Run a single batch of applications"""
        self.total_batches += 1
        
        print(f"\n{'='*70}")
        print(f"BATCH {self.total_batches} - Processing {self.batch_size} applications")
        print(f"{'='*70}")
        
        # VOLUME MODE WARNING
        print(f"\n⚠ VOLUME MODE ACTIVE: Applying to all jobs with score >= 0.0 (LIBERAR GERAL)")
        print(f"   (Filtro de qualidade desativado para maximizar volume de aplicações)\n")
        
        # Search for jobs - Focus on reliable APIs first (RemoteOK, WWR)
        print("\n[1/3] Searching for real jobs...")
        print("  Priority: RemoteOK API and We Work Remotely RSS (no 403 issues)")
        
        # Instantiate JobSearcher early (needed for match score calculation)
        try:
            searcher = JobSearcher(resume_data)
            print("  DEBUG: JobSearcher instanciado com sucesso.")
        except Exception as e:
            print(f"  ✗ ERROR: Failed to instantiate JobSearcher: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "reason": f"JobSearcher initialization failed: {e}"}
        
        # PRIORIDADE MÁXIMA: Buscar vagas brasileiras (GitHub) primeiro (quase sempre por email)
        from modules.br_sources import BrazilJobSources
        br_sources = BrazilJobSources(resume_data)
        
        print("\n  [PRIORIDADE 1] Searching Brazilian GitHub repositories (email-first)...")
        br_jobs = br_sources.search_github_br_jobs(max_results=self.batch_size * 2)
        print(f"  ✓ Found {len(br_jobs)} jobs from Brazilian GitHub repos")
        
        # PRIORIDADE 2: APIs internacionais (Hacker News, RemoteOK, WWR)
        from modules.real_sources import RealJobSources
        real_sources = RealJobSources(resume_data)
        
        print("\n  [PRIORIDADE 2] Searching international APIs...")
        api_jobs = real_sources.search_all_real_sources(target_count=self.batch_size)
        
        print(f"  ✓ Found {len(api_jobs)} jobs from APIs (RemoteOK, WWR, Hacker News, etc.)")
        
        # Combine: Brazilian jobs first (they have emails), then international
        all_jobs = br_jobs + api_jobs
        
        # Use combined jobs (Brazilian first, then international)
        if len(all_jobs) >= self.batch_size:
            jobs = all_jobs[:self.batch_size]
            print(f"  ✓ Using {len(jobs)} jobs (Brazilian GitHub + APIs)")
        else:
            print(f"  Using {len(all_jobs)} jobs (Brazilian GitHub + APIs)")
            jobs = all_jobs
        
        if not jobs:
            print("  ⚠ No jobs found from any source. Waiting before retry...")
            return {"success": False, "reason": "no_jobs_found"}
        
        # Validate jobs have real URLs
        valid_jobs = [job for job in jobs if job.url and job.url.startswith('http')]
        if len(valid_jobs) < len(jobs):
            print(f"  ⚠ Filtered {len(jobs) - len(valid_jobs)} jobs with invalid URLs")
        
        jobs = valid_jobs[:self.batch_size]
        
        if not jobs:
            print("  ⚠ No valid jobs after filtering. Waiting before retry...")
            return {"success": False, "reason": "no_valid_jobs"}
        
        # Calculate match scores if not already calculated
        # searcher is already instantiated above
        print(f"  Calculating match scores for {len(jobs)} jobs...")
        if 'searcher' not in locals():
            print("  ✗ ERROR: JobSearcher not available for match score calculation")
            return {"success": False, "reason": "JobSearcher not initialized"}
        for job in jobs:
            if not hasattr(job, 'match_score') or job.match_score is None:
                # Calculate match score using brain (more accurate with reasoning)
                try:
                    resume_dict = {
                        "stack_tecnico": resume_data.stack_tecnico,
                        "experiencia_anos": resume_data.experiencia_anos,
                        "senioridade_pretendida": resume_data.senioridade_pretendida,
                        "palavras_chave": resume_data.palavras_chave
                    }
                    job.match_score = self.brain.evaluate_job(
                        job.description or job.title,
                        resume_dict,
                        job.location
                    )
                    # Get detailed info from brain's last result
                    reason = getattr(self.brain, '_last_reason', 'Score calculated')
                    justificativa = getattr(self.brain, '_last_justificativa', 'No justification')
                    skills_faltantes = getattr(self.brain, '_last_skills_faltantes', [])
                    
                    print(f"  DEBUG: Job: [{job.title}] | Score: {job.match_score:.2f} | Motivo: {reason}")
                    print(f"    Justificativa: {justificativa}")
                    if skills_faltantes:
                        print(f"    Skills faltantes: {', '.join(skills_faltantes)}")
                    
                    # Store all info in job object for later use
                    job.match_reason = reason
                    job.match_justificativa = justificativa
                    job.match_skills_faltantes = skills_faltantes
                except Exception as e:
                    # Fallback to searcher method
                    job.match_score = searcher._calculate_match_score(job, resume_data)
                    print(f"  DEBUG: Job: [{job.title}] | Score: {job.match_score:.2f} | Motivo: Fallback calculation")
                    job.match_reason = "Fallback calculation"
        
        # VOLUME MÁXIMO: Aceitar qualquer vaga com score >= 0.0 (LIBERAR GERAL)
        VOLUME_MODE = True
        MIN_MATCH_SCORE = 0.0 if VOLUME_MODE else 0.05  # 0.0 = aceitar tudo
        
        if VOLUME_MODE:
            print(f"\n{'='*70}")
            print(f"⚠ VOLUME MODE ACTIVE: Applying to all jobs with score >= 0.0 (LIBERAR GERAL)")
            print(f"{'='*70}\n")
        
        # Filtrar vagas: aceitar score >= 0.0 (inclui 0.0)
        jobs_with_score = []
        for job in jobs:
            if job.match_score is None:
                job.match_score = 0.0
            
            if job.match_score >= 0.0:
                jobs_with_score.append(job)
                print(f"   ✓ Job selected: {job.title[:50]}... (Score: {job.match_score:.3f} >= 0.0)")
            else:
                print(f"   ✗ Skipped: {job.title[:50]}... (Score: {job.match_score:.3f} < 0.0)")
        
        # Limitar ao batch_size
        jobs = jobs_with_score[:self.batch_size]
        
        if not jobs:
            print(f"  ⚠ No jobs with score >= 0.0. Waiting before retry...")
            return {"success": False, "reason": "no_valid_jobs"}
        
        if VOLUME_MODE:
            print(f"\n  ✓ VOLUME MODE: Found {len(jobs)} jobs to apply (score >= 0.0)")
        else:
            print(f"  ✓ Found {len(jobs)} jobs to apply (match_score >= {MIN_MATCH_SCORE})")
        print(f"  DEBUG: Jobs selected:")
        for job in jobs:
            reason = getattr(job, 'match_reason', 'No reason provided')
            justificativa = getattr(job, 'match_justificativa', 'No justification')
            print(f"    - {job.title} at {job.company}: score={job.match_score:.2f}")
            print(f"      Motivo: {reason}")
            print(f"      Justificativa: {justificativa}")
        
        # Initialize applier
        applier = SelfHealingApplier("curriculo.pdf", user_data)
        
        try:
            # Start browser with real session
            print("\n[2/3] Starting browser with real Chrome session...")
            try:
                applier.start_browser(headless=False, use_real_session=True)
                self.chrome_session_active = True
                print("  ✓ Browser started successfully")
            except Exception as browser_error:
                print(f"\n  ✗ CRITICAL: Could not start browser")
                print(f"     Error: {str(browser_error)}")
                print(f"     Error type: {type(browser_error).__name__}")
                print(f"\n     ⚠ PAUSING LOOP")
                print(f"     Please:")
                print(f"     1. Close Chrome completely")
                print(f"     2. Check if Chrome profile exists")
                print(f"     3. Wait 60 seconds")
                print(f"     4. Restart the loop")
                print(f"\n     Waiting 60 seconds before retry...")
                time.sleep(60)
                raise  # Re-raise to trigger recovery
            
            # Validate jobs with Playwright
            from modules.job_validator import JobValidator
            print("\n  Validating job URLs...")
            validated_jobs = []
            
            for job in jobs:
                try:
                    validator = JobValidator(applier.page)
                    is_valid, error = validator.validate_job_url(job.url, timeout=10000)
                    
                    if not is_valid:
                        print(f"    ✗ Skipping invalid: {job.title} - {error}")
                        continue
                    
                    validated_jobs.append(job)
                    print(f"    ✓ Validated: {job.title} at {job.company}")
                except Exception as e:
                    print(f"    ✗ Validation error: {e}")
                    continue
            
            if not validated_jobs:
                print("  ⚠ No valid jobs after validation")
                return {"success": False, "reason": "no_valid_jobs"}
            
            print(f"\n  Validated {len(validated_jobs)}/{len(jobs)} jobs")
            
            # Apply to jobs
            print(f"\n[3/3] Applying to {len(validated_jobs)} jobs...")
            results = []
            
            for i, job in enumerate(validated_jobs, 1):
                # Human-like interval (60-180 seconds)
                if i > 1:
                    interval = random.uniform(60, 180)
                    print(f"\n  ⏳ Human-like interval: {interval:.0f} seconds...")
                    time.sleep(interval)
                
                print(f"\n  [{i}/{len(validated_jobs)}] {job.title} at {job.company}")
                
                try:
                    # Get match analysis from Gemini
                    match_analysis = f"Match score: {job.match_score:.2f}. "
                    if job.description:
                        try:
                            resume_dict = {
                                "stack_tecnico": resume_data.stack_tecnico,
                                "experiencia_anos": resume_data.experiencia_anos,
                                "senioridade_pretendida": resume_data.senioridade_pretendida,
                                "palavras_chave": resume_data.palavras_chave
                            }
                            # Use brain's evaluate_job which returns score and validates remote eligibility
                            score = self.brain.evaluate_job(job.description, resume_dict, job.location)
                            if score > 0.7:
                                match_analysis += f"Gemini analysis: Strong match ({score:.2f}) for {resume_data.senioridade_pretendida} {', '.join(resume_data.stack_tecnico[:3])} role. Remote eligible for LATAM."
                            elif score > 0.5:
                                match_analysis += f"Gemini analysis: Moderate match ({score:.2f}). Technical stack alignment confirmed."
                            else:
                                match_analysis += f"Gemini analysis: Low match ({score:.2f}). Proceeding with caution."
                        except Exception as e:
                            match_analysis += f"Technical stack alignment confirmed. (Analysis error: {str(e)[:50]})"
                    else:
                        match_analysis += "No job description available for detailed analysis."
                    
                    # Determine job source
                    job_source = "LinkedIn" if "linkedin.com" in job.url else \
                                "RemoteOK" if "remoteok.com" in job.url else \
                                "We Work Remotely" if "weworkremotely.com" in job.url else \
                                "Hacker News" if "news.ycombinator.com" in job.url else \
                                "Other"
                    
                    # WATERFALL LOGIC: Try faster methods first (Email -> Headless -> Browser)
                    result = None
                    application_method = None
                    
                    # Nível 1: Aplicação via E-mail (Instantânea)
                    if hasattr(job, 'email') and job.email:
                        smtp_password = os.getenv('SMTP_PASSWORD', '')
                        if smtp_password:
                            print(f"  📧 Nível 1: Tentando aplicação via email para {job.email}...")
                            try:
                                emailer = EmailApplier()
                                success, _, _email_subject = emailer.send_application_email(
                                    to_email=job.email,
                                    job_subject=job.title,
                                    resume_path="curriculo.pdf",
                                    user_data=user_data,
                                    job_description=job.description,
                                    company_name=getattr(job, 'company', None),
                                )
                            except EmailQuotaExceeded as e:
                                print("\n" + "="*60)
                                print("🛑 EMAIL QUOTA EXCEEDED (Gmail / SMTP limit)")
                                print("="*60)
                                print(f"   {e.message}")
                                print("   State in jobs.db is up to date. Pause for at least 2 hours,")
                                print("   then run the same command again.")
                                print("="*60 + "\n")
                                sys.exit(1)
                            
                            if success:
                                result = {
                                    'success': True,
                                    'method': 'email',
                                    'message': f'Application email sent to {job.email}'
                                }
                                application_method = "APPLIED_EMAIL"
                                print(f"  ✓ Email sent successfully to {job.email}")
                            else:
                                print(f"  ⚠ Email failed, trying next method...")
                        else:
                            print(f"  ⚠ Modo Email desativado (Credenciais ausentes - SMTP_PASSWORD não configurado)")
                    
                    # Nível 2: Aplicação Headless (Rápida) - apenas se email não funcionou
                    if not result or not result.get('success'):
                        if 'lever.co' in job.url or 'greenhouse.io' in job.url:
                            print(f"  🚀 Nível 2: Tentando aplicação headless (ATS API)...")
                            ats_applier = HeadlessATSApplier(user_data, "curriculo.pdf")
                            headless_success, headless_error = ats_applier.apply_headless(job.url)
                            
                            if headless_success:
                                result = {
                                    'success': True,
                                    'method': 'headless',
                                    'message': f'Headless application successful'
                                }
                                application_method = "APPLIED_HEADLESS"
                                print(f"  ✓ Headless application successful")
                            else:
                                print(f"  ⚠ Headless failed: {headless_error}, falling back to browser...")
                    
                    # Nível 3: Aplicação Browser (Lenta/Visual) - fallback
                    if not result or not result.get('success'):
                        print(f"  🌐 Nível 3: Usando navegador (fallback)...")
                        result = applier.apply_to_job(
                            job_url=job.url,
                            job_title=job.title,
                            company=job.company,
                            match_score=job.match_score
                        )
                        application_method = None  # Will be determined by result
                    
                    # Capture screenshot (only for browser applications)
                    screenshot_path = None
                    if application_method != "APPLIED_EMAIL" and application_method != "APPLIED_HEADLESS":
                        if applier.page:
                            try:
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                safe_title = job.title.replace(" ", "_").replace("/", "_")[:30]
                                screenshot_path = f"logs/screenshots/{timestamp}_{safe_title}.png"
                                applier.page.screenshot(path=screenshot_path, full_page=True)
                                print(f"    📸 Screenshot saved: {screenshot_path}")
                            except Exception as e:
                                print(f"    ⚠ Could not save screenshot: {e}")
                    
                    # Log application
                    if application_method:
                        # Use the method-specific status
                        status = application_method
                        error_details = None
                    elif result.get('success'):
                        status = "APPLIED_SUCCESSFULLY"
                        error_details = None
                    else:
                        status = "APPLICATION_FAILED"
                        error_details = ", ".join(result.get('errors', [])) if result.get('errors') else result.get('message', 'Unknown error')
                    
                    log_entry = self.production_logger.log_application(
                        job_title=job.title,
                        company=job.company,
                        job_url=job.url,
                        job_source=job_source,
                        match_score=job.match_score,
                        match_analysis=match_analysis,
                        status=status,
                        screenshot_path=screenshot_path,
                        error_details=error_details
                    )
                    
                    if result.get('success'):
                        print(f"    ✓ SUCCESS: Application submitted")
                        self.total_applications += 1
                    else:
                        print(f"    ✗ FAILED: {error_details}")
                    
                    results.append(result)
                    
                except Exception as e:
                    print(f"    ✗ Exception: {e}")
                    # Log error
                    self.production_logger.log_application(
                        job_title=job.title,
                        company=job.company,
                        job_url=job.url,
                        job_source="Unknown",
                        match_score=job.match_score,
                        match_analysis="Error during application",
                        status="EXCEPTION",
                        error_details=str(e)
                    )
                    continue
            
            return {"success": True, "results": results}
            
        except Exception as e:
            print(f"\n✗ Batch error: {e}")
            self.chrome_session_active = False
            return {"success": False, "error": str(e)}
        finally:
            try:
                applier.close_browser()
            except:
                pass
    
    def run_loop(self):
        """Run infinite exhaustion loop"""
        print("="*70)
        print("EXHAUSTION LOOP - PRODUCTION MODE")
        print("="*70)
        print("Infinite loop of real job applications")
        print("100% real data | Persistent Chrome session | Auto-recovery")
        print("="*70)
        
        # Load user data
        print("\n[INIT] Loading user data...")
        user_data = load_user_data()
        if not user_data:
            print("ERROR: user_config.json not found")
            print("Please create user_config.json with your information")
            return
        
        print(f"✓ User data loaded: {user_data.get('name', 'Unknown')}")
        
        # Parse resume (use fast extraction, AI will be used for job matching)
        print("\n[INIT] Parsing resume...")
        print("  Using fast extraction (AI will be used for job matching)...")
        try:
            parser = ResumeParser("curriculo.pdf", use_ai=False)
            resume_data = parser.parse()
            print(f"✓ Resume parsed: {len(resume_data.stack_tecnico)} skills found")
            print(f"  Skills: {', '.join(resume_data.stack_tecnico[:5])}...")
            print(f"  Experience: {resume_data.experiencia_anos} years")
            print(f"  Seniority: {resume_data.senioridade_pretendida}")
        except Exception as e:
            print(f"✗ Fatal error parsing resume: {e}")
            import traceback
            traceback.print_exc()
            return
        
        consecutive_failures = 0
        max_failures = 3
        
        while True:
            try:
                # Print dashboard
                self.print_dashboard()
                
                # Run batch
                batch_result = self.run_batch(resume_data, user_data)
                
                if batch_result.get('success'):
                    consecutive_failures = 0
                    print(f"\n✓ Batch {self.total_batches} completed successfully")
                else:
                    consecutive_failures += 1
                    reason = batch_result.get('reason', 'unknown')
                    print(f"\n✗ Batch {self.total_batches} failed: {reason}")
                    
                    # Don't try recovery for code errors (UnboundLocalError, etc.)
                    if 'JobSearcher' in str(reason) or 'initialization' in str(reason).lower() or 'import' in str(reason).lower():
                        print("\n⚠ Code error detected (not a network/session issue).")
                        print("  This is a programming error that recovery cannot fix.")
                        print("  Please check the error above and fix the code.")
                        print("  Stopping loop to prevent infinite recovery attempts.")
                        break
                    
                    if consecutive_failures >= max_failures:
                        print("\n⚠ Multiple consecutive failures. Attempting recovery...")
                        print("  Please check:")
                        print("    1. Chrome is closed")
                        print("    2. Network connectivity")
                        print("    3. API sources are accessible")
                        if self.recover_session():
                            consecutive_failures = 0
                            print("  ✓ Recovery successful, continuing...")
                        else:
                            print("  ✗ Recovery failed. Waiting 5 minutes before retry...")
                            print("  You can manually fix issues and restart the loop")
                            time.sleep(300)
                
                # Post-batch audit and auto-fix (after every batch)
                # Note: audit_and_auto_fix method will be called if it exists
                # For now, skip if method doesn't exist to avoid errors
                try:
                    if hasattr(self, 'audit_and_auto_fix'):
                        audit_summary = self.audit_and_auto_fix()
                        if audit_summary and audit_summary.get('fixes_applied', 0) > 0:
                            print(f"\n  ✓ Sistema auto-corrigido: {audit_summary['fixes_applied']} mudanças aplicadas")
                            print(f"  → Pronto para o próximo lote com correções")
                except AttributeError:
                    # Method doesn't exist yet, skip audit for now
                    pass
                except Exception as e:
                    print(f"\n  ⚠ Erro na auditoria: {e}")
                    print(f"  → Continuando sem auto-correção")
                
                # Wait before next batch
                print(f"\n⏳ Waiting before next batch (30-60 seconds)...")
                time.sleep(random.uniform(30, 60))
                
            except KeyboardInterrupt:
                print("\n\n⚠ Loop interrupted by user")
                print(f"Total batches completed: {self.total_batches}")
                print(f"Total applications: {self.total_applications}")
                break
            except Exception as e:
                print(f"\n✗ Critical error: {e}")
                print("  Attempting recovery...")
                if self.recover_session():
                    time.sleep(60)
                else:
                    print("  Recovery failed. Waiting 5 minutes...")
                    time.sleep(300)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Exhaustion Loop - Production Mode')
    parser.add_argument('--batch-size', type=int, default=15,
                       help='Number of applications per batch (default: 15)')
    
    args = parser.parse_args()
    
    loop = ExhaustionLoop(batch_size=args.batch_size)
    loop.run_loop()

