"""
Managed OpenAI client with cost control and caching.

Combines budget_guard.py (per-request budget, dynamic pricing, context shrinking)
with response caching for maximum efficiency.
"""

import json
import os
from typing import List, Dict, Any, Optional

import structlog
import tiktoken
from openai import OpenAI

from backend.app.services.budget_guard import (
    get_gpt4o_mini_prices_cached,
    get_embedding_prices_cached,
    plan_output_tokens,
    shrink_context,
    estimate_cost,
    format_cost_info,
)
from backend.app.services.openai_cache import OpenAICache
from backend.app.services.price_tracker import RealTimeCostTracker

logger = structlog.get_logger()


def print_cost(msg: str):
    """Print cost info to stdout (in addition to structured logging)."""
    print(f"  {msg}")


class BudgetExceededError(Exception):
    """Raised when a request would exceed the per-request budget."""
    pass


class ManagedOpenAIClient:
    """
    OpenAI client with intelligent cost management.
    
    Features:
    - Response caching (60-80% cost savings)
    - Per-request budget enforcement (€0.30 default)
    - Dynamic pricing from OpenAI website
    - Automatic context shrinking if needed
    - Precise token counting with tiktoken
    - Cost tracking and metrics
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        max_per_request_eur: float = 0.30,
        cache_db: str = ".cache/openai_cache.db"
    ):
        """
        Initialize managed OpenAI client.
        
        Args:
            api_key: OpenAI API key (or from OPENAI_API_KEY env var)
            max_per_request_eur: Maximum EUR per request
            cache_db: Path to SQLite cache database
        """
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.max_per_request_eur = max_per_request_eur
        self.cache = OpenAICache(cache_db)
        self.cost_tracker = RealTimeCostTracker()  # Track real costs
        
        # Initialize tokenizer for gpt-4o-mini
        try:
            self.tokenizer = tiktoken.encoding_for_model("gpt-4o-mini")
        except Exception:
            # Fallback to cl100k_base (GPT-4 encoding)
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        logger.info(
            "openai_client_initialized",
            max_per_request_eur=max_per_request_eur,
            cache_db=cache_db
        )
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        return len(self.tokenizer.encode(text))
    
    def _messages_to_text(self, messages: List[Dict[str, str]]) -> str:
        """Convert messages list to single text for token counting."""
        return "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create chat completion with cost control and caching.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (default: gpt-4o-mini)
            temperature: Sampling temperature
            max_tokens: Max output tokens (if None, calculated from budget)
            response_format: Response format spec (e.g., {"type": "json_object"})
            **kwargs: Additional OpenAI API parameters
            
        Returns:
            Dict with:
                - response: Response text
                - response_json: Parsed JSON (if applicable)
                - usage: Token usage dict
                - cost_eur: Cost in EUR
                - from_cache: Whether from cache
                
        Raises:
            BudgetExceededError: If request would exceed per-request budget
        """
        # Create cache key
        params = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format,
            **kwargs
        }
        prompt_text = self._messages_to_text(messages)
        
        # Check cache first
        cached = self.cache.get_llm_response(prompt_text, model, params)
        if cached:
            # Track as cache hit
            self.cache.track_cost(
                model=model,
                operation="chat_completion",
                input_tokens=cached["usage"]["prompt_tokens"],
                output_tokens=cached["usage"]["completion_tokens"],
                cost_eur=0.0,
                from_cache=True
            )
            
            # Print cache hit info
            cost_msg = format_cost_info(
                tokens_in=cached["usage"]["prompt_tokens"],
                tokens_out=cached["usage"]["completion_tokens"],
                cost_eur=cached.get("original_cost_eur", 0.0),
                model=model,
                budget_eur=self.max_per_request_eur,
                from_cache=True
            )
            print_cost(cost_msg)
            
            return cached
        
        # Not in cache - prepare request
        logger.info("cache_miss", model=model)
        
        # Get current prices
        prices = get_gpt4o_mini_prices_cached()
        
        # Count input tokens
        tokens_in = self._count_tokens(prompt_text)
        
        # Determine max_tokens within budget
        if max_tokens is None:
            # Calculate from budget
            max_tokens_budget, fits = plan_output_tokens(
                tokens_in=tokens_in,
                price_in_per_million=prices.input_per_million,
                price_out_per_million=prices.output_per_million,
                budget_eur=self.max_per_request_eur,
                hard_cap_out=800
            )
            
            if not fits or max_tokens_budget == 0:
                # Try shrinking context (last user message typically contains context)
                logger.warning(
                    "context_too_large_shrinking",
                    original_tokens=tokens_in,
                    budget_eur=self.max_per_request_eur
                )
                
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i]["role"] == "user":
                        # Shrink this message
                        original_content = messages[i]["content"]
                        messages[i]["content"] = shrink_context(
                            original_content,
                            max_tokens=1000,  # Target size
                            tokenizer=self._count_tokens
                        )
                        
                        # Recalculate
                        prompt_text = self._messages_to_text(messages)
                        tokens_in = self._count_tokens(prompt_text)
                        max_tokens_budget, fits = plan_output_tokens(
                            tokens_in=tokens_in,
                            price_in_per_million=prices.input_per_million,
                            price_out_per_million=prices.output_per_million,
                            budget_eur=self.max_per_request_eur,
                            hard_cap_out=800
                        )
                        
                        if fits and max_tokens_budget > 0:
                            logger.info(
                                "context_shrank_success",
                                new_tokens=tokens_in,
                                max_tokens=max_tokens_budget
                            )
                            break
                else:
                    # Still doesn't fit
                    raise BudgetExceededError(
                        f"Request exceeds budget even after context shrinking. "
                        f"Input tokens: {tokens_in}, Budget: €{self.max_per_request_eur}"
                    )
            
            max_tokens = max_tokens_budget
        else:
            # User specified max_tokens - check if it fits budget
            estimated_cost = estimate_cost(tokens_in, max_tokens, model)
            if estimated_cost > self.max_per_request_eur:
                raise BudgetExceededError(
                    f"Request would cost €{estimated_cost:.4f} > budget €{self.max_per_request_eur}"
                )
        
        # Make API request
        logger.info(
            "openai_request",
            model=model,
            tokens_in=tokens_in,
            max_tokens=max_tokens,
            estimated_cost_eur=estimate_cost(tokens_in, max_tokens, model)
        )
        
        api_kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        
        if response_format:
            api_kwargs["response_format"] = response_format
        
        response = self.client.chat.completions.create(**api_kwargs)
        
        # Extract response
        response_text = response.choices[0].message.content
        
        # Try to parse as JSON if requested
        response_json = None
        if response_format and response_format.get("type") == "json_object":
            try:
                response_json = json.loads(response_text)
            except json.JSONDecodeError:
                logger.warning("failed_to_parse_json_response")
        
        # Calculate actual cost
        usage = response.usage
        actual_cost = estimate_cost(usage.prompt_tokens, usage.completion_tokens, model)
        
        # Save to cache
        self.cache.save_llm_response(
            prompt=prompt_text,
            model=model,
            params=params,
            response=response_text,
            response_json=response_json,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_eur=actual_cost
        )
        
        # Track cost (both in cache DB and real-time tracker)
        self.cache.track_cost(
            model=model,
            operation="chat_completion",
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_eur=actual_cost,
            from_cache=False
        )
        
        self.cost_tracker.record_request(
            model=model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_eur=actual_cost,
            from_cache=False
        )
        
        logger.info(
            "openai_response",
            model=model,
            tokens_in=usage.prompt_tokens,
            tokens_out=usage.completion_tokens,
            cost_eur=actual_cost
        )
        
        # Print cost info with colors
        cost_msg = format_cost_info(
            tokens_in=usage.prompt_tokens,
            tokens_out=usage.completion_tokens,
            cost_eur=actual_cost,
            model=model,
            budget_eur=self.max_per_request_eur,
            from_cache=False
        )
        print_cost(cost_msg)
        
        return {
            "response": response_text,
            "response_json": response_json,
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
            "cost_eur": actual_cost,
            "from_cache": False,
        }
    
    def create_embedding(
        self,
        text: str,
        model: str = "text-embedding-3-small"
    ) -> Dict[str, Any]:
        """
        Create embedding with caching.
        
        Args:
            text: Text to embed
            model: Embedding model name
            
        Returns:
            Dict with:
                - embedding: Embedding vector (list of floats)
                - dimension: Vector dimension
                - tokens: Token count
                - cost_eur: Cost in EUR
                - from_cache: Whether from cache
        """
        # Check cache
        cached = self.cache.get_embedding(text, model)
        if cached:
            # Track as cache hit
            self.cache.track_cost(
                model=model,
                operation="embedding",
                input_tokens=cached["tokens"],
                output_tokens=0,
                cost_eur=0.0,
                from_cache=True
            )
            
            # Print cache hit info
            cost_msg = format_cost_info(
                tokens_in=cached["tokens"],
                tokens_out=0,
                cost_eur=cached.get("original_cost_eur", 0.0),
                model=model,
                budget_eur=self.max_per_request_eur,
                from_cache=True
            )
            print_cost(cost_msg)
            
            return cached
        
        # Not in cache - make request
        logger.info("embedding_cache_miss", model=model, text_length=len(text))
        
        # Get prices for cost estimation
        prices = get_embedding_prices_cached()
        tokens = self._count_tokens(text)
        estimated_cost = (tokens / 1_000_000) * prices.embedding_per_million
        
        # Check budget
        if estimated_cost > self.max_per_request_eur:
            raise BudgetExceededError(
                f"Embedding would cost €{estimated_cost:.4f} > budget €{self.max_per_request_eur}"
            )
        
        # Make request
        response = self.client.embeddings.create(
            model=model,
            input=text
        )
        
        # Extract embedding
        embedding = response.data[0].embedding
        actual_tokens = response.usage.total_tokens
        actual_cost = (actual_tokens / 1_000_000) * prices.embedding_per_million
        
        # Save to cache
        self.cache.save_embedding(
            text=text,
            model=model,
            embedding=embedding,
            tokens=actual_tokens,
            cost_eur=actual_cost
        )
        
        # Track cost (both in cache DB and real-time tracker)
        self.cache.track_cost(
            model=model,
            operation="embedding",
            input_tokens=actual_tokens,
            output_tokens=0,
            cost_eur=actual_cost,
            from_cache=False
        )
        
        self.cost_tracker.record_request(
            model=model,
            input_tokens=actual_tokens,
            output_tokens=0,
            cost_eur=actual_cost,
            from_cache=False
        )
        
        logger.info(
            "embedding_created",
            model=model,
            tokens=actual_tokens,
            dimension=len(embedding),
            cost_eur=actual_cost
        )
        
        # Print cost info with colors
        cost_msg = format_cost_info(
            tokens_in=actual_tokens,
            tokens_out=0,
            cost_eur=actual_cost,
            model=model,
            budget_eur=self.max_per_request_eur,
            from_cache=False
        )
        print_cost(cost_msg)
        
        return {
            "embedding": embedding,
            "dimension": len(embedding),
            "tokens": actual_tokens,
            "cost_eur": actual_cost,
            "from_cache": False,
        }
    
    def get_stats(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get cost statistics.
        
        Args:
            date: Date in ISO format, or None for today
            
        Returns:
            Dict with statistics
        """
        return self.cache.get_stats(date)

