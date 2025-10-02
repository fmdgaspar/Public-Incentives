"""
Real-time cost tracker that uses actual tokens from API responses.

This module tracks the REAL cost of each request by:
1. Using actual token counts returned by OpenAI API
2. Applying current exchange rates
3. Maintaining accurate running totals
"""

from datetime import datetime
from typing import Dict, Optional
from pathlib import Path
import json

import structlog

logger = structlog.get_logger()


class RealTimeCostTracker:
    """
    Tracks real costs based on actual API responses.
    
    This is more accurate than pre-estimating because it uses
    the exact token counts that OpenAI bills for.
    """
    
    def __init__(self, tracking_file: str = ".cache/cost_tracking.json"):
        """
        Initialize cost tracker.
        
        Args:
            tracking_file: JSON file to store tracking data
        """
        self.tracking_file = Path(tracking_file)
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_tracking_data()
    
    def _load_tracking_data(self):
        """Load existing tracking data."""
        if self.tracking_file.exists():
            try:
                with open(self.tracking_file, 'r') as f:
                    self.data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load tracking data: {e}")
                self.data = self._empty_data()
        else:
            self.data = self._empty_data()
    
    def _empty_data(self) -> Dict:
        """Create empty tracking data structure."""
        return {
            "last_updated": datetime.utcnow().isoformat(),
            "daily_totals": {},
            "model_stats": {},
        }
    
    def _save_tracking_data(self):
        """Save tracking data to file."""
        try:
            self.data["last_updated"] = datetime.utcnow().isoformat()
            with open(self.tracking_file, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save tracking data: {e}")
    
    def record_request(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_eur: float,
        from_cache: bool = False
    ):
        """
        Record a request with actual token counts and cost.
        
        Args:
            model: Model name
            input_tokens: Actual input tokens (from API response)
            output_tokens: Actual output tokens (from API response)
            cost_eur: Actual cost in EUR
            from_cache: Whether this was a cache hit
        """
        today = datetime.utcnow().date().isoformat()
        
        # Initialize daily total if needed
        if today not in self.data["daily_totals"]:
            self.data["daily_totals"][today] = {
                "total_cost_eur": 0.0,
                "requests": 0,
                "cache_hits": 0,
                "tokens_in": 0,
                "tokens_out": 0,
            }
        
        # Initialize model stats if needed
        if model not in self.data["model_stats"]:
            self.data["model_stats"][model] = {
                "total_cost_eur": 0.0,
                "requests": 0,
                "tokens_in": 0,
                "tokens_out": 0,
            }
        
        # Update daily total
        daily = self.data["daily_totals"][today]
        daily["requests"] += 1
        daily["tokens_in"] += input_tokens
        daily["tokens_out"] += output_tokens
        
        if from_cache:
            daily["cache_hits"] += 1
        else:
            daily["total_cost_eur"] += cost_eur
        
        # Update model stats (only for non-cached)
        if not from_cache:
            model_stat = self.data["model_stats"][model]
            model_stat["requests"] += 1
            model_stat["total_cost_eur"] += cost_eur
            model_stat["tokens_in"] += input_tokens
            model_stat["tokens_out"] += output_tokens
        
        self._save_tracking_data()
        
        logger.debug(
            "cost_recorded",
            model=model,
            tokens_in=input_tokens,
            tokens_out=output_tokens,
            cost_eur=cost_eur,
            from_cache=from_cache
        )
    
    def get_daily_cost(self, date: Optional[str] = None) -> float:
        """
        Get total cost for a specific day.
        
        Args:
            date: Date in YYYY-MM-DD format (None = today)
            
        Returns:
            Total cost in EUR
        """
        if date is None:
            date = datetime.utcnow().date().isoformat()
        
        return self.data["daily_totals"].get(date, {}).get("total_cost_eur", 0.0)
    
    def get_daily_stats(self, date: Optional[str] = None) -> Dict:
        """
        Get detailed stats for a day.
        
        Args:
            date: Date in YYYY-MM-DD format (None = today)
            
        Returns:
            Dict with stats
        """
        if date is None:
            date = datetime.utcnow().date().isoformat()
        
        daily = self.data["daily_totals"].get(date, {
            "total_cost_eur": 0.0,
            "requests": 0,
            "cache_hits": 0,
            "tokens_in": 0,
            "tokens_out": 0,
        })
        
        return {
            "date": date,
            **daily,
            "cache_hit_rate": (
                daily["cache_hits"] / daily["requests"] * 100
                if daily["requests"] > 0 else 0.0
            )
        }
    
    def get_model_stats(self) -> Dict:
        """Get stats by model."""
        return self.data["model_stats"]
    
    def get_summary(self) -> Dict:
        """Get overall summary."""
        today = datetime.utcnow().date().isoformat()
        
        return {
            "today": self.get_daily_stats(today),
            "by_model": self.get_model_stats(),
        }

