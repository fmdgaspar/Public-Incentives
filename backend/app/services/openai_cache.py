"""
SQLite cache for OpenAI API responses.
Prevents duplicate requests and tracks costs.
"""

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import structlog

logger = structlog.get_logger()


class OpenAICache:
    """SQLite-based cache for OpenAI API responses."""
    
    def __init__(self, cache_path: str = ".cache/openai_cache.db"):
        """
        Initialize cache.
        
        Args:
            cache_path: Path to SQLite database file
        """
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Create cache tables if they don't exist."""
        conn = sqlite3.connect(self.cache_path)
        
        # LLM completions cache
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                prompt_hash TEXT NOT NULL,
                response_text TEXT NOT NULL,
                response_json TEXT,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cost_eur REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 1
            )
        """)
        
        # Embeddings cache
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                text_hash TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                tokens INTEGER NOT NULL,
                cost_eur REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 1
            )
        """)
        
        # Cost tracking
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cost_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date TEXT NOT NULL,
                model TEXT NOT NULL,
                operation TEXT NOT NULL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cost_eur REAL NOT NULL,
                from_cache INTEGER DEFAULT 0
            )
        """)
        
        # Indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cost_date ON cost_tracking(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cost_timestamp ON cost_tracking(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_prompt ON llm_cache(prompt_hash)")
        
        conn.commit()
        conn.close()
        
        logger.info("cache_initialized", path=str(self.cache_path))
    
    def _hash_prompt(self, prompt: str, model: str, params: Dict) -> str:
        """Create unique hash for prompt + model + params."""
        content = f"{model}::{prompt}::{json.dumps(params, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _hash_text(self, text: str) -> str:
        """Create hash of text."""
        return hashlib.sha256(text.encode()).hexdigest()
    
    def get_llm_response(
        self,
        prompt: str,
        model: str,
        params: Dict
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached LLM response.
        
        Args:
            prompt: The prompt text
            model: Model name
            params: Request parameters (temperature, max_tokens, etc.)
            
        Returns:
            Dict with response and metadata, or None if not cached
        """
        cache_key = self._hash_prompt(prompt, model, params)
        
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.execute(
            """
            SELECT response_text, response_json, input_tokens, output_tokens, cost_eur
            FROM llm_cache
            WHERE cache_key = ?
            """,
            (cache_key,)
        )
        row = cursor.fetchone()
        
        if row:
            # Update access stats
            conn.execute(
                """
                UPDATE llm_cache
                SET last_accessed = CURRENT_TIMESTAMP, access_count = access_count + 1
                WHERE cache_key = ?
                """,
                (cache_key,)
            )
            conn.commit()
            
            logger.info(
                "cache_hit_llm",
                cache_key=cache_key[:8],
                model=model,
                cost_saved_eur=row[4]
            )
            
            conn.close()
            
            return {
                "response": row[0],
                "response_json": json.loads(row[1]) if row[1] else None,
                "usage": {
                    "prompt_tokens": row[2],
                    "completion_tokens": row[3],
                    "total_tokens": row[2] + row[3],
                },
                "cost_eur": 0.0,  # No cost for cache hit
                "original_cost_eur": row[4],
                "from_cache": True,
            }
        
        conn.close()
        return None
    
    def save_llm_response(
        self,
        prompt: str,
        model: str,
        params: Dict,
        response: str,
        response_json: Optional[Dict],
        input_tokens: int,
        output_tokens: int,
        cost_eur: float
    ):
        """
        Save LLM response to cache.
        
        Args:
            prompt: The prompt text
            model: Model name
            params: Request parameters
            response: Response text
            response_json: Parsed JSON response (if applicable)
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cost_eur: Cost in EUR
        """
        cache_key = self._hash_prompt(prompt, model, params)
        prompt_hash = self._hash_text(prompt)
        
        conn = sqlite3.connect(self.cache_path)
        conn.execute(
            """
            INSERT OR REPLACE INTO llm_cache
            (cache_key, model, prompt_hash, response_text, response_json,
             input_tokens, output_tokens, cost_eur)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cache_key,
                model,
                prompt_hash,
                response,
                json.dumps(response_json) if response_json else None,
                input_tokens,
                output_tokens,
                cost_eur
            )
        )
        conn.commit()
        conn.close()
        
        logger.debug("cache_saved_llm", cache_key=cache_key[:8], cost_eur=cost_eur)
    
    def get_embedding(self, text: str, model: str) -> Optional[Dict[str, Any]]:
        """
        Get cached embedding.
        
        Args:
            text: Text to embed
            model: Model name
            
        Returns:
            Dict with embedding and metadata, or None if not cached
        """
        text_hash = self._hash_text(f"{model}::{text}")
        
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.execute(
            """
            SELECT embedding_json, dimension, tokens, cost_eur
            FROM embedding_cache
            WHERE text_hash = ?
            """,
            (text_hash,)
        )
        row = cursor.fetchone()
        
        if row:
            # Update access stats
            conn.execute(
                """
                UPDATE embedding_cache
                SET last_accessed = CURRENT_TIMESTAMP, access_count = access_count + 1
                WHERE text_hash = ?
                """,
                (text_hash,)
            )
            conn.commit()
            
            logger.info(
                "cache_hit_embedding",
                text_hash=text_hash[:8],
                model=model,
                cost_saved_eur=row[3]
            )
            
            conn.close()
            
            return {
                "embedding": json.loads(row[0]),
                "dimension": row[1],
                "tokens": row[2],
                "cost_eur": 0.0,
                "original_cost_eur": row[3],
                "from_cache": True,
            }
        
        conn.close()
        return None
    
    def save_embedding(
        self,
        text: str,
        model: str,
        embedding: list[float],
        tokens: int,
        cost_eur: float
    ):
        """
        Save embedding to cache.
        
        Args:
            text: Text that was embedded
            model: Model name
            embedding: Embedding vector
            tokens: Number of tokens
            cost_eur: Cost in EUR
        """
        text_hash = self._hash_text(f"{model}::{text}")
        
        conn = sqlite3.connect(self.cache_path)
        conn.execute(
            """
            INSERT OR REPLACE INTO embedding_cache
            (text_hash, model, embedding_json, dimension, tokens, cost_eur)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                text_hash,
                model,
                json.dumps(embedding),
                len(embedding),
                tokens,
                cost_eur
            )
        )
        conn.commit()
        conn.close()
        
        logger.debug("cache_saved_embedding", text_hash=text_hash[:8], cost_eur=cost_eur)
    
    def track_cost(
        self,
        model: str,
        operation: str,
        input_tokens: int,
        output_tokens: int,
        cost_eur: float,
        from_cache: bool = False
    ):
        """
        Track cost in database.
        
        Args:
            model: Model name
            operation: Operation type (e.g., 'chat_completion', 'embedding')
            input_tokens: Input tokens
            output_tokens: Output tokens
            cost_eur: Cost in EUR
            from_cache: Whether this was a cache hit
        """
        today = datetime.utcnow().date().isoformat()
        
        conn = sqlite3.connect(self.cache_path)
        conn.execute(
            """
            INSERT INTO cost_tracking
            (date, model, operation, input_tokens, output_tokens, cost_eur, from_cache)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (today, model, operation, input_tokens, output_tokens, cost_eur, int(from_cache))
        )
        conn.commit()
        conn.close()
    
    def get_stats(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get cost statistics.
        
        Args:
            date: Date in ISO format (YYYY-MM-DD), or None for today
            
        Returns:
            Dict with statistics
        """
        if date is None:
            date = datetime.utcnow().date().isoformat()
        
        conn = sqlite3.connect(self.cache_path)
        
        # Total cost
        cursor = conn.execute(
            "SELECT SUM(cost_eur) FROM cost_tracking WHERE date = ?",
            (date,)
        )
        total_cost = cursor.fetchone()[0] or 0.0
        
        # Cost by model
        cursor = conn.execute(
            """
            SELECT model, SUM(cost_eur), COUNT(*)
            FROM cost_tracking
            WHERE date = ?
            GROUP BY model
            """,
            (date,)
        )
        by_model = {row[0]: {"cost_eur": row[1], "count": row[2]} for row in cursor.fetchall()}
        
        # Cache stats
        cursor = conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE from_cache = 1) as cached,
                COUNT(*) FILTER (WHERE from_cache = 0) as uncached,
                SUM(cost_eur) FILTER (WHERE from_cache = 0) as actual_cost
            FROM cost_tracking
            WHERE date = ?
            """,
            (date,)
        )
        cache_stats = cursor.fetchone()
        
        conn.close()
        
        return {
            "date": date,
            "total_cost_eur": round(total_cost, 4),
            "by_model": by_model,
            "cache": {
                "hits": cache_stats[0] or 0,
                "misses": cache_stats[1] or 0,
                "actual_cost_eur": round(cache_stats[2] or 0.0, 4),
            },
        }

