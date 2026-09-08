-- X Research Collector - MySQL Schema
-- ==========================================

-- Tweets table: stores collected post data
CREATE TABLE IF NOT EXISTS tweets (
    tweet_id        BIGINT PRIMARY KEY,
    text            TEXT NOT NULL,
    author_id       BIGINT,
    username        VARCHAR(255),
    created_at      DATETIME,
    retweet_count   INT DEFAULT 0,
    reply_count     INT DEFAULT 0,
    like_count      INT DEFAULT 0,
    quote_count     INT DEFAULT 0,
    lang            VARCHAR(10),
    conversation_id BIGINT,
    query           TEXT,
    collected_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tweets_created_at (created_at),
    INDEX idx_tweets_author_id (author_id),
    INDEX idx_tweets_query (query(255)),
    INDEX idx_tweets_lang (lang)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Collection runs table: tracks each collection session
CREATE TABLE IF NOT EXISTS collection_runs (
    run_id          INT AUTO_INCREMENT PRIMARY KEY,
    query           TEXT NOT NULL,
    run_type        VARCHAR(50) DEFAULT 'initial',  -- 'initial', 'scraper', or 'continuous'
    started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at    DATETIME NULL,
    posts_fetched   INT DEFAULT 0,
    posts_inserted  INT DEFAULT 0,
    duplicates      INT DEFAULT 0,
    pages_requested INT DEFAULT 0,
    retry_attempts  INT DEFAULT 0,
    status          VARCHAR(50) DEFAULT 'running',  -- running, success, failed, interrupted
    error_message   TEXT,
    since_id        BIGINT,
    newest_id       BIGINT,
    INDEX idx_collection_runs_query (query(255)),
    INDEX idx_collection_runs_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==========================================
-- Example Research Queries (MySQL)
-- ==========================================

-- Total posts collected
-- SELECT COUNT(*) AS total_posts FROM tweets;

-- Posts by day
-- SELECT DATE(created_at) AS day, COUNT(*) AS post_count
-- FROM tweets GROUP BY DATE(created_at) ORDER BY day DESC;

-- Posts by language
-- SELECT lang, COUNT(*) AS post_count
-- FROM tweets GROUP BY lang ORDER BY post_count DESC;

-- Top authors by post count
-- SELECT username, author_id, COUNT(*) AS post_count
-- FROM tweets GROUP BY username, author_id ORDER BY post_count DESC LIMIT 20;

-- Engagement statistics
-- SELECT
--     COUNT(*) AS total_posts,
--     SUM(like_count) AS total_likes,
--     SUM(retweet_count) AS total_retweets,
--     SUM(reply_count) AS total_replies,
--     SUM(quote_count) AS total_quotes,
--     ROUND(AVG(like_count), 2) AS avg_likes,
--     ROUND(AVG(retweet_count), 2) AS avg_retweets
-- FROM tweets;

-- Collection run history
-- SELECT run_id, query, run_type, started_at, completed_at,
--        posts_fetched, posts_inserted, duplicates, status
-- FROM collection_runs ORDER BY started_at DESC;
