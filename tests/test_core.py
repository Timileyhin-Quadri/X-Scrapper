"""Unit tests for core models, config, and repository layers."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from app.config import Config
from app.models import Tweet, CollectionRun
from app.repository import TweetRepository, CollectionRunRepository


class TestConfig:
    """Tests for application configuration."""

    def test_validate_missing_password(self):
        config = Config(db_password="")
        errors = config.validate()
        assert any("DB_PASSWORD" in e for e in errors)

    def test_validate_success(self):
        config = Config(db_password="secret_password")
        errors = config.validate()
        assert len(errors) == 0

    def test_validate_invalid_interval(self):
        config = Config(db_password="secret_password", collection_interval=5)
        errors = config.validate()
        assert any("COLLECTION_INTERVAL_SECONDS" in e for e in errors)

    def test_database_url(self):
        config = Config(
            db_host="localhost",
            db_port=5432,
            db_name="testdb",
            db_user="user",
            db_password="password123",
        )
        assert config.database_url == "postgresql://user:password123@localhost:5432/testdb"

    def test_cdp_port_default(self):
        config = Config()
        assert config.cdp_port == 922


class TestTweetModel:
    """Tests for Tweet data model."""

    def test_tweet_creation(self):
        now = datetime.now(timezone.utc)
        tweet = Tweet(
            tweet_id=123456789,
            text="Research tweet #PutSouthAfricaFirst",
            author_id=987654,
            username="test_author",
            created_at=now,
            retweet_count=10,
            reply_count=5,
            like_count=25,
            quote_count=2,
            lang="en",
            conversation_id=123456789,
            query="#PutSouthAfricaFirst",
        )
        assert tweet.tweet_id == 123456789
        assert tweet.text == "Research tweet #PutSouthAfricaFirst"
        assert tweet.author_id == 987654
        assert tweet.username == "test_author"
        assert tweet.like_count == 25
        assert tweet.collected_at is not None

    def test_tweet_default_values(self):
        tweet = Tweet(
            tweet_id=999,
            text="Simple tweet",
        )
        assert tweet.author_id is None
        assert tweet.username is None
        assert tweet.retweet_count == 0
        assert tweet.reply_count == 0
        assert tweet.like_count == 0
        assert tweet.quote_count == 0
        assert tweet.lang is None
        assert isinstance(tweet.collected_at, datetime)


class TestCollectionRunModel:
    """Tests for CollectionRun data model."""

    def test_collection_run_defaults(self):
        run = CollectionRun(query="#PutSouthAfricaFirst", run_type="scraper")
        assert run.query == "#PutSouthAfricaFirst"
        assert run.run_type == "scraper"
        assert run.status == "running"
        assert run.posts_fetched == 0
        assert run.posts_inserted == 0
        assert run.duplicates == 0
        assert run.pages_requested == 0
        assert run.retry_attempts == 0
        assert run.run_id is None
        assert run.completed_at is None
        assert isinstance(run.started_at, datetime)


class TestRepositories:
    """Tests for repository interactions with mocked database."""

    def test_insert_empty_tweets(self):
        mock_db = MagicMock()
        repo = TweetRepository(mock_db)
        inserted, duplicates = repo.insert_tweets([])
        assert inserted == 0
        assert duplicates == 0
        assert not mock_db.cursor.called

    def test_insert_tweets_batch(self):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_db.cursor.return_value.__enter__.return_value = mock_cursor

        repo = TweetRepository(mock_db)
        tweets = [
            Tweet(tweet_id=1, text="First post"),
            Tweet(tweet_id=2, text="Second post"),
        ]
        inserted, duplicates = repo.insert_tweets(tweets)
        assert inserted == 2
        assert duplicates == 0
        assert mock_cursor.execute.call_count == 2

    def test_start_collection_run(self):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [42]
        mock_db.cursor.return_value.__enter__.return_value = mock_cursor

        repo = CollectionRunRepository(mock_db)
        run_id = repo.start_run("#PutSouthAfricaFirst", "scraper")
        assert run_id == 42
        assert mock_cursor.execute.called


class TestPlaywrightScraperConfig:
    """Tests for PlaywrightScraper initialization and CDP options."""

    def test_default_cdp_port(self):
        from app.playwright_scraper import PlaywrightScraper

        scraper = PlaywrightScraper()
        assert scraper.cdp_port == 922
        assert scraper.headless is False

    def test_custom_cdp_port_and_path(self):
        from app.playwright_scraper import PlaywrightScraper

        scraper = PlaywrightScraper(cdp_port=9222, chrome_path="C:\\dummy\\chrome.exe")
        assert scraper.cdp_port == 9222
        assert scraper.chrome_path == "C:\\dummy\\chrome.exe"

    def test_find_chrome_executable(self):
        from app.playwright_scraper import PlaywrightScraper
        import os

        # Verify it finds the existing system Chrome or Playwright Chromium
        path = PlaywrightScraper.find_chrome_executable()
        assert path is not None
        assert os.path.isfile(path)
        assert path.lower().endswith(".exe")

    def test_session_path_default(self):
        from app.playwright_scraper import PlaywrightScraper

        scraper = PlaywrightScraper()
        assert scraper.session_path.endswith("session.json")

    def test_load_session_from_file(self, tmp_path):
        import asyncio
        import json
        from unittest.mock import AsyncMock, MagicMock
        from app.playwright_scraper import PlaywrightScraper

        session_file = tmp_path / "test_session.json"
        cookie_data = {
            "cookies": [
                {"name": "auth_token", "value": "xyz123", "domain": ".x.com", "path": "/"}
            ]
        }
        session_file.write_text(json.dumps(cookie_data), encoding="utf-8")

        scraper = PlaywrightScraper(session_path=str(session_file))
        scraper.context = MagicMock()
        scraper.context.add_cookies = AsyncMock()

        loaded = asyncio.run(scraper.load_session())
        assert loaded is True
        scraper.context.add_cookies.assert_called_once_with(cookie_data["cookies"])

    def test_load_session_missing_file(self, tmp_path):
        import asyncio
        from app.playwright_scraper import PlaywrightScraper

        missing_file = tmp_path / "non_existent.json"
        scraper = PlaywrightScraper(session_path=str(missing_file))
        loaded = asyncio.run(scraper.load_session())
        assert loaded is False


