"""Real-time CSV writer for scraped tweets with deduplication."""

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Set
from app.models import Tweet
from app.logging_config import setup_logging

logger = setup_logging()

CSV_FIELDS = [
    "tweet_id",
    "text",
    "author_id",
    "username",
    "created_at",
    "retweet_count",
    "reply_count",
    "like_count",
    "quote_count",
    "lang",
    "conversation_id",
    "query",
    "collected_at",
]


class CsvTweetWriter:
    """Manages real-time append-only CSV streaming for tweets.

    Features:
    - Zero external database setup needed.
    - Automatic directory creation.
    - Deduplication across restarts: pre-loads existing tweet IDs from the file.
    - Immediate disk flushing (`f.flush()`) after each write to ensure zero data loss on crash.
    """

    def __init__(self, filepath: str = "data/tweets.csv"):
        self.filepath = Path(filepath)
        self.seen_ids: Set[int] = set()
        self.written_count: int = 0
        self.duplicates_skipped: int = 0
        self._file = None
        self._writer = None

        self._initialize()

    def _initialize(self):
        """Prepare directory and preload existing tweet IDs for resume/deduplication."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        file_existed = self.filepath.exists() and self.filepath.stat().st_size > 0

        # Pre-load seen tweet IDs if file already has content
        if file_existed:
            try:
                with open(self.filepath, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        tid = row.get("tweet_id")
                        if tid:
                            try:
                                self.seen_ids.add(int(tid))
                            except ValueError:
                                pass
                logger.info(
                    f"Pre-loaded {len(self.seen_ids):,} existing tweet IDs from {self.filepath} for deduplication."
                )
            except Exception as e:
                logger.warning(f"Could not read existing tweet IDs from {self.filepath}: {e}")

        # Open file in append mode
        self._file = open(self.filepath, "a", newline="", encoding="utf-8-sig")
        self._writer = csv.writer(self._file)

        # Write header if file was newly created
        if not file_existed:
            self._writer.writerow(CSV_FIELDS)
            self._file.flush()
            logger.info(f"Initialized new CSV file with headers at: {self.filepath}")

    def write_tweet(self, tweet: Tweet) -> bool:
        """Write a single tweet to CSV in real-time.

        Args:
            tweet: Tweet dataclass object.

        Returns:
            True if written as a new tweet, False if skipped as duplicate.
        """
        if tweet.tweet_id in self.seen_ids:
            self.duplicates_skipped += 1
            return False

        row = [
            tweet.tweet_id,
            tweet.text,
            tweet.author_id or "",
            tweet.username or "",
            tweet.created_at.isoformat() if isinstance(tweet.created_at, datetime) else (tweet.created_at or ""),
            tweet.retweet_count,
            tweet.reply_count,
            tweet.like_count,
            tweet.quote_count,
            tweet.lang or "",
            tweet.conversation_id or "",
            tweet.query or "",
            tweet.collected_at.isoformat() if isinstance(tweet.collected_at, datetime) else (tweet.collected_at or ""),
        ]

        self._writer.writerow(row)
        self._file.flush()  # Real-time persistence

        self.seen_ids.add(tweet.tweet_id)
        self.written_count += 1
        return True

    def close(self):
        """Flush and close the file handle."""
        if self._file and not self._file.closed:
            self._file.flush()
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
