#!/usr/bin/env python3
# Use: python3 super_loop.py (not python)
"""
Super Loop - Continuous Improvement System
Runs batches of 100 applications until 100% success rate is achieved
Auto-corrects code using Gemini AI based on error analysis
"""
import sys
import json
import time
import random
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict
import subprocess

# Add modules to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.parser import ResumeParser, ResumeData
from modules.searcher import JobSearcher, JobListing
from modules.applier import SelfHealingApplier
from modules.logger import ApplicationLogger, ApplicationStatus
from modules.brain import AIBrain
from main import JobAutomationEngine, load_user_data


class SuperLoop:
    """Orchestrator for continuous improvement loop"""
    
    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
        self.logger = ApplicationLogger()
        self.brain = AIBrain()
        self.current_batch = 0
        self.code_snapshots_dir = Path("code_snapshots")
        self.debug_html_dir = Path("logs/debug_html")
        self.code_snapshots_dir.mkdir(exist_ok=True)
        self.debug_html_dir.mkdir(exist_ok=True)
        
    def create_code_snapshot(self, batch_num: int) -> str:
        """Create a snapshot of current code before auto-adjustment"""
        snapshot_dir = self.code_snapshots_dir / f"batch_{batch_num}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        snapshot_dir.mkdir(exist_ok=True)
        
        # Copy critical files
        files_to_snapshot = [
            "modules/applier.py",
            "modules/brain.py",
            "modules/searcher.py",
            "modules/logger.py"
        ]
        
        for file_path in files_to_snapshot:
            src = Path(file_path)
            if src.exists():
                dst = snapshot_dir / src.name
                shutil.copy2(src, dst)
        
        # Save metadata
        metadata = {
            "batch": batch_num,
            "timestamp": datetime.now().isoformat(),
            "files_snapshot": files_to_snapshot
        }
        
        with open(snapshot_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"  ✓ Code snapshot created: {snapshot_dir}")
        return str(snapshot_dir)
    
    def restore_code_snapshot(self, snapshot_path: str):
        """Restore code from snapshot"""
        snapshot_dir = Path(snapshot_path)
        if not snapshot_dir.exists():
            print(f"  ✗ Snapshot not found: {snapshot_path}")
            return False
        
        metadata_file = snapshot_dir / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            for file_name in metadata.get("files_snapshot", []):
                src = snapshot_dir / Path(file_name).name
                dst = Path(file_name)
                if src.exists():
                    shutil.copy2(src, dst)
                    print(f"  ✓ Restored: {file_name}")
        
        return True
    
    def save_debug_html(self, job_url: str, html_content: str, error_type: str):
        """Save HTML content for debugging"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_url = job_url.replace("https://", "").replace("http://", "").replace("/", "_")[:50]
        filename = f"{timestamp}_{error_type}_{safe_url}.html"
        filepath = self.debug_html_dir / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            return str(filepath)
        except Exception as e:
            print(f"  Error saving debug HTML: {e}")
            return None
    
    def analyze_batch_errors(self, batch_logs: List[Dict]) -> Dict[str, Any]:
        """Analyze errors from a batch and group by type"""
        failed_logs = [log for log in batch_logs if log.get('status') == 'failed']
        
        if not failed_logs:
            return {
                "total": len(batch_logs),
                "successful": len(batch_logs),
                "failed": 0,
                "error_groups": {},
                "success_rate": 1.0
            }
        
        # Group errors by type
        error_groups = defaultdict(list)
        companies_with_errors = defaultdict(list)
        
        for log in failed_logs:
            error_details = log.get('error_details', {})
            error_type = error_details.get('type', 'unknown')
            error_message = error_details.get('message', 'Unknown error')
            
            error_groups[error_type].append({
                "job_title": log.get('job_title'),
                "company": log.get('company'),
                "url": log.get('url'),
                "message": error_message,
                "gemini_suggestion": log.get('gemini_suggestion'),
                "selectors_used": log.get('selectors_used', {}),
                "screenshot_path": log.get('screenshot_path')
            })
            
            companies_with_errors[log.get('company', 'Unknown')].append(error_type)
        
        # Calculate percentages
        total_failed = len(failed_logs)
        error_percentages = {
            error_type: (len(errors) / total_failed * 100)
            for error_type, errors in error_groups.items()
        }
        
        return {
            "total": len(batch_logs),
            "successful": len(batch_logs) - total_failed,
            "failed": total_failed,
            "success_rate": (len(batch_logs) - total_failed) / len(batch_logs) if batch_logs else 0,
            "error_groups": dict(error_groups),
            "error_percentages": error_percentages,
            "companies_with_errors": dict(companies_with_errors)
        }
    
    def auto_correct_code(self, error_analysis: Dict[str, Any]) -> bool:
        """Use Gemini to auto-correct code based on error analysis"""
        print("\n" + "="*60)
        print("AUTO-CORRECTION PHASE")
        print("="*60)
        
        if error_analysis['failed'] == 0:
            print("No errors to correct!")
            return True
        
        # Create snapshot before changes
        snapshot_path = self.create_code_snapshot(self.current_batch)
        
        # Build error summary for Gemini
        error_summary = []
        for error_type, errors in error_analysis['error_groups'].items():
            error_summary.append(f"{error_type}: {len(errors)} occurrences ({error_analysis['error_percentages'][error_type]:.1f}%)")
            # Include examples
            for error in errors[:3]:  # First 3 examples
                error_summary.append(f"  - {error['company']}: {error['message']}")
                if error.get('gemini_suggestion'):
                    error_summary.append(f"    Suggestion: {error['gemini_suggestion']}")
        
        error_summary_text = "\n".join(error_summary)
        
        # Read current applier.py
        applier_code = Path("modules/applier.py").read_text(encoding='utf-8')
        
        prompt = f"""Analyze these application errors and suggest code improvements to modules/applier.py.

