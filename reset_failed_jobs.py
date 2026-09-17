#!/usr/bin/env python3
"""
Script para resetar vagas com status FAILED para EASY_APPLY_PENDING
Permite que o robô tente novamente aplicar nas vagas que falharam
"""

import sqlite3
import sys
from pathlib import Path

def reset_failed_jobs():
    """Reset jobs with FAILED status to EASY_APPLY_PENDING"""
    db_path = Path("jobs.db")
    
    if not db_path.exists():
        print("  ✗ Database not found: jobs.db")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Contar vagas com status FAILED
        cursor.execute("SELECT COUNT(*) FROM jobs_processed WHERE status = 'FAILED'")
        failed_count = cursor.fetchone()[0]
        
        if failed_count == 0:
            print("  ℹ No jobs with FAILED status found.")
            return True
        
        print(f"  📊 Found {failed_count} jobs with FAILED status")
        
        # Mostrar algumas vagas que serão resetadas
        cursor.execute("""
            SELECT url, title, company 
            FROM jobs_processed 
            WHERE status = 'FAILED' 
            LIMIT 5
        """)
        sample_jobs = cursor.fetchall()
        
        print(f"\n  📋 Sample jobs to reset:")
        for url, title, company in sample_jobs:
            print(f"    - {title} at {company}")
        
        # Confirmar reset
        print(f"\n  ⚠ About to reset {failed_count} jobs from FAILED to EASY_APPLY_PENDING")
        response = input("  Continue? (y/n): ").strip().lower()
        
        if response != 'y':
            print("  ✗ Reset cancelled.")
            return False
        
        # Reset status
        cursor.execute("""
            UPDATE jobs_processed 
            SET status = 'EASY_APPLY_PENDING',
                processed_at = datetime('now')
            WHERE status = 'FAILED'
        """)
        
        conn.commit()
        
        # Verificar resultado
        cursor.execute("SELECT COUNT(*) FROM jobs_processed WHERE status = 'FAILED'")
        remaining_failed = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM jobs_processed WHERE status = 'EASY_APPLY_PENDING'")
        pending_count = cursor.fetchone()[0]
        
        print(f"\n  ✓ Reset completed!")
        print(f"  → {failed_count} jobs reset to EASY_APPLY_PENDING")
        print(f"  → Remaining FAILED: {remaining_failed}")
        print(f"  → Total EASY_APPLY_PENDING: {pending_count}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"  ✗ Error resetting jobs: {e}")
        return False

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  RESET FAILED JOBS TO EASY_APPLY_PENDING")
    print("="*60 + "\n")
    
    success = reset_failed_jobs()
    
    if success:
        print("\n  ✅ Script completed successfully!")
        print("  → Run: ./run.sh --mode 'easy-apply' --max-applications 10")
    else:
        print("\n  ✗ Script failed.")
        sys.exit(1)



