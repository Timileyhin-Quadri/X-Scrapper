-- X Research Collector - PostgreSQL Schema
-- ==========================================

-- Tweets table: stores collected post data
CREATE TABLE IF NOT EXISTS tweets (
    tweet_id        BIGINT PRIMARY KEY,
    text            TEXT NOT NULL,
    author_id       BIGINT,
    username        VARCHAR(255),
    created_at      TIMESTAMPTZ,
    retweet_count   INTEGER DEFAULT 0,
    reply_count     INTEGER DEFAULT 0,
    like_count      INTEGER DEFAULT 0,
    quote_count     INTEGER DEFAULT 0,
    lang            VARCHAR(10),
    conversation_id BIGINT,
    query           TEXT,
    collected_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets (created_at);
CREATE INDEX IF NOT EXISTS idx_tweets_author_id ON tweets (author_id);
CREATE INDEX IF NOT EXISTS idx_tweets_query ON tweets (query);
CREATE INDEX IF NOT EXISTS idx_tweets_lang ON tweets (lang);

-- Collection runs table: tracks each collection session
CREATE TABLE IF NOT EXISTS collection_runs (
    run_id          SERIAL PRIMARY KEY,
    query           TEXT NOT NULL,
    run_type        VARCHAR(50) DEFAULT 'initial',  -- 'initial' or 'continuous'
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    posts_fetched   INTEGER DEFAULT 0,
    posts_inserted  INTEGER DEFAULT 0,
    duplicates      INTEGER DEFAULT 0,
    pages_requested INTEGER DEFAULT 0,
    retry_attempts  INTEGER DEFAULT 0,
    status          VARCHAR(50) DEFAULT 'running',  -- running, success, failed, interrupted
    error_message   TEXT,
    since_id        BIGINT,
    newest_id       BIGINT
);

CREATE INDEX IF NOT EXISTS idx_collection_runs_query ON collection_runs (query);
CREATE INDEX IF NOT EXISTS idx_collection_runs_status ON collection_runs (status);

-- ==========================================
-- Example Research Queries
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
--     AVG(like_count)::NUMERIC(10,2) AS avg_likes,
--     AVG(retweet_count)::NUMERIC(10,2) AS avg_retweets
-- FROM tweets;

-- Collection run history
-- SELECT run_id, query, run_type, started_at, completed_at,
--        posts_fetched, posts_inserted, duplicates, status
-- FROM collection_runs ORDER BY started_at DESC;