ERROR ANALYSIS:
{error_summary_text}

CURRENT CODE (modules/applier.py):
{applier_code[:5000]}  # First 5000 chars

CRITICAL REQUIREMENTS:
1. DO NOT break existing functionality that works
2. Maintain compatibility with sites that already work
3. Focus on fixing the most common error types
4. If error is "selector_not_found", improve field detection logic
5. If error is "timeout" or "element not visible", improve click/submit logic
6. If error is "visa_incompatibility", ensure detection is working
7. Return ONLY the improved code sections, not the entire file
8. Use clear comments explaining the fix

Return a JSON object with:
{{
    "improvements": [
        {{
            "file": "modules/applier.py",
            "function": "function_name",
            "old_code": "code to replace",
            "new_code": "improved code",
            "reason": "why this fixes the error"
        }}
    ],
    "summary": "brief summary of changes"
}}"""

        try:
            print("  Requesting code improvements from Gemini...")
            response = self.brain.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Remove markdown if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            improvements = json.loads(response_text)
            
            print(f"  ✓ Received {len(improvements.get('improvements', []))} improvement suggestions")
            print(f"  Summary: {improvements.get('summary', 'N/A')}")
            
            # Apply improvements
            applied = 0
            for improvement in improvements.get('improvements', []):
                file_path = Path(improvement['file'])
                if not file_path.exists():
                    print(f"  ⚠ File not found: {file_path}")
                    continue
                
                old_code = improvement['old_code']
                new_code = improvement['new_code']
                
                # Read file
                file_content = file_path.read_text(encoding='utf-8')
                
                # Check if old_code exists in file
                if old_code in file_content:
                    # Replace
                    file_content = file_content.replace(old_code, new_code)
                    file_path.write_text(file_content, encoding='utf-8')
                    print(f"  ✓ Applied improvement to {improvement['function']}")
                    applied += 1
                else:
                    print(f"  ⚠ Could not find exact match for {improvement['function']}")
            
            if applied > 0:
                print(f"\n  ✓ Applied {applied} code improvements")
                return True
            else:
                print("\n  ⚠ No improvements could be applied automatically")
                print("  Manual review recommended")
                return False
                
        except Exception as e:
            print(f"\n  ✗ Error during auto-correction: {e}")
            print(f"  Restoring snapshot: {snapshot_path}")
            self.restore_code_snapshot(snapshot_path)
            return False
    
    def run_batch(self, resume_data: ResumeData, user_data: Dict[str, str]) -> Dict[str, Any]:
        """Run a batch of applications"""
        self.current_batch += 1
        
        print("\n" + "="*60)
        print(f"BATCH {self.current_batch} - Processing {self.batch_size} applications")
        print("="*60)
        
        # Search for jobs across 100+ REAL sources - NO MOCK DATA
        print("\n[1/3] Searching for remote jobs across 100+ REAL sources...")
        print("      (NO mock/test data will be generated)")
        searcher = JobSearcher(resume_data)
        
        # Search only real sources - will return empty if no real jobs found
        jobs = searcher.search_all(
            location="Remote", 
            max_per_source=self.batch_size // 2, 
            target_count=self.batch_size
        )
        
        # CRITICAL: If not enough real jobs, STOP - do not generate mock data
        if len(jobs) < self.batch_size:
            print(f"\n⚠⚠⚠ WARNING: Only {len(jobs)} real jobs found (target: {self.batch_size})")
            print("   The system will process only real jobs found.")
            print("   NO mock/test data will be generated.")
            print("   To get more jobs:")
            print("   1. Add API keys to .env (JOOBLE_API_KEY, SERPAPI_KEY)")
            print("   2. Check network connectivity")
            print("   3. Wait for sources to have more postings")
        
        # Filter by match score and limit to batch_size
        jobs = [job for job in jobs if job.match_score >= 0.3][:self.batch_size]
        
        if not jobs:
            print("  ⚠ No jobs found matching criteria")
            return {
                "batch": self.current_batch,
                "total": 0,
                "successful": 0,
                "failed": 0,
                "logs": []
            }
        
        print(f"  ✓ Found {len(jobs)} jobs to apply")
        
        # Get initial log count
        initial_log_count = len(self.logger.logs)
        
        # Apply to jobs
        print(f"\n[2/3] Applying to {len(jobs)} jobs...")
        applier = SelfHealingApplier("curriculo.pdf", user_data)
        # Start browser with real session to avoid 403
        applier.start_browser(headless=False, use_real_session=True)
        
        # Validate jobs with Playwright before applying
        from modules.job_validator import JobValidator
        print("\n  Validating job URLs with Playwright...")
        validated_jobs = []
        
        for job in jobs:
            try:
                validator = JobValidator(applier.page)
                is_valid, error = validator.validate_job_url(job.url, timeout=10000)
                
                if not is_valid:
                    print(f"    ✗ Skipping invalid job: {job.title} - {error}")
                    continue
                
                validated_jobs.append(job)
                print(f"    ✓ Validated: {job.title} at {job.company}")
                
            except Exception as e:
                print(f"    ✗ Validation error for {job.title}: {e}")
                continue
        
        print(f"\n  Validated {len(validated_jobs)}/{len(jobs)} jobs")
        
        if not validated_jobs:
            print("  ⚠ No valid jobs to apply. Closing browser...")
            applier.close_browser()
            return {
                "batch": self.current_batch,
                "total": 0,
                "successful": 0,
                "failed": 0,
                "logs": []
            }
        
        results = []
        try:
            for i, job in enumerate(validated_jobs, 1):
                # Human-like jitter: random delay between 2-5 seconds
                if i > 1:
                    jitter = random.uniform(2.0, 5.0)
                    time.sleep(jitter)
                
                print(f"\n[{i}/{len(jobs)}] {job.title} at {job.company}")
                
                try:
                    result = applier.apply_to_job(
                        job_url=job.url,
                        job_title=job.title,
                        company=job.company,
                        match_score=job.match_score
                    )
                    
                    # Save debug HTML if failed
                    if not result.get('success') and applier.page:
                        try:
                            html_content = applier.page.content()
                            error_type = result.get('errors', ['unknown'])[0] if result.get('errors') else 'unknown'
                            self.save_debug_html(job.url, html_content, error_type)
                        except:
                            pass
                    
                    results.append(result)
                    
                except Exception as e:
                    print(f"  ✗ Exception: {e}")
                    # Save debug HTML
                    if applier.page:
                        try:
                            html_content = applier.page.content()
                            self.save_debug_html(job.url, html_content, 'exception')
                        except:
                            pass
                    
                    results.append({
                        'success': False,
                        'job_title': job.title,
                        'company': job.company,
                        'url': job.url,
                        'errors': [str(e)]
                    })
        finally:
            applier.close_browser()
        
        # Get new logs (only from this batch)
        all_logs = self.logger.logs
        batch_logs = all_logs[initial_log_count:]
        
        print(f"\n[3/3] Batch complete: {len(results)} applications processed")
        
        return {
            "batch": self.current_batch,
            "total": len(results),
            "successful": sum(1 for r in results if r.get('success')),
            "failed": sum(1 for r in results if not r.get('success')),
            "logs": batch_logs
        }
    
    def print_dashboard(self, batch_result: Dict, error_analysis: Dict):
        """Print real-time dashboard"""
        print("\n" + "="*60)
        print("DASHBOARD")
        print("="*60)
        print(f"Batch: {batch_result['batch']}")
        print(f"Total Applications: {batch_result['total']}")
        print(f"Successful: {batch_result['successful']} ({error_analysis['success_rate']*100:.1f}%)")
        print(f"Failed: {batch_result['failed']}")
        
        if error_analysis['error_groups']:
            print("\nError Breakdown:")
            for error_type, percentage in sorted(
                error_analysis['error_percentages'].items(), 
                key=lambda x: x[1], 
                reverse=True
            ):
                count = len(error_analysis['error_groups'][error_type])
                print(f"  {error_type}: {count} ({percentage:.1f}%)")
        
        print("="*60)
    
    def run_loop(self, max_iterations: int = None):
        """Run the continuous improvement loop"""
        print("="*60)
        print("SUPER LOOP - Continuous Improvement System")
        print("="*60)
        print(f"Target: {self.batch_size} applications per batch")
        print("Goal: 100% success rate")
        print("="*60)
        
        # Load resume and user data
        resume_path = Path("curriculo.pdf")
        if not resume_path.exists():
            print("ERROR: curriculo.pdf not found")
            return
        
        user_data = load_user_data()
        if not user_data:
            print("ERROR: user_config.json not found")
            return
        
        parser = ResumeParser(str(resume_path), use_ai=True)
        resume_data = parser.parse()
        
        iteration = 0
        while True:
            iteration += 1
            if max_iterations and iteration > max_iterations:
                print(f"\nReached max iterations: {max_iterations}")
                break
            
            # Run batch
            batch_result = self.run_batch(resume_data, user_data)
            
            if batch_result['total'] == 0:
                print("\nNo jobs to process. Waiting 60 seconds before retry...")
                time.sleep(60)
                continue
            
            # Analyze errors
            error_analysis = self.analyze_batch_errors(batch_result['logs'])
            
            # Print dashboard
            self.print_dashboard(batch_result, error_analysis)
            
            # Check if we achieved 100% success
            if error_analysis['success_rate'] >= 1.0:
                print("\n" + "="*60)
                print("🎉 SUCCESS! 100% success rate achieved!")
                print("="*60)
                print(f"Batch {batch_result['batch']}: {batch_result['successful']}/{batch_result['total']} successful")
                break
            
            # Auto-correct if there are errors
            if error_analysis['failed'] > 0:
                print(f"\n⚠ {error_analysis['failed']} failures detected. Attempting auto-correction...")
                correction_success = self.auto_correct_code(error_analysis)
                
                if correction_success:
                    print("\n✓ Code improvements applied. Starting next batch in 10 seconds...")
                    time.sleep(10)
                else:
                    print("\n⚠ Auto-correction failed or incomplete. Manual review recommended.")
                    print("Continuing with next batch in 30 seconds...")
                    time.sleep(30)
            else:
                print("\n✓ No errors to correct!")
                break


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Super Loop - Continuous Improvement System')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Number of applications per batch (default: 100)')
    parser.add_argument('--max-iterations', type=int, default=None,
                       help='Maximum number of batches (default: unlimited)')
    
    args = parser.parse_args()
    
    loop = SuperLoop(batch_size=args.batch_size)
    loop.run_loop(max_iterations=args.max_iterations)

