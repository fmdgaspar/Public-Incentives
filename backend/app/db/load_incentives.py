"""
Script to load scraped incentives into the database.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal

import structlog
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models import Incentive

logger = structlog.get_logger()


def parse_date(date_str: str | None) -> date | None:
    """Parse date string to date object."""
    if not date_str:
        return None
    
    try:
        # Handle ISO format
        if isinstance(date_str, str):
            return datetime.fromisoformat(date_str.split('T')[0]).date()
        return None
    except (ValueError, AttributeError):
        return None


def parse_decimal(value: str | float | None) -> Decimal | None:
    """Parse value to Decimal."""
    if value is None:
        return None
    
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return None


def load_incentives_from_json(json_path: str | Path) -> int:
    """
    Load incentives from JSON file into database.
    
    Args:
        json_path: Path to incentives JSON file
        
    Returns:
        Number of incentives loaded
    """
    json_path = Path(json_path)
    
    if not json_path.exists():
        logger.error("file_not_found", path=str(json_path))
        raise FileNotFoundError(f"File not found: {json_path}")
    
    logger.info("loading_incentives_started", path=str(json_path))
    
    # Load JSON data
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    logger.info("json_loaded", count=len(data))
    
    # Create database session
    db: Session = SessionLocal()
    loaded_count = 0
    updated_count = 0
    
    try:
        for item in data:
            # Check if incentive already exists
            existing = db.query(Incentive).filter(
                Incentive.incentive_id == item['incentive_id']
            ).first()
            
            if existing:
                # Update existing
                existing.title = item['title']
                existing.description = item.get('description')
                existing.ai_description = item.get('ai_description')
                existing.document_urls = item.get('document_urls', [])
                existing.publication_date = parse_date(item.get('publication_date'))
                existing.start_date = parse_date(item.get('start_date'))
                existing.end_date = parse_date(item.get('end_date'))
                existing.total_budget = parse_decimal(item.get('total_budget'))
                existing.source_link = item['source_link']
                existing.updated_at = datetime.utcnow()
                
                updated_count += 1
                
            else:
                # Create new
                incentive = Incentive(
                    incentive_id=item['incentive_id'],
                    title=item['title'],
                    description=item.get('description'),
                    ai_description=item.get('ai_description'),
                    document_urls=item.get('document_urls', []),
                    publication_date=parse_date(item.get('publication_date')),
                    start_date=parse_date(item.get('start_date')),
                    end_date=parse_date(item.get('end_date')),
                    total_budget=parse_decimal(item.get('total_budget')),
                    source_link=item['source_link'],
                )
                
                db.add(incentive)
                loaded_count += 1
        
        # Commit transaction
        db.commit()
        
        logger.info("incentives_loaded",
                   new=loaded_count,
                   updated=updated_count,
                   total=loaded_count + updated_count)
        
        return loaded_count + updated_count
        
    except Exception as e:
        db.rollback()
        logger.error("load_failed", error=str(e), exc_info=True)
        raise
        
    finally:
        db.close()


def main():
    """Main entry point."""
    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )
    
    # Get JSON path from args or use default
    if len(sys.argv) > 1:
        json_path = sys.argv[1]
    else:
        json_path = "data/processed/incentives.json"
    
    try:
        count = load_incentives_from_json(json_path)
        print(f"\n✅ Successfully loaded {count} incentives into database!")
        
    except Exception as e:
        print(f"\n❌ Failed to load incentives: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

