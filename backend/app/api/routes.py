"""
FastAPI routes for the Public Incentives API.
"""

import time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.incentive import Incentive, IncentiveEmbedding
from backend.app.models.company import Company, CompanyEmbedding
from backend.app.services.matching_service import MatchingService, MatchResult
from backend.app.services.openai_client import ManagedOpenAIClient
from backend.app.api.models import (
    IncentiveResponse, CompanyResponse, MatchingRequest, MatchingResponse,
    IncentiveListResponse, CompanyListResponse, HealthResponse, MatchResult as APIMatchResult,
    MatchComponent, ChatRequest, ChatResponse, ChatSource
)

# Create router
router = APIRouter()

# Initialize services
openai_client = ManagedOpenAIClient()
matching_service = MatchingService(openai_client=openai_client)

# Import RAG service
from backend.app.services.rag_service import RAGService
rag_service = RAGService(openai_client=openai_client)


def convert_company_to_response(company: Company) -> CompanyResponse:
    """Convert Company model to API response."""
    return CompanyResponse(
        company_id=company.company_id,
        name=company.name,
        cae_codes=company.cae_codes,
        size=company.size,
        district=company.district,
        county=company.county,
        parish=company.parish,
        website=company.website,
        raw=company.raw
    )


def convert_incentive_to_response(incentive: Incentive) -> IncentiveResponse:
    """Convert Incentive model to API response."""
    return IncentiveResponse(
        incentive_id=incentive.incentive_id,
        title=incentive.title,
        description=incentive.description,
        ai_description=incentive.ai_description,
        document_urls=incentive.document_urls,
        publication_date=incentive.publication_date,
        start_date=incentive.start_date,
        end_date=incentive.end_date,
        total_budget=incentive.total_budget,
        source_link=incentive.source_link
    )


def convert_match_result_to_response(match: MatchResult) -> APIMatchResult:
    """Convert internal MatchResult to API response."""
    return APIMatchResult(
        company=convert_company_to_response(
            Company(
                company_id=match.company_id,
                name=match.company_name,
                cae_codes=[],  # Will be filled from DB
                size=None,
                district=None,
                county=None,
                parish=None,
                website=None,
                raw=None
            )
        ),
        score=match.score,
        explanation=match.explanation,
        components=MatchComponent(
            vector=match.component_scores["vector"],
            bm25=match.component_scores["bm25"],
            llm=match.component_scores["llm"]
        ),
        penalties=match.penalties_applied
    )


@router.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    try:
        # Check database connection
        total_incentives = db.query(Incentive).count()
        total_companies = db.query(Company).count()
        
        # Check OpenAI configuration
        openai_configured = openai_client.client.api_key is not None
        
        return HealthResponse(
            status="healthy",
            version="1.0.0",
            database_connected=True,
            openai_configured=openai_configured,
            total_incentives=total_incentives,
            total_companies=total_companies
        )
    except Exception as e:
        return HealthResponse(
            status="unhealthy",
            version="1.0.0",
            database_connected=False,
            openai_configured=False,
            total_incentives=0,
            total_companies=0
        )


