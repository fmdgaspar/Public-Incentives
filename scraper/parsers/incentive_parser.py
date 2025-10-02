"""
Parser for extracting structured data from incentive HTML pages.
"""

import re
from datetime import date
from typing import List, Optional

import structlog
from bs4 import BeautifulSoup
from decimal import Decimal

from scraper.config import BASE_URL
from scraper.models import IncentiveData, RawIncentive
from scraper.utils import (
    normalize_url,
    parse_portuguese_date,
    parse_budget,
    extract_text
)

logger = structlog.get_logger()


class IncentiveParser:
    """Parser for incentive HTML pages."""
    
    def __init__(self):
        self.base_url = BASE_URL
    
    def parse(self, raw_incentive: RawIncentive) -> Optional[IncentiveData]:
        """
        Parse raw HTML into structured incentive data.
        
        Args:
            raw_incentive: RawIncentive object with HTML
            
        Returns:
            IncentiveData object or None if parsing fails
        """
        try:
            soup = BeautifulSoup(raw_incentive.raw_html, 'html.parser')
            
            title = self._extract_title(soup)
            if not title:
                logger.warning("title_not_found", incentive_id=raw_incentive.incentive_id)
                return None
            
            description = self._extract_description(soup)
            document_urls = self._extract_document_urls(soup)
            publication_date = self._extract_publication_date(soup)
            start_date = self._extract_start_date(soup)
            end_date = self._extract_end_date(soup)
            total_budget = self._extract_budget(soup)
            
            incentive_data = IncentiveData(
                incentive_id=raw_incentive.incentive_id,
                title=title,
                description=description,
                source_link=raw_incentive.source_link,
                document_urls=document_urls,
                publication_date=publication_date,
                start_date=start_date,
                end_date=end_date,
                total_budget=total_budget
            )
            
            logger.info("incentive_parsed",
                       incentive_id=raw_incentive.incentive_id,
                       title=title[:50] if title else None)
            
            return incentive_data
            
        except Exception as e:
            logger.error("parse_failed",
                        incentive_id=raw_incentive.incentive_id,
                        error=str(e))
            return None
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract title from HTML."""
        # Try common title selectors
        selectors = [
            'h1',
            'h2',
            '.page-title',
            '.title',
            '[class*="titulo"]',
            '[class*="title"]'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                title = extract_text(str(element))
                if title and len(title) > 5:  # Sanity check
                    return title
        
        # Fallback to page title
        title_tag = soup.find('title')
        if title_tag:
            return extract_text(str(title_tag))
        
        return None
    
    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract description/summary from HTML."""
        # Try meta description first
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            return meta_desc['content'].strip()
        
        # Try common content selectors
        selectors = [
            '.description',
            '.summary',
            '.content',
            '[class*="descricao"]',
            '[class*="resumo"]',
            'article',
            '.main-content'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                desc = extract_text(str(element))
                if desc and len(desc) > 20:  # Sanity check
                    return desc
        
        # Fallback: get first substantial paragraph
        for p in soup.find_all('p'):
            text = extract_text(str(p))
            if text and len(text) > 50:
                return text
        
        return None
    
    def _extract_document_urls(self, soup: BeautifulSoup) -> List[str]:
        """Extract document URLs (PDFs, etc.) from HTML."""
        document_urls = []
        
        # Find all links
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            # Check if it's a document (PDF, DOC, DOCX, etc.)
            if re.search(r'\.(pdf|doc|docx|xls|xlsx)$', href, re.IGNORECASE):
                full_url = normalize_url(href, self.base_url)
                if full_url not in document_urls:
                    document_urls.append(full_url)
            
            # Also check for "documento", "edital", "regulamento" keywords
            link_text = extract_text(str(link)).lower()
            if any(keyword in link_text for keyword in ['documento', 'edital', 'regulamento', 'aviso', 'candidatura']):
                full_url = normalize_url(href, self.base_url)
                if full_url not in document_urls:
                    document_urls.append(full_url)
        
        logger.debug("documents_extracted", count=len(document_urls))
        
        return document_urls
    
    def _extract_date_from_text(self, text: str, keywords: List[str]) -> Optional[date]:
        """
        Extract date from text using keywords.
        
        Args:
            text: Text to search
            keywords: Keywords that might precede the date
            
        Returns:
            Parsed date or None
        """
        text_lower = text.lower()
        
        for keyword in keywords:
            # Look for keyword followed by a date pattern
            pattern = f"{keyword}.*?(\\d{{1,2}}[/-]\\d{{1,2}}[/-]\\d{{4}})"
            match = re.search(pattern, text_lower, re.IGNORECASE)
            
            if match:
                date_str = match.group(1)
                parsed_date = parse_portuguese_date(date_str)
                if parsed_date:
                    return date.fromisoformat(parsed_date)
        
        return None
    
    def _extract_publication_date(self, soup: BeautifulSoup) -> Optional[date]:
        """Extract publication date from HTML."""
        # Try meta tags first
        meta_date = soup.find('meta', attrs={'property': 'article:published_time'})
        if meta_date and meta_date.get('content'):
            parsed = parse_portuguese_date(meta_date['content'])
            if parsed:
                return date.fromisoformat(parsed)
        
        # Search in text
        text = soup.get_text()
        keywords = ['publicado', 'publicação', 'data de publicação', 'published']
        
        return self._extract_date_from_text(text, keywords)
    
    def _extract_start_date(self, soup: BeautifulSoup) -> Optional[date]:
        """Extract start date from HTML."""
        text = soup.get_text()
        keywords = [
            'início', 'inicio', 'abertura', 'começo', 'start',
            'data de início', 'data de abertura'
        ]
        
        return self._extract_date_from_text(text, keywords)
    
    def _extract_end_date(self, soup: BeautifulSoup) -> Optional[date]:
        """Extract end date from HTML."""
        text = soup.get_text()
        keywords = [
            'fim', 'término', 'encerramento', 'fecho', 'end',
            'data de fim', 'data de encerramento', 'prazo'
        ]
        
        return self._extract_date_from_text(text, keywords)
    
    def _extract_budget(self, soup: BeautifulSoup) -> Optional[Decimal]:
        """Extract total budget from HTML."""
        text = soup.get_text()
        text_lower = text.lower()
        
        # Keywords that might precede budget info
        keywords = [
            'orçamento', 'dotação', 'valor', 'montante',
            'financiamento', 'budget', 'investimento'
        ]
        
        for keyword in keywords:
            # Look for keyword followed by a monetary value
            pattern = f"{keyword}.*?((?:\\d{{1,3}}\\.)*\\d{{1,3}},\\d{{2}}\\s*€)"
            match = re.search(pattern, text_lower, re.IGNORECASE)
            
            if match:
                budget_str = match.group(1)
                budget = parse_budget(budget_str)
                if budget:
                    return budget
        
        # Try finding any large monetary value (heuristic)
        pattern = r'((?:\d{1,3}\.)*\d{1,3},\d{2}\s*€)'
        matches = re.findall(pattern, text)
        
        budgets = [parse_budget(m) for m in matches]
        budgets = [b for b in budgets if b and b > 10000]  # Filter for substantial amounts
        
        if budgets:
            # Return the largest (likely the total budget)
            return max(budgets)
        
        return None

