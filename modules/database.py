"""
Database Manager Module
Manages SQLite database for tracking job applications and preventing duplicates
"""
import os
import sqlite3
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
import json


class DatabaseManager:
    """Manages SQLite database for application tracking"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database manager.

        Relative paths are stored below DATA_DIR when it is configured so the
        SQLite state survives container replacements and scheduled executions.
        """
        configured_path = db_path or os.getenv("DATABASE_PATH", "applications.db")
        path = Path(configured_path).expanduser()
        data_dir = os.getenv("DATA_DIR")
        if data_dir and not path.is_absolute():
            path = Path(data_dir).expanduser() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = path
        self.conn = None
        self._init_database()
    
    def _init_database(self):
        """Initialize database and create tables if they don't exist"""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row  # Enable column access by name
            
            cursor = self.conn.cursor()
            
            # Create jobs_processed table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs_processed (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT,
                    company TEXT,
                    status TEXT NOT NULL,
                    match_score REAL,
                    processed_at TEXT NOT NULL,
                    error_details TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create index on url for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_url ON jobs_processed(url)
            """)
            
            # Create index on processed_at for querying recent applications
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_at ON jobs_processed(processed_at)
            """)
            
            # Add source column for analytics (optional; backward compatible)
            try:
                cursor.execute("ALTER TABLE jobs_processed ADD COLUMN source TEXT")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists
            # Add email column for recovery (PENDING jobs can have email filled later)
            try:
                cursor.execute("ALTER TABLE jobs_processed ADD COLUMN email TEXT")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists
            # Add apply_link for deep_recovery (link de formulário quando não há e-mail)
            try:
                cursor.execute("ALTER TABLE jobs_processed ADD COLUMN apply_link TEXT")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists
            # SMTP Message-ID para rastreio de envio (batch_sender / relatórios)
            try:
                cursor.execute("ALTER TABLE jobs_processed ADD COLUMN smtp_message_id TEXT")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists
            # job_id: unique per (email, job) so we can send to same email for different jobs
            try:
                cursor.execute("ALTER TABLE jobs_processed ADD COLUMN job_id TEXT")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_email_job_id ON jobs_processed(email, job_id) WHERE email IS NOT NULL AND job_id IS NOT NULL")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass
            # description: first 1000 chars of post text (lets us recover post content if URL dies)
            try:
                cursor.execute("ALTER TABLE jobs_processed ADD COLUMN description TEXT")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass
            # job_code: recruiter identification code extracted from post (e.g. "ENGFULLJAVA - 01")
            try:
                cursor.execute("ALTER TABLE jobs_processed ADD COLUMN job_code TEXT")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass
            # followup_sent_at: timestamp of the follow-up email (NULL = not yet sent)
            try:
                cursor.execute("ALTER TABLE jobs_processed ADD COLUMN followup_sent_at TEXT")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass
            # email_subject: assunto exato enviado (dedup + auditoria)
            try:
                cursor.execute("ALTER TABLE jobs_processed ADD COLUMN email_subject TEXT")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass

            self.conn.commit()
            print(f"  ✓ Database initialized: {self.db_path}")
            
        except Exception as e:
            print(f"  ✗ Error initializing database: {e}")
            raise
    
    def is_job_processed(self, job_url: str) -> bool:
        """
        Check if a job URL has already been processed
        
        Args:
            job_url: Job URL to check
            
        Returns:
            bool: True if job has been processed before, False otherwise
        """
        if not self.conn:
            return False
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM jobs_processed WHERE url = ?",
                (job_url,)
            )
            count = cursor.fetchone()[0]
            return count > 0
        except Exception as e:
            print(f"  ⚠ Error checking if job processed: {e}")
            return False
    
    def is_already_seen(self, job_url: str) -> bool:
        """Alias for is_job_processed for backward compatibility"""
        return self.is_job_processed(job_url)
    
    def is_sent_to_email_for_job(self, email: str, job_id: str) -> bool:
        """
        Check if we already sent to this (email, job_id) pair with status SUCCESS.
        Used to allow sending to the same email for different jobs (e.g. same recruiter, two posts).
        """
        if not self.conn or not email or not job_id:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT 1 FROM jobs_processed WHERE email = ? AND job_id = ? AND status = 'SUCCESS' LIMIT 1",
                (email.strip(), job_id.strip()),
            )
            return cursor.fetchone() is not None
        except Exception as e:
            return False

    def is_sent_to_email_with_subject(self, email: str, subject: str) -> bool:
        """Retorna True se já enviamos com sucesso um email com esse assunto para esse endereço."""
        if not self.conn or not email or not subject:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT 1 FROM jobs_processed WHERE email = ? AND email_subject = ? AND status = 'SUCCESS' LIMIT 1",
                (email.strip(), subject.strip()),
            )
            return cursor.fetchone() is not None
        except Exception:
            return False
    
    def get_followup_info(self, job_url: str) -> Optional[Dict]:
        """Return the DB record for job_url if it was processed successfully and follow-up not yet sent.
        Returns None if the job hasn't been sent, was sent too recently (<7 days), or follow-up already sent.
        """
        if not self.conn:
            return None
        try:
            cursor = self.conn.cursor()
            row = cursor.execute(
                "SELECT url, email, processed_at, followup_sent_at, title, description, job_code "
                "FROM jobs_processed WHERE url = ? AND status = 'SUCCESS'",
                (job_url,)
            ).fetchone()
            if not row:
                return None
            if row['followup_sent_at']:
                return None  # already followed up
            from datetime import datetime, timedelta
            sent_at = datetime.fromisoformat(row['processed_at'])
            if datetime.now() - sent_at < timedelta(days=7):
                return None  # too soon (< 7 days)
            return dict(row)
        except Exception:
            return None

    def mark_followup_sent(self, job_url: str) -> bool:
        """Record that a follow-up was sent for job_url."""
        if not self.conn:
            return False
        try:
            self.conn.execute(
                "UPDATE jobs_processed SET followup_sent_at = ? WHERE url = ?",
                (datetime.now().isoformat(), job_url)
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def get_pending_jobs(self, status: str = "EASY_APPLY_PENDING", limit: int = None) -> List[Dict]:
        """
        Get jobs with specific status from database
        
        Args:
            status: Status to filter by (e.g., "EASY_APPLY_PENDING")
            limit: Maximum number of jobs to return (None for all)
            
        Returns:
            List[Dict]: List of job records with url, title, company, etc.
        """
        if not self.conn:
            return []
        
        try:
            cursor = self.conn.cursor()
            # For PENDING: exclude jobs where (email, job_id) already has SUCCESS; include job_id in SELECT
            base_cols = "url, title, company, match_score, status, email"
            has_job_id_col = False
            try:
                cursor.execute("SELECT job_id FROM jobs_processed LIMIT 1")
                base_cols += ", job_id"
                has_job_id_col = True
            except sqlite3.OperationalError:
                pass
            if status == "PENDING":
                if has_job_id_col:
                    j_cols = ", ".join("j." + c.strip() for c in base_cols.split(","))
                    query = f"""SELECT {j_cols}
                        FROM jobs_processed j
                        WHERE j.status = ?
                        AND NOT EXISTS (
                            SELECT 1 FROM jobs_processed s
                            WHERE s.status = 'SUCCESS' AND s.email = j.email AND COALESCE(s.job_id, '') = COALESCE(j.job_id, '')
                        )
                        ORDER BY j.match_score DESC, j.processed_at DESC"""
                else:
                    query = """SELECT url, title, company, match_score, status, email FROM jobs_processed
                        WHERE status = ?
                        AND (email IS NULL OR email = '' OR email NOT IN (
                            SELECT email FROM jobs_processed WHERE status = 'SUCCESS' AND email IS NOT NULL AND email != ''
                        ))
                        ORDER BY match_score DESC, processed_at DESC"""
            else:
                query = f"SELECT {base_cols} FROM jobs_processed WHERE status = ? ORDER BY processed_at DESC"
            if limit:
                query += f" LIMIT {limit}"
            try:
                cursor.execute(query, (status,))
            except sqlite3.OperationalError:
                query = "SELECT url, title, company, match_score, status FROM jobs_processed WHERE status = ? ORDER BY processed_at DESC"
                if limit:
                    query += f" LIMIT {limit}"
                cursor.execute(query, (status,))
            rows = cursor.fetchall()
            col_count = len(rows[0]) if rows else 0
            jobs = []
            for row in rows:
                r = {
                    'url': row[0],
                    'title': row[1] or 'Unknown',
                    'company': row[2] or 'Unknown',
                    'match_score': row[3] or 0.0,
                    'status': row[4]
                }
                if col_count >= 6:
                    r['email'] = row[5]
                else:
                    r['email'] = None
                if col_count >= 7:
                    r['job_id'] = row[6]
                else:
                    r['job_id'] = None
                jobs.append(r)
            
            return jobs
        except Exception as e:
            print(f"  ⚠ Error getting pending jobs: {e}")
            return []
    
    def save_job(self, job_data: Dict, status: str = "UNKNOWN") -> bool:
        """
        Save a job record to the database
        
        Args:
            job_data: Dictionary with job information (url, title, company, match_score, etc.)
            status: Application status (SUCCESS, FAILED, SKIPPED)
            
        Returns:
            bool: True if successfully saved, False otherwise
        """
        if not self.conn:
            return False
        
        try:
            job_url = job_data.get('url') or job_data.get('job_url', '')
            if not job_url:
                print("  ⚠ Cannot save job: no URL provided")
                return False
            
            source = job_data.get('source')
            email = job_data.get('email') or None
            job_id = job_data.get('job_id') or None
            description = (job_data.get('description') or '')[:1000] or None
            job_code = job_data.get('job_code') or None
            email_subject = job_data.get('email_subject') or None
            if email and isinstance(email, str):
                email = email.strip() or None
            if job_id and isinstance(job_id, str):
                job_id = job_id.strip() or None
            if email_subject and isinstance(email_subject, str):
                email_subject = email_subject.strip() or None

            # Check if already exists (by url)
            if self.is_job_processed(job_url):
                cursor = self.conn.cursor()
                try:
                    cursor.execute("""
                        UPDATE jobs_processed
                        SET status = ?, processed_at = ?, error_details = ?, source = COALESCE(?, source),
                            email = COALESCE(?, email), job_id = COALESCE(?, job_id),
                            description = COALESCE(?, description), job_code = COALESCE(?, job_code),
                            email_subject = COALESCE(?, email_subject)
                        WHERE url = ?
                    """, (
                        status, datetime.now().isoformat(),
                        json.dumps(job_data.get('error_details', {})),
                        source, email, job_id, description, job_code, email_subject, job_url
                    ))
                except sqlite3.OperationalError:
                    cursor.execute("""
                        UPDATE jobs_processed
                        SET status = ?, processed_at = ?, error_details = ?, source = COALESCE(?, source)
                        WHERE url = ?
                    """, (
                        status, datetime.now().isoformat(),
                        json.dumps(job_data.get('error_details', {})),
                        source, job_url
                    ))
            else:
                cursor = self.conn.cursor()
                try:
                    cursor.execute("""
                        INSERT INTO jobs_processed
                        (url, title, company, status, match_score, processed_at, error_details,
                         source, email, job_id, description, job_code, email_subject)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        job_url,
                        job_data.get('title') or job_data.get('job_title', 'Unknown'),
                        job_data.get('company', 'Unknown'),
                        status,
                        job_data.get('match_score', 0.0),
                        datetime.now().isoformat(),
                        json.dumps(job_data.get('error_details', {})),
                        source, email, job_id, description, job_code, email_subject
                    ))
                except sqlite3.OperationalError:
                    # Older schema without newer columns — insert base fields only
                    cursor.execute("""
                        INSERT INTO jobs_processed
                        (url, title, company, status, match_score, processed_at, error_details, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        job_url,
                        job_data.get('title') or job_data.get('job_title', 'Unknown'),
                        job_data.get('company', 'Unknown'),
                        status,
                        job_data.get('match_score', 0.0),
                        datetime.now().isoformat(),
                        json.dumps(job_data.get('error_details', {})),
                        source
                    ))
            
            self.conn.commit()
            return True
            
        except sqlite3.IntegrityError:
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    UPDATE jobs_processed
                    SET status = ?, processed_at = ?, error_details = ?, source = COALESCE(?, source),
                        email = COALESCE(?, email), job_id = COALESCE(?, job_id),
                        email_subject = COALESCE(?, email_subject)
                    WHERE url = ?
                """, (
                    status,
                    datetime.now().isoformat(),
                    json.dumps(job_data.get('error_details', {})),
                    source,
                    email,
                    job_id,
                    email_subject,
                    job_url
                ))
                self.conn.commit()
                return True
            except Exception as e:
                print(f"  ⚠ Error updating job: {e}")
                return False
        except Exception as e:
            print(f"  ⚠ Error saving job: {e}")
            return False
    
    def add_application(self, job_data: Dict, status: str = "UNKNOWN") -> bool:
        """Alias for save_job for backward compatibility"""
        return self.save_job(job_data, status)

    def update_job_email(self, url: str, email: str) -> bool:
        """Update the email field for a job by url (e.g. after recovery extraction)."""
        if not self.conn or not url or not email:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE jobs_processed SET email = ? WHERE url = ?", (email.strip(), url))
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.OperationalError:
            return False  # email column may not exist
        except Exception as e:
            print(f"  ⚠ Error updating job email: {e}")
            return False

    def update_job_status(self, url: str, status: str) -> bool:
        """Update the status of a job by url."""
        if not self.conn or not url:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE jobs_processed SET status = ? WHERE url = ?", (status, url))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"  ⚠ Error updating job status: {e}")
            return False

    def update_job_apply_link(self, url: str, apply_link: str) -> bool:
        """Update the apply_link field (form URL) for a job by url."""
        if not self.conn or not url or not apply_link:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE jobs_processed SET apply_link = ? WHERE url = ?", (apply_link.strip(), url))
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.OperationalError:
            return False
        except Exception as e:
            print(f"  ⚠ Error updating job apply_link: {e}")
            return False

    def update_smtp_message_id(self, url: str, message_id: str) -> bool:
        """Registra o message_id do SMTP para rastreio futuro (batch_sender / report)."""
        if not self.conn or not url or not message_id:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE jobs_processed SET smtp_message_id = ? WHERE url = ?", (message_id.strip(), url))
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.OperationalError:
            return False
        except Exception as e:
            print(f"  ⚠ Error updating smtp_message_id: {e}")
            return False

    def get_recovery_targets(self, limit: int = None) -> List[Dict]:
        """Vagas MANUAL_REVIEW ou PENDING com email NULL, ordenadas por match_score DESC (maior primeiro)."""
        if not self.conn:
            return []
        try:
            cursor = self.conn.cursor()
            query = """
                SELECT url, title, company, match_score, status
                FROM jobs_processed
                WHERE status IN ('MANUAL_REVIEW', 'PENDING')
                AND (email IS NULL OR email = '')
                AND url NOT LIKE 'email:%'
                ORDER BY match_score DESC
            """
            if limit:
                query += f" LIMIT {limit}"
            cursor.execute(query)
            return [
                {"url": row[0], "title": row[1] or "Unknown", "company": row[2] or "Unknown", "match_score": row[3] or 0.0, "status": row[4]}
                for row in cursor.fetchall()
            ]
        except sqlite3.OperationalError:
            try:
                cursor = self.conn.cursor()
                q = """
                    SELECT url, title, company, match_score, status
                    FROM jobs_processed
                    WHERE status IN ('MANUAL_REVIEW', 'PENDING')
                    AND url NOT LIKE 'email:%'
                    ORDER BY match_score DESC
                """
                if limit:
                    q += f" LIMIT {limit}"
                cursor.execute(q)
                return [
                    {"url": row[0], "title": row[1] or "Unknown", "company": row[2] or "Unknown", "match_score": row[3] or 0.0, "status": row[4]}
                    for row in cursor.fetchall()
                ]
            except Exception as e:
                print(f"  ⚠ Error get_recovery_targets: {e}")
                return []
        except Exception as e:
            print(f"  ⚠ Error get_recovery_targets: {e}")
            return []

    def get_pending_without_email(self, limit: int = None) -> List[Dict]:
        """Return PENDING jobs that have no email (for recovery script)."""
        if not self.conn:
            return []
        try:
            cursor = self.conn.cursor()
            query = """
                SELECT url, title, company FROM jobs_processed
                WHERE status = 'PENDING' AND url NOT LIKE 'email:%'
                AND (email IS NULL OR email = '')
                ORDER BY processed_at DESC
            """
            if limit:
                query += f" LIMIT {limit}"
            cursor.execute(query)
            return [{"url": row[0], "title": row[1] or "Unknown", "company": row[2] or "Unknown"} for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            # email column may not exist yet
            try:
                cursor = self.conn.cursor()
                q = "SELECT url, title, company FROM jobs_processed WHERE status = 'PENDING' AND url NOT LIKE 'email:%' ORDER BY processed_at DESC"
                if limit:
                    q += f" LIMIT {limit}"
                cursor.execute(q)
                return [{"url": row[0], "title": row[1] or "Unknown", "company": row[2] or "Unknown"} for row in cursor.fetchall()]
            except Exception as e:
                print(f"  ⚠ Error get_pending_without_email: {e}")
                return []
        except Exception as e:
            print(f"  ⚠ Error get_pending_without_email: {e}")
            return []

    def get_recent_applications(self, limit: int = 10) -> List[Dict]:
        """
        Get recent applications from database
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List[Dict]: List of recent application records
        """
        if not self.conn:
            return []
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM jobs_processed 
                ORDER BY processed_at DESC 
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"  ⚠ Error getting recent applications: {e}")
            return []
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about applications
        
        Returns:
            Dict: Statistics including total, by status, etc.
        """
        if not self.conn:
            return {}
        
        try:
            cursor = self.conn.cursor()
            
            # Total count
            cursor.execute("SELECT COUNT(*) FROM jobs_processed")
            total = cursor.fetchone()[0]
            
            # Count by status
            cursor.execute("""
                SELECT status, COUNT(*) as count 
                FROM jobs_processed 
                GROUP BY status
            """)
            status_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Recent applications (last 24 hours)
            cursor.execute("""
                SELECT COUNT(*) FROM jobs_processed 
                WHERE processed_at > datetime('now', '-1 day')
            """)
            recent_24h = cursor.fetchone()[0]
            
            return {
                'total': total,
                'by_status': status_counts,
                'recent_24h': recent_24h
            }
        except Exception as e:
            print(f"  ⚠ Error getting statistics: {e}")
            return {}
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


if __name__ == "__main__":
    # Test the database
    db = DatabaseManager("test_applications.db")
    
    # Test adding an application
    test_job = {
        'url': 'https://example.com/job1',
        'title': 'Test Job',
        'company': 'Test Company',
        'match_score': 0.8
    }
    
    db.add_application(test_job, status="SUCCESS")
    print(f"Is seen: {db.is_already_seen('https://example.com/job1')}")
    
    # Get statistics
    stats = db.get_statistics()
    print(f"Statistics: {stats}")
    
    db.close()
    
    # Clean up test database
    Path("test_applications.db").unlink(missing_ok=True)
    print("Test completed successfully!")

