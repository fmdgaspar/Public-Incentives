"""
Budget guard module for OpenAI API cost control.
Fetches real-time prices from OpenAI website and enforces per-request budget.

Adapted from original budget_guard.py with improvements:
- Cache prices for 24h
- Fallback to cached prices if fetch fails
- Integration with tiktoken
"""

from __future__ import annotations

import re
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable

import requests

logger = logging.getLogger("budget_guard")


# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

# URLs for price scraping
OPENAI_PRICING_URL = "https://openai.com/api/pricing/"
EMBED_MODEL_CARD_URL = "https://platform.openai.com/docs/models/text-embedding-3-small"
GPT4O_MINI_NEWS_URL = "https://openai.com/index/gpt-4o-mini-advancing-cost-efficient-intelligence/"

# Currency conversion API (free tier: 250 requests/month)
EXCHANGE_RATE_API_URL = "https://api.exchangerate-api.com/v4/latest/USD"
EUR_PER_USD_FALLBACK = 0.93  # Fallback if API fails
CURRENCY = "EUR"

# Fallback prices (updated manually, last: 2024-10-02)
# Source: https://openai.com/api/pricing/
FALLBACK_PRICES = {
    "gpt-4o-mini": {
        "input_usd": 0.150,   # $0.150 per 1M tokens
        "output_usd": 0.600,  # $0.600 per 1M tokens
    },
    "text-embedding-3-small": {
        "embedding_usd": 0.020,  # $0.020 per 1M tokens
    },
}

# Cache settings
PRICE_CACHE_HOURS = 24
EXCHANGE_RATE_CACHE_HOURS = 12  # Update twice a day
# Use local cache directory in project root
CACHE_DIR = Path(__file__).parent.parent.parent.parent / ".cache"


@dataclass
class ModelPrices:
    """Model pricing in EUR per million tokens."""
    
    input_per_million: Optional[float] = None
    output_per_million: Optional[float] = None
    embedding_per_million: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)


def fetch_exchange_rate(timeout: int = 10) -> float:
    """
    Fetch current USD to EUR exchange rate from API.
    
    Args:
        timeout: Request timeout in seconds
        
    Returns:
        EUR per 1 USD (e.g., 0.93 means 1 USD = 0.93 EUR)
        
    Raises:
        RuntimeError: If rate cannot be fetched
    """
    try:
        headers = {'User-Agent': 'PublicIncentivesBot/1.0'}
        r = requests.get(EXCHANGE_RATE_API_URL, timeout=timeout, headers=headers)
        r.raise_for_status()
        data = r.json()
        
        # API returns rates with USD as base
        # We need EUR rate
        eur_rate = data.get("rates", {}).get("EUR")
        
        if not eur_rate:
            raise RuntimeError("EUR rate not found in response")
        
        logger.info(f"Fetched exchange rate: 1 USD = {eur_rate:.4f} EUR")
        return eur_rate
    
    except Exception as e:
        logger.error(f"Failed to fetch exchange rate: {e}")
        raise


def get_exchange_rate_cached(force_refresh: bool = False) -> float:
    """
    Get USD to EUR exchange rate with caching.
    
    Args:
        force_refresh: Force fetch from API, ignoring cache
        
    Returns:
        EUR per 1 USD
    """
    cache_file = CACHE_DIR / "exchange_rate.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Try cache first
    if not force_refresh and cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            cached_at = datetime.fromisoformat(data["cached_at"])
            age = datetime.utcnow() - cached_at
            
            if age.total_seconds() < EXCHANGE_RATE_CACHE_HOURS * 3600:
                rate = data["eur_per_usd"]
                logger.info(
                    f"Using cached exchange rate: 1 USD = {rate:.4f} EUR "
                    f"(age: {age.total_seconds()/3600:.1f}h)"
                )
                return rate
        except Exception as e:
            logger.warning(f"Failed to load exchange rate cache: {e}")
    
    # Fetch fresh rate
    try:
        rate = fetch_exchange_rate()
        
        # Save to cache
        cache_data = {
            "cached_at": datetime.utcnow().isoformat(),
            "eur_per_usd": rate,
        }
        cache_file.write_text(json.dumps(cache_data, indent=2))
        
        return rate
    
    except Exception as e:
        logger.error(f"Exchange rate fetch failed: {e}")
        
        # Try stale cache
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                rate = data["eur_per_usd"]
                logger.warning(f"Using stale cached exchange rate: 1 USD = {rate:.4f} EUR")
                return rate
            except Exception:
                pass
        
        # Final fallback
        logger.warning(f"Using fallback exchange rate: 1 USD = {EUR_PER_USD_FALLBACK:.4f} EUR")
        return EUR_PER_USD_FALLBACK


