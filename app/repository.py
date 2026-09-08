"""Repository layer for tweet and collection run persistence."""

from datetime import datetime, timezone
from typing import Optional
from app.database import Database
from app.models import Tweet, CollectionRun
from app.logging_config import setup_logging

logger = setup_logging()


class TweetRepository:
    """Handles tweet persistence in PostgreSQL."""

    def __init__(self, db: Database):
        self.db = db

    def insert_tweets(self, tweets: list[Tweet]) -> tuple[int, int]:
        """Insert tweets with ON CONFLICT DO NOTHING for idempotency.

        Returns:
            Tuple of (inserted_count, duplicate_count).
        """
        if not tweets:
            return 0, 0

        inserted = 0
        duplicates = 0

        insert_sql = """
            INSERT INTO tweets (
                tweet_id, text, author_id, username, created_at,
                retweet_count, reply_count, like_count, quote_count,
                lang, conversation_id, query, collected_at
            ) VALUES (
                %(tweet_id)s, %(text)s, %(author_id)s, %(username)s, %(created_at)s,
                %(retweet_count)s, %(reply_count)s, %(like_count)s, %(quote_count)s,
                %(lang)s, %(conversation_id)s, %(query)s, %(collected_at)s
            )
            ON CONFLICT (tweet_id) DO NOTHING
        """

        with self.db.cursor() as cur:
            for tweet in tweets:
                cur.execute(insert_sql, {
                    "tweet_id": tweet.tweet_id,
                    "text": tweet.text,
                    "author_id": tweet.author_id,
                    "username": tweet.username,
                    "created_at": tweet.created_at,
                    "retweet_count": tweet.retweet_count,
                    "reply_count": tweet.reply_count,
                    "like_count": tweet.like_count,
                    "quote_count": tweet.quote_count,
                    "lang": tweet.lang,
                    "conversation_id": tweet.conversation_id,
                    "query": tweet.query,
                    "collected_at": tweet.collected_at,
                })
                if cur.rowcount > 0:
                    inserted += 1
                else:
                    duplicates += 1

        logger.info(f"Batch insert: {inserted} new, {duplicates} duplicates")
        return inserted, duplicates

    def get_total_count(self, query: Optional[str] = None) -> int:
        """Get total tweet count, optionally filtered by query."""
        with self.db.cursor() as cur:
            if query:
                cur.execute("SELECT COUNT(*) FROM tweets WHERE query = %s", (query,))
            else:
                cur.execute("SELECT COUNT(*) FROM tweets")
            return cur.fetchone()[0]

    def get_newest_tweet_id(self, query: str) -> Optional[int]:
        """Get the newest tweet_id for a given query (for since_id)."""
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT MAX(tweet_id) FROM tweets WHERE query = %s",
                (query,),
            )
            result = cur.fetchone()[0]
            return result


class CollectionRunRepository:
    """Handles collection run tracking in PostgreSQL."""

    def __init__(self, db: Database):
        self.db = db

    def start_run(self, query: str, run_type: str = "initial", since_id: Optional[int] = None) -> int:
        """Create a new collection run record. Returns run_id."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO collection_runs (query, run_type, started_at, status, since_id)
                VALUES (%s, %s, %s, 'running', %s)
                RETURNING run_id
                """,
                (query, run_type, datetime.now(timezone.utc), since_id),
            )
            run_id = cur.fetchone()[0]
            logger.info(f"Collection run {run_id} started (type={run_type})")
            return run_id

    def update_run(self, run: CollectionRun):
        """Update a collection run record."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE collection_runs SET
                    completed_at = %s,
                    posts_fetched = %s,
                    posts_inserted = %s,
                    duplicates = %s,
                    pages_requested = %s,
                    retry_attempts = %s,
                    status = %s,
                    error_message = %s,
                    newest_id = %s
                WHERE run_id = %s
                """,
                (
                    run.completed_at,
                    run.posts_fetched,
                    run.posts_inserted,
                    run.duplicates,
                    run.pages_requested,
                    run.retry_attempts,
                    run.status,
                    run.error_message,
                    run.newest_id,
                    run.run_id,
                ),
            )

    def get_latest_newest_id(self, query: str) -> Optional[int]:
        """Get the newest_id from the last successful run for a query."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT newest_id FROM collection_runs
                WHERE query = %s AND status = 'success' AND newest_id IS NOT NULL
                ORDER BY completed_at DESC LIMIT 1
                """,
                (query,),
            )
            result = cur.fetchone()
            return result[0] if result else None
