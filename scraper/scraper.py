"""
Main scraper implementation for Fundo Ambiental incentives.
"""

import asyncio
import hashlib
import time
from pathlib import Path
from typing import List, Optional
from urllib.robotparser import RobotFileParser

import structlog
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from scraper.config import (
    BASE_URL,
    APOIOS_PRR_URL,
    USER_AGENT,
    MAX_CONCURRENT_REQUESTS,
    DELAY_BETWEEN_REQUESTS_MS,
    RETRY_ATTEMPTS,
    PAGE_LOAD_TIMEOUT,
    RAW_DATA_DIR,
    RESPECT_ROBOTS_TXT
)
from scraper.models import RawIncentive
from scraper.utils import generate_incentive_id, normalize_url

logger = structlog.get_logger()


class IncentiveScraper:
    """Scraper for Fundo Ambiental public incentives."""
    
    def __init__(self):
        self.base_url = BASE_URL
        self.target_url = APOIOS_PRR_URL
        self.user_agent = USER_AGENT
        self.max_concurrent = MAX_CONCURRENT_REQUESTS
        self.delay_ms = DELAY_BETWEEN_REQUESTS_MS
        self.raw_data_dir = Path(RAW_DATA_DIR)
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        
        # Robots.txt parser
        self.robot_parser: Optional[RobotFileParser] = None
        if RESPECT_ROBOTS_TXT:
            self._init_robots_parser()
    
    def _init_robots_parser(self):
        """Initialize robots.txt parser."""
        try:
            self.robot_parser = RobotFileParser()
            self.robot_parser.set_url(f"{self.base_url}/robots.txt")
            self.robot_parser.read()
            logger.info("robots_txt_loaded", url=f"{self.base_url}/robots.txt")
        except Exception as e:
            logger.warning("robots_txt_failed", error=str(e))
            self.robot_parser = None
    
    def can_fetch(self, url: str) -> bool:
        """
        Check if we can fetch a URL according to robots.txt.
        
        Args:
            url: URL to check
            
        Returns:
            True if allowed, False otherwise
        """
        if not self.robot_parser:
            return True
        
        return self.robot_parser.can_fetch(self.user_agent, url)
    
    @retry(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def fetch_page(self, page: Page, url: str) -> str:
        """
        Fetch a page with retry logic.
        
        Args:
            page: Playwright page object
            url: URL to fetch
            
        Returns:
            HTML content
        """
        if not self.can_fetch(url):
            logger.warning("robots_txt_disallow", url=url)
            raise ValueError(f"Robots.txt disallows fetching {url}")
        
        logger.info("fetching_page", url=url)
        
        await page.goto(url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT * 1000)
        
        # Wait for content to load
        await page.wait_for_timeout(1000)
        
        html = await page.content()
        
        logger.info("page_fetched", url=url, html_size=len(html))
        
        # Respect rate limiting
        await asyncio.sleep(self.delay_ms / 1000)
        
        return html
    
    def save_raw_html(self, incentive_id: str, html: str, url: str) -> Path:
        """
        Save raw HTML for audit purposes.
        
        Args:
            incentive_id: Unique incentive ID
            html: Raw HTML content
            url: Source URL
            
        Returns:
            Path to saved file
        """
        timestamp = int(time.time())
        filename = f"{incentive_id}_{timestamp}.html"
        filepath = self.raw_data_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"<!-- Source: {url} -->\n")
            f.write(f"<!-- Scraped at: {timestamp} -->\n")
            f.write(html)
        
        logger.info("raw_html_saved", filepath=str(filepath), size=len(html))
        
        return filepath
    
    async def discover_incentive_urls(self, browser: Browser) -> List[str]:
        """
        Discover all incentive URLs from the main page.
        
        Args:
            browser: Playwright browser instance
            
        Returns:
            List of incentive URLs
        """
        page = await browser.new_page()
        
        try:
            html = await self.fetch_page(page, self.target_url)
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find all incentive links
            # This will need to be adjusted based on the actual page structure
            incentive_links = []
            
            # Look for links in the main content area
            # Adjust selectors based on actual page structure
            for link in soup.find_all('a', href=True):
                href = link['href']
                
                # Filter for incentive detail pages
                # This is a heuristic - adjust based on actual URL patterns
                if any(keyword in href.lower() for keyword in ['apoio', 'incentivo', 'financiamento', 'candidatura']):
                    full_url = normalize_url(href, self.base_url)
                    if full_url not in incentive_links:
                        incentive_links.append(full_url)
            
            logger.info("incentive_urls_discovered", count=len(incentive_links))
            
            return incentive_links
            
        finally:
            await page.close()
    
    async def scrape_incentive(self, browser: Browser, url: str) -> RawIncentive:
        """
        Scrape a single incentive page.
        
        Args:
            browser: Playwright browser instance
            url: Incentive page URL
            
        Returns:
            RawIncentive object
        """
        page = await browser.new_page()
        
        try:
            html = await self.fetch_page(page, url)
            
            incentive_id = generate_incentive_id(url)
            html_hash = hashlib.sha256(html.encode('utf-8')).hexdigest()
            
            # Save raw HTML
            self.save_raw_html(incentive_id, html, url)
            
            raw_incentive = RawIncentive(
                incentive_id=incentive_id,
                source_link=url,
                raw_html=html,
                html_hash=html_hash
            )
            
            logger.info("incentive_scraped", incentive_id=incentive_id, url=url)
            
            return raw_incentive
            
        finally:
            await page.close()
    
    async def scrape_all(self) -> List[RawIncentive]:
        """
        Scrape all incentives from the target page.
        
        Returns:
            List of RawIncentive objects
        """
        logger.info("scraping_started", target_url=self.target_url)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            try:
                # Set default context with user agent
                context = await browser.new_context(user_agent=self.user_agent)
                await context.close()
                
                # Discover all incentive URLs
                incentive_urls = await self.discover_incentive_urls(browser)
                
                if not incentive_urls:
                    logger.warning("no_incentives_found")
                    return []
                
                # Scrape incentives with concurrency control
                raw_incentives = []
                semaphore = asyncio.Semaphore(self.max_concurrent)
                
                async def scrape_with_semaphore(url: str):
                    async with semaphore:
                        try:
                            return await self.scrape_incentive(browser, url)
                        except Exception as e:
                            logger.error("scrape_failed", url=url, error=str(e))
                            return None
                
                tasks = [scrape_with_semaphore(url) for url in incentive_urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Filter out None and exceptions
                raw_incentives = [r for r in results if isinstance(r, RawIncentive)]
                
                logger.info("scraping_completed", 
                           total_urls=len(incentive_urls),
                           successful=len(raw_incentives))
                
                return raw_incentives
                
            finally:
                await browser.close()


async def main():
    """Main entry point for scraper."""
    scraper = IncentiveScraper()
    raw_incentives = await scraper.scrape_all()
    
    logger.info("scraping_summary", total_scraped=len(raw_incentives))
    
    return raw_incentives


if __name__ == "__main__":
    asyncio.run(main())

