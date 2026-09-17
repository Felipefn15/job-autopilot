#!/usr/bin/env python3
"""
Log Analysis Script
Provides performance summary and insights from application logs
"""
import sys
from pathlib import Path
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.logger import ApplicationLogger, ApplicationStatus


def format_percentage(value: float) -> str:
    """Format percentage with 2 decimal places"""
    return f"{value * 100:.2f}%"


def analyze_logs():
    """Analyze application logs and provide performance summary"""
    logger = ApplicationLogger()
    
    print("="*60)
    print("APPLICATION LOGS ANALYSIS")
    print("="*60)
    print()
    
    # Overall statistics
    stats = logger.get_statistics()
    
    print("OVERALL STATISTICS")
    print("-" * 60)
    print(f"Total Applications: {stats['total_applications']}")
    print(f"Successful: {stats['successful']}")
    print(f"Failed: {stats['failed']}")
    print(f"Pending: {stats['pending']}")
    print(f"Success Rate: {format_percentage(stats['success_rate'])}")
    print(f"Average Match Score: {stats['average_match_score']:.2f}")
    print(f"Companies Attempted: {stats['companies_attempted']}")
    print()
    
    if stats['total_applications'] == 0:
        print("No applications logged yet.")
        return
    
    # Recent failures
    failed_logs = logger.get_failed_logs(limit=10)
    if failed_logs:
        print("RECENT FAILURES (Last 10)")
        print("-" * 60)
        for i, log in enumerate(failed_logs, 1):
            timestamp = log.get('timestamp', 'Unknown')
            job_title = log.get('job_title', 'Unknown')
            company = log.get('company', 'Unknown')
            error = log.get('error_details', {}).get('message', 'Unknown error')
            
            print(f"{i}. {job_title} at {company}")
            print(f"   Time: {timestamp}")
            print(f"   Error: {error[:80]}...")
            if log.get('gemini_suggestion'):
                print(f"   AI Suggestion: {log['gemini_suggestion'][:80]}...")
            print()
    
    # Recent successes
    successful_logs = logger.get_successful_logs(limit=10)
    if successful_logs:
        print("RECENT SUCCESSES (Last 10)")
        print("-" * 60)
        for i, log in enumerate(successful_logs, 1):
            timestamp = log.get('timestamp', 'Unknown')
            job_title = log.get('job_title', 'Unknown')
            company = log.get('company', 'Unknown')
            match_score = log.get('match_score', 0)
            
            print(f"{i}. {job_title} at {company}")
            print(f"   Time: {timestamp} | Match Score: {match_score:.2f}")
            print()
    
    # Company analysis
    all_companies = set(log.get('company', '') for log in logger.logs if log.get('company'))
    if all_companies:
        print("COMPANY PERFORMANCE")
        print("-" * 60)
        company_stats = []
        for company in all_companies:
            pattern = logger.get_company_error_patterns(company)
            if pattern:
                company_stats.append(pattern)
        
        # Sort by success rate
        company_stats.sort(key=lambda x: x.get('success_rate', 0), reverse=True)
        
        for stat in company_stats[:10]:  # Top 10 companies
            company = stat['company']
            success_rate = stat['success_rate']
            total = stat['total_attempts']
            failed = stat['failed_attempts']
            
            print(f"{company}:")
            print(f"  Attempts: {total} | Failed: {failed} | Success Rate: {format_percentage(success_rate)}")
            
            if stat.get('error_types'):
                print("  Common Errors:")
                for error_type, count in sorted(stat['error_types'].items(), key=lambda x: x[1], reverse=True)[:3]:
                    print(f"    - {error_type}: {count} times")
            print()
    
    # Error type analysis
    error_types = {}
    for log in logger.logs:
        if log.get('status') == ApplicationStatus.FAILED.value:
            error_details = log.get('error_details', {})
            error_type = error_details.get('type', 'unknown')
            error_types[error_type] = error_types.get(error_type, 0) + 1
    
    if error_types:
        print("ERROR TYPE ANALYSIS")
        print("-" * 60)
        for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / stats['failed']) * 100 if stats['failed'] > 0 else 0
            print(f"{error_type}: {count} ({percentage:.1f}% of failures)")
        print()
    
    # Recommendations
    print("RECOMMENDATIONS")
    print("-" * 60)
    if stats['success_rate'] < 0.5:
        print("⚠ Low success rate detected. Consider:")
        print("  - Reviewing failed applications for common patterns")
        print("  - Adjusting selector strategies")
        print("  - Improving form field detection")
    elif stats['success_rate'] < 0.7:
        print("✓ Moderate success rate. Consider:")
        print("  - Analyzing company-specific patterns")
        print("  - Fine-tuning AI suggestions")
    else:
        print("✓ Good success rate! Continue monitoring for improvements.")
    
    if failed_logs:
        companies_with_failures = set(log.get('company', '') for log in failed_logs)
        if len(companies_with_failures) > 0:
            print(f"\n⚠ {len(companies_with_failures)} companies have recent failures.")
            print("  Review error patterns for these companies.")
    
    print()
    print("="*60)
    print(f"Analysis complete. Log file: {logger.log_file}")
    print("="*60)


if __name__ == "__main__":
    analyze_logs()

