"""
Matching service for finding best companies for each incentive.

Implements a hybrid scoring approach:
1. Deterministic filters (CAE, location, size) - apply penalties
2. Vector similarity (cosine) - 55% weight
3. BM25 text search - 25% weight
4. LLM re-ranking (top-20) - 20% weight

Final score: (0.55 * cosine + 0.25 * bm25 + 0.20 * llm) * penalties
"""

import numpy as np
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy.orm import Session
from sqlalchemy import func, text, cast
from sqlalchemy.types import String
from rank_bm25 import BM25Okapi

from backend.app.models.incentive import Incentive, IncentiveEmbedding
from backend.app.models.company import Company, CompanyEmbedding
from backend.app.services.openai_client import ManagedOpenAIClient

logger = structlog.get_logger()


@dataclass
class MatchResult:
    """Result of matching a company to an incentive."""
    company_id: str
    company_name: str
    score: float
    explanation: str
    penalties_applied: Dict[str, float]
    component_scores: Dict[str, float]


class MatchingService:
    """Service for matching companies to incentives."""
    
    def __init__(
        self,
        openai_client: Optional[ManagedOpenAIClient] = None,
        weights: Optional[Dict[str, float]] = None
    ):
        """
        Initialize matching service.
        
        Args:
            openai_client: OpenAI client for LLM re-ranking
            weights: Custom weights for scoring components
        """
        self.client = openai_client or ManagedOpenAIClient()
        
        # Weights emphasizing LLM as specified in roadmap
        self.weights = weights or {
            'vector': 0.50,  # Reduced to give more weight to LLM
            'bm25': 0.20,    # Keep moderate weight
            'llm': 0.30      # Increased significantly - LLM is key for matching
        }
        
        # Adjusted penalty factors (less severe)
        self.penalties = {
            'size_mismatch': 0.8,  # Less severe: 0.6 -> 0.8
            'cae_mismatch': 0.7,   # Less severe: 0.5 -> 0.7
            'geo_mismatch': 0.9    # Much less severe: 0.7 -> 0.9
        }
    
    def _apply_deterministic_filters(
        self,
        incentive: Incentive,
        company: Company
    ) -> Tuple[float, Dict[str, float]]:
        """
        Apply deterministic filters and calculate penalty.
        
        Args:
            incentive: Incentive to match
            company: Company to evaluate
            
        Returns:
            Tuple of (penalty_multiplier, penalties_applied)
        """
        penalty = 1.0
        penalties_applied = {}
        
        ai_desc = incentive.ai_description or {}
        
        # 1. Company size filter
        if ai_desc.get('company_size'):
            allowed_sizes = ai_desc['company_size']
            
            # Skip penalty if "não aplicável"
            if 'não aplicável' not in [s.lower() for s in allowed_sizes]:
                if company.size and company.size not in allowed_sizes:
                    penalty *= self.penalties['size_mismatch']
                    penalties_applied['size'] = self.penalties['size_mismatch']
                    logger.debug("size_penalty_applied",
                               company_id=company.company_id,
                               company_size=company.size,
                               required_sizes=allowed_sizes)
        
        # 2. CAE codes filter
        incentive_caes = set(ai_desc.get('caes', []))
        company_caes = set(company.cae_codes or [])
        
        if incentive_caes and company_caes:
            # Check for intersection
            if not incentive_caes.intersection(company_caes):
                penalty *= self.penalties['cae_mismatch']
                penalties_applied['cae'] = self.penalties['cae_mismatch']
                logger.debug("cae_penalty_applied",
                           company_id=company.company_id,
                           company_caes=list(company_caes),
                           required_caes=list(incentive_caes))
        
        # 3. Geographic location filter (improved)
        geo_location = ai_desc.get('geographic_location', '').lower()
        if geo_location and company.district:
            company_district = company.district.lower()
            
            # More intelligent geographic matching
            geo_match = False
            
            # Direct district match
            if company_district in geo_location:
                geo_match = True
            
            # Check for common geographic terms
            elif any(term in geo_location for term in ['portugal', 'nacional', 'todo o país', 'todas as regiões']):
                geo_match = True
            
            # Check for regional matches (e.g., "Algarve" matches "Faro")
            elif 'algarve' in geo_location and company_district == 'faro':
                geo_match = True
            elif 'centro' in geo_location and company_district in ['coimbra', 'leiria', 'aveiro']:
                geo_match = True
            elif 'norte' in geo_location and company_district in ['porto', 'braga', 'vila real']:
                geo_match = True
            elif 'lisboa' in geo_location and company_district in ['lisboa', 'setúbal']:
                geo_match = True
            
            # Apply penalty only if no match found
            if not geo_match:
                penalty *= self.penalties['geo_mismatch']
                penalties_applied['geo'] = self.penalties['geo_mismatch']
                logger.debug("geo_penalty_applied",
                           company_id=company.company_id,
                           company_district=company.district,
                           required_location=geo_location)
        
        return penalty, penalties_applied
    
    def _calculate_cosine_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Cosine similarity (0-1)
        """
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # Normalize vectors
        vec1_norm = vec1 / np.linalg.norm(vec1)
        vec2_norm = vec2 / np.linalg.norm(vec2)
        
        # Calculate cosine similarity
        similarity = np.dot(vec1_norm, vec2_norm)
        
        # Ensure it's in [0, 1] range
        return float((similarity + 1) / 2)
    
    def _calculate_bm25_score(
        self,
        incentive: Incentive,
        company: Company,
        bm25_index: Optional[BM25Okapi] = None
    ) -> float:
        """
        Calculate BM25 score for text matching.
        
        Args:
            incentive: Incentive to match
            company: Company to evaluate
            bm25_index: Pre-computed BM25 index (optional)
            
        Returns:
            Normalized BM25 score (0-1)
        """
        # Create search query from incentive
        query_parts = [incentive.title]
        
        if incentive.description:
            query_parts.append(incentive.description)
        
        if incentive.ai_description:
            ai_desc = incentive.ai_description
            if ai_desc.get('investment_objectives'):
                query_parts.extend(ai_desc['investment_objectives'])
            if ai_desc.get('specific_purposes'):
                query_parts.extend(ai_desc['specific_purposes'])
            if ai_desc.get('caes'):
                query_parts.extend(ai_desc['caes'])
            if ai_desc.get('eligibility_criteria'):
                query_parts.extend(ai_desc['eligibility_criteria'][:3])  # Top 3 criteria
        
        query_text = ' '.join(query_parts).lower()
        query_tokens = self._tokenize_text(query_text)
        
        # Create document from company
        doc_parts = [company.name]
        
        if company.cae_codes:
            doc_parts.extend(company.cae_codes)
        
        if company.raw and company.raw.get('description'):
            doc_parts.append(company.raw['description'])
        
        if company.district:
            doc_parts.append(company.district)
        
        doc_text = ' '.join(doc_parts).lower()
        doc_tokens = self._tokenize_text(doc_text)
        
        # Calculate improved BM25-like score
        query_set = set(query_tokens)
        doc_set = set(doc_tokens)
        
        intersection = query_set.intersection(doc_set)
        
        if not query_set:
            return 0.0
        
        # Calculate term frequency in document
        doc_token_counts = {}
        for token in doc_tokens:
            doc_token_counts[token] = doc_token_counts.get(token, 0) + 1
        
        # Calculate BM25-like score with term frequency
        score = 0.0
        for token in intersection:
            tf = doc_token_counts.get(token, 0)
            if tf > 0:
                # Simple BM25 formula: tf / (tf + k1 * (1 - b + b * (doc_len / avg_doc_len)))
                # Simplified version with k1=1.2, b=0.75, avg_doc_len=50
                doc_len = len(doc_tokens)
                avg_doc_len = 50
                k1, b = 1.2, 0.75
                
                idf = 1.0  # Simplified IDF
                bm25_term = (tf * idf) / (tf + k1 * (1 - b + b * (doc_len / avg_doc_len)))
                score += bm25_term
        
        # Normalize by query length
        normalized_score = score / len(query_set) if query_set else 0.0
        
        # Apply sigmoid to get 0-1 range
        import math
        sigmoid_score = 1 / (1 + math.exp(-normalized_score * 5))  # Scale factor of 5
        
        return float(sigmoid_score)
    
    def _tokenize_text(self, text: str) -> List[str]:
        """
        Tokenize text for BM25 scoring.
        
        Args:
            text: Text to tokenize
            
        Returns:
            List of tokens
        """
        import re
        
        # Remove punctuation and split
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        tokens = text.split()
        
        # Remove very short tokens and common words
        stop_words = {'de', 'da', 'do', 'em', 'para', 'com', 'por', 'que', 'e', 'a', 'o', 'as', 'os', 'um', 'uma', 'uns', 'umas'}
        
        filtered_tokens = []
        for token in tokens:
            if len(token) > 2 and token not in stop_words:
                filtered_tokens.append(token)
        
        return filtered_tokens
    
    def _llm_rerank(
        self,
        incentive: Incentive,
        companies: List[Company],
        document_id: Optional[str] = None
    ) -> Dict[str, Tuple[float, str]]:
        """
        Use LLM to re-rank and explain matches.
        
        Args:
            incentive: Incentive to match
            companies: List of companies to evaluate
            document_id: Document ID for cost tracking
            
        Returns:
            Dict mapping company_id to (score, explanation)
        """
        if not companies:
            return {}
        
        # Create prompt for LLM
        incentive_desc = f"""
