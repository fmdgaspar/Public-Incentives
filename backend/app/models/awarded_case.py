"""
Awarded cases database model.
"""

from typing import Optional
from decimal import Decimal

from sqlalchemy import String, Text, Integer, Numeric, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class AwardedCase(Base):
    """
    Awarded cases for ground-truth evaluation.
    
    This table stores historical data of companies that received
    incentives, used for evaluating the matching algorithm.
    """
    
    __tablename__ = "awarded_cases"
    
    # Primary key
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # Source information
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    incentive_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Award details
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Raw data for audit
    raw: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    def __repr__(self) -> str:
        return f"<AwardedCase(id={self.id}, company={self.company_name}, incentive={self.incentive_id})>"

