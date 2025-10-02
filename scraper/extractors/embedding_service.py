"""
Embedding service for creating vector representations.

Generates embeddings for incentives and companies using OpenAI.
"""

from typing import List, Optional, Dict, Any

import structlog
from sqlalchemy.orm import Session

# Import from backend
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.services.openai_client import ManagedOpenAIClient
from backend.app.models import Incentive, IncentiveEmbedding, Company, CompanyEmbedding

logger = structlog.get_logger()


class EmbeddingService:
    """Service for generating and managing embeddings."""
    
    def __init__(
        self,
        openai_client: Optional[ManagedOpenAIClient] = None,
        model: str = "text-embedding-3-small"
    ):
        """
        Initialize embedding service.
        
        Args:
            openai_client: Managed OpenAI client
            model: Embedding model to use
        """
        self.client = openai_client or ManagedOpenAIClient(
            max_per_request_eur=0.30
        )
        self.model = model
    
    def create_incentive_text(self, incentive: Incentive) -> str:
        """
        Create text representation of incentive for embedding.
        
        Combines title, description, and AI-extracted fields.
        
        Args:
            incentive: Incentive model instance
            
        Returns:
            Text for embedding
        """
        parts = [
            f"Título: {incentive.title}",
        ]
        
        if incentive.description:
            parts.append(f"Descrição: {incentive.description[:500]}")  # Truncate long descriptions
        
        if incentive.ai_description:
            ai_desc = incentive.ai_description
            
            if ai_desc.get("caes"):
                parts.append(f"CAE: {', '.join(ai_desc['caes'])}")
            
            if ai_desc.get("geographic_location"):
                parts.append(f"Localização: {ai_desc['geographic_location']}")
            
            if ai_desc.get("company_size"):
                parts.append(f"Tamanho de empresa: {', '.join(ai_desc['company_size'])}")
            
            if ai_desc.get("investment_objectives"):
                parts.append(f"Objetivos: {', '.join(ai_desc['investment_objectives'])}")
            
            if ai_desc.get("specific_purposes"):
                parts.append(f"Finalidades: {', '.join(ai_desc['specific_purposes'][:3])}")  # Top 3
        
        return "\n".join(parts)
    
    def create_company_text(self, company: Company) -> str:
        """
        Create text representation of company for embedding.
        
        Args:
            company: Company model instance
            
        Returns:
            Text for embedding
        """
        parts = [f"Empresa: {company.name}"]
        
        if company.cae_codes:
            parts.append(f"CAE: {', '.join(company.cae_codes)}")
        
        if company.district:
            location_parts = [company.district]
            if company.county:
                location_parts.append(company.county)
            parts.append(f"Localização: {', '.join(location_parts)}")
        
        if company.size:
            parts.append(f"Tamanho: {company.size}")
        
        return "\n".join(parts)
    
    def generate_incentive_embedding(
        self,
        db: Session,
        incentive: Incentive,
        force_refresh: bool = False
    ) -> Optional[IncentiveEmbedding]:
        """
        Generate and save embedding for an incentive.
        
        Args:
            db: Database session
            incentive: Incentive to embed
            force_refresh: Regenerate even if embedding exists
            
        Returns:
            IncentiveEmbedding instance or None on failure
        """
        # Check if already exists
        if not force_refresh:
            existing = db.query(IncentiveEmbedding).filter(
                IncentiveEmbedding.incentive_id == incentive.incentive_id
            ).first()
            
            if existing:
                logger.info(
                    "embedding_already_exists",
                    incentive_id=incentive.incentive_id,
                    title=incentive.title[:50]
                )
                return existing
        
        # Create text
        text = self.create_incentive_text(incentive)
        
        try:
            # Generate embedding
            result = self.client.create_embedding(text, model=self.model)
            
            # Create or update embedding record
            embedding_record = db.query(IncentiveEmbedding).filter(
                IncentiveEmbedding.incentive_id == incentive.incentive_id
            ).first()
            
            if embedding_record:
                embedding_record.embedding = result["embedding"]
            else:
                embedding_record = IncentiveEmbedding(
                    incentive_id=incentive.incentive_id,
                    embedding=result["embedding"]
                )
                db.add(embedding_record)
            
            db.commit()
            
            logger.info(
                "incentive_embedding_generated",
                incentive_id=incentive.incentive_id,
                title=incentive.title[:50],
                dimension=result["dimension"],
                cost_eur=result["cost_eur"],
                from_cache=result["from_cache"]
            )
            
            return embedding_record
            
        except Exception as e:
            logger.error(
                "embedding_generation_failed",
                incentive_id=incentive.incentive_id,
                error=str(e),
                exc_info=True
            )
            db.rollback()
            return None
    
    def generate_company_embedding(
        self,
        db: Session,
        company: Company,
        force_refresh: bool = False
    ) -> Optional[CompanyEmbedding]:
        """
        Generate and save embedding for a company.
        
        Args:
            db: Database session
            company: Company to embed
            force_refresh: Regenerate even if embedding exists
            
        Returns:
            CompanyEmbedding instance or None on failure
        """
        # Check if already exists
        if not force_refresh:
            existing = db.query(CompanyEmbedding).filter(
                CompanyEmbedding.company_id == company.company_id
            ).first()
            
            if existing:
                logger.info(
                    "company_embedding_already_exists",
                    company_id=company.company_id,
                    name=company.name
                )
                return existing
        
        # Create text
        text = self.create_company_text(company)
        
        try:
            # Generate embedding
            result = self.client.create_embedding(text, model=self.model)
            
            # Create or update embedding record
            embedding_record = db.query(CompanyEmbedding).filter(
                CompanyEmbedding.company_id == company.company_id
            ).first()
            
            if embedding_record:
                embedding_record.embedding = result["embedding"]
            else:
                embedding_record = CompanyEmbedding(
                    company_id=company.company_id,
                    embedding=result["embedding"]
                )
                db.add(embedding_record)
            
            db.commit()
            
            logger.info(
                "company_embedding_generated",
                company_id=company.company_id,
                name=company.name,
                dimension=result["dimension"],
                cost_eur=result["cost_eur"],
                from_cache=result["from_cache"]
            )
            
            return embedding_record
            
        except Exception as e:
            logger.error(
                "company_embedding_generation_failed",
                company_id=company.company_id,
                error=str(e),
                exc_info=True
            )
            db.rollback()
            return None
    
    def generate_batch_incentive_embeddings(
        self,
        db: Session,
        batch_size: int = 50,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Generate embeddings for all incentives in batches.
        
        Args:
            db: Database session
            batch_size: Number to process at once
            force_refresh: Regenerate all embeddings
            
        Returns:
            Dict with statistics
        """
        # Get incentives without embeddings (or all if force_refresh)
        if force_refresh:
            incentives = db.query(Incentive).all()
        else:
            # Find incentives without embeddings
            incentives = db.query(Incentive).outerjoin(IncentiveEmbedding).filter(
                IncentiveEmbedding.incentive_id.is_(None)
            ).all()
        
        total = len(incentives)
        success_count = 0
        failed_count = 0
        
        logger.info("batch_embedding_started", total=total, force_refresh=force_refresh)
        
        for i, incentive in enumerate(incentives, 1):
            try:
                result = self.generate_incentive_embedding(db, incentive, force_refresh)
                if result:
                    success_count += 1
                else:
                    failed_count += 1
                
                if i % 10 == 0:
                    logger.info(
                        "batch_progress",
                        processed=i,
                        total=total,
                        success=success_count,
                        failed=failed_count
                    )
            
            except Exception as e:
                logger.error(
                    "batch_item_failed",
                    incentive_id=incentive.incentive_id,
                    error=str(e)
                )
                failed_count += 1
        
        stats = {
            "total": total,
            "success": success_count,
            "failed": failed_count,
        }
        
        logger.info("batch_embedding_completed", **stats)
        
        return stats
    
    def generate_batch_company_embeddings(
        self,
        db: Session,
        batch_size: int = 50,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Generate embeddings for all companies in batches.
        
        Args:
            db: Database session
            batch_size: Number to process at once
            force_refresh: Regenerate all embeddings
            
        Returns:
            Dict with statistics
        """
        # Get companies without embeddings (or all if force_refresh)
        if force_refresh:
            companies = db.query(Company).all()
        else:
            companies = db.query(Company).outerjoin(CompanyEmbedding).filter(
                CompanyEmbedding.company_id.is_(None)
            ).all()
        
        total = len(companies)
        success_count = 0
        failed_count = 0
        
        logger.info("batch_company_embedding_started", total=total, force_refresh=force_refresh)
        
        for i, company in enumerate(companies, 1):
            try:
                result = self.generate_company_embedding(db, company, force_refresh)
                if result:
                    success_count += 1
                else:
                    failed_count += 1
                
                if i % 10 == 0:
                    logger.info(
                        "batch_progress",
                        processed=i,
                        total=total,
                        success=success_count,
                        failed=failed_count
                    )
            
            except Exception as e:
                logger.error(
                    "batch_company_item_failed",
                    company_id=company.company_id,
                    error=str(e)
                )
                failed_count += 1
        
        stats = {
            "total": total,
            "success": success_count,
            "failed": failed_count,
        }
        
        logger.info("batch_company_embedding_completed", **stats)
        
        return stats

