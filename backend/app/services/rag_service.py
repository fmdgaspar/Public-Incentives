"""
RAG (Retrieval-Augmented Generation) service for chatbot functionality.
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

import structlog
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.app.models.incentive import Incentive, IncentiveEmbedding
from backend.app.models.company import Company, CompanyEmbedding
from backend.app.services.openai_client import ManagedOpenAIClient
from backend.app.services.document_cost_tracker import document_cost_tracker

logger = structlog.get_logger()


@dataclass
class RAGResult:
    """Result of RAG query."""
    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    cost_eur: float


class RAGService:
    """Service for Retrieval-Augmented Generation."""
    
    def __init__(self, openai_client: Optional[ManagedOpenAIClient] = None):
        """
        Initialize RAG service.
        
        Args:
            openai_client: OpenAI client for LLM operations
        """
        self.client = openai_client or ManagedOpenAIClient()
        
        # RAG prompt template
        self.rag_prompt = """Tu és um assistente especializado em incentivos públicos portugueses e empresas.

CONTEXTO RETRIEVED:
{context}

PERGUNTA DO UTILIZADOR:
{question}

INSTRUÇÕES:
1. Responde à pergunta baseando-te APENAS no contexto fornecido
2. Se não tiveres informação suficiente, diz "Não tenho informação suficiente para responder a esta pergunta"
3. Inclui citações específicas dos documentos quando relevante
4. Seja preciso e útil
5. Responde em português

