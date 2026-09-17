#!/usr/bin/env python3
"""Create or refresh the persistent LinkedIn session through the noVNC window."""

import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from modules.session_manager import SessionManager


def has_authenticated_session(context, page) -> bool:
    try:
        cookies = context.cookies(["https://www.linkedin.com"])
        has_li_at = any(cookie.get("name") == "li_at" and cookie.get("value") for cookie in cookies)
        current_url = (page.url or "").lower()
        requires_login = any(part in current_url for part in ("/login", "/checkpoint", "/uas/"))
        return has_li_at and not requires_login
    except Exception:
        return False


def main() -> int:
    timeout_seconds = int(os.getenv("SESSION_SETUP_TIMEOUT", "1800"))
    profile_dir = SessionManager().get_playwright_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"Persistent profile: {profile_dir}")
    print("Open the noVNC tunnel in your browser and complete LinkedIn login/2FA.")
    print(f"The setup window will remain open for up to {timeout_seconds // 60} minutes.")

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={"width": 1920, "height": 1080},
            args=[
                "--disable-gpu",
                "--disable-features=SyncRequiresConsent,ChromeSignin",
            ],
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(
                "https://www.linkedin.com/feed",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            page.bring_to_front()

            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                if has_authenticated_session(context, page):
                    marker = Path(os.getenv("DATA_DIR", "/data")) / "linkedin_session_ready"
                    marker.write_text(
                        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        encoding="utf-8",
                    )
                    print("LinkedIn session authenticated and persisted successfully.")
                    time.sleep(5)
                    return 0
                time.sleep(5)

            print("Session setup timed out before LinkedIn authentication completed.")
            return 1
        finally:
            context.close()


if __name__ == "__main__":
    raise SystemExit(main())

