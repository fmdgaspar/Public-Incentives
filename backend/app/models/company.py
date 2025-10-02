"""
Company database models.
"""

from typing import Optional

from sqlalchemy import String, Text, ARRAY, CheckConstraint, Index, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from backend.app.db.base import Base


class Company(Base):
    """Company model."""
    
    __tablename__ = "companies"
    
    # Primary key
    company_id: Mapped[str] = mapped_column(String, primary_key=True)
    
    # Core fields
    name: Mapped[str] = mapped_column(Text, nullable=False)
    cae_codes: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True, default=list)
    
    # Size constraint
    size: Mapped[Optional[str]] = mapped_column(
        String,
        CheckConstraint("size IN ('micro', 'pme', 'grande', 'unknown')"),
        nullable=True
    )
    
    # Location
    district: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    county: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parish: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Additional info
    website: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Relationship to embedding
    embedding: Mapped[Optional["CompanyEmbedding"]] = relationship(
        "CompanyEmbedding",
        back_populates="company",
        cascade="all, delete-orphan",
        uselist=False
    )
    
    # Index
    __table_args__ = (
        Index("idx_companies_name", "name"),
    )
    
    def __repr__(self) -> str:
        return f"<Company(id={self.company_id}, name={self.name})>"


class CompanyEmbedding(Base):
    """Company embeddings for vector search."""
    
    __tablename__ = "company_embeddings"
    
    company_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("companies.company_id", ondelete="CASCADE"),
        primary_key=True
    )
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1536), nullable=True)
    
    # Relationship
    company: Mapped["Company"] = relationship(
        "Company",
        back_populates="embedding"
    )
    
    def __repr__(self) -> str:
        return f"<CompanyEmbedding(company_id={self.company_id})>"

