#!/usr/bin/env python3
"""
Validate Logs Script
Checks that all URLs in logs are real and accessible
Removes any entries with invalid URLs or mock data
"""
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.scanner import LinkScanner

def validate_logs():
    """Validate all URLs in applications_history.json"""
    log_file = Path("logs/applications_history.json")
    
    if not log_file.exists():
        print("No log file found. Nothing to validate.")
        return
    
    scanner = LinkScanner()
    logs = json.loads(log_file.read_text())
    
    print(f"Validating {len(logs)} log entries...")
    
    valid_logs = []
    invalid_count = 0
    
    for log in logs:
        url = log.get('url', '')
        
        # Check if URL is real (not mock/test)
        if not scanner.is_real_data(url, log.get('job_title', '')):
            print(f"  ✗ Removing mock data: {log.get('job_title', 'Unknown')} - {url}")
            invalid_count += 1
            continue
        
        # Check if URL is valid
        if url and url.startswith('http'):
            is_valid, error = scanner.validate_url(url)
            if not is_valid:
                print(f"  ✗ Invalid URL: {log.get('job_title', 'Unknown')} - {url} ({error})")
                invalid_count += 1
                continue
        
        # Check is_real_data flag
        if not log.get('is_real_data', True):
            print(f"  ✗ Removing entry with is_real_data=False: {log.get('job_title', 'Unknown')}")
            invalid_count += 1
            continue
        
        # Check if source required API key (should not be in logs)
        url_lower = url.lower()
        key_required_sources = ['jooble', 'serpapi']
        if any(source in url_lower for source in key_required_sources):
            print(f"  ⚠ Warning: Job from key-required source: {log.get('job_title', 'Unknown')}")
            # Don't remove, but warn
        
        valid_logs.append(log)
    
    # Save validated logs
    if invalid_count > 0:
        log_file.write_text(json.dumps(valid_logs, indent=2))
        print(f"\n✓ Removed {invalid_count} invalid entries")
        print(f"✓ Kept {len(valid_logs)} valid entries")
    else:
        print(f"\n✓ All {len(valid_logs)} entries are valid")
    
    return len(valid_logs), invalid_count

if __name__ == "__main__":
    valid, invalid = validate_logs()
    sys.exit(0 if invalid == 0 else 1)

