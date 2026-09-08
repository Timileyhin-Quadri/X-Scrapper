#!/usr/bin/env python3
"""Export collected tweets to CSV.

Usage:
    python scripts/export_csv.py --output data/tweets.csv
    python scripts/export_csv.py --output data/tweets.csv --query "#PutSouthAfricaFirst"
"""

import argparse
import csv
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_config
from app.database import Database
from app.logging_config import setup_logging

logger = setup_logging()

CSV_FIELDS = [
    "tweet_id", "text", "author_id", "username", "created_at",
    "retweet_count", "reply_count", "like_count", "quote_count",
    "lang", "conversation_id", "query", "collected_at",
]


def main():
    parser = argparse.ArgumentParser(description="Export collected tweets to CSV.")
    parser.add_argument(
        "--output",
        type=str,
        default="data/tweets.csv",
        help="Output CSV file path (default: data/tweets.csv)",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Filter by query (optional)",
    )

    args = parser.parse_args()

    config = get_config()
    db = Database(config)

    try:
        db.connect()

        # Ensure output directory exists
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

        with db.cursor() as cur:
            if args.query:
                cur.execute(
                    f"SELECT {', '.join(CSV_FIELDS)} FROM tweets WHERE query = %s ORDER BY created_at DESC",
                    (args.query,),
                )
            else:
                cur.execute(
                    f"SELECT {', '.join(CSV_FIELDS)} FROM tweets ORDER BY created_at DESC"
                )

            rows = cur.fetchall()

        with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_FIELDS)
            for row in rows:
                writer.writerow(row)

        logger.info(f"Exported {len(rows)} tweets to {args.output}")
        print(f"[+] Exported {len(rows):,} tweets to {args.output}")

    except Exception as e:
        logger.error(f"Export failed: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
