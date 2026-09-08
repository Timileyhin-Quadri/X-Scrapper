#!/usr/bin/env python3
"""Interactive manual login script for X (Twitter).

Launches Google Chrome/Chromium, attaches via CDP (port 922), allows the user
to log in manually (including 2FA/SMS verification), and saves session cookies
to a JSON file (default: session.json) for automated scraping.

Usage:
    python scripts/login.py
    python scripts/login.py --session-file session.json --cdp-port 922
"""

import argparse
import asyncio
import os
import sys

# Ensure project root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.playwright_scraper import PlaywrightScraper
from app.logging_config import setup_logging

logger = setup_logging()


async def main():
    parser = argparse.ArgumentParser(
        description="Log in to X/Twitter manually and save session cookies.",
    )
    parser.add_argument(
        "--session-file",
        type=str,
        default=os.getenv("SESSION_PATH", "session.json"),
        help="Path to save session cookies (default: session.json)",
    )
    parser.add_argument(
        "--cdp-port",
        type=int,
        default=int(os.getenv("CDP_PORT", "922")),
        help="Google Chrome/Chromium remote debugging port (default: 922)",
    )
    parser.add_argument(
        "--chrome-path",
        type=str,
        default=os.getenv("CHROME_PATH", ""),
        help="Path to Google Chrome/Chromium executable (optional)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds to wait for login (default: 300)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force fresh login flow even if existing cookies exist",
    )

    args = parser.parse_args()

    print("=" * 65)
    print("      X Research Collector - Manual Login & Cookie Exporter")
    print("=" * 65)
    print(f"  CDP Debugging Port: {args.cdp_port}")
    print(f"  Target Session File: {args.session_file}")
    print("=" * 65)

    scraper = PlaywrightScraper(
        headless=False,
        cdp_port=args.cdp_port,
        chrome_path=args.chrome_path or None,
        session_path=args.session_file,
    )

    try:
        await scraper.start()

        # Check if already authenticated (unless --force is specified)
        if not args.force and await scraper.is_already_logged_in():
            await scraper.save_session(args.session_file)
            print("\n[+] Your browser session is ALREADY verified and logged in to X!")
            print(f"[+] Session cookies saved to: {args.session_file}")
            print("\nYou can now run automated scraping with:")
            print(f"    python scripts/scrape_tweets.py --target 1000\n")
            print("(To force re-login, run: python scripts/login.py --force)")
            return

        # Proceed with manual login
        success = await scraper.manual_login(timeout=args.timeout)
        if success:
            await scraper.save_session(args.session_file)
            print("\n[+] All set! Your session cookies are ready for automated scraping.")
            print(f"  Run: python scripts/scrape_tweets.py --target 1000\n")
        else:
            print("\n[!] Login timed out. Please try running this script again.")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Login failed: {e}")
        sys.exit(1)
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
