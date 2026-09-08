#!/usr/bin/env python3
"""Playwright-based tweet scraper script.

Fallback when the X API returns 401/403 (no valid credentials or credits).

Usage:
    # With login (recommended for full access):
    python scripts/scrape_tweets.py --username YOUR_X_USERNAME --password YOUR_PASSWORD --target 10000

    # With login + email verification:
    python scripts/scrape_tweets.py --username YOUR_X_USERNAME --password YOUR_PASSWORD --email YOUR_EMAIL --target 10000

    # Show browser (non-headless, useful for debugging):
    python scripts/scrape_tweets.py --username YOUR_X_USERNAME --password YOUR_PASSWORD --target 100 --visible
"""

import argparse
import asyncio
import sys
import os
import signal

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_config
from app.database import Database
from app.models import CollectionRun
from app.repository import TweetRepository, CollectionRunRepository
from app.playwright_scraper import PlaywrightScraper
from app.logging_config import setup_logging
from datetime import datetime, timezone
import time

logger = setup_logging()

_shutdown = False


def handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    _shutdown = True


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


async def main():
    parser = argparse.ArgumentParser(
        description="Scrape X/Twitter posts using Playwright browser automation.",
        epilog=(
            "This is a fallback when the X API is unavailable. "
            "You must have an X account to log in."
        ),
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Search query (default: from .env DEFAULT_QUERY)",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=10000,
        help="Target number of tweets to collect (default: 10000)",
    )
    parser.add_argument(
        "--username",
        type=str,
        default=os.getenv("X_USERNAME", ""),
        help="X/Twitter username for login",
    )
    parser.add_argument(
        "--password",
        type=str,
        default=os.getenv("X_PASSWORD", ""),
        help="X/Twitter password for login",
    )
    parser.add_argument(
        "--email",
        type=str,
        default=os.getenv("X_EMAIL", ""),
        help="Email for verification challenge (if prompted)",
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Show the browser window (non-headless mode)",
    )
    parser.add_argument(
        "--scroll-pause",
        type=float,
        default=2.0,
        help="Seconds between scroll actions (default: 2.0)",
    )
    parser.add_argument(
        "--cdp-port",
        type=int,
        default=int(os.getenv("CDP_PORT", "922")),
        help="Google Chrome/Chromium remote debugging port (default: 922)",
    )
    parser.add_argument(
        "--session-file",
        type=str,
        default=os.getenv("SESSION_PATH", "session.json"),
        help="Path to session cookies file (default: session.json)",
    )
    parser.add_argument(
        "--chrome-path",
        type=str,
        default=os.getenv("CHROME_PATH", ""),
        help="Path to Chrome/Chromium executable (optional, auto-detected if omitted)",
    )
    parser.add_argument(
        "--manual-login",
        action="store_true",
        help="Open browser window for manual login before scraping",
    )

    args = parser.parse_args()

    config = get_config()
    query = args.query or config.default_query

    logger.info("=" * 60)
    logger.info("X Research Collector - Playwright Scraper")
    logger.info("=" * 60)
    logger.info(f"Query: {query}")
    logger.info(f"Target: {args.target:,} tweets")
    logger.info(f"Mode: {'Visible' if args.visible or args.manual_login else 'Headless'}")
    logger.info(f"CDP Port: {args.cdp_port}")
    logger.info(f"Session File: {args.session_file}")
    if args.chrome_path:
        logger.info(f"Chrome Path: {args.chrome_path}")

    # Initialize database
    db = Database(config)
    db.connect()
    db.initialize_schema()

    tweet_repo = TweetRepository(db)
    run_repo = CollectionRunRepository(db)

    # Start collection run
    run = CollectionRun(query=query, run_type="scraper")
    run.run_id = run_repo.start_run(query, "scraper")

    # If manual login requested, browser must be visible
    is_headless = not (args.visible or args.manual_login)

    scraper = PlaywrightScraper(
        headless=is_headless,
        cdp_port=args.cdp_port,
        chrome_path=args.chrome_path or None,
        session_path=args.session_file,
    )
    start_time = time.time()

    try:
        await scraper.start()

        # Handle login
        if args.manual_login:
            logger.info("Manual login requested...")
            await scraper.manual_login()
        else:
            logged_in = await scraper.is_already_logged_in()
            if logged_in:
                logger.info("Using authenticated session from saved cookies / persistent profile.")
            elif args.username and args.password:
                logger.info("Performing login with provided credentials...")
                await scraper.login(args.username, args.password, args.email)
                await scraper.save_session(args.session_file)
            else:
                logger.warning(
                    "Session is not authenticated. "
                    "Run 'python scripts/login.py' to log in manually and save session cookies."
                )

        # Collect tweets
        tweets = await scraper.search_and_collect(
            query=query,
            target=args.target,
            scroll_pause=args.scroll_pause,
        )

        # Persist to database
        if tweets:
            inserted, dupes = tweet_repo.insert_tweets(tweets)
            run.posts_fetched = len(tweets)
            run.posts_inserted = inserted
            run.duplicates = dupes
        else:
            run.posts_fetched = 0
            run.posts_inserted = 0
            run.duplicates = 0

        run.completed_at = datetime.now(timezone.utc)
        run.status = "success"
        run_repo.update_run(run)

        duration = time.time() - start_time
        hours, remainder = divmod(int(duration), 3600)
        minutes, seconds = divmod(remainder, 60)

        summary_box = f"""
====================================================
     Playwright Scraper - Collection Complete     
====================================================
  Query:              {query}
  Requested target:   {args.target:,}
  Tweets scraped:     {run.posts_fetched:,}
  New tweets saved:   {run.posts_inserted:,}
  Duplicates:         {run.duplicates:,}
  Duration:           {hours:02d}:{minutes:02d}:{seconds:02d}
  Status:             {run.status.upper()}
  Method:             Playwright Browser Scraping
====================================================
"""
        print(summary_box)

    except Exception as e:
        run.completed_at = datetime.now(timezone.utc)
        run.status = "failed"
        run.error_message = str(e)
        run_repo.update_run(run)
        logger.error(f"Scraping failed: {e}")
        raise
    finally:
        await scraper.close()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