Incentivo: {incentive.title}
Descrição: {incentive.description or 'N/A'}
"""
        
        if incentive.ai_description:
            ai_desc = incentive.ai_description
            if ai_desc.get('investment_objectives'):
                incentive_desc += f"\nObjetivos: {', '.join(ai_desc['investment_objectives'])}"
            if ai_desc.get('eligibility_criteria'):
                incentive_desc += f"\nCritérios: {', '.join(ai_desc['eligibility_criteria'][:3])}"
        
        companies_desc = []
        for i, company in enumerate(companies[:20], 1):  # Limit to top 20
            comp_desc = f"{i}. {company.name}"
            if company.cae_codes:
                comp_desc += f" (CAE: {', '.join(company.cae_codes[:3])})"
            if company.district:
                comp_desc += f" - {company.district}"
            companies_desc.append(comp_desc)
        
        prompt = f"""Avalia a adequação destas empresas ao seguinte incentivo.

{incentive_desc}

Empresas:
{chr(10).join(companies_desc)}

Para cada empresa, atribui:
1. Score de 0-10 (0=inadequada, 10=perfeita)
2. Breve explicação (2-3 palavras)

Responde em JSON:
{{
  "rankings": [
    {{"company_index": 1, "score": 8, "reason": "Área relevante, localização adequada"}},
    ...
  ]
}}
"""
        
        try:
            result = self.client.chat_completion(
                messages=[
                    {"role": "system", "content": "Você é um especialista em matching de incentivos públicos com empresas."},
                    {"role": "user", "content": prompt}
                ],
                model="gpt-4o-mini",
                temperature=0.0,
                response_format={"type": "json_object"},
                document_id=document_id
            )
            
            import json
            response_data = json.loads(result["response"])
            
            # Map results back to companies
            results = {}
            for ranking in response_data.get("rankings", []):
                idx = ranking.get("company_index", 0) - 1
                if 0 <= idx < len(companies):
                    company = companies[idx]
                    score = ranking.get("score", 5) / 10.0  # Normalize to 0-1
                    reason = ranking.get("reason", "")
                    results[company.company_id] = (score, reason)
            
            logger.info("llm_reranking_complete",
                       incentive_id=incentive.incentive_id,
                       companies_evaluated=len(companies),
                       cost_eur=result.get("cost_eur", 0))
            
            return results
            
        except Exception as e:
            logger.error("llm_reranking_failed",
                        incentive_id=incentive.incentive_id,
                        error=str(e),
                        exc_info=True)
            return {}
    
    def find_matches(
        self,
        db: Session,
        incentive_id: str,
        top_k: int = 5,
        candidate_pool: int = 100,
        use_llm: bool = True
    ) -> List[MatchResult]:
        """
        Find top matching companies for an incentive.
        
        Args:
            db: Database session
            incentive_id: ID of incentive to match
            top_k: Number of top matches to return
            candidate_pool: Number of candidates to consider
            use_llm: Whether to use LLM for re-ranking
            
        Returns:
            List of MatchResult objects
        """
        # Load incentive and its embedding
        incentive = db.query(Incentive).filter(
            Incentive.incentive_id == incentive_id
        ).first()
        
        if not incentive:
            logger.error("incentive_not_found", incentive_id=incentive_id)
            return []
        
        incentive_embedding = db.query(IncentiveEmbedding).filter(
            IncentiveEmbedding.incentive_id == incentive_id
        ).first()
        
        if not incentive_embedding or incentive_embedding.embedding is None:
            logger.error("incentive_embedding_not_found", incentive_id=incentive_id)
            return []
        
        # Get candidate companies using vector similarity
        # Using raw SQL for pgvector compatibility
        incentive_emb_list = incentive_embedding.embedding.tolist() if hasattr(incentive_embedding.embedding, 'tolist') else list(incentive_embedding.embedding)
        embedding_str = '[' + ','.join(map(str, incentive_emb_list)) + ']'
        
        # Use raw SQL query for vector similarity
        sql_query = text("""
            SELECT 
                c.company_id, c.name, c.cae_codes, c.size, c.district, c.county, c.parish, c.website, c.raw,
                ce.embedding,
                (1 - cosine_distance(ce.embedding, :embedding)) as vector_similarity
            FROM companies c
            JOIN company_embeddings ce ON c.company_id = ce.company_id
            WHERE ce.embedding IS NOT NULL
            ORDER BY vector_similarity DESC
            LIMIT :limit
        """)
        
        result = db.execute(sql_query, {'embedding': embedding_str, 'limit': candidate_pool})
        
        # Convert results to our expected format
        candidates = []
        for row in result:
            # Create mock objects for compatibility
            company = Company(
                company_id=row.company_id,
                name=row.name,
                cae_codes=row.cae_codes,
                size=row.size,
                district=row.district,
                county=row.county,
                parish=row.parish,
                website=row.website,
                raw=row.raw
            )
            
            embedding = CompanyEmbedding(
                company_id=row.company_id,
                embedding=row.embedding
            )
            
            candidates.append((company, embedding, row.vector_similarity))
        
        logger.info("candidates_retrieved",
                   incentive_id=incentive_id,
                   candidates_count=len(candidates))
        
        # Calculate scores for each candidate
        scored_candidates = []
        
        for company, embedding, vector_sim in candidates:
            # 1. Apply deterministic filters
            penalty, penalties_applied = self._apply_deterministic_filters(
                incentive, company
            )
            
            # 2. Vector similarity (already calculated)
            vector_score = float(vector_sim)
            
            # 3. BM25 score
            bm25_score = self._calculate_bm25_score(incentive, company)
            
            # Store component scores
            component_scores = {
                'vector': vector_score,
                'bm25': bm25_score,
                'penalty': penalty
            }
            
            # Calculate preliminary score (without LLM)
            prelim_score = (
                self.weights['vector'] * vector_score +
                self.weights['bm25'] * bm25_score
            ) * penalty
            
            scored_candidates.append({
                'company': company,
                'score': prelim_score,
                'component_scores': component_scores,
                'penalties_applied': penalties_applied
            })
        
        # Sort by preliminary score
        scored_candidates.sort(key=lambda x: x['score'], reverse=True)
        
        # 4. LLM re-ranking for top candidates
        llm_scores = {}
        if use_llm and scored_candidates:
            top_candidates = [c['company'] for c in scored_candidates[:20]]
            document_id = f"rerank_{incentive_id}"
            llm_scores = self._llm_rerank(incentive, top_candidates, document_id)
        
        # Combine all scores
        final_results = []
        
        for candidate in scored_candidates[:top_k]:
            company = candidate['company']
            component_scores = candidate['component_scores']
            
            # Add LLM score if available
            llm_score, llm_reason = llm_scores.get(company.company_id, (0.5, ""))
            component_scores['llm'] = llm_score
            
            # Calculate final score
            final_score = (
                self.weights['vector'] * component_scores['vector'] +
                self.weights['bm25'] * component_scores['bm25'] +
                (self.weights['llm'] * llm_score if use_llm else 0)
            ) * component_scores['penalty']
            
            # Create explanation
            explanation_parts = []
            if llm_reason:
                explanation_parts.append(llm_reason)
            if candidate['penalties_applied']:
                penalties_str = ", ".join(
                    f"{k}: {v:.0%}" for k, v in candidate['penalties_applied'].items()
                )
                explanation_parts.append(f"Penalizações: {penalties_str}")
            
            explanation = ". ".join(explanation_parts) if explanation_parts else "Match baseado em similaridade"
            
            result = MatchResult(
                company_id=company.company_id,
                company_name=company.name,
                score=final_score,
                explanation=explanation,
                penalties_applied=candidate['penalties_applied'],
                component_scores=component_scores
            )
            
            final_results.append(result)
        
        # Sort final results by score (descending) - best matches first
        final_results.sort(key=lambda x: x.score, reverse=True)
        
        logger.info("matching_complete",
                   incentive_id=incentive_id,
                   matches_found=len(final_results),
                   top_score=final_results[0].score if final_results else 0)
        
        return final_results

