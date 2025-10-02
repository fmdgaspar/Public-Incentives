"""
Database session management and connection.
"""

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Get database URL from environment
DATABASE_URL = os.getenv(
    "DB_DSN",
    "postgresql+psycopg://postgres:postgres@localhost:5432/ai_challenge"
)

# Create engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Test connections before using
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",  # Log SQL queries if enabled
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for getting database sessions.
    
    Yields:
        Session: Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

