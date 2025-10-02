"""
Scraper configuration and constants.
"""

import os
from typing import Final

# Base URL for Fundo Ambiental
BASE_URL: Final[str] = "https://www.fundoambiental.pt"

# Target page - Apoios PRR tab
APOIOS_PRR_URL: Final[str] = f"{BASE_URL}/apoios-prr.aspx"

# User Agent
USER_AGENT: Final[str] = os.getenv(
    "SCRAPER_USER_AGENT",
    "Mozilla/5.0 (compatible; PublicIncentivesBot/1.0; +https://github.com/fmdgaspar/Public-Incentives)"
)

# Rate limiting and concurrency
MAX_CONCURRENT_REQUESTS: Final[int] = int(os.getenv("SCRAPER_MAX_CONCURRENT", "4"))
DELAY_BETWEEN_REQUESTS_MS: Final[int] = int(os.getenv("SCRAPER_DELAY_MS", "1000"))
RETRY_ATTEMPTS: Final[int] = int(os.getenv("SCRAPER_RETRY_ATTEMPTS", "3"))

# Timeouts (in seconds)
PAGE_LOAD_TIMEOUT: Final[int] = 30
REQUEST_TIMEOUT: Final[int] = 30

# Storage paths
RAW_DATA_DIR: Final[str] = os.getenv("RAW_DATA_DIR", "./data/raw")
PROCESSED_DATA_DIR: Final[str] = os.getenv("PROCESSED_DATA_DIR", "./data/processed")

# Robots.txt compliance
RESPECT_ROBOTS_TXT: Final[bool] = os.getenv("RESPECT_ROBOTS_TXT", "true").lower() == "true"

