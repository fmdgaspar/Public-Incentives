"""
Utility functions for scraping and data processing.
"""

import hashlib
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import urljoin, urlparse

import structlog

logger = structlog.get_logger()


def generate_incentive_id(source_url: str) -> str:
    """
    Generate a stable, unique ID for an incentive based on its source URL.
    
    Args:
        source_url: The source URL of the incentive
        
    Returns:
        SHA1 hash of the URL as hex string
    """
    return hashlib.sha1(source_url.encode('utf-8')).hexdigest()


def normalize_url(url: str, base_url: str) -> str:
    """
    Convert relative URLs to absolute URLs.
    
    Args:
        url: The URL to normalize (may be relative or absolute)
        base_url: The base URL to use for relative URLs
        
    Returns:
        Absolute URL
    """
    return urljoin(base_url, url)


def is_valid_url(url: str) -> bool:
    """
    Check if a URL is valid.
    
    Args:
        url: The URL to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def parse_portuguese_date(date_str: str) -> Optional[str]:
    """
    Parse Portuguese date formats and convert to YYYY-MM-DD.
    
    Handles formats like:
    - dd/mm/yyyy
    - dd-mm-yyyy
    - dd de mês de yyyy
    
    Args:
        date_str: Date string in Portuguese format
        
    Returns:
        ISO format date string (YYYY-MM-DD) or None if parsing fails
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Try dd/mm/yyyy or dd-mm-yyyy
    patterns = [
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # dd/mm/yyyy or dd-mm-yyyy
        r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # yyyy/mm/dd or yyyy-mm-dd
    ]
    
    for pattern in patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                if pattern.startswith(r'(\d{4})'):  # yyyy-mm-dd format
                    year, month, day = match.groups()
                else:  # dd-mm-yyyy format
                    day, month, year = match.groups()
                
                dt = datetime(int(year), int(month), int(day))
                return dt.strftime('%Y-%m-%d')
            except (ValueError, TypeError) as e:
                logger.warning("date_parse_failed", date_str=date_str, error=str(e))
                continue
    
    # Try textual month format: dd de mês de yyyy
    month_names = {
        'janeiro': 1, 'fevereiro': 2, 'março': 3, 'abril': 4,
        'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8,
        'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12
    }
    
    for month_name, month_num in month_names.items():
        if month_name in date_str.lower():
            match = re.search(r'(\d{1,2})\s+de\s+' + month_name + r'\s+de\s+(\d{4})', date_str.lower())
            if match:
                try:
                    day, year = match.groups()
                    dt = datetime(int(year), month_num, int(day))
                    return dt.strftime('%Y-%m-%d')
                except (ValueError, TypeError) as e:
                    logger.warning("date_parse_failed", date_str=date_str, error=str(e))
                    continue
    
    logger.warning("date_parse_failed_no_match", date_str=date_str)
    return None


def parse_budget(budget_str: str) -> Optional[Decimal]:
    """
    Parse budget strings with Portuguese number formatting.
    
    Handles formats like:
    - 1.000.000,00 €
    - 1 000 000,00 EUR
    - €1.000.000
    
    Args:
        budget_str: Budget string
        
    Returns:
        Decimal value or None if parsing fails
    """
    if not budget_str:
        return None
    
    # Remove currency symbols and text
    budget_str = re.sub(r'[€EUR\s]', '', budget_str, flags=re.IGNORECASE)
    
    # Portuguese format: 1.000.000,00 -> 1000000.00
    # Replace . (thousand separator) with nothing
    # Replace , (decimal separator) with .
    budget_str = budget_str.replace('.', '').replace(',', '.')
    
    try:
        return Decimal(budget_str)
    except (InvalidOperation, ValueError) as e:
        logger.warning("budget_parse_failed", budget_str=budget_str, error=str(e))
        return None


def sanitize_html(html: str) -> str:
    """
    Basic HTML sanitization - remove scripts and dangerous tags.
    
    Args:
        html: Raw HTML string
        
    Returns:
        Sanitized HTML
    """
    # Remove script tags
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove style tags
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    
    return html


def extract_text(html: str) -> str:
    """
    Extract clean text from HTML.
    
    Args:
        html: HTML string
        
    Returns:
        Plain text
    """
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

