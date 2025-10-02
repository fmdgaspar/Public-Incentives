"""
Database initialization script.
"""

import structlog
from sqlalchemy import text

from backend.app.db.session import engine
from backend.app.db.base import Base
from backend.app.models import (
    Incentive,
    IncentiveEmbedding,
    Company,
    CompanyEmbedding,
    AwardedCase,
)

logger = structlog.get_logger()


def init_db() -> None:
    """
    Initialize the database.
    
    - Creates pgvector extension
    - Creates all tables
    """
    logger.info("database_init_started")
    
    try:
        # Create pgvector extension
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
            logger.info("pgvector_extension_created")
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("database_tables_created")
        
        logger.info("database_init_completed")
        
    except Exception as e:
        logger.error("database_init_failed", error=str(e), exc_info=True)
        raise


def drop_db() -> None:
    """
    Drop all database tables.
    
    WARNING: This will delete all data!
    """
    logger.warning("database_drop_started")
    
    try:
        Base.metadata.drop_all(bind=engine)
        logger.warning("database_tables_dropped")
        
    except Exception as e:
        logger.error("database_drop_failed", error=str(e), exc_info=True)
        raise


def reset_db() -> None:
    """
    Reset database (drop and recreate).
    
    WARNING: This will delete all data!
    """
    logger.warning("database_reset_started")
    drop_db()
    init_db()
    logger.warning("database_reset_completed")


if __name__ == "__main__":
    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )
    
    init_db()
    print("\n✅ Database initialized successfully!")

