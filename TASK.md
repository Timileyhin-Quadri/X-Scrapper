# Task: X Hashtag Recent-Post Research Collector

## Objective

Build a production-ready Python data collection service for academic research that collects recent public X posts matching configurable hashtags/search queries and persists the data in PostgreSQL.

Primary research example:

`#PutSouthAfricaFirst`

The collector is for **data collection and persistence only**. Do not perform sentiment analysis, topic modelling, LLM processing, or other NLP analysis in this task.

The system must use the official X API where possible rather than browser automation or unofficial scraping techniques.

---

## Core Requirements

### 1. X API integration

Use the X API Recent Search endpoint.

Requirements:

- Authenticate using an X Bearer Token loaded from environment variables.
- Do not hard-code credentials.
- Make the search query configurable.
- Default query:

```text
#PutSouthAfricaFirst -is:retweet
```

- Support pagination using `next_token`.
- Request up to the endpoint's supported page size.
- Request the fields needed for research and persistence.
- Handle HTTP errors, rate limits, timeouts, and transient failures.
- Implement retry/backoff behavior.
- Do not attempt to bypass X API rate limits.

Recommended fields:

- `id`
- `text`
- `author_id`
- `created_at`
- `public_metrics`
- `lang`
- `conversation_id`

Recommended expansion:

- `author_id`

Recommended user field:

- `username`

---

## 2. PostgreSQL persistence

Use PostgreSQL as the primary datastore.

Create a database schema that includes at least:

### tweets

Fields:

- `tweet_id` — primary key / unique identifier
- `text`
- `author_id`
- `username`
- `created_at`
- `retweet_count`
- `reply_count`
- `like_count`
- `quote_count`
- `lang`
- `conversation_id`
- `query`
- `collected_at`

Add appropriate indexes for:

- `tweet_id`
- `created_at`
- `author_id`
- `query`

Use an idempotent insert strategy such as:

```sql
ON CONFLICT (tweet_id) DO NOTHING
```

The collector must never create duplicate posts when restarted.

---

## 3. Initial historical-within-available-window collection

Create a command that attempts to collect a configurable number of posts.

Example:

```bash
python collect_recent.py --query "#PutSouthAfricaFirst -is:retweet" --target 10000
```

It should:

1. Start a collection run.
2. Search Recent Posts.
3. Persist every valid post immediately or in safe batches.
4. Follow pagination.
5. Deduplicate using `tweet_id`.
6. Continue until:
   - target number of unique posts is reached,
   - no more pages are available,
   - the API's available search window is exhausted,
   - or a non-recoverable error occurs.
7. Record collection statistics.
8. Exit cleanly.

Important: do not assume that 10,000 posts are available. The application must report the actual number collected.

---

## 4. Continuous recent-post collector

Create a second command/service for ongoing collection.

Example:

```bash
python continuous_collector.py --query "#PutSouthAfricaFirst -is:retweet" --interval 300
```

The collector should:

- Poll at a configurable interval.
- Retrieve only new posts where possible.
- Persist posts to PostgreSQL.
- Track the newest successfully persisted `tweet_id`.
- Use `since_id` for subsequent searches where appropriate.
- Recover automatically after temporary failures.
- Avoid creating duplicates.
- Log every collection cycle.

Do not assume a five-minute polling interval is universally sufficient. Make it configurable.

---

## 5. Collection-run tracking

Create a table such as:

### collection_runs

Fields:

- `run_id`
- `query`
- `started_at`
- `completed_at`
- `posts_fetched`
- `posts_inserted`
- `duplicates`
- `status`
- `error_message`

Track:

- start/end time
- API pages requested
- posts returned
- unique posts inserted
- duplicate posts ignored
- failures
- retry attempts

This is important for academic reproducibility.

---

## 6. Query configuration

Do not hard-code the hashtag into application logic.

Support configuration through:

- CLI arguments
- environment variables
- or a configuration file

