"""
Incentive database models.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Text, Date, Numeric, TIMESTAMP, ARRAY, Index, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from backend.app.db.base import Base


class Incentive(Base):
    """Incentive model matching the specification."""
    
    __tablename__ = "incentives"
    
    # Primary key
    incentive_id: Mapped[str] = mapped_column(String, primary_key=True)
    
    # Core fields
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_description: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    document_urls: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=True, default=list)
    
    # Dates
    publication_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Budget
    total_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    
    # Source
    source_link: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
    # Relationship to embedding
    embedding: Mapped[Optional["IncentiveEmbedding"]] = relationship(
        "IncentiveEmbedding",
        back_populates="incentive",
        cascade="all, delete-orphan",
        uselist=False
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_incentives_pubdate", "publication_date"),
        Index("idx_incentives_dates", "start_date", "end_date"),
    )
    
    def __repr__(self) -> str:
        return f"<Incentive(id={self.incentive_id}, title={self.title[:50]})>"


class IncentiveEmbedding(Base):
    """Incentive embeddings for vector search."""
    
    __tablename__ = "incentive_embeddings"
    
    incentive_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("incentives.incentive_id", ondelete="CASCADE"),
        primary_key=True
    )
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1536), nullable=True)
    
    # Relationship
    incentive: Mapped["Incentive"] = relationship(
        "Incentive",
        back_populates="embedding"
    )
    
    def __repr__(self) -> str:
        return f"<IncentiveEmbedding(incentive_id={self.incentive_id})>"

