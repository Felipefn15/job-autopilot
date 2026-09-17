"""
Integration Test Script - AI-Powered Stress Test
Runs the full pipeline with real LinkedIn job applications
Uses Gemini AI for self-healing when selectors fail
"""
import sys
from pathlib import Path
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.parser import ResumeParser
from modules.searcher import JobSearcher
from modules.applier import SelfHealingApplier
from modules.brain import AIBrain
from main import JobAutomationEngine
import json
import traceback
import time


def test_parser():
    """Test resume parsing"""
    print("="*60)
    print("TEST 1: Resume Parser")
    print("="*60)
    
    resume_path = Path("curriculo.pdf")
    if not resume_path.exists():
        print(f"ERROR: Resume not found at {resume_path}")
        print("Please ensure curriculo.pdf is in the project root.")
        return None
    
    try:
        parser = ResumeParser(str(resume_path))
        data = parser.parse()
        
        print(f"✓ Parser successful")
        print(f"  Technical Stack: {len(data.stack_tecnico)} skills found")
        print(f"  Years of Experience: {data.experiencia_anos}")
        print(f"  Seniority: {data.senioridade_pretendida}")
        print(f"  Keywords: {len(data.palavras_chave)} found")
        
        return data
    except Exception as e:
        print(f"✗ Parser failed: {e}")
        traceback.print_exc()
        return None


def test_searcher(resume_data):
    """Test job search"""
    print("\n" + "="*60)
    print("TEST 2: Job Searcher")
    print("="*60)
    
    if not resume_data:
        print("SKIP: No resume data available")
        return []
    
    try:
        searcher = JobSearcher(resume_data)
        jobs = searcher.search_all(location="Brazil", max_per_source=5)
        
        print(f"✓ Searcher successful")
        print(f"  Found {len(jobs)} jobs")
        
        if jobs:
            print("\n  Top 3 jobs:")
            for i, job in enumerate(jobs[:3], 1):
                print(f"    {i}. {job.title} at {job.company} (Score: {job.match_score:.2f})")
        
        return jobs
    except Exception as e:
        print(f"✗ Searcher failed: {e}")
        traceback.print_exc()
        return []


def test_applier_stress(job_url: str, max_retries: int = 3):
    """
    Stress test: Apply to a real LinkedIn job with AI-powered self-healing
    If it fails, analyze errors and retry with AI adjustments
    """
    print("\n" + "="*60)
    print("STRESS TEST: Real LinkedIn Job Application")
    print("="*60)
    print(f"Target URL: {job_url}")
    print(f"Max Retries: {max_retries}")
    
    resume_path = Path("curriculo.pdf")
    if not resume_path.exists():
        print("✗ ERROR: Resume not found at curriculo.pdf")
        return None
    
    # Load user config
    config_path = Path("user_config.json")
    if not config_path.exists():
        print("✗ ERROR: user_config.json not found")
        print("Please create user_config.json with your real information")
        return None
    
    with open(config_path, 'r', encoding='utf-8') as f:
        user_data = json.load(f)
    
    print(f"\nUsing user data:")
    print(f"  Name: {user_data.get('name', 'N/A')}")
    print(f"  Email: {user_data.get('email', 'N/A')}")
    
    brain = AIBrain()
    applier = None
    
    for attempt in range(1, max_retries + 1):
        print(f"\n{'='*60}")
        print(f"ATTEMPT {attempt}/{max_retries}")
        print(f"{'='*60}")
        
        try:
            if applier:
                applier.close_browser()
            
            applier = SelfHealingApplier(str(resume_path), user_data)
            applier.start_browser(headless=False)
            
            print(f"\nApplying to job...")
            result = applier.apply_to_job(job_url)
            
            print(f"\n{'='*60}")
            print("APPLICATION RESULT")
            print(f"{'='*60}")
            print(f"Success: {result['success']}")
            print(f"Steps Completed: {', '.join(result.get('steps_completed', []))}")
            
            if result['errors']:
                print(f"\nErrors ({len(result['errors'])}):")
                for error in result['errors']:
                    print(f"  - {error}")
            
            if result['success']:
                print("\n✓ SUCCESS: Application completed!")
                applier.close_browser()
                return result
            else:
                print(f"\n⚠ FAILED: Application did not complete successfully")
                
                # If not last attempt, analyze and retry
                if attempt < max_retries:
                    print(f"\nAnalyzing failure for retry {attempt + 1}...")
                    # The applier already uses AI for self-healing
                    # We can add additional analysis here if needed
                    time.sleep(2)
                else:
                    print("\n✗ All retry attempts exhausted")
                    applier.close_browser()
                    return result
                    
        except Exception as e:
            print(f"\n✗ Exception during application: {e}")
            traceback.print_exc()
            
            if attempt < max_retries:
                print(f"\nRetrying in 3 seconds...")
                time.sleep(3)
            else:
                if applier:
                    applier.close_browser()
                return {'success': False, 'errors': [str(e)]}
    
    if applier:
        applier.close_browser()
    return None


