"""
Code Auto-Fixer Module
Automatically applies code fixes based on AI analysis
Validates syntax before applying changes
"""
import re
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class CodeFixer:
    """Automatically applies code fixes with syntax validation"""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.backup_dir = self.project_root / "backups"
        self.backup_dir.mkdir(exist_ok=True)
    
    def create_backup(self, file_path: Path) -> Optional[Path]:
        """Create backup of file before modification"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
            shutil.copy2(file_path, backup_path)
            return backup_path
        except Exception as e:
            print(f"  ⚠ Could not create backup: {e}")
            return None
    
    def validate_syntax(self, file_path: Path) -> bool:
        """Validate Python syntax using py_compile"""
        try:
            result = subprocess.run(
                ["python3", "-m", "py_compile", str(file_path)],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            print(f"  ⚠ Syntax validation error: {e}")
            return False
    
    def apply_fix(self, fix: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply a code fix to a file
        
        Args:
            fix: {
                "file": "modules/applier.py",
                "location": "Line ~450",
                "current_code": "element = self.page.query_selector(selector)",
                "suggested_code": "element = self.find_element_with_fallback(selector, use_ai=True)",
                "reason": "Recurring SelectorNotFound errors"
            }
        
        Returns:
            {
                "success": bool,
                "message": str,
                "backup_path": str
            }
        """
        try:
            file_path = self.project_root / fix['file']
            
            if not file_path.exists():
                return {
                    "success": False,
                    "message": f"File not found: {fix['file']}"
                }
            
            # Create backup
            backup_path = self.create_backup(file_path)
            
            # Read current file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find and replace
            current_code = fix.get('current_code', '').strip()
            suggested_code = fix.get('suggested_code', '').strip()
            
            if not current_code or not suggested_code:
                return {
                    "success": False,
                    "message": "Missing current_code or suggested_code in fix"
                }
            
            # Try exact match first
            if current_code in content:
                new_content = content.replace(current_code, suggested_code, 1)
            else:
                # Try fuzzy match (find similar lines)
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if current_code[:30] in line:  # Match first 30 chars
                        lines[i] = suggested_code
                        new_content = '\n'.join(lines)
                        break
                else:
                    return {
                        "success": False,
                        "message": f"Could not find code to replace: {current_code[:50]}..."
                    }
            
            # Write new content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            # Validate syntax
            if not self.validate_syntax(file_path):
                # Restore backup
                if backup_path and backup_path.exists():
                    shutil.copy2(backup_path, file_path)
                return {
                    "success": False,
                    "message": "Syntax validation failed - changes reverted",
                    "backup_path": str(backup_path)
                }
            
            return {
                "success": True,
                "message": f"Fix applied successfully to {fix['file']}",
                "backup_path": str(backup_path)
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Error applying fix: {e}"
            }
    
    def apply_fixes(self, fixes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Apply multiple fixes
        
        Returns:
            {
                "total_fixes": int,
                "applied": int,
                "failed": int,
                "results": List[Dict]
            }
        """
        results = []
        applied = 0
        failed = 0
        
        for fix in fixes:
            result = self.apply_fix(fix)
            results.append({
                "fix": fix,
                "result": result
            })
            
            if result.get('success'):
                applied += 1
                print(f"  ✓ Applied fix: {fix.get('reason', 'Unknown reason')}")
            else:
                failed += 1
                print(f"  ✗ Failed to apply fix: {result.get('message', 'Unknown error')}")
        
        return {
            "total_fixes": len(fixes),
            "applied": applied,
            "failed": failed,
            "results": results
        }


if __name__ == "__main__":
    # Test
    fixer = CodeFixer()
    print("CodeFixer initialized")

