"""
Session Manager Module
Manages real browser sessions to avoid 403 errors
Uses persistent context with real user profile
"""
import os
import platform
from pathlib import Path
from typing import Optional, Tuple
import shutil


class SessionManager:
    """Manages real browser sessions for authenticated access"""
    
    def __init__(self):
        self.system = platform.system()
        self.user_data_dir = None
        self.profile_name = "Default"
    
    def find_chrome_profile(self) -> Optional[Path]:
        """Find Chrome user data directory automatically"""
        if self.system == "Darwin":  # macOS
            chrome_paths = [
                Path.home() / "Library/Application Support/Google/Chrome",
                Path.home() / "Library/Application Support/Chromium",
            ]
        elif self.system == "Windows":
            local_appdata = os.getenv("LOCALAPPDATA")
            if local_appdata:
                chrome_paths = [
                    Path(local_appdata) / "Google/Chrome/User Data",
                    Path(local_appdata) / "Chromium/User Data",
                ]
            else:
                chrome_paths = []
        elif self.system == "Linux":
            chrome_paths = [
                Path.home() / ".config/google-chrome",
                Path.home() / ".config/chromium",
            ]
        else:
            chrome_paths = []
        
        for chrome_path in chrome_paths:
            if chrome_path.exists():
                default_profile = chrome_path / self.profile_name
                if default_profile.exists():
                    return chrome_path
        
        return None
    
    def find_edge_profile(self) -> Optional[Path]:
        """Find Edge user data directory"""
        if self.system == "Darwin":  # macOS
            edge_paths = [
                Path.home() / "Library/Application Support/Microsoft Edge",
            ]
        elif self.system == "Windows":
            local_appdata = os.getenv("LOCALAPPDATA")
            if local_appdata:
                edge_paths = [
                    Path(local_appdata) / "Microsoft/Edge/User Data",
                ]
            else:
                edge_paths = []
        elif self.system == "Linux":
            edge_paths = [
                Path.home() / ".config/microsoft-edge",
            ]
        else:
            edge_paths = []
        
        for edge_path in edge_paths:
            if edge_path.exists():
                default_profile = edge_path / self.profile_name
                if default_profile.exists():
                    return edge_path
        
        return None
    
    def get_user_data_dir(self, browser: str = "chrome") -> Tuple[Optional[Path], str]:
        """
        Get user data directory for specified browser
        
        Returns:
            (user_data_dir, message)
        """
        if browser.lower() == "chrome":
            user_data_dir = self.find_chrome_profile()
            browser_name = "Chrome"
        elif browser.lower() == "edge":
            user_data_dir = self.find_edge_profile()
            browser_name = "Edge"
        else:
            return None, f"Unsupported browser: {browser}"
        
        if user_data_dir:
            return user_data_dir, f"✓ Found {browser_name} profile at: {user_data_dir}"
        else:
            return None, f"✗ {browser_name} profile not found. Please ensure {browser_name} is installed."
    
    def create_isolated_session(self, source_dir: Path, project_dir: Path = None) -> Optional[Path]:
        """
        Create isolated session copy with only Cookies and Local Storage
        This avoids ProcessSingleton and token decryption errors
        Creates temp_session/ in project directory
        """
        try:
            # Use project directory for isolation
            if project_dir is None:
                from pathlib import Path
                project_dir = Path.cwd()
            
            temp_session_dir = project_dir / "temp_session"
            
            # Remove existing session if it exists
            if temp_session_dir.exists():
                print(f"  Removing existing temp_session: {temp_session_dir}")
                try:
                    shutil.rmtree(temp_session_dir)
                except Exception as e:
                    print(f"  ⚠ Could not remove existing session: {e}")
            
            # Create temp_session structure
            temp_session_dir.mkdir(exist_ok=True)
            default_dir = temp_session_dir / "Default"
            default_dir.mkdir(exist_ok=True)
            
            print(f"  Creating isolated session from {source_dir}...")
            print(f"  Copying only essential data (Cookies, Local Storage)...")
            
            # Copy only essential directories for session
            # Including authentication data for Google login
            essential_dirs = [
                "Cookies",
                "Local Storage",
                "Session Storage",
                "Preferences",
                "Login Data",
                "Web Data",  # Contains authentication tokens
                "Network Action Predictor",  # May contain auth data
                "Trusted Vault",  # Google account sync data
            ]
            
            copied_count = 0
            for dir_name in essential_dirs:
                source_path = source_dir / dir_name
                if source_path.exists():
                    try:
                        dest_path = default_dir / dir_name
                        if source_path.is_dir():
                            shutil.copytree(source_path, dest_path, ignore=shutil.ignore_patterns('*.lock', '*.tmp'))
                        else:
                            shutil.copy2(source_path, dest_path)
                        copied_count += 1
                        print(f"    ✓ Copied: {dir_name}")
                    except Exception as e:
                        print(f"    ⚠ Could not copy {dir_name}: {e}")
            
            # Copy Preferences file (contains login state)
            prefs_file = source_dir / "Preferences"
            if prefs_file.exists():
                try:
                    shutil.copy2(prefs_file, default_dir / "Preferences")
                    print(f"    ✓ Copied: Preferences")
                except:
                    pass
            
            # Copy additional authentication files
            auth_files = [
                "Web Data",  # SQLite database with auth tokens
                "Login Data",  # SQLite database with saved passwords
            ]
            for auth_file in auth_files:
                source_file = source_dir / auth_file
                if source_file.exists():
                    try:
                        dest_file = default_dir / auth_file
                        shutil.copy2(source_file, dest_file)
                        print(f"    ✓ Copied: {auth_file}")
                    except Exception as e:
                        print(f"    ⚠ Could not copy {auth_file}: {e}")
            
            if copied_count > 0:
                print(f"  ✓ Isolated session created: {temp_session_dir}")
                print(f"  ✓ Copied {copied_count} essential components")
                print(f"  ✓ Safe to use - no ProcessSingleton conflicts")
                return temp_session_dir
            else:
                print(f"  ⚠ No essential data copied. Using empty session.")
                return temp_session_dir
            
        except Exception as e:
            print(f"  ✗ Error creating isolated session: {e}")
            import traceback
            print(f"  Details: {traceback.format_exc()[:200]}")
            return None
    
    def create_profile_copy(self, source_dir: Path, copy_name: str = "temp_profile") -> Optional[Path]:
        """
        DEPRECATED: Use create_isolated_session instead
        Create a copy of the profile for Playwright to use
        """
        return self.create_isolated_session(source_dir)
    
    def check_chrome_running(self) -> bool:
        """Check if Chrome is currently running"""
        if self.system == "Darwin":
            import subprocess
            try:
                result = subprocess.run(
                    ["pgrep", "-f", "Google Chrome"],
                    capture_output=True,
                    text=True
                )
                return result.returncode == 0
            except:
                return False
        elif self.system == "Windows":
            import subprocess
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                    capture_output=True,
                    text=True
                )
                return "chrome.exe" in result.stdout
            except:
                return False
        else:
            # Linux
            import subprocess
            try:
                result = subprocess.run(
                    ["pgrep", "-f", "chrome"],
                    capture_output=True,
                    text=True
                )
                return result.returncode == 0
            except:
                return False
    
    def get_playwright_profile_dir(self) -> Path:
        """
        Returns a dedicated persistent profile directory for Playwright.
        This profile is separate from Chrome and survives between runs.
        After the first login (done automatically via credentials), subsequent
        runs reuse the saved session without re-logging in.
        """
        import json
        configured_dir = os.getenv("BROWSER_PROFILE_DIR")
        if configured_dir:
            base_dir = Path(configured_dir).expanduser()
        else:
            data_dir = Path(os.getenv("DATA_DIR", ".")).expanduser()
            base_dir = data_dir / "playwright_profile"
        profile_dir = base_dir / "Default"
        profile_dir.mkdir(parents=True, exist_ok=True)

        # Suppress Chromium first-run "Sign in to Chromium" dialog and sync prompts.
        # These keys are patched every launch so they survive profile updates.
        prefs_file = profile_dir / "Preferences"
        try:
            prefs = json.loads(prefs_file.read_text()) if prefs_file.exists() else {}
            prefs.setdefault("browser", {}).update({
                "has_seen_welcome_page": True,
                "first_run_tabs": [],
            })
            prefs["signin"] = {
                "allowed": False,
                "allowed_on_next_startup": False,
                "accounts_metadata_dict": prefs.get("signin", {}).get("accounts_metadata_dict", {}),
            }
            prefs["sync_promo"] = {
                "show_count": 100,
                "startup_count": 100,
                "user_skipped": True,
            }
            prefs_file.write_text(json.dumps(prefs))
        except Exception:
            pass

        return base_dir

    def get_context_args(self, browser: str = "chrome") -> dict:
        """
        Returns launch_persistent_context args using a dedicated Playwright profile.
        This avoids all macOS Keychain/cookie-encryption issues that occur when
        copying Chrome's profile — Playwright owns this profile from the start.
        """
        profile_dir = self.get_playwright_profile_dir()
        print(f"  ✓ Usando perfil Playwright dedicado: {profile_dir}")
        return {
            'user_data_dir': str(profile_dir),
            'profile_name': 'Default',
            'message': f"Using dedicated Playwright profile: {profile_dir}",
            'can_use_real_session': True,
            'chrome_running': False,
            'isolated': False,
        }


if __name__ == "__main__":
    # Test
    manager = SessionManager()
    
    print("Detecting browser profiles...")
    print()
    
    # Try Chrome
    chrome_dir, chrome_msg = manager.get_user_data_dir("chrome")
    print(f"Chrome: {chrome_msg}")
    if chrome_dir:
        print(f"  Profile path: {chrome_dir / 'Default'}")
    
    print()
    
    # Try Edge
    edge_dir, edge_msg = manager.get_user_data_dir("edge")
    print(f"Edge: {edge_msg}")
    if edge_dir:
        print(f"  Profile path: {edge_dir / 'Default'}")
    
    print()
    
    # Check if Chrome is running
    if manager.check_chrome_running():
        print("⚠ Chrome is currently running.")
        print("  Recommendation: Close Chrome or use profile copy")
    else:
        print("✓ Chrome is not running. Can use profile directly")


