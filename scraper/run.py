"""
Main entry point for running the scraper.
"""

import asyncio
import json
import sys
from pathlib import Path

import structlog

from scraper.config import PROCESSED_DATA_DIR
from scraper.parsers import IncentiveParser
from scraper.scraper import IncentiveScraper

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


async def run_scraper():
    """Run the complete scraping pipeline."""
    logger.info("scraper_run_started")
    
    try:
        # Step 1: Scrape raw HTML
        scraper = IncentiveScraper()
        raw_incentives = await scraper.scrape_all()
        
        if not raw_incentives:
            logger.warning("no_incentives_scraped")
            return []
        
        logger.info("raw_scraping_completed", count=len(raw_incentives))
        
        # Step 2: Parse into structured data
        parser = IncentiveParser()
        incentives = []
        
        for raw in raw_incentives:
            incentive_data = parser.parse(raw)
            if incentive_data:
                incentives.append(incentive_data)
        
        logger.info("parsing_completed", 
                   total=len(raw_incentives),
                   successful=len(incentives))
        
        # Step 3: Save to JSON (temporary, will move to DB later)
        output_dir = Path(PROCESSED_DATA_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / "incentives.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            data = [inc.model_dump() for inc in incentives]
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info("incentives_saved", 
                   file=str(output_file),
                   count=len(incentives))
        
        return incentives
        
    except Exception as e:
        logger.error("scraper_run_failed", error=str(e), exc_info=True)
        raise


def main():
    """Main entry point."""
    try:
        incentives = asyncio.run(run_scraper())
        
        print(f"\n✅ Scraping completed successfully!")
        print(f"   Total incentives scraped: {len(incentives)}")
        print(f"   Output: {PROCESSED_DATA_DIR}/incentives.json")
        
        sys.exit(0)
        
    except KeyboardInterrupt:
        logger.info("scraper_interrupted")
        sys.exit(1)
        
    except Exception as e:
        logger.error("scraper_failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()