RESPOSTA:"""

    def _retrieve_relevant_documents(
        self,
        db: Session,
        query: str,
        max_docs: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant documents using vector similarity.
        
        Args:
            db: Database session
            query: User query
            max_docs: Maximum number of documents to retrieve
            
        Returns:
            List of relevant documents with metadata
        """
        try:
            # Generate query embedding
            query_embedding_result = self.client.create_embedding(
                text=query,
                model="text-embedding-3-small",
                document_id=f"rag_query_{hash(query) % 1000000}"
            )
            
            if not query_embedding_result or not query_embedding_result.get('embedding'):
                logger.error("failed_to_generate_query_embedding")
                return []
            
            query_embedding = query_embedding_result['embedding']
            query_emb_list = query_embedding.tolist() if hasattr(query_embedding, 'tolist') else list(query_embedding)
            embedding_str = '[' + ','.join(map(str, query_emb_list)) + ']'
            
            # Search in incentives
            incentive_sql = f"""
                SELECT 
                    i.incentive_id, i.title, i.description, i.ai_description,
                    i.publication_date, i.start_date, i.end_date, i.total_budget,
                    i.source_link,
                    (1 - cosine_distance(ie.embedding, '{embedding_str}'::vector)) as similarity
                FROM incentives i
                JOIN incentive_embeddings ie ON i.incentive_id = ie.incentive_id
                WHERE ie.embedding IS NOT NULL
                ORDER BY similarity DESC
                LIMIT {max_docs}
            """
            
            incentive_results = db.execute(text(incentive_sql))
            
            # Search in companies
            company_sql = f"""
                SELECT 
                    c.company_id, c.name, c.cae_codes, c.size, c.district,
                    c.raw,
                    (1 - cosine_distance(ce.embedding, '{embedding_str}'::vector)) as similarity
                FROM companies c
                JOIN company_embeddings ce ON c.company_id = ce.company_id
                WHERE ce.embedding IS NOT NULL
                ORDER BY similarity DESC
                LIMIT {max_docs}
            """
            
            company_results = db.execute(text(company_sql))
            
            # Combine and format results
            documents = []
            
            for row in incentive_results:
                doc = {
                    'type': 'incentive',
                    'id': row.incentive_id,
                    'title': row.title,
                    'content': f"{row.title}\n{row.description or ''}",
                    'metadata': {
                        'publication_date': str(row.publication_date) if row.publication_date else None,
                        'start_date': str(row.start_date) if row.start_date else None,
                        'end_date': str(row.end_date) if row.end_date else None,
                        'total_budget': str(row.total_budget) if row.total_budget else None,
                        'source_link': row.source_link,
                        'ai_description': row.ai_description
                    },
                    'similarity': row.similarity
                }
                documents.append(doc)
            
            for row in company_results:
                doc = {
                    'type': 'company',
                    'id': row.company_id,
                    'title': row.name,
                    'content': f"{row.name}\n{row.raw.get('description', '') if row.raw else ''}",
                    'metadata': {
                        'cae_codes': row.cae_codes,
                        'size': row.size,
                        'district': row.district,
                        'raw': row.raw
                    },
                    'similarity': row.similarity
                }
                documents.append(doc)
            
            # Sort by similarity and limit
            documents.sort(key=lambda x: x['similarity'], reverse=True)
            documents = documents[:max_docs]
            
            logger.info("documents_retrieved", 
                       query=query[:50],
                       count=len(documents),
                       avg_similarity=sum(d['similarity'] for d in documents) / len(documents) if documents else 0)
            
            return documents
            
        except Exception as e:
            logger.error("document_retrieval_failed", error=str(e), exc_info=True)
            return []

    def _generate_answer(
        self,
        query: str,
        documents: List[Dict[str, Any]]
    ) -> Tuple[str, float]:
        """
        Generate answer using retrieved documents.
        
        Args:
            query: User query
            documents: Retrieved documents
            
        Returns:
            Tuple of (answer, confidence)
        """
        if not documents:
            return "Não tenho informação suficiente para responder a esta pergunta.", 0.0
        
        # Prepare context
        context_parts = []
        for i, doc in enumerate(documents, 1):
            context_part = f"DOCUMENTO {i} ({doc['type'].upper()}):\n"
            context_part += f"Título: {doc['title']}\n"
            context_part += f"Conteúdo: {doc['content'][:500]}...\n"
            if doc['metadata']:
                context_part += f"Metadados: {json.dumps(doc['metadata'], ensure_ascii=False, indent=2)}\n"
            context_parts.append(context_part)
        
        context = "\n\n".join(context_parts)
        
        # Generate answer
        prompt = self.rag_prompt.format(
            context=context,
            question=query
        )
        
        try:
            response = self.client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="gpt-4o-mini",
                max_tokens=800,
                document_id=f"rag_answer_{hash(query) % 1000000}"
            )
            
            if not response or not response.get('content'):
                return "Erro ao gerar resposta.", 0.0
            
            answer = response['content'].strip()
            
            # Calculate confidence based on document similarities
            avg_similarity = sum(doc['similarity'] for doc in documents) / len(documents)
            confidence = min(avg_similarity * 1.2, 1.0)  # Boost confidence slightly
            
            return answer, confidence
            
        except Exception as e:
            logger.error("answer_generation_failed", error=str(e), exc_info=True)
            return "Erro ao gerar resposta.", 0.0

    def query(
        self,
        db: Session,
        question: str,
        max_documents: int = 5
    ) -> RAGResult:
        """
        Process a RAG query.
        
        Args:
            db: Database session
            question: User question
            max_documents: Maximum documents to retrieve
            
        Returns:
            RAGResult with answer, sources, and metadata
        """
        logger.info("rag_query_started", question=question[:50])
        
        # Retrieve relevant documents
        documents = self._retrieve_relevant_documents(db, question, max_documents)
        
        # Generate answer
        answer, confidence = self._generate_answer(question, documents)
        
        # Prepare sources
        sources = []
        for doc in documents:
            source = {
                'type': doc['type'],
                'id': doc['id'],
                'title': doc['title'],
                'similarity': doc['similarity'],
                'metadata': doc['metadata']
            }
            sources.append(source)
        
        # Calculate cost (approximate)
        cost_eur = 0.0
        if documents:
            # Estimate cost based on typical RAG operations
            cost_eur = 0.001  # ~1 cent per query
        
        result = RAGResult(
            answer=answer,
            sources=sources,
            confidence=confidence,
            cost_eur=cost_eur
        )
        
        logger.info("rag_query_complete",
                   question=question[:50],
                   answer_length=len(answer),
                   sources_count=len(sources),
                   confidence=confidence,
                   cost_eur=cost_eur)
        
        return result