def _usd_to_eur(amount_usd: float, eur_per_usd: Optional[float] = None) -> float:
    """
    Convert USD to EUR.
    
    Args:
        amount_usd: Amount in USD
        eur_per_usd: Exchange rate (if None, fetches current rate)
        
    Returns:
        Amount in EUR
    """
    if eur_per_usd is None:
        eur_per_usd = get_exchange_rate_cached()
    
    return round(amount_usd * eur_per_usd, 6)


def _get_cache_path(model_name: str) -> Path:
    """Get cache file path for a model."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"prices_{model_name}.json"


def _save_prices_cache(model_name: str, prices: ModelPrices) -> None:
    """Save prices to cache."""
    cache_path = _get_cache_path(model_name)
    data = {
        "cached_at": datetime.utcnow().isoformat(),
        "prices": prices.to_dict(),
    }
    cache_path.write_text(json.dumps(data, indent=2))
    logger.info(f"Cached prices for {model_name}")


def _load_prices_cache(model_name: str, max_age_hours: int = PRICE_CACHE_HOURS) -> Optional[ModelPrices]:
    """Load prices from cache if not expired."""
    cache_path = _get_cache_path(model_name)
    
    if not cache_path.exists():
        return None
    
    try:
        data = json.loads(cache_path.read_text())
        cached_at = datetime.fromisoformat(data["cached_at"])
        age = datetime.utcnow() - cached_at
        
        if age.total_seconds() < max_age_hours * 3600:
            logger.info(f"Using cached prices for {model_name} (age: {age.total_seconds()/3600:.1f}h)")
            return ModelPrices(**data["prices"])
        else:
            logger.info(f"Cache expired for {model_name} (age: {age.total_seconds()/3600:.1f}h)")
            return None
    except Exception as e:
        logger.warning(f"Failed to load cache for {model_name}: {e}")
        return None


def fetch_gpt4o_mini_prices(timeout: int = 20) -> ModelPrices:
    """
    Fetch gpt-4o-mini prices from official OpenAI announcement.
    
    Args:
        timeout: Request timeout in seconds
        
    Returns:
        ModelPrices with input/output prices in EUR
        
    Raises:
        RuntimeError: If prices cannot be extracted
    """
    r = requests.get(GPT4O_MINI_NEWS_URL, timeout=timeout)
    r.raise_for_status()
    html = r.text
    
    # Try to find prices in cents
    cents_in = re.findall(r"(?i)(\d+(?:\.\d+)?)\s*cents?\s+per\s+1M\s+input\s+tokens", html)
    cents_out = re.findall(r"(?i)(\d+(?:\.\d+)?)\s*cents?\s+per\s+1M\s+output\s+tokens", html)
    
    if cents_in and cents_out:
        usd_in = float(cents_in[0]) / 100.0
        usd_out = float(cents_out[0]) / 100.0
    else:
        # Try to find prices in dollars
        dollars_in = re.findall(r"\$\s*(\d+(?:\.\d+)?)\s*/\s*1M\s*input", html, re.I)
        dollars_out = re.findall(r"\$\s*(\d+(?:\.\d+)?)\s*/\s*1M\s*output", html, re.I)
        
        if dollars_in and dollars_out:
            usd_in = float(dollars_in[0])
            usd_out = float(dollars_out[0])
        else:
            raise RuntimeError("Failed to extract gpt-4o-mini prices from webpage")
    
    logger.info(f"Fetched gpt-4o-mini prices: ${usd_in:.4f} input, ${usd_out:.4f} output per 1M tokens")
    
    return ModelPrices(
        input_per_million=_usd_to_eur(usd_in),
        output_per_million=_usd_to_eur(usd_out),
        embedding_per_million=None
    )


def fetch_embedding_small_price(timeout: int = 20) -> ModelPrices:
    """
    Fetch text-embedding-3-small price from OpenAI documentation.
    
    Args:
        timeout: Request timeout in seconds
        
    Returns:
        ModelPrices with embedding price in EUR
        
    Raises:
        RuntimeError: If price cannot be extracted
    """
    # Use realistic User-Agent
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    
    # Try model card first
    r = requests.get(EMBED_MODEL_CARD_URL, timeout=timeout, headers=headers)
    r.raise_for_status()
    html = r.text
    
    m = re.search(r"\$\s*(\d+(?:\.\d+)?)\s*(?:per|/)\s*1M\s*tokens", html, re.I)
    
    if not m:
        # Fallback to pricing page
        r2 = requests.get(OPENAI_PRICING_URL, timeout=timeout, headers=headers)
        r2.raise_for_status()
        html2 = r2.text
        m = re.search(r"text-embedding-3-small.*?\$\s*(\d+(?:\.\d+)?)\s*(?:/|per)\s*1M", html2, re.I | re.S)
        
        if not m:
            raise RuntimeError("Failed to extract text-embedding-3-small price from webpage")
    
    usd = float(m.group(1))
    logger.info(f"Fetched text-embedding-3-small price: ${usd:.4f} per 1M tokens")
    
    return ModelPrices(embedding_per_million=_usd_to_eur(usd))


def get_gpt4o_mini_prices_cached(force_refresh: bool = False) -> ModelPrices:
    """
    Get gpt-4o-mini prices with caching.
    
    Strategy:
    1. Try cache first (if exists and not expired)
    2. Try fetching from web
    3. Try stale cache
    4. Use hardcoded fallback prices
    
    Args:
        force_refresh: Force fetch from web, ignoring cache
        
    Returns:
        ModelPrices with input/output prices
    """
    model_name = "gpt-4o-mini"
    
    # Try cache first
    if not force_refresh:
        cached = _load_prices_cache(model_name)
        if cached and cached.input_per_million and cached.output_per_million:
            return cached
    
    # Try fetching fresh prices from web
    try:
        prices = fetch_gpt4o_mini_prices()
        _save_prices_cache(model_name, prices)
        return prices
    except Exception as e:
        logger.warning(f"Failed to fetch {model_name} prices from web: {e}")
        
        # Try stale cache
        cached = _load_prices_cache(model_name, max_age_hours=24 * 30)  # Accept up to 1 month old
        if cached and cached.input_per_million and cached.output_per_million:
            logger.warning(f"Using stale cache for {model_name}")
            return cached
        
        # Final fallback: use hardcoded prices
        logger.warning(f"Using hardcoded fallback prices for {model_name}")
        exchange_rate = get_exchange_rate_cached()
        prices = ModelPrices(
            input_per_million=_usd_to_eur(FALLBACK_PRICES[model_name]["input_usd"], exchange_rate),
            output_per_million=_usd_to_eur(FALLBACK_PRICES[model_name]["output_usd"], exchange_rate),
        )
        
        # Save to cache for next time
        _save_prices_cache(model_name, prices)
        
        return prices


def get_embedding_prices_cached(force_refresh: bool = False) -> ModelPrices:
    """
    Get text-embedding-3-small prices with caching.
    
    Strategy:
    1. Try cache first
    2. Try fetching from web
    3. Try stale cache
    4. Use hardcoded fallback prices
    
    Args:
        force_refresh: Force fetch from web, ignoring cache
        
    Returns:
        ModelPrices with embedding price
    """
    model_name = "text-embedding-3-small"
    
    # Try cache first
    if not force_refresh:
        cached = _load_prices_cache(model_name)
        if cached and cached.embedding_per_million:
            return cached
    
    # Try fetching fresh prices from web
    try:
        prices = fetch_embedding_small_price()
        _save_prices_cache(model_name, prices)
        return prices
    except Exception as e:
        logger.warning(f"Failed to fetch {model_name} prices from web: {e}")
        
        # Try stale cache
        cached = _load_prices_cache(model_name, max_age_hours=24 * 30)
        if cached and cached.embedding_per_million:
            logger.warning(f"Using stale cache for {model_name}")
            return cached
        
        # Final fallback: use hardcoded prices
        logger.warning(f"Using hardcoded fallback prices for {model_name}")
        exchange_rate = get_exchange_rate_cached()
        prices = ModelPrices(
            embedding_per_million=_usd_to_eur(FALLBACK_PRICES[model_name]["embedding_usd"], exchange_rate)
        )
        
        # Save to cache for next time
        _save_prices_cache(model_name, prices)
        
        return prices


def plan_output_tokens(
    tokens_in: int,
    price_in_per_million: float,
    price_out_per_million: float,
    budget_eur: float = 0.30,
    hard_cap_out: int = 800
) -> tuple[int, bool]:
    """
    Calculate max output tokens that fit within budget.
    
    Args:
        tokens_in: Number of input tokens
        price_in_per_million: Input price per million tokens (EUR)
        price_out_per_million: Output price per million tokens (EUR)
        budget_eur: Maximum budget for this request (EUR)
        hard_cap_out: Hard cap on output tokens
        
    Returns:
        Tuple of (max_output_tokens, fits_in_budget)
    """
    # Calculate input cost
    cost_in = (tokens_in / 1_000_000) * price_in_per_million
    
    # Calculate remaining budget for output
    remain = budget_eur - cost_in
    
    if remain <= 0:
        logger.warning(f"Input alone exceeds budget: €{cost_in:.4f} > €{budget_eur:.4f}")
        return 0, False
    
    # Calculate max output tokens within budget
    tok_out_max = int((remain / price_out_per_million) * 1_000_000)
    
    # Apply hard cap
    tok_out = min(tok_out_max, hard_cap_out)
    
    logger.debug(
        f"Budget plan: {tokens_in} in + {tok_out} out = €{cost_in:.4f} + €{(tok_out/1_000_000)*price_out_per_million:.4f}"
    )
    
    return tok_out, True


def shrink_context(text: str, max_tokens: int, tokenizer: Callable[[str], int]) -> str:
    """
    Shrink text to fit within token limit by keeping start and end.
    
    Strategy: Keep 70% from start, 30% from end (important for context).
    
    Args:
        text: Text to shrink
        max_tokens: Maximum tokens allowed
        tokenizer: Function that counts tokens in text
        
    Returns:
        Shrunken text
    """
    # Clean up whitespace first
    cleaned = re.sub(r"\s+\n", "\n", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    
    current_tokens = tokenizer(cleaned)
    
    if current_tokens <= max_tokens:
        return cleaned
    
    # Calculate how much to keep
    keep_tokens = max_tokens
    head_tokens = int(keep_tokens * 0.7)
    tail_tokens = keep_tokens - head_tokens
    
    # Estimate characters per token (rough)
    char_per_tok = len(cleaned) / current_tokens
    
    head_chars = int(head_tokens * char_per_tok)
    tail_chars = int(tail_tokens * char_per_tok)
    
    # Extract head and tail
    head = cleaned[:head_chars]
    tail = cleaned[-tail_chars:]
    
    result = head + "\n\n[...contexto reduzido...]\n\n" + tail
    
    logger.info(f"Shrank context: {current_tokens} → ~{max_tokens} tokens")
    
    return result


def estimate_cost(
    tokens_in: int,
    tokens_out: int,
    model: str = "gpt-4o-mini"
) -> float:
    """
    Estimate cost of a request in EUR.
    
    Args:
        tokens_in: Input tokens
        tokens_out: Output tokens
        model: Model name
        
    Returns:
        Estimated cost in EUR
    """
    if "embed" in model.lower():
        prices = get_embedding_prices_cached()
        return (tokens_in / 1_000_000) * prices.embedding_per_million
    else:
        prices = get_gpt4o_mini_prices_cached()
        cost_in = (tokens_in / 1_000_000) * prices.input_per_million
        cost_out = (tokens_out / 1_000_000) * prices.output_per_million
        return cost_in + cost_out


def format_cost_info(
    tokens_in: int,
    tokens_out: int,
    cost_eur: float,
    model: str,
    budget_eur: float = 0.30,
    from_cache: bool = False
) -> str:
    """
    Format cost information with colors for terminal display.
    
    Args:
        tokens_in: Input tokens
        tokens_out: Output tokens
        cost_eur: Actual cost in EUR
        model: Model name
        budget_eur: Budget per request
        from_cache: Whether from cache
        
    Returns:
        Formatted string with colors
    """
    if from_cache:
        return (
            f"{Colors.GREEN}💰 CACHE HIT{Colors.RESET} - "
            f"Saved €{cost_eur:.6f} | "
            f"{tokens_in} tokens"
        )
    
    # Calculate percentage of budget used
    pct = (cost_eur / budget_eur) * 100 if budget_eur > 0 else 0
    
    # Choose color based on budget usage
    if pct < 50:
        color = Colors.GREEN
        emoji = "✅"
    elif pct < 80:
        color = Colors.YELLOW
        emoji = "⚠️"
    else:
        color = Colors.RED
        emoji = "🔴"
    
    return (
        f"{color}{emoji} Cost: €{cost_eur:.6f}{Colors.RESET} "
        f"({pct:.1f}% of €{budget_eur} budget) | "
        f"{Colors.CYAN}{tokens_in}{Colors.RESET} in + "
        f"{Colors.CYAN}{tokens_out}{Colors.RESET} out = "
        f"{Colors.BOLD}{tokens_in + tokens_out}{Colors.RESET} total tokens | "
        f"Model: {Colors.BLUE}{model}{Colors.RESET}"
    )

