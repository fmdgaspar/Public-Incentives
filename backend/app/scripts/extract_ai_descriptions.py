"""
Script to extract AI descriptions for all incentives.

Usage:
    python -m backend.app.scripts.extract_ai_descriptions [--limit N] [--force]
"""

import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

import structlog
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models import Incentive
from backend.app.services.openai_client import ManagedOpenAIClient
from scraper.extractors.llm_extractor import LLMExtractor
from scraper.extractors.embedding_service import EmbeddingService

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


def extract_ai_descriptions(
    db: Session,
    limit: int = None,
    force: bool = False
) -> dict:
    """
    Extract AI descriptions for incentives.
    
    Args:
        db: Database session
        limit: Maximum number to process (None = all)
        force: Re-extract even if ai_description exists
        
    Returns:
        Statistics dict
    """
    # Initialize services
    openai_client = ManagedOpenAIClient(max_per_request_eur=0.30)
    extractor = LLMExtractor(openai_client=openai_client)
    
    # Get incentives to process
    query = db.query(Incentive)
    
    if not force:
        # Only those without ai_description
        query = query.filter(
            (Incentive.ai_description.is_(None)) | (Incentive.ai_description == {})
        )
    
    if limit:
        query = query.limit(limit)
    
    incentives = query.all()
    
    total = len(incentives)
    success_count = 0
    failed_count = 0
    total_cost = 0.0
    
    logger.info("extraction_started", total=total, force=force)
    
    for i, incentive in enumerate(incentives, 1):
        try:
            logger.info(
                "processing_incentive",
                progress=f"{i}/{total}",
                incentive_id=incentive.incentive_id,
                title=incentive.title[:50]
            )
            
            # Extract (with document URLs for PDF processing)
            document_id = f"incentive_{incentive.incentive_id}"
            ai_desc = extractor.extract(
                title=incentive.title,
                description=incentive.description or "",
                document_urls=incentive.document_urls if incentive.document_urls else None,
                document_id=document_id
            )
            
            if ai_desc:
                # Update incentive - usar mode='json' para serializar dates e Decimals
                incentive.ai_description = ai_desc.model_dump(mode='json')
                db.commit()
                
                success_count += 1
                
                logger.info(
                    "extraction_success",
                    incentive_id=incentive.incentive_id,
                    caes=ai_desc.caes,
                    location=ai_desc.geographic_location,
                    size=ai_desc.company_size
                )
            else:
                failed_count += 1
                logger.warning("extraction_failed", incentive_id=incentive.incentive_id)
        
        except Exception as e:
            failed_count += 1
            logger.error(
                "processing_error",
                incentive_id=incentive.incentive_id,
                error=str(e),
                exc_info=True
            )
            db.rollback()
    
    # Get cost stats
    stats = openai_client.get_stats()
    total_cost = stats.get("total_cost_eur", 0.0)
    
    result = {
        "total": total,
        "success": success_count,
        "failed": failed_count,
        "total_cost_eur": total_cost,
    }
    
    logger.info("extraction_completed", **result)
    
    return result


def generate_embeddings(
    db: Session,
    limit: int = None,
    force: bool = False
) -> dict:
    """
    Generate embeddings for incentives.
    
    Args:
        db: Database session
        limit: Maximum number to process
        force: Regenerate all
        
    Returns:
        Statistics dict
    """
    openai_client = ManagedOpenAIClient(max_per_request_eur=0.30)
    embedding_service = EmbeddingService(openai_client=openai_client)
    
    logger.info("embedding_generation_started")
    
    # Get incentives with ai_description
    incentives = db.query(Incentive).filter(
        Incentive.ai_description.isnot(None)
    )
    
    if limit:
        incentives = incentives.limit(limit)
    
    incentives = incentives.all()
    
    success_count = 0
    failed_count = 0
    
    for i, incentive in enumerate(incentives, 1):
        try:
            document_id = f"incentive_{incentive.incentive_id}"
            result = embedding_service.generate_incentive_embedding(
                db, incentive, force_refresh=force, document_id=document_id
            )
            if result:
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            logger.error(
                "embedding_error",
                incentive_id=incentive.incentive_id,
                error=str(e)
            )
            failed_count += 1
    
    stats = {
        "total": len(incentives),
        "success": success_count,
        "failed": failed_count,
    }
    
    logger.info("embedding_generation_completed", **stats)
    
    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract AI descriptions and embeddings for incentives"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of incentives to process"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract even if ai_description exists"
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip embedding generation"
    )
    
    args = parser.parse_args()
    
    db = SessionLocal()
    
    try:
        # Extract AI descriptions
        print("\n" + "="*60)
        print("EXTRACTING AI DESCRIPTIONS")
        print("="*60 + "\n")
        
        extraction_stats = extract_ai_descriptions(
            db,
            limit=args.limit,
            force=args.force
        )
        
        print(f"\n✅ AI Description Extraction Complete!")
        print(f"   Total: {extraction_stats['total']}")
        print(f"   Success: {extraction_stats['success']}")
        print(f"   Failed: {extraction_stats['failed']}")
        print(f"   Cost: €{extraction_stats['total_cost_eur']:.4f}")
        
        # Generate embeddings
        if not args.skip_embeddings:
            print("\n" + "="*60)
            print("GENERATING EMBEDDINGS")
            print("="*60 + "\n")
            
            embedding_stats = generate_embeddings(
                db,
                limit=args.limit,
                force=args.force
            )
            
            print(f"\n✅ Embedding Generation Complete!")
            print(f"   Total: {embedding_stats['total']}")
            print(f"   Success: {embedding_stats['success']}")
            print(f"   Failed: {embedding_stats['failed']}")
        
        print("\n" + "="*60)
        print("ALL PROCESSING COMPLETE")
        print("="*60 + "\n")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        logger.error("script_failed", error=str(e), exc_info=True)
        sys.exit(1)
    
    finally:
        db.close()


if __name__ == "__main__":
    main()

