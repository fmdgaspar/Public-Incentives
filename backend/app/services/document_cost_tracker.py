"""
Document cost tracker to enforce €0.30 per document limit.
"""

import structlog
from typing import Dict, Optional
from datetime import datetime

logger = structlog.get_logger()


class DocumentCostTracker:
    """
    Tracks costs per document to enforce €0.30 per document limit.
    """
    
    def __init__(self):
        self.document_costs: Dict[str, float] = {}
        self.max_cost_per_document = 0.30  # €0.30 per document
        
    def can_spend(self, document_id: str, estimated_cost: float) -> bool:
        """
        Check if we can spend the estimated cost for this document.
        
        Args:
            document_id: Document identifier (URL or hash)
            estimated_cost: Estimated cost in EUR
            
        Returns:
            True if we can spend, False otherwise
        """
        current_cost = self.document_costs.get(document_id, 0.0)
        total_cost = current_cost + estimated_cost
        
        if total_cost > self.max_cost_per_document:
            logger.warning(
                "document_budget_exceeded",
                document_id=document_id,
                current_cost=current_cost,
                estimated_cost=estimated_cost,
                total_cost=total_cost,
                max_cost=self.max_cost_per_document
            )
            return False
            
        return True
    
    def record_cost(self, document_id: str, actual_cost: float) -> None:
        """
        Record actual cost for a document.
        
        Args:
            document_id: Document identifier
            actual_cost: Actual cost in EUR
        """
        current_cost = self.document_costs.get(document_id, 0.0)
        new_cost = current_cost + actual_cost
        
        self.document_costs[document_id] = new_cost
        
        logger.info(
            "document_cost_recorded",
            document_id=document_id,
            actual_cost=actual_cost,
            total_cost=new_cost,
            remaining_budget=self.max_cost_per_document - new_cost
        )
    
    def get_remaining_budget(self, document_id: str) -> float:
        """
        Get remaining budget for a document.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Remaining budget in EUR
        """
        current_cost = self.document_costs.get(document_id, 0.0)
        return self.max_cost_per_document - current_cost
    
    def get_document_cost(self, document_id: str) -> float:
        """
        Get total cost for a document.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Total cost in EUR
        """
        return self.document_costs.get(document_id, 0.0)
    
    def reset_document(self, document_id: str) -> None:
        """
        Reset cost tracking for a document.
        
        Args:
            document_id: Document identifier
        """
        if document_id in self.document_costs:
            del self.document_costs[document_id]
            logger.info("document_cost_reset", document_id=document_id)
    
    def get_stats(self) -> Dict[str, any]:
        """
        Get cost tracking statistics.
        
        Returns:
            Dictionary with statistics
        """
        total_documents = len(self.document_costs)
        total_cost = sum(self.document_costs.values())
        
        return {
            "total_documents_processed": total_documents,
            "total_cost_eur": total_cost,
            "average_cost_per_document": total_cost / total_documents if total_documents > 0 else 0,
            "max_cost_per_document": self.max_cost_per_document
        }


# Global instance
document_cost_tracker = DocumentCostTracker()
