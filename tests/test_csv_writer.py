"""Unit tests for CsvTweetWriter and real-time CSV persistence."""

import csv
import pytest
from datetime import datetime, timezone
from pathlib import Path
from app.config import Config
from app.csv_writer import CsvTweetWriter, CSV_FIELDS
from app.models import Tweet


@pytest.fixture
def sample_tweet():
    return Tweet(
        tweet_id=1234567890123456789,
        text="Sample research tweet about #PutSouthAfricaFirst with emojis 🇿🇦🔥 and newlines\nsecond line",
        author_id=987654321,
        username="south_africa_voice",
        created_at=datetime(2022, 1, 15, 12, 30, 0, tzinfo=timezone.utc),
        retweet_count=42,
        reply_count=10,
        like_count=150,
        quote_count=5,
        lang="en",
        conversation_id=1234567890123456789,
        query="#PutSouthAfricaFirst",
    )


class TestCsvTweetWriter:
    """Tests for CsvTweetWriter functionality."""

    def test_create_new_csv_with_headers(self, tmp_path, sample_tweet):
        csv_file = tmp_path / "test_tweets.csv"
        with CsvTweetWriter(str(csv_file)) as writer:
            written = writer.write_tweet(sample_tweet)
            assert written is True
            assert writer.written_count == 1
            assert writer.duplicates_skipped == 0

        assert csv_file.exists()

        with open(csv_file, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)
            row = next(reader)

        assert header == CSV_FIELDS
        assert row[0] == str(sample_tweet.tweet_id)
        assert row[1] == sample_tweet.text
        assert row[2] == str(sample_tweet.author_id)
        assert row[3] == sample_tweet.username
        assert row[5] == "42"  # retweet_count
        assert row[7] == "150"  # like_count

    def test_duplicate_skipped_in_same_session(self, tmp_path, sample_tweet):
        csv_file = tmp_path / "test_dupes.csv"
        with CsvTweetWriter(str(csv_file)) as writer:
            assert writer.write_tweet(sample_tweet) is True
            assert writer.write_tweet(sample_tweet) is False
            assert writer.written_count == 1
            assert writer.duplicates_skipped == 1

        with open(csv_file, "r", encoding="utf-8-sig") as f:
            lines = [l for l in csv.reader(f) if l]

        # 1 header line + 1 data line
        assert len(lines) == 2

    def test_resumable_collection_preexisting_file(self, tmp_path, sample_tweet):
        csv_file = tmp_path / "test_resume.csv"

        # Session 1: Write first tweet
        with CsvTweetWriter(str(csv_file)) as writer1:
            assert writer1.write_tweet(sample_tweet) is True
            assert writer1.written_count == 1

        # Session 2: Reopen writer, try re-writing same tweet, then a new tweet
        second_tweet = Tweet(
            tweet_id=9999999999999999999,
            text="Second unique tweet",
            username="another_user",
        )

        with CsvTweetWriter(str(csv_file)) as writer2:
            assert sample_tweet.tweet_id in writer2.seen_ids
            assert writer2.write_tweet(sample_tweet) is False  # duplicate
            assert writer2.write_tweet(second_tweet) is True  # new
            assert writer2.written_count == 1
            assert writer2.duplicates_skipped == 1

        with open(csv_file, "r", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 2
        assert rows[0]["tweet_id"] == str(sample_tweet.tweet_id)
        assert rows[1]["tweet_id"] == str(second_tweet.tweet_id)

    def test_automatic_nested_directory_creation(self, tmp_path, sample_tweet):
        nested_csv = tmp_path / "deeply" / "nested" / "folder" / "data.csv"
        with CsvTweetWriter(str(nested_csv)) as writer:
            assert writer.write_tweet(sample_tweet) is True

        assert nested_csv.exists()


class TestConfigValidationStorageModes:
    """Tests for config validation with and without required database."""

    def test_validate_without_database_succeeds(self):
        config = Config(db_password="")
        errors = config.validate(require_db=False)
        assert len(errors) == 0

    def test_validate_with_database_fails_if_password_missing(self):
        config = Config(db_password="")
        errors = config.validate(require_db=True)
        assert any("DB_PASSWORD" in e for e in errors)

    def test_csv_output_path_default(self):
        config = Config()
        assert config.csv_output_path == "data/tweets.csv"
