"""Playwright-based X/Twitter scraper fallback.

Used when the X API is unavailable (401/403/no credits).
Scrapes tweets from X's search page using browser automation.
"""

import asyncio
import glob
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional
from app.models import Tweet
from app.logging_config import setup_logging

logger = setup_logging()


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PlaywrightScraper:
    """Scrapes tweets from X using Playwright attached to Google Chrome/Chromium CDP."""

    def __init__(
        self,
        headless: bool = False,
        user_data_dir: str = ".x_session",
        cdp_port: int = 922,
        chrome_path: Optional[str] = None,
        session_path: str = "session.json",
    ):
        """Initialize scraper.

        Args:
            headless: Run browser in headless mode (set False to see the browser).
            user_data_dir: Directory to persist browser cookies and session state.
            cdp_port: Google Chrome/Chromium remote debugging port (default: 922).
            chrome_path: Explicit path to chrome.exe / chromium.exe (optional).
            session_path: Path to save/load JSON session cookies (default: session.json).
        """
        self.headless = headless
        self.user_data_dir = (
            user_data_dir if os.path.isabs(user_data_dir)
            else os.path.join(PROJECT_ROOT, user_data_dir)
        )
        self.cdp_port = cdp_port
        self.chrome_path = chrome_path
        self.session_path = (
            session_path if os.path.isabs(session_path)
            else os.path.join(PROJECT_ROOT, session_path)
        )
        self.chrome_process: Optional[subprocess.Popen] = None
        self.browser = None
        self.context = None
        self.page = None
        self._tweet_count = 0
        self._pw = None

    @staticmethod
    def find_chrome_executable(custom_path: Optional[str] = None) -> str:
        """Find Google Chrome or Chromium executable on the system."""
        if custom_path and os.path.isfile(custom_path):
            return custom_path

        env_path = os.getenv("CHROME_PATH")
        if env_path and os.path.isfile(env_path):
            return env_path

        # Standard Windows install paths for Google Chrome / Chromium
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files\Chromium\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Chromium\Application\chrome.exe"),
        ]

        # Check Playwright-installed chromium
        playwright_dir = os.path.expanduser(r"~\AppData\Local\ms-playwright")
        if os.path.isdir(playwright_dir):
            for pattern in ["chromium-*/chrome-win64/chrome.exe", "chromium-*/chrome-win/chrome.exe"]:
                candidates.extend(glob.glob(os.path.join(playwright_dir, pattern)))

        # Check system PATH
        for name in ["chrome", "google-chrome", "chromium", "chromium-browser"]:
            which_path = shutil.which(name)
            if which_path:
                candidates.append(which_path)

        for path in candidates:
            if path and os.path.isfile(path):
                logger.info(f"Found Chrome/Chromium executable: {path}")
                return path

        raise FileNotFoundError(
            "Could not find Google Chrome or Chromium executable. "
            "Please install Google Chrome or set the CHROME_PATH environment variable."
        )

    def _is_cdp_ready(self) -> bool:
        """Check if Chrome CDP debugging endpoint is listening and ready."""
        try:
            url = f"http://127.0.0.1:{self.cdp_port}/json/version"
            with urllib.request.urlopen(url, timeout=1) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def start(self):
        """Launch Google Chrome/Chromium on remote debugging port and attach Playwright."""
        from playwright.async_api import async_playwright

        os.makedirs(self.user_data_dir, exist_ok=True)

        # Clean up stale Chromium lock files from crashed/interrupted sessions
        for lock_file in glob.glob(os.path.join(self.user_data_dir, "Singleton*")):
            try:
                os.remove(lock_file)
                logger.info(f"Removed stale lock file: {lock_file}")
            except OSError:
                pass

        # Check if Google Chrome/Chromium is already running on debugging port
        if self._is_cdp_ready():
            logger.info(
                f"Google Chrome/Chromium already listening on debugging port {self.cdp_port}. "
                "Attaching Playwright directly..."
            )
        else:
            executable = self.find_chrome_executable(self.chrome_path)
            logger.info(
                f"Launching Google Chrome/Chromium: '{executable}' "
                f"with --remote-debugging-port={self.cdp_port}..."
            )

            launch_cmd = [
                executable,
                f"--remote-debugging-port={self.cdp_port}",
                f"--user-data-dir={self.user_data_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--start-maximized",
            ]
            if self.headless:
                launch_cmd.append("--headless=new")

            self.chrome_process = subprocess.Popen(
                launch_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"Started browser process (PID: {self.chrome_process.pid})")

            # Wait for CDP endpoint to respond
            logger.info(f"Waiting for debugging port {self.cdp_port} to become available...")
            ready = False
            for attempt in range(30):
                if self._is_cdp_ready():
                    ready = True
                    break
                await asyncio.sleep(0.5)

            if not ready:
                raise RuntimeError(
                    f"Failed to connect to Google Chrome/Chromium on debugging port {self.cdp_port} within 15 seconds."
                )

        # Attach Playwright to the running browser via CDP
        self._pw = await async_playwright().start()
        cdp_endpoint = f"http://127.0.0.1:{self.cdp_port}"
        logger.info(f"Attaching Playwright via CDP to {cdp_endpoint}...")

        self.browser = await self._pw.chromium.connect_over_cdp(cdp_endpoint)
        self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        # Apply stealth init scripts to bypass webdriver detection
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        # Auto-load saved session cookies if session file exists
        if os.path.isfile(self.session_path):
            await self.load_session(self.session_path)

        logger.info(f"Playwright attached successfully to Google Chrome on debugging port {self.cdp_port}")

    async def save_session(self, path: Optional[str] = None) -> str:
        """Save session cookies and storage state to JSON file.

        Args:
            path: Target JSON file path (defaults to self.session_path).

        Returns:
            Absolute path to the saved session file.
        """
        target_path = os.path.abspath(path or self.session_path)
        os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)

        # Save Playwright storage state (cookies + localStorage)
        await self.context.storage_state(path=target_path)

        # Extract and log cookie summary
        cookies = await self.context.cookies()
        auth_names = [c["name"] for c in cookies if c.get("name") in ("auth_token", "ct0", "twid")]
        logger.info(
            f"Saved session state with {len(cookies)} cookies "
            f"(auth keys: {', '.join(auth_names) if auth_names else 'none'}) "
            f"to: {target_path}"
        )
        return target_path

    async def load_session(self, path: Optional[str] = None) -> bool:
        """Load saved cookies from JSON file into current browser context.

        Args:
            path: Source JSON file path (defaults to self.session_path).

        Returns:
            True if cookies were successfully loaded, False otherwise.
        """
        source_path = os.path.abspath(path or self.session_path)
        if not os.path.isfile(source_path):
            logger.debug(f"Session file not found: {source_path}")
            return False

        try:
            with open(source_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            cookies = state.get("cookies", [])
            if cookies:
                await self.context.add_cookies(cookies)
                logger.info(f"Loaded {len(cookies)} session cookies from {source_path}")
                return True
        except Exception as e:
            logger.warning(f"Failed to load session cookies from {source_path}: {e}")
        return False

    async def is_already_logged_in(self) -> bool:
        """Check if current session is genuinely logged in to X.

        Strictly requires an active auth_token cookie. If present, navigates to /home
        to ensure the session has not expired.
        """
        try:
            cookies = await self.context.cookies()
            has_auth_token = any(
                c.get("name") == "auth_token" and len(c.get("value", "")) > 10
                for c in cookies
            )

            # Strict check: without auth_token cookie, X is NEVER logged in
            if not has_auth_token:
                logger.info("No auth_token cookie found in browser session. Not logged in.")
                return False

            logger.info("Found auth_token cookie. Verifying active session on X...")
            await self.page.goto("https://x.com/home", wait_until="commit", timeout=25000)
            await asyncio.sleep(4)

            current_url = self.page.url
            if "login" in current_url or "/i/flow" in current_url:
                logger.info("Session expired or redirected to login flow.")
                return False

            # Check if authenticated UI elements are present
            for sel in [
                '[data-testid="SideNav_AccountSwitcher_Button"]',
                '[data-testid="SideNav_NewTweet_Button"]',
                'a[data-testid="AppTabBar_Profile_Link"]',
                'a[data-testid="AppTabBar_Home_Link"]',
                '[data-testid="primaryColumn"]',
            ]:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    logger.info("Session verified successfully via authenticated UI.")
                    return True

            if "home" in current_url:
                login_dialog = await self.page.query_selector('[data-testid="sheetDialog"]')
                if not login_dialog:
                    logger.info("Session confirmed via home feed URL.")
                    return True

        except Exception as e:
            logger.debug(f"Session check error: {e}")
        return False

    async def manual_login(self, timeout: int = 300) -> bool:
        """Open X login page and wait for manual user login, then save cookies.

        Args:
            timeout: Maximum seconds to wait for login (default: 300s).

        Returns:
            True if login was detected and session saved, False on timeout.
        """
        logger.info("Navigating to X login page (https://x.com/i/flow/login)...")
        try:
            await self.page.goto("https://x.com/i/flow/login", wait_until="commit", timeout=30000)
        except Exception as e:
            logger.warning(f"Navigation notice: {e}")

        banner = f"""
======================================================================
                     MANUAL LOGIN TO X (TWITTER)
======================================================================
  A Google Chrome window is open on debugging port {self.cdp_port}.
  Please log in to your X account in that browser window:
    1. Enter your Username / Email and click Next.
    2. Enter your Password and complete any 2FA or SMS verification.
    3. Keep going until you are logged in to your account.
======================================================================
  Watching for login... (Or press ENTER here once you're logged in)
"""
        print(banner)
        logger.info(f"Waiting up to {timeout}s for manual login to complete...")

        enter_event = asyncio.Event()

        def listen_for_enter():
            try:
                input(">> Press [ENTER] in this terminal when you have finished logging in: ")
                loop.call_soon_threadsafe(enter_event.set)
            except Exception:
                pass

        import threading
        enter_thread = threading.Thread(target=listen_for_enter, daemon=True)
        enter_thread.start()

        async def poll_for_login():
            start = time.time()
            while time.time() - start < timeout:
                await asyncio.sleep(2)
                try:
                    cookies = await self.context.cookies()
                    has_auth = any(
                        c.get("name") == "auth_token" and len(c.get("value", "")) > 10
                        for c in cookies
                    )
                    current_url = self.page.url

                    account_btn = None
                    try:
                        account_btn = await self.page.query_selector(
                            '[data-testid="SideNav_AccountSwitcher_Button"], '
                            'a[data-testid="AppTabBar_Profile_Link"], '
                            '[data-testid="SideNav_NewTweet_Button"]'
                        )
                    except Exception:
                        pass

                    if has_auth and ("login" not in current_url and "/i/flow" not in current_url):
                        logger.info("auth_token cookie and active session confirmed!")
                        return True

                    if account_btn:
                        logger.info("Authenticated navigation bar detected!")
                        return True
                except Exception as e:
                    logger.debug(f"Polling check: {e}")
            return False

        login_poll_task = asyncio.create_task(poll_for_login())
        enter_wait_task = asyncio.create_task(enter_event.wait())

        done, pending = await asyncio.wait(
            [login_poll_task, enter_wait_task],
            return_when=asyncio.FIRST_COMPLETED,
            timeout=timeout,
        )

        for task in pending:
            task.cancel()

        # Allow cookies to settle
        await asyncio.sleep(2)

        cookies = await self.context.cookies()
        has_auth = any(
            c.get("name") == "auth_token" and len(c.get("value", "")) > 10
            for c in cookies
        )

        if has_auth:
            saved_path = await self.save_session()
            print(f"""
======================================================================
                   LOGIN SUCCESSFUL & SESSION SAVED!
======================================================================
  Session cookies saved to:
  --> {saved_path}

  You can now run automated scraping with:
  python scripts/scrape_tweets.py --target 1000
======================================================================
""")
            return True
        else:
            logger.warning(
                "auth_token cookie was not found. "
                "Make sure you complete login in the Chrome browser window."
            )
            return False

    async def close(self):
        """Close browser context and terminate spawned browser process."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception as e:
            logger.debug(f"Error disconnecting Playwright: {e}")

        # Cleanly terminate browser process if it was spawned by this instance
        if self.chrome_process and self.chrome_process.poll() is None:
            try:
                self.chrome_process.terminate()
                self.chrome_process.wait(timeout=5)
            except Exception:
                try:
                    self.chrome_process.kill()
                except Exception:
                    pass

        logger.info("Browser closed")

    async def login(self, username: str, password: str, email: str = ""):
        """Log in to X/Twitter.

        Args:
            username: X username or handle.
            password: X password.
            email: Email for verification challenge (if prompted).
        """
        # Navigate directly to the login flow URL (X's landing page no longer
        # exposes input fields — it only shows a "Sign in" button).
        logger.info("Navigating to X login page...")
        try:
            await self.page.goto("https://x.com/i/flow/login", wait_until="commit", timeout=30000)
        except Exception as e:
            logger.warning(f"Navigation warning: {e}")

        await asyncio.sleep(5)
        await self.page.screenshot(path="landing_page_debug.png")

        # Check if already logged in (redirected to /home)
        home_nav = await self.page.query_selector('a[data-testid="AppTabBar_Home_Link"], [data-testid="SideNav_NewTweet_Button"]')
        if home_nav:
            logger.info("Already logged in on main page!")
            return

        # If we ended up on the landing page instead, click "Sign in" first
        if "/i/flow/login" not in self.page.url:
            logger.info("Redirected to landing page, looking for Sign In button...")
            for sel in [
                'a[href="/login"]',
                'a[href="/i/flow/login"]',
                'a:has-text("Sign in")',
                '[role="link"]:has-text("Sign in")',
                'button:has-text("Sign in")',
            ]:
                try:
                    btn = await self.page.query_selector(sel)
                    if btn and await btn.is_visible():
                        logger.info(f"Clicking sign-in link: {sel}")
                        await btn.click()
                        await asyncio.sleep(4)
                        break
                except Exception:
                    continue

        # Wait for the login form's username input to appear
        logger.info("Locating username/email input on X login form...")
        username_input = None
        for sel in [
            'input[autocomplete="username"]',
            'input[name="text"]',
            'input[placeholder*="email or username" i]',
            'input[type="text"]',
        ]:
            try:
                el = await self.page.wait_for_selector(sel, timeout=10000)
                if el and await el.is_visible():
                    username_input = el
                    logger.info(f"Found input field with selector '{sel}'")
                    break
            except Exception:
                continue

        if not username_input:
            # Final fallback — wait for any input
            username_input = await self.page.wait_for_selector('input', timeout=15000)

        logger.info("Entering username...")
        await username_input.fill(username)
        await asyncio.sleep(1)

        # Click Continue / Next button
        continue_btn = None
        for sel in [
            'button:has-text("Continue")',
            '[role="button"]:has-text("Continue")',
            'button:has-text("Next")',
            '[role="button"]:has-text("Next")',
        ]:
            el = await self.page.query_selector(sel)
            if el and await el.is_visible():
                continue_btn = el
                break

        if continue_btn:
            await continue_btn.click(force=True)
        else:
            await self.page.keyboard.press("Enter")

        await asyncio.sleep(4)
        await self.page.screenshot(path="after_continue_debug.png")

        # Check if phone number challenge or 2FA appears
        await asyncio.sleep(3)
        page_text = await self.page.evaluate("() => document.body.innerText")
        if "phone number" in page_text.lower() or "verification code" in page_text.lower() or "confirm your phone" in page_text.lower():
            logger.warning(
                "X Phone / SMS 2FA verification challenge detected. "
                "If running in visible mode, please complete the prompt in the browser window. "
                "Waiting up to 60 seconds for verification..."
            )
            for wait_sec in range(12):
                await asyncio.sleep(5)
                current_url = self.page.url
                if "home" in current_url or "search" in current_url:
                    logger.info("Verification completed successfully!")
                    break
                # Check if password field finally appeared
                pass_check = await self.page.query_selector('input[name="password"], input[type="password"]')
                if pass_check and await pass_check.is_visible():
                    break

        # Now locate password input field if prompted
        password_input = None
        for attempt in range(8):
            for sel in ['input[name="password"]', 'input[type="password"]', 'input[autocomplete="current-password"]']:
                try:
                    el = await self.page.query_selector(sel)
                    if el and await el.is_visible():
                        password_input = el
                        break
                except Exception:
                    continue
            if password_input:
                break
            await asyncio.sleep(1.5)

        if password_input:
            logger.info("Entering password...")
            try:
                await password_input.fill(password)
            except Exception:
                await password_input.click(force=True)
                await self.page.keyboard.type(password, delay=30)

            await asyncio.sleep(1)

            # Click Log in button or press Enter
            login_btn = await self.page.query_selector('button:has-text("Log in"), button:has-text("Sign in"), [role="button"]:has-text("Log in"), [data-testid="LoginForm_Login_Button"]')
            if login_btn:
                try:
                    await login_btn.click(force=True)
                except Exception:
                    await self.page.keyboard.press("Enter")
            else:
                await self.page.keyboard.press("Enter")

            await asyncio.sleep(6)
        await self.page.screenshot(path="login_step6_after_login_submit.png")

        # Dismiss any post-login onboarding dialogs or modals
        await asyncio.sleep(3)
        for _ in range(3):
            try:
                for dismiss_sel in [
                    'button:has-text("Skip for now")',
                    'button:has-text("Not now")',
                    'button:has-text("Dismiss")',
                    'button:has-text("Maybe later")',
                    'button:has-text("Accept all cookies")',
                    '[data-testid="sheetDialog"] button',
                    '[aria-label="Close"]',
                ]:
                    btn = await self.page.query_selector(dismiss_sel)
                    if btn and await btn.is_visible():
                        logger.info(f"Dismissing modal/prompt: {dismiss_sel}")
                        await btn.click(force=True)
                        await asyncio.sleep(2)
            except Exception:
                pass

        # If stuck on an onboarding/signup flow, navigate away to home
        current_url = self.page.url
        if "onboarding" in current_url or "signup" in current_url or "/i/flow" in current_url:
            logger.warning(f"Detected onboarding/signup flow at {current_url}, navigating to home...")
            try:
                await self.page.goto("https://x.com/home", wait_until="commit", timeout=30000)
                await asyncio.sleep(5)
            except Exception as e:
                logger.warning(f"Navigation to home failed: {e}")

        logger.info(f"Login completed. Current page URL: {self.page.url}")

    async def search_and_collect(
        self,
        query: str,
        target: int = 10000,
        scroll_pause: float = 2.5,
    ) -> list[Tweet]:
        """Search X and collect tweets by scrolling.

        Args:
            query: Search query (e.g., "#PutSouthAfricaFirst").
            target: Target number of tweets.
            scroll_pause: Seconds to wait between scrolls.

        Returns:
            List of collected Tweet objects.
        """
        import urllib.parse

        # Navigate to search (Live / latest tab)
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://x.com/search?q={encoded_query}&src=typed_query&f=live"

        logger.info(f"Navigating to search URL: {search_url}")
        try:
            await self.page.goto(search_url, wait_until="commit", timeout=30000)
        except Exception as e:
            logger.warning(f"Initial navigation slow ({e}), continuing...")

        await asyncio.sleep(6)

        # Check for and dismiss any dialogs on search page
        for dismiss_sel in ['button:has-text("Refuse non-essential cookies")', 'button:has-text("Accept all cookies")', '[aria-label="Close"]']:
            try:
                btn = await self.page.query_selector(dismiss_sel)
                if btn and await btn.is_visible():
                    await btn.click(force=True)
                    await asyncio.sleep(1)
            except Exception:
                pass

        # Take a screenshot of the search page for debugging
        await self.page.screenshot(path="search_page_debug.png")
        logger.info(f"Search page URL: {self.page.url}")

        # Wait for tweets to appear
        found_tweets = False
        for selector in ['article[data-testid="tweet"]', '[data-testid="tweet"]', 'div[data-testid="cellInnerDiv"]']:
            try:
                el = await self.page.wait_for_selector(selector, timeout=12000)
                if el:
                    found_tweets = True
                    logger.info(f"Found tweets using selector '{selector}'")
                    break
            except Exception:
                continue

        if not found_tweets:
            logger.warning("No immediate tweets on Live tab; checking Top tab...")
            top_url = f"https://x.com/search?q={encoded_query}&src=typed_query"
            try:
                await self.page.goto(top_url, wait_until="commit", timeout=30000)
                await asyncio.sleep(5)
                await self.page.screenshot(path="search_top_tab_debug.png")
            except Exception:
                pass

        tweets: dict[int, Tweet] = {}
        no_new_tweets_count = 0
        max_no_new = 12  # Stop after 12 scrolls with no new tweets
        scroll_count = 0

        logger.info(f"Starting to scroll and collect tweets (target: {target})...")

        while len(tweets) < target and no_new_tweets_count < max_no_new:
            # Extract tweets from current view
            new_tweets = await self._extract_tweets_from_page(query)
            new_count = 0

            for tweet in new_tweets:
                if tweet.tweet_id not in tweets:
                    tweets[tweet.tweet_id] = tweet
                    new_count += 1

            if new_count > 0:
                no_new_tweets_count = 0
                logger.info(
                    f"Scroll {scroll_count}: found {new_count} new tweets "
                    f"(total: {len(tweets)}/{target})"
                )
            else:
                no_new_tweets_count += 1

            scroll_count += 1

            # Scroll down
            await self.page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
            await asyncio.sleep(scroll_pause)

            # Check for empty state / rate limit
            try:
                error_el = await self.page.query_selector('[data-testid="empty_state_header_text"]')
                if error_el:
                    error_text = await error_el.inner_text()
                    logger.warning(f"X page state message: {error_text}")
                    if no_new_tweets_count > 4:
                        break
            except Exception:
                pass

        if len(tweets) == 0:
            await self.page.screenshot(path="search_empty_debug.png")

        logger.info(f"Collection complete: {len(tweets)} tweets collected in {scroll_count} scrolls")
        return list(tweets.values())

    async def _extract_tweets_from_page(self, query: str) -> list[Tweet]:
        """Extract tweet data from currently visible tweet elements."""
        tweets = []

        tweet_elements = await self.page.query_selector_all('article[data-testid="tweet"], [data-testid="tweet"]')

        for element in tweet_elements:
            try:
                tweet = await self._parse_tweet_element(element, query)
                if tweet:
                    tweets.append(tweet)
            except Exception as e:
                logger.debug(f"Failed to parse tweet element: {e}")
                continue

        return tweets

    async def _parse_tweet_element(self, element, query: str) -> Optional[Tweet]:
        """Parse a single tweet article element into a Tweet model."""
        try:
            # Get tweet text
            text_el = await element.query_selector('[data-testid="tweetText"]')
            text = await text_el.inner_text() if text_el else ""

            if not text:
                return None

            # Get username and user info
            user_links = await element.query_selector_all('a[role="link"]')
            username = None
            author_id = None

            for link in user_links:
                href = await link.get_attribute("href")
                if href and href.startswith("/") and not href.startswith("/i/"):
                    username = href.strip("/").split("/")[0]
                    break

            # Get tweet link (contains tweet ID)
            tweet_id = None
            time_el = await element.query_selector("time")
            if time_el:
                parent_link = await time_el.evaluate(
                    """el => {
                        let parent = el.parentElement;
                        while (parent) {
                            if (parent.tagName === 'A' && parent.href) return parent.href;
                            parent = parent.parentElement;
                        }
                        return null;
                    }"""
                )
                if parent_link:
                    # Extract tweet ID from URL like /username/status/123456789
                    match = re.search(r"/status/(\d+)", parent_link)
                    if match:
                        tweet_id = int(match.group(1))

            if not tweet_id:
                # Generate a hash-based ID as fallback
                tweet_id = abs(hash(text + (username or ""))) % (10**18)

            # Get timestamp
            created_at = None
            if time_el:
                datetime_attr = await time_el.get_attribute("datetime")
                if datetime_attr:
                    try:
                        created_at = datetime.fromisoformat(datetime_attr.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass

            # Get metrics
            metrics = {"retweet_count": 0, "reply_count": 0, "like_count": 0, "quote_count": 0}

            # Reply count
            reply_el = await element.query_selector('[data-testid="reply"]')
            if reply_el:
                metrics["reply_count"] = await self._parse_metric(reply_el)

            # Retweet count
            retweet_el = await element.query_selector('[data-testid="retweet"]')
            if retweet_el:
                metrics["retweet_count"] = await self._parse_metric(retweet_el)

            # Like count
            like_el = await element.query_selector('[data-testid="like"]')
            if like_el:
                metrics["like_count"] = await self._parse_metric(like_el)

            # Get language from text (basic detection)
            lang = "und"  # undetermined

            tweet = Tweet(
                tweet_id=tweet_id,
                text=text,
                author_id=abs(hash(username)) % (10**15) if username else None,
                username=username,
                created_at=created_at,
                retweet_count=metrics["retweet_count"],
                reply_count=metrics["reply_count"],
                like_count=metrics["like_count"],
                quote_count=metrics["quote_count"],
                lang=lang,
                conversation_id=tweet_id,
                query=query,
            )

            return tweet

        except Exception as e:
            logger.debug(f"Error parsing tweet: {e}")
            return None

    async def _parse_metric(self, element) -> int:
        """Parse a metric value from an engagement button element."""
        try:
            aria_label = await element.get_attribute("aria-label")
            if aria_label:
                # aria-label format: "123 Likes" or "1,234 replies"
                match = re.search(r"([\d,]+)", aria_label)
                if match:
                    return int(match.group(1).replace(",", ""))
        except Exception:
            pass
        return 0
