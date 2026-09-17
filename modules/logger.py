"""
Application Logger Module
Structured logging system for learning from past attempts
Logs are readable by both humans and AI for continuous improvement
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum


class ApplicationStatus(Enum):
    """Application status enumeration"""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    RETRY = "retry"


@dataclass
class ApplicationLog:
    """Structured log entry for an application attempt"""
    timestamp: str
    job_title: str
    company: str
    url: str
    match_score: float
    status: str
    is_real_data: bool = True  # CRITICAL: Must be True - no mock data allowed
    url_validated: bool = False  # Whether URL was validated as accessible
    error_details: Optional[Dict[str, Any]] = None
    gemini_suggestion: Optional[str] = None
    steps_completed: List[str] = None
    selectors_used: Dict[str, str] = None
    screenshot_path: Optional[str] = None
    retry_count: int = 0
    previous_attempts: List[str] = None  # URLs of previous attempts for same job
    
    def __post_init__(self):
        if self.steps_completed is None:
            self.steps_completed = []
        if self.selectors_used is None:
            self.selectors_used = {}
        if self.previous_attempts is None:
            self.previous_attempts = []


class ApplicationLogger:
    """Logger for application attempts with learning capabilities"""
    
    def __init__(self, log_dir: Optional[str] = None):
        configured_dir = log_dir or os.getenv("LOG_DIR", "logs")
        path = Path(configured_dir).expanduser()
        data_dir = os.getenv("DATA_DIR")
        if data_dir and not path.is_absolute():
            path = Path(data_dir).expanduser() / path
        self.log_dir = path
        self.log_file = self.log_dir / "applications_history.json"
        self.logs: List[Dict] = []
        
        # Create logs directory if it doesn't exist
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing logs
        self._load_logs()
    
    def _load_logs(self):
        """Load existing logs from file"""
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    self.logs = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load existing logs: {e}")
                self.logs = []
        else:
            self.logs = []
    
    def _save_logs(self):
        """Save logs to file"""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(self.logs, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving logs: {e}")
    
    def log_application(
        self,
        job_title: str,
        company: str,
        url: str,
        match_score: float,
        status: ApplicationStatus,
        error_details: Optional[Dict[str, Any]] = None,
        gemini_suggestion: Optional[str] = None,
        steps_completed: Optional[List[str]] = None,
        selectors_used: Optional[Dict[str, str]] = None,
        screenshot_path: Optional[str] = None,
        retry_count: int = 0,
        is_real_data: bool = True,
        url_validated: bool = False
    ) -> str:
        """
        Log an application attempt
        
        Returns:
            log_id: Unique identifier for this log entry
        """
        log_entry = ApplicationLog(
            timestamp=datetime.now().isoformat(),
            job_title=job_title,
            company=company,
            url=url,
            match_score=match_score,
            status=status.value,
            error_details=error_details,
            gemini_suggestion=gemini_suggestion,
            steps_completed=steps_completed or [],
            selectors_used=selectors_used or {},
            screenshot_path=screenshot_path,
            retry_count=retry_count
        )
        
        # Check for previous attempts at same URL
        previous_logs = self.get_logs_by_url(url)
        if previous_logs:
            log_entry.previous_attempts = [log['timestamp'] for log in previous_logs]
            log_entry.retry_count = len(previous_logs)
        
        log_dict = asdict(log_entry)
        self.logs.append(log_dict)
        self._save_logs()
        
        return log_dict['timestamp']
    
    def log_action(
        self,
        action_type: str,
        description: str,
        selector: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
        html_snippet: Optional[str] = None
    ):
        """Log a specific action (click, fill, etc.) for debugging"""
        action_log = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type,
            "description": description,
            "selector": selector,
            "success": success,
            "error": error,
            "html_snippet": html_snippet[:500] if html_snippet else None  # Limit HTML size
        }
        
        action_file = self.log_dir / f"actions_{datetime.now().strftime('%Y%m%d')}.json"
        
        # Load existing actions for today
        actions = []
        if action_file.exists():
            try:
                with open(action_file, 'r', encoding='utf-8') as f:
                    actions = json.load(f)
            except (json.JSONDecodeError, IOError):
                actions = []
        
        actions.append(action_log)
        
        # Save actions log
        try:
            with open(action_file, 'w', encoding='utf-8') as f:
                json.dump(actions, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving action log: {e}")
    
    def get_logs_by_company(self, company: str) -> List[Dict]:
        """Get all logs for a specific company"""
        return [log for log in self.logs if log.get('company', '').lower() == company.lower()]
    
    def get_logs_by_url(self, url: str) -> List[Dict]:
        """Get all logs for a specific URL"""
        return [log for log in self.logs if log.get('url') == url]
    
    def get_failed_logs(self, limit: int = 10) -> List[Dict]:
        """Get recent failed applications"""
        failed = [log for log in self.logs if log.get('status') == ApplicationStatus.FAILED.value]
        return sorted(failed, key=lambda x: x.get('timestamp', ''), reverse=True)[:limit]
    
    def get_successful_logs(self, limit: int = 10) -> List[Dict]:
        """Get recent successful applications"""
        successful = [log for log in self.logs if log.get('status') == ApplicationStatus.SUCCESS.value]
        return sorted(successful, key=lambda x: x.get('timestamp', ''), reverse=True)[:limit]
    
    def get_company_error_patterns(self, company: str) -> Dict[str, Any]:
        """Analyze error patterns for a specific company"""
        company_logs = self.get_logs_by_company(company)
        failed_logs = [log for log in company_logs if log.get('status') == ApplicationStatus.FAILED.value]
        
        if not failed_logs:
            return {}
        
        # Collect common errors
        error_types = {}
        common_selectors = {}
        
        for log in failed_logs:
            error_details = log.get('error_details', {})
            error_type = error_details.get('type', 'unknown')
            error_types[error_type] = error_types.get(error_type, 0) + 1
            
            selectors = log.get('selectors_used', {})
            for field, selector in selectors.items():
                if selector not in common_selectors:
                    common_selectors[selector] = {'field': field, 'count': 0, 'success': 0}
                common_selectors[selector]['count'] += 1
                if log.get('status') == ApplicationStatus.SUCCESS.value:
                    common_selectors[selector]['success'] += 1
        
        return {
            'company': company,
            'total_attempts': len(company_logs),
            'failed_attempts': len(failed_logs),
            'success_rate': (len(company_logs) - len(failed_logs)) / len(company_logs) if company_logs else 0,
            'error_types': error_types,
            'common_selectors': common_selectors
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get overall statistics from logs"""
        if not self.logs:
            return {
                'total_applications': 0,
                'success_rate': 0,
                'average_match_score': 0
            }
        
        total = len(self.logs)
        successful = len([log for log in self.logs if log.get('status') == ApplicationStatus.SUCCESS.value])
        failed = len([log for log in self.logs if log.get('status') == ApplicationStatus.FAILED.value])
        
        match_scores = [log.get('match_score', 0) for log in self.logs if log.get('match_score')]
        avg_score = sum(match_scores) / len(match_scores) if match_scores else 0
        
        return {
            'total_applications': total,
            'successful': successful,
            'failed': failed,
            'pending': len([log for log in self.logs if log.get('status') == ApplicationStatus.PENDING.value]),
            'success_rate': successful / total if total > 0 else 0,
            'average_match_score': avg_score,
            'companies_attempted': len(set(log.get('company', '') for log in self.logs))
        }
    
    def save_screenshot(self, screenshot_data: bytes, log_id: str) -> str:
        """Save a screenshot and return the path"""
        screenshot_dir = self.log_dir / "screenshots"
        screenshot_dir.mkdir(exist_ok=True)
        
        screenshot_path = screenshot_dir / f"error_{log_id.replace(':', '-')}.png"
        
        try:
            with open(screenshot_path, 'wb') as f:
                f.write(screenshot_data)
            return str(screenshot_path)
        except IOError as e:
            print(f"Error saving screenshot: {e}")
            return ""


if __name__ == "__main__":
    # Test the logger
    logger = ApplicationLogger()
    
    # Test log entry
    logger.log_application(
        job_title="Full Stack Developer",
        company="Test Company",
        url="https://example.com/job/123",
        match_score=0.85,
        status=ApplicationStatus.SUCCESS,
        steps_completed=["navigation", "form_filled", "resume_uploaded", "submitted"],
        selectors_used={
            "email": "input[name='email']",
            "name": "#full-name",
            "submit": "button[type='submit']"
        }
    )
    
    print("Logger test completed")
    print(f"Statistics: {logger.get_statistics()}")


