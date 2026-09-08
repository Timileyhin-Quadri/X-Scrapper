FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run scraper collection
CMD ["python", "scripts/scrape_tweets.py"]
