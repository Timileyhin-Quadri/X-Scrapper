"""Configuration management for X Research Collector."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    # PostgreSQL
    db_host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    db_port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    db_name: str = field(default_factory=lambda: os.getenv("DB_NAME", "x_research"))
    db_user: str = field(default_factory=lambda: os.getenv("DB_USER", "postgres"))
    db_password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))

    # Collection defaults
    default_query: str = field(
        default_factory=lambda: os.getenv("DEFAULT_QUERY", "#PutSouthAfricaFirst -is:retweet")
    )
    collection_interval: int = field(
        default_factory=lambda: int(os.getenv("COLLECTION_INTERVAL_SECONDS", "300"))
    )
    csv_output_path: str = field(
        default_factory=lambda: os.getenv("CSV_OUTPUT_PATH", "data/tweets.csv")
    )

    # Playwright / Google Chromium CDP Configuration
    cdp_port: int = field(
        default_factory=lambda: int(os.getenv("CDP_PORT", "922"))
    )
    chrome_path: str = field(
        default_factory=lambda: os.getenv("CHROME_PATH", "")
    )
    session_path: str = field(
        default_factory=lambda: os.getenv("SESSION_PATH", "session.json")
    )

    @property
    def database_url(self) -> str:
        """Build PostgreSQL connection string."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    def validate(self, require_db: bool = True) -> list[str]:
        """Validate configuration. Returns list of errors."""
        errors = []
        if require_db and not self.db_password:
            errors.append("DB_PASSWORD is not set")
        if self.collection_interval < 10:
            errors.append("COLLECTION_INTERVAL_SECONDS must be >= 10")
        return errors


def get_config() -> Config:
    """Get validated configuration."""
    return Config()