Examples:

```text
#PutSouthAfricaFirst
```

```text
#PutSouthAfricaFirst -is:retweet
```

Potential future query:

```text
("#PutSouthAfricaFirst" OR "#PutSouthAfricaFirstMovement") -is:retweet
```

Document X search syntax clearly.

---

## 7. Academic research requirements

The application must preserve enough metadata to make the collection process reproducible.

Record:

- exact search query
- collection timestamp
- X post ID
- post creation timestamp
- author ID
- available public engagement metrics
- language
- conversation ID
- username when available
- collector/application version if practical

Do not modify the original post text.

Do not publish personal data unnecessarily.

Do not build functionality intended to evade X access controls, rate limits, authentication, or platform restrictions.

The README must clearly state that the dataset is a research collection and that the researcher is responsible for complying with applicable X developer policies, terms, privacy requirements, institutional ethics requirements, and data-protection requirements.

---

## 8. Data quality

Implement validation for:

- missing tweet IDs
- missing text
- malformed timestamps
- invalid API responses
- duplicate tweet IDs

The application should tolerate partial records when permitted by the API but must not silently corrupt data.

Use UTC timestamps.

---

## 9. Logging

Use Python's standard `logging` module or an equivalent structured logging solution.

Log:

- startup
- query
- collection run ID
- API request attempts
- page counts
- number of posts returned
- number inserted
- duplicate count
- rate-limit events
- retries
- errors
- completion statistics

Never log:

- Bearer tokens
- passwords
- database credentials
- other secrets

---

## 10. Environment configuration

Create `.env.example`:

```env
X_BEARER_TOKEN=

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=x_research
POSTGRES_USER=postgres
POSTGRES_PASSWORD=

DEFAULT_QUERY=#PutSouthAfricaFirst -is:retweet
COLLECTION_INTERVAL_SECONDS=300
```

Use `python-dotenv` or an equivalent configuration approach.

Provide clear setup instructions.

---

## 11. Docker

Provide a `docker-compose.yml` for PostgreSQL and the collector.

The PostgreSQL database should use a persistent volume.

Example architecture:

```text
Docker Compose
│
├── postgres
│   └── persistent volume
│
└── collector
    └── Python application
```

The X Bearer Token must be supplied through environment configuration/secrets and must not be committed to Git.

---

## 12. Project structure

Use a maintainable structure similar to:

```text
x-research-collector/
│
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── x_client.py
│   ├── database.py
│   ├── models.py
│   ├── repository.py
│   ├── collector.py
│   └── logging_config.py
│
├── scripts/
│   ├── collect_recent.py
│   └── continuous_collector.py
│
├── tests/
│   ├── test_x_client.py
│   ├── test_repository.py
│   └── test_collector.py
│
├── sql/
│   └── schema.sql
│
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
└── TASK.md
```

The exact structure can be changed if there is a better architectural reason.

---

## 13. Testing

Write automated tests for:

- query construction
- API response parsing
- pagination
- duplicate handling
- PostgreSQL insertion
- retry behavior
- rate-limit handling
- `since_id` tracking
- malformed API responses
- collection-run statistics

Do not make automated tests depend on live X API calls.

Mock the X API in unit tests.

---

## 14. CLI requirements

Support commands/options such as:

```bash
python scripts/collect_recent.py   --query "#PutSouthAfricaFirst -is:retweet"   --target 10000
```

and:

```bash
python scripts/continuous_collector.py   --query "#PutSouthAfricaFirst -is:retweet"   --interval 300
```

Also provide a health/status option if useful.

---

## 15. CSV backup/export

Provide an optional export command:

```bash
python scripts/export_csv.py --output data/tweets.csv
```

The CSV export should contain the persisted research fields.

Do not use CSV as the primary storage mechanism. PostgreSQL remains the source of truth.

---

## 16. Graceful shutdown and recovery

The collector must:

