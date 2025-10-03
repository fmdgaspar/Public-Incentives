"""
Pydantic models for API requests and responses.
"""

from typing import List, Optional, Dict, Any
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field


class CompanyResponse(BaseModel):
    """Company information response model."""
    company_id: str
    name: str
    cae_codes: Optional[List[str]] = None
    size: Optional[str] = None
    district: Optional[str] = None
    county: Optional[str] = None
    parish: Optional[str] = None
    website: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class IncentiveResponse(BaseModel):
    """Incentive information response model."""
    incentive_id: str
    title: str
    description: Optional[str] = None
    ai_description: Optional[Dict[str, Any]] = None
    document_urls: Optional[List[str]] = None
    publication_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    total_budget: Optional[Decimal] = None
    source_link: Optional[str] = None


class MatchComponent(BaseModel):
    """Individual scoring component."""
    vector: float = Field(..., description="Vector similarity score (0-1)")
    bm25: float = Field(..., description="BM25 text matching score (0-1)")
    llm: float = Field(..., description="LLM re-ranking score (0-1)")


class MatchResult(BaseModel):
    """Matching result for a company."""
    company: CompanyResponse
    score: float = Field(..., description="Overall matching score (0-1)")
    explanation: str = Field(..., description="Human-readable explanation of the match")
    components: MatchComponent
    penalties: Optional[Dict[str, float]] = Field(None, description="Applied penalties")


class MatchingRequest(BaseModel):
    """Request model for finding matches."""
    incentive_id: str = Field(..., description="ID of the incentive to find matches for")
    limit: int = Field(5, ge=1, le=20, description="Maximum number of matches to return")


class MatchingResponse(BaseModel):
    """Response model for matching results."""
    incentive: IncentiveResponse
    matches: List[MatchResult]
    total_candidates: int = Field(..., description="Total number of companies evaluated")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")


class IncentiveListResponse(BaseModel):
    """Response model for listing incentives."""
    incentives: List[IncentiveResponse]
    total: int
    page: int
    page_size: int


class CompanyListResponse(BaseModel):
    """Response model for listing companies."""
    companies: List[CompanyResponse]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    database_connected: bool
    openai_configured: bool
    total_incentives: int
    total_companies: int


class ChatRequest(BaseModel):
    """Request model for chatbot queries."""
    question: str = Field(..., description="User question about incentives or companies")
    max_documents: int = Field(5, ge=1, le=10, description="Maximum number of documents to retrieve")


class ChatSource(BaseModel):
    """Source document for chat response."""
    type: str = Field(..., description="Type of document (incentive or company)")
    id: str = Field(..., description="Document ID")
    title: str = Field(..., description="Document title")
    similarity: float = Field(..., description="Similarity score (0-1)")
    metadata: Dict[str, Any] = Field(..., description="Document metadata")


class ChatResponse(BaseModel):
    """Response model for chatbot queries."""
    answer: str = Field(..., description="Generated answer")
    sources: List[ChatSource] = Field(..., description="Source documents used")
    confidence: float = Field(..., description="Confidence score (0-1)")
    cost_eur: float = Field(..., description="Estimated cost in EUR")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
