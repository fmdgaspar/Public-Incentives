# Scraper Module

Web scraper for collecting public incentives from Fundo Ambiental "Apoios PRR" section.

## Features

- ✅ **Robots.txt compliance** - Respects website crawling rules
- ✅ **Rate limiting** - Configurable delays between requests
- ✅ **Retry logic** - Exponential backoff for failed requests
- ✅ **Concurrent scraping** - Controlled parallelism for efficiency
- ✅ **Raw HTML storage** - Saves original HTML for audit purposes
- ✅ **Structured parsing** - Extracts title, description, dates, budget, documents
- ✅ **Portuguese date/number parsing** - Handles local formats

## Usage

### Run scraper once

```bash
python -m scraper.run
```

### With Docker

```bash
docker-compose up scraper
```

## Configuration

Environment variables (see `scraper/config.py`):

- `SCRAPER_USER_AGENT` - User agent string (default: PublicIncentivesBot/1.0)
- `SCRAPER_MAX_CONCURRENT` - Max concurrent requests (default: 4)
- `SCRAPER_DELAY_MS` - Delay between requests in ms (default: 1000)
- `SCRAPER_RETRY_ATTEMPTS` - Number of retry attempts (default: 3)
- `RAW_DATA_DIR` - Directory for raw HTML (default: ./data/raw)
- `PROCESSED_DATA_DIR` - Directory for parsed data (default: ./data/processed)

## Architecture

```
IncentiveScraper (scraper.py)
    ↓ discover_incentive_urls()
    ↓ scrape_incentive() → RawIncentive
    
IncentiveParser (parsers/incentive_parser.py)
    ↓ parse(RawIncentive) → IncentiveData
    
Output: JSON file with structured incentives
```

## Data Models

### RawIncentive
- `incentive_id`: Unique ID (SHA1 of source URL)
- `source_link`: Original URL
- `raw_html`: Complete HTML content
- `html_hash`: SHA256 of HTML for change detection
- `scraped_at`: Timestamp

### IncentiveData
- `incentive_id`: Unique ID
- `title`: Incentive title
- `description`: Summary/description
- `source_link`: Original URL
- `document_urls`: List of PDF/document links
- `publication_date`: Date published
- `start_date`: Application start date
- `end_date`: Application end date
- `total_budget`: Total budget amount
- `created_at/updated_at`: Timestamps

## Testing

```bash
# Run unit tests
pytest tests/unit/test_utils.py -v

# Run all scraper tests
pytest tests/unit/ -v
```

## Notes

- The scraper uses Playwright for JavaScript-heavy pages
- Falls back to requests+BeautifulSoup for static content
- Implements idempotent scraping (same URL = same ID)
- Stores raw HTML for audit and re-parsing

