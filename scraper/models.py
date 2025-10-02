"""
Data models for scraped incentives.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class RawIncentive(BaseModel):
    """Raw scraped incentive data before processing."""
    
    incentive_id: str
    source_link: str
    raw_html: str
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    html_hash: str


class IncentiveData(BaseModel):
    """Structured incentive data after parsing."""
    
    incentive_id: str
    title: str
    description: Optional[str] = None
    source_link: str
    document_urls: List[str] = Field(default_factory=list)
    publication_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    total_budget: Optional[Decimal] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            Decimal: str,
            date: lambda v: v.isoformat() if v else None,
            datetime: lambda v: v.isoformat() if v else None,
        }