def test_full_pipeline():
    """Test the complete pipeline"""
    print("\n" + "="*60)
    print("TEST 4: Full Pipeline Integration")
    print("="*60)
    
    # Load or create user config
    config_path = Path("user_config.json")
    if not config_path.exists():
        print("WARNING: user_config.json not found. Using test data.")
        user_data = {
            'name': 'Test User',
            'email': 'test@example.com',
            'phone': '+55 11 99999-9999',
            'linkedin': 'https://linkedin.com/in/testuser'
        }
    else:
        with open(config_path, 'r', encoding='utf-8') as f:
            user_data = json.load(f)
    
    try:
        engine = JobAutomationEngine(resume_path="curriculo.pdf", user_data=user_data)
        
        # Run with limited applications for testing
        results = engine.run_full_pipeline(
            location="Brazil",
            max_applications=2,  # Limit for testing
            min_match_score=0.2  # Lower threshold for testing
        )
        
        if 'error' in results:
            print(f"✗ Pipeline failed: {results['error']}")
            return False
        
        print(f"\n✓ Pipeline completed")
        print(f"  Jobs found: {results['jobs_found']}")
        print(f"  Applications sent: {len(results['applications'])}")
        print(f"  Successful: {results['successful_applications']}")
        
        return True
        
    except Exception as e:
        print(f"✗ Pipeline failed: {e}")
        traceback.print_exc()
        return False


def analyze_errors():
    """Analyze errors and suggest fixes"""
    print("\n" + "="*60)
    print("ERROR ANALYSIS")
    print("="*60)
    
    # Check for common issues
    issues = []
    
    # Check if resume exists
    if not Path("curriculo.pdf").exists():
        issues.append({
            'type': 'missing_file',
            'file': 'curriculo.pdf',
            'fix': 'Place your resume PDF in the project root as curriculo.pdf'
        })
    
    # Check if user config exists
    if not Path("user_config.json").exists():
        issues.append({
            'type': 'missing_config',
            'file': 'user_config.json',
            'fix': 'Create user_config.json with your name, email, phone, and LinkedIn URL'
        })
    
    # Check dependencies
    try:
        import playwright
        import pdfplumber
        import pydantic
    except ImportError as e:
        issues.append({
            'type': 'missing_dependency',
            'package': str(e),
            'fix': 'Run: pip install -r requirements.txt && playwright install chromium'
        })
    
    if issues:
        print("\nFound issues:")
        for i, issue in enumerate(issues, 1):
            print(f"\n{i}. {issue['type'].upper()}")
            if 'file' in issue:
                print(f"   Missing: {issue['file']}")
            if 'package' in issue:
                print(f"   Package: {issue['package']}")
            print(f"   Fix: {issue['fix']}")
    else:
        print("✓ No obvious issues found")
    
    return issues


def main():
    """Run AI-powered stress tests"""
    print("\n" + "="*60)
    print("JOB AUTOMATION ENGINE - AI-POWERED STRESS TEST")
    print("="*60)
    print("\nThis test will:")
    print("1. Parse your resume using Gemini AI")
    print("2. Search for real jobs")
    print("3. Apply to a real LinkedIn job with AI-powered self-healing")
    print("4. Retry with AI adjustments if it fails")
    
    # Check for API key
    if not os.getenv('GEMINI_API_KEY'):
        print("\n✗ ERROR: GEMINI_API_KEY not found in environment")
        print("Please ensure .env file exists with GEMINI_API_KEY")
        return
    
    # Analyze for common issues first
    issues = analyze_errors()
    
    if issues:
        print("\n⚠ Please fix the issues above before running tests.")
        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            return
    
    # Test 1: Resume parsing with AI
    print("\n" + "="*60)
    print("STEP 1: AI-Powered Resume Parsing")
    print("="*60)
    resume_data = test_parser()
    
    if not resume_data:
        print("\n✗ Cannot continue without resume data")
        return
    
    # Test 2: Job search with AI matching
    print("\n" + "="*60)
    print("STEP 2: AI-Powered Job Search & Matching")
    print("="*60)
    jobs = test_searcher(resume_data)
    
    if not jobs:
        print("\n⚠ No jobs found. You can still test with a manual URL.")
        manual_url = input("\nEnter a LinkedIn job URL to test (or press Enter to skip): ").strip()
        if manual_url:
            test_applier_stress(manual_url)
        return
    
    # Test 3: Stress test with real application
    print("\n" + "="*60)
    print("STEP 3: Real Job Application Stress Test")
    print("="*60)
    print(f"\nFound {len(jobs)} jobs. Top match:")
    top_job = jobs[0]
    print(f"  Title: {top_job.title}")
    print(f"  Company: {top_job.company}")
    print(f"  Match Score: {top_job.match_score:.2f}")
    print(f"  URL: {top_job.url}")
    
    print("\n⚠ WARNING: This will attempt a REAL application to this job!")
    response = input("\nContinue with stress test? (y/n): ")
    
    if response.lower() == 'y':
        result = test_applier_stress(top_job.url, max_retries=3)
        
        if result and result.get('success'):
            print("\n" + "="*60)
            print("✓ STRESS TEST PASSED")
            print("="*60)
        else:
            print("\n" + "="*60)
            print("✗ STRESS TEST FAILED")
            print("="*60)
            print("\nThe AI-powered self-healing attempted to recover but")
            print("the application could not be completed. Review the errors above.")
    else:
        print("\nStress test skipped.")
    
    print("\n" + "="*60)
    print("TESTS COMPLETE")
    print("="*60)


if __name__ == "__main__":
    main()