@router.get("/incentives", response_model=IncentiveListResponse)
async def list_incentives(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    has_ai_description: Optional[bool] = Query(None, description="Filter by AI description presence"),
    db: Session = Depends(get_db)
):
    """List all incentives with pagination."""
    query = db.query(Incentive)
    
    if has_ai_description is not None:
        if has_ai_description:
            query = query.filter(Incentive.ai_description.isnot(None))
        else:
            query = query.filter(Incentive.ai_description.is_(None))
    
    total = query.count()
    incentives = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return IncentiveListResponse(
        incentives=[convert_incentive_to_response(incentive) for incentive in incentives],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/incentives/{incentive_id}", response_model=IncentiveResponse)
async def get_incentive(incentive_id: str, db: Session = Depends(get_db)):
    """Get a specific incentive by ID."""
    incentive = db.query(Incentive).filter(Incentive.incentive_id == incentive_id).first()
    if not incentive:
        raise HTTPException(status_code=404, detail="Incentive not found")
    
    return convert_incentive_to_response(incentive)


@router.get("/companies", response_model=CompanyListResponse)
async def list_companies(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    district: Optional[str] = Query(None, description="Filter by district"),
    size: Optional[str] = Query(None, description="Filter by company size"),
    db: Session = Depends(get_db)
):
    """List all companies with pagination and filtering."""
    query = db.query(Company)
    
    if district:
        query = query.filter(Company.district.ilike(f"%{district}%"))
    
    if size:
        query = query.filter(Company.size == size)
    
    total = query.count()
    companies = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return CompanyListResponse(
        companies=[convert_company_to_response(company) for company in companies],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/companies/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: str, db: Session = Depends(get_db)):
    """Get a specific company by ID."""
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    return convert_company_to_response(company)


@router.post("/matching", response_model=MatchingResponse)
async def find_matches(request: MatchingRequest, db: Session = Depends(get_db)):
    """Find matching companies for an incentive."""
    start_time = time.time()
    
    # Get the incentive
    incentive = db.query(Incentive).filter(Incentive.incentive_id == request.incentive_id).first()
    if not incentive:
        raise HTTPException(status_code=404, detail="Incentive not found")
    
    # Check if incentive has embeddings
    incentive_embedding = db.query(IncentiveEmbedding).filter(
        IncentiveEmbedding.incentive_id == request.incentive_id
    ).first()
    
    if not incentive_embedding or incentive_embedding.embedding is None:
        raise HTTPException(
            status_code=400, 
            detail="Incentive does not have embeddings. Please run the embedding generation process first."
        )
    
    # Find matches
    try:
        matches = matching_service.find_matches(db, request.incentive_id, top_k=request.limit)
        
        # Get full company data for matches
        company_ids = [match.company_id for match in matches]
        companies = db.query(Company).filter(Company.company_id.in_(company_ids)).all()
        company_dict = {company.company_id: company for company in companies}
        
        # Convert matches to API format
        api_matches = []
        for match in matches:
            company = company_dict.get(match.company_id)
            if company:
                api_match = APIMatchResult(
                    company=convert_company_to_response(company),
                    score=match.score,
                    explanation=match.explanation,
                    components=MatchComponent(
                        vector=match.component_scores["vector"],
                        bm25=match.component_scores["bm25"],
                        llm=match.component_scores["llm"]
                    ),
                    penalties=match.penalties_applied
                )
                api_matches.append(api_match)
        
        processing_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        return MatchingResponse(
            incentive=convert_incentive_to_response(incentive),
            matches=api_matches,
            total_candidates=100,  # This is the candidate pool size
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error finding matches: {str(e)}")


@router.get("/matching/{incentive_id}", response_model=MatchingResponse)
async def find_matches_get(
    incentive_id: str,
    limit: int = Query(5, ge=1, le=20, description="Maximum number of matches"),
    db: Session = Depends(get_db)
):
    """Find matching companies for an incentive (GET version)."""
    request = MatchingRequest(incentive_id=incentive_id, limit=limit)
    return await find_matches(request, db)


@router.post("/chat", response_model=ChatResponse)
async def chat_with_rag(request: ChatRequest, db: Session = Depends(get_db)):
    """Chat with RAG system about incentives and companies."""
    start_time = time.time()
    
    try:
        # Process RAG query
        result = rag_service.query(
            db=db,
            question=request.question,
            max_documents=request.max_documents
        )
        
        # Convert sources to API format
        api_sources = []
        for source in result.sources:
            api_source = ChatSource(
                type=source['type'],
                id=source['id'],
                title=source['title'],
                similarity=source['similarity'],
                metadata=source['metadata']
            )
            api_sources.append(api_source)
        
        processing_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        return ChatResponse(
            answer=result.answer,
            sources=api_sources,
            confidence=result.confidence,
            cost_eur=result.cost_eur,
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat query: {str(e)}")


@router.get("/chat", response_model=ChatResponse)
async def chat_with_rag_get(
    question: str = Query(..., description="User question about incentives or companies"),
    max_documents: int = Query(5, ge=1, le=10, description="Maximum number of documents to retrieve"),
    db: Session = Depends(get_db)
):
    """Chat with RAG system (GET version)."""
    request = ChatRequest(question=question, max_documents=max_documents)
    return await chat_with_rag(request, db)
