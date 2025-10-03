"""
PDF extraction utilities for incentive documents.

Downloads and extracts text from PDFs linked in incentive pages.
Also handles HTML pages disguised as PDFs (common with .aspx files).
"""

import re
import hashlib
import io
from pathlib import Path
from typing import List, Optional, Dict
from urllib.parse import urljoin, urlparse

import requests
import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger()

# Try importing PDF libraries
try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    logger.warning("PyPDF2 not installed - PDF extraction will be limited")

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


class PDFExtractor:
    """Extractor for PDF documents."""
    
    def __init__(
        self,
        cache_dir: str = "data/raw/pdfs",
        max_pdf_size_mb: int = 10,
        timeout: int = 30
    ):
        """
        Initialize PDF extractor.
        
        Args:
            cache_dir: Directory to cache downloaded PDFs
            max_pdf_size_mb: Maximum PDF size to download (MB)
            timeout: Request timeout in seconds
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_pdf_size_bytes = max_pdf_size_mb * 1024 * 1024
        self.timeout = timeout
    
    def _get_pdf_cache_path(self, url: str) -> Path:
        """Get cache path for a PDF URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.pdf"
    
    def _get_text_cache_path(self, url: str) -> Path:
        """Get cache path for extracted text."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.txt"
    
    def find_pdf_urls(self, page_url: str) -> List[str]:
        """
        Find PDF URLs on a webpage.
        
        Args:
            page_url: URL of the page to scrape
            
        Returns:
            List of PDF URLs found
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            
            r = requests.get(page_url, timeout=self.timeout, headers=headers)
            r.raise_for_status()
            
            soup = BeautifulSoup(r.text, 'html.parser')
            pdf_urls = []
            
            # Find all links
            for link in soup.find_all('a', href=True):
                href = link['href']
                
                # Check if it's a PDF
                if href.lower().endswith('.pdf') or 'pdf' in href.lower():
                    # Make absolute URL
                    absolute_url = urljoin(page_url, href)
                    if absolute_url not in pdf_urls:
                        pdf_urls.append(absolute_url)
            
            logger.info(
                "pdfs_found",
                page_url=page_url,
                count=len(pdf_urls)
            )
            
            return pdf_urls
        
        except Exception as e:
            logger.error(
                "pdf_search_failed",
                page_url=page_url,
                error=str(e)
            )
            return []
    
    def download_pdf(self, url: str, force: bool = False) -> Optional[Path]:
        """
        Download a PDF file.
        
        Args:
            url: URL of the PDF
            force: Force re-download even if cached
            
        Returns:
            Path to downloaded file or None
        """
        cache_path = self._get_pdf_cache_path(url)
        
        # Check cache
        if cache_path.exists() and not force:
            logger.info("pdf_cache_hit", url=url)
            return cache_path
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            
            # Stream download to check size
            r = requests.get(url, stream=True, timeout=self.timeout, headers=headers)
            r.raise_for_status()
            
            # Check content length
            content_length = int(r.headers.get('content-length', 0))
            if content_length > self.max_pdf_size_bytes:
                logger.warning(
                    "pdf_too_large",
                    url=url,
                    size_mb=content_length / (1024 * 1024)
                )
                return None
            
            # Download
            with open(cache_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(
                "pdf_downloaded",
                url=url,
                size_mb=cache_path.stat().st_size / (1024 * 1024)
            )
            
            return cache_path
        
        except Exception as e:
            logger.error(
                "pdf_download_failed",
                url=url,
                error=str(e)
            )
            return None
    
    def _extract_text_from_html(self, content: bytes) -> Optional[str]:
        """
        Extract text from HTML content (for .aspx files disguised as PDFs).
        
        Args:
            content: HTML content as bytes
            
        Returns:
            Extracted text or None
        """
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            logger.info("html_text_extracted", length=len(text))
            return text
            
        except Exception as e:
            logger.error(f"html_extraction_failed: {e}")
            return None
    
    def extract_text_from_pdf(self, pdf_path: Path) -> Optional[str]:
        """
        Extract text from a PDF file or HTML file disguised as PDF.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Extracted text or None
        """
        # First, check if it's actually HTML
        try:
            with open(pdf_path, 'rb') as f:
                header = f.read(1024)
                # Check if it starts with HTML markers
                if b'<!DOCTYPE' in header or b'<html' in header.lower():
                    logger.info("detected_html_as_pdf", pdf=pdf_path.name)
                    f.seek(0)
                    content = f.read()
                    return self._extract_text_from_html(content)
        except Exception as e:
            logger.warning(f"html_detection_failed: {e}")
        
        # Try pdfplumber first (better quality)
        if HAS_PDFPLUMBER:
            try:
                import pdfplumber
                with pdfplumber.open(pdf_path) as pdf:
                    text = []
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text.append(page_text)
                    
                    result = "\n\n".join(text)
                    logger.info(
                        "pdf_text_extracted_pdfplumber",
                        pdf=pdf_path.name,
                        length=len(result)
                    )
                    return result
            except Exception as e:
                logger.warning(f"pdfplumber extraction failed: {e}")
        
        # Fallback to PyPDF2
        if HAS_PYPDF2:
            try:
                import PyPDF2
                with open(pdf_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = []
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text.append(page_text)
                    
                    result = "\n\n".join(text)
                    logger.info(
                        "pdf_text_extracted_pypdf2",
                        pdf=pdf_path.name,
                        length=len(result)
                    )
                    return result
            except Exception as e:
                logger.error(f"PyPDF2 extraction failed: {e}")
        
        logger.error("no_pdf_library_available")
        return None
    
    def get_pdf_text(self, url: str, use_cache: bool = True) -> Optional[str]:
        """
        Get text from a PDF URL (download + extract).
        
        Args:
            url: URL of the PDF
            use_cache: Use cached text if available
            
        Returns:
            Extracted text or None
        """
        text_cache_path = self._get_text_cache_path(url)
        
        # Check text cache
        if use_cache and text_cache_path.exists():
            logger.info("pdf_text_cache_hit", url=url)
            return text_cache_path.read_text(encoding='utf-8')
        
        # Download PDF
        pdf_path = self.download_pdf(url)
        if not pdf_path:
            return None
        
        # Extract text
        text = self.extract_text_from_pdf(pdf_path)
        
        # Cache extracted text
        if text:
            text_cache_path.write_text(text, encoding='utf-8')
            logger.info("pdf_text_cached", url=url)
        
        return text
    
    def get_all_pdfs_text_from_pages(
        self,
        page_urls: List[str],
        max_pdfs_per_page: int = 3
    ) -> Dict[str, str]:
        """
        Get text from all PDFs found on multiple pages.
        
        Args:
            page_urls: List of page URLs to scrape
            max_pdfs_per_page: Maximum PDFs to process per page
            
        Returns:
            Dict mapping PDF URL to extracted text
        """
        all_texts = {}
        
        for page_url in page_urls:
            # Find PDFs on page
            pdf_urls = self.find_pdf_urls(page_url)
            
            # Limit per page
            pdf_urls = pdf_urls[:max_pdfs_per_page]
            
            # Extract text from each
            for pdf_url in pdf_urls:
                text = self.get_pdf_text(pdf_url)
                if text:
                    all_texts[pdf_url] = text
        
        logger.info(
            "all_pdfs_processed",
            total_pages=len(page_urls),
            total_pdfs=len(all_texts)
        )
        
        return all_texts

