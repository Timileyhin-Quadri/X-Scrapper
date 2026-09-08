"""Data models for X Research Collector."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Tweet:
    """Represents a collected tweet/post."""

    tweet_id: int
    text: str
    author_id: Optional[int] = None
    username: Optional[str] = None
    created_at: Optional[datetime] = None
    retweet_count: int = 0
    reply_count: int = 0
    like_count: int = 0
    quote_count: int = 0
    lang: Optional[str] = None
    conversation_id: Optional[int] = None
    query: Optional[str] = None
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))



@dataclass
class CollectionRun:
    """Tracks metadata for a collection run."""

    run_id: Optional[int] = None
    query: str = ""
    run_type: str = "initial"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    posts_fetched: int = 0
    posts_inserted: int = 0
    duplicates: int = 0
    pages_requested: int = 0
    retry_attempts: int = 0
    status: str = "running"
    error_message: Optional[str] = None
    since_id: Optional[int] = None
    newest_id: Optional[int] = None