- handle SIGINT/SIGTERM
- commit safe batches
- close database connections
- save collection state
- resume without duplicating data
- provide a useful final summary

Example:

```text
Collection completed

Query: #PutSouthAfricaFirst -is:retweet
Requested target: 10,000
Posts fetched: 10,000
New posts inserted: 9,842
Duplicates: 158
Pages: 100
Duration: 00:12:41
Status: SUCCESS
```

---

## 17. Important X API limitation

The implementation must explicitly document that Recent Search only provides access to the recent search window available through the endpoint.

Do not claim that the collector can retrieve arbitrary historical posts.

If the requested target cannot be reached because fewer matching posts are available in the accessible search window, the program must report this rather than fabricate or repeat data.

For research requiring older historical periods, document that a different X API access level/endpoint or an appropriately licensed research dataset may be required.

---

## 18. Security

Add a `.gitignore` containing at least:

```text
.env
__pycache__/
*.pyc
.venv/
venv/
data/
*.log
```

Never commit:

- X credentials
- database passwords
- private research credentials
- production `.env` files

---

## 19. Deliverables

Produce all of the following:

1. Complete Python source code.
2. PostgreSQL schema.
3. Initial collection script.
4. Continuous collection script.
5. CSV export script.
6. Unit tests.
7. Dockerfile.
8. Docker Compose configuration.
9. `.env.example`.
10. `requirements.txt`.
11. README with:
   - setup
   - X developer account configuration
   - PostgreSQL setup
   - API authentication
   - initial collection
   - continuous collection
   - CSV export
   - troubleshooting
   - academic/research considerations
12. Example SQL queries for:
   - total posts
   - posts by day
   - posts by language
   - top authors by post count
   - engagement statistics
13. Collection-run monitoring/query examples.

---

## 20. Recommended implementation approach

Prefer:

- Python 3.11+
- `requests` or an official X Python SDK where appropriate
- PostgreSQL
- `psycopg2` or `psycopg`
- `python-dotenv`
- Docker Compose
- pytest

Keep the application simple and reliable.

Do not introduce unnecessary ML, LangChain, Azure OpenAI, vector databases, or frontend components.

This is a **data collection and persistence system**, not an AI analytics system.

---

## 21. Acceptance criteria

The implementation is complete when all of the following are true:

- [ ] A developer can configure an X Bearer Token through `.env`.
- [ ] A developer can configure a hashtag/search query.
- [ ] The collector successfully calls Recent Search.
- [ ] Pagination works correctly.
- [ ] Up to the requested target can be collected when matching posts are available and API access permits it.
- [ ] Posts are persisted in PostgreSQL.
- [ ] Duplicate posts are rejected safely.
- [ ] Collection runs are recorded.
- [ ] The continuous collector can resume after restart.
- [ ] `since_id` is used appropriately for incremental collection.
- [ ] Rate-limit responses are handled without attempting to bypass limits.
- [ ] API failures are logged and retried where appropriate.
- [ ] Secrets are never logged.
- [ ] Unit tests pass without requiring live X API access.
- [ ] Docker Compose starts PostgreSQL successfully.
- [ ] CSV export works.
- [ ] README contains complete setup and usage instructions.
- [ ] The documentation clearly distinguishes Recent Search from full historical search.
- [ ] The system never fabricates, duplicates, or silently alters research data.

---

## Final instruction

Implement the system end-to-end.

Before writing code, inspect the current X API documentation and verify the current Recent Search endpoint, authentication method, pagination behavior, supported search operators, response fields, rate limits, and pricing/access model.

If current X API behavior conflicts with assumptions in this task, follow the current official X documentation and clearly document the difference.

The primary research use case is:

```text
#PutSouthAfricaFirst
```

with an initial target of:

```text
10,000 posts
```

and a possible expanded target of:

```text
20,000 posts
```

The system must be designed so these targets are configuration values, not hard-coded limits.
