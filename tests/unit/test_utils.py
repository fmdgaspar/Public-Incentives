"""
Unit tests for scraper utility functions.
"""

import pytest
from decimal import Decimal
from scraper.utils import (
    generate_incentive_id,
    normalize_url,
    is_valid_url,
    parse_portuguese_date,
    parse_budget,
    extract_text
)


class TestGenerateIncentiveId:
    """Tests for generate_incentive_id function."""
    
    def test_generates_consistent_id(self):
        """Should generate same ID for same URL."""
        url = "https://example.com/incentive/123"
        id1 = generate_incentive_id(url)
        id2 = generate_incentive_id(url)
        assert id1 == id2
    
    def test_generates_different_ids_for_different_urls(self):
        """Should generate different IDs for different URLs."""
        url1 = "https://example.com/incentive/123"
        url2 = "https://example.com/incentive/456"
        id1 = generate_incentive_id(url1)
        id2 = generate_incentive_id(url2)
        assert id1 != id2
    
    def test_returns_hex_string(self):
        """Should return hexadecimal string."""
        url = "https://example.com/incentive/123"
        id = generate_incentive_id(url)
        assert len(id) == 40  # SHA1 produces 40 hex characters
        assert all(c in '0123456789abcdef' for c in id)


class TestNormalizeUrl:
    """Tests for normalize_url function."""
    
    def test_absolute_url_unchanged(self):
        """Absolute URLs should remain unchanged."""
        url = "https://example.com/page"
        base = "https://example.com"
        result = normalize_url(url, base)
        assert result == url
    
    def test_relative_url_converted(self):
        """Relative URLs should be converted to absolute."""
        url = "/page"
        base = "https://example.com"
        result = normalize_url(url, base)
        assert result == "https://example.com/page"
    
    def test_relative_path_converted(self):
        """Relative paths should be converted."""
        url = "documents/file.pdf"
        base = "https://example.com/incentives/"
        result = normalize_url(url, base)
        assert result == "https://example.com/incentives/documents/file.pdf"


class TestIsValidUrl:
    """Tests for is_valid_url function."""
    
    def test_valid_http_url(self):
        """HTTP URLs should be valid."""
        assert is_valid_url("http://example.com") is True
    
    def test_valid_https_url(self):
        """HTTPS URLs should be valid."""
        assert is_valid_url("https://example.com") is True
    
    def test_invalid_no_scheme(self):
        """URLs without scheme should be invalid."""
        assert is_valid_url("example.com") is False
    
    def test_invalid_empty(self):
        """Empty string should be invalid."""
        assert is_valid_url("") is False


class TestParsePortugueseDate:
    """Tests for parse_portuguese_date function."""
    
    def test_slash_format(self):
        """Should parse dd/mm/yyyy format."""
        result = parse_portuguese_date("25/12/2023")
        assert result == "2023-12-25"
    
    def test_dash_format(self):
        """Should parse dd-mm-yyyy format."""
        result = parse_portuguese_date("25-12-2023")
        assert result == "2023-12-25"
    
    def test_single_digit_day_month(self):
        """Should parse single digit day and month."""
        result = parse_portuguese_date("5/3/2023")
        assert result == "2023-03-05"
    
    def test_textual_month(self):
        """Should parse textual month format."""
        result = parse_portuguese_date("25 de dezembro de 2023")
        assert result == "2023-12-25"
    
    def test_invalid_date(self):
        """Should return None for invalid dates."""
        result = parse_portuguese_date("invalid date")
        assert result is None
    
    def test_empty_string(self):
        """Should return None for empty string."""
        result = parse_portuguese_date("")
        assert result is None


class TestParseBudget:
    """Tests for parse_budget function."""
    
    def test_portuguese_format_with_euro(self):
        """Should parse Portuguese format with € symbol."""
        result = parse_budget("1.000.000,00 €")
        assert result == Decimal("1000000.00")
    
    def test_portuguese_format_with_eur(self):
        """Should parse Portuguese format with EUR."""
        result = parse_budget("1.000.000,00 EUR")
        assert result == Decimal("1000000.00")
    
    def test_small_amount(self):
        """Should parse small amounts."""
        result = parse_budget("500,50 €")
        assert result == Decimal("500.50")
    
    def test_no_decimal_places(self):
        """Should handle amounts without decimal places."""
        result = parse_budget("€1.000.000")
        # This might fail depending on implementation - adjust as needed
        assert result == Decimal("1000000")
    
    def test_invalid_budget(self):
        """Should return None for invalid budget strings."""
        result = parse_budget("not a budget")
        assert result is None
    
    def test_empty_string(self):
        """Should return None for empty string."""
        result = parse_budget("")
        assert result is None


class TestExtractText:
    """Tests for extract_text function."""
    
    def test_removes_html_tags(self):
        """Should remove HTML tags."""
        html = "<p>Hello <strong>world</strong></p>"
        result = extract_text(html)
        assert result == "Hello world"
    
    def test_normalizes_whitespace(self):
        """Should normalize whitespace."""
        html = "<p>Hello    \n\n  world</p>"
        result = extract_text(html)
        assert result == "Hello world"
    
    def test_handles_nested_tags(self):
        """Should handle nested tags."""
        html = "<div><p>Hello</p><p>world</p></div>"
        result = extract_text(html)
        assert "Hello" in result and "world" in result
    
    def test_empty_html(self):
        """Should handle empty HTML."""
        result = extract_text("")
        assert result == ""

