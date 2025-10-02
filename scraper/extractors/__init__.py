"""Extractors package for LLM-based data extraction."""

from scraper.extractors.llm_extractor import LLMExtractor, AIDescription
from scraper.extractors.embedding_service import EmbeddingService

__all__ = ["LLMExtractor", "AIDescription", "EmbeddingService"]

