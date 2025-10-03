"""
LLM-based extractor for structured incentive data.

Extracts structured JSON from incentive descriptions using GPT-4o-mini.
"""

import json
from typing import Optional, List, Literal
from datetime import date
from decimal import Decimal

import structlog
from pydantic import BaseModel, Field, ValidationError

# Import from backend (will need to adjust Python path)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.services.openai_client import ManagedOpenAIClient, BudgetExceededError

logger = structlog.get_logger()


class AIDescription(BaseModel):
    """
    Structured description of incentive extracted by AI.
    
    This matches the JSON schema required for the ai_description field.
    """
    
    caes: List[str] = Field(
        default_factory=list,
        description="CAE codes applicable to this incentive (e.g., ['8413', '8520'])"
    )
    
    geographic_location: str = Field(
        default="",
        description="Geographic location or regions where incentive applies (e.g., 'Lisboa, Porto' or 'Todo o país')"
    )
    
    company_size: List[Literal["micro", "pme", "grande", "não aplicável"]] = Field(
        default_factory=list,
        description="Company sizes eligible for this incentive"
    )
    
    investment_objectives: List[str] = Field(
        default_factory=list,
        description="Investment objectives or goals (e.g., 'Eficiência energética', 'Digitalização')"
    )
    
    specific_purposes: List[str] = Field(
        default_factory=list,
        description="Specific purposes or use cases (e.g., 'Painéis solares', 'Software ERP')"
    )
    
    eligibility_criteria: List[str] = Field(
        default_factory=list,
        description="Eligibility criteria or requirements (e.g., 'Sede em Portugal', 'Menos de 250 colaboradores')"
    )
    
    publication_date: Optional[date] = Field(
        default=None,
        description="Publication date of the incentive (extract from text if available, format: YYYY-MM-DD)"
    )
    
    start_date: Optional[date] = Field(
        default=None,
        description="Start date for applications (extract from text if available, format: YYYY-MM-DD)"
    )
    
    end_date: Optional[date] = Field(
        default=None,
        description="End date for applications (extract from text if available, format: YYYY-MM-DD)"
    )
    
    total_budget: Optional[Decimal] = Field(
        default=None,
        description="Total budget available for this incentive (extract from text if available, in euros)"
    )
    
    class Config:
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
            Decimal: lambda v: float(v) if v else None,
        }
        json_schema_extra = {
            "example": {
                "caes": ["8413", "8520", "8517"],
                "geographic_location": "Cantanhede, Figueira da Foz, Lisboa",
                "company_size": ["pme", "micro"],
                "investment_objectives": ["Eficiência energética", "Energias renováveis"],
                "specific_purposes": ["Painéis fotovoltaicos", "Sistemas de aquecimento eficiente"],
                "eligibility_criteria": ["Empresas com sede em Portugal", "Investimento mínimo de €10.000"],
                "publication_date": "2024-03-15",
                "start_date": "2024-04-01",
                "end_date": "2024-06-30",
                "total_budget": 2000000.00
            }
        }


EXTRACTION_SYSTEM_PROMPT = """Você é um assistente especializado em analisar documentos de incentivos públicos portugueses.

Sua tarefa é extrair informação estruturada de descrições de incentivos e retornar APENAS um objeto JSON válido.

O JSON deve seguir EXATAMENTE este schema:
{
  "caes": ["código CAE 1", "código CAE 2", ...],
  "geographic_location": "localização ou regiões aplicáveis",
  "company_size": ["micro" | "pme" | "grande" | "não aplicável"],
  "investment_objectives": ["objetivo 1", "objetivo 2", ...],
  "specific_purposes": ["finalidade específica 1", ...],
  "eligibility_criteria": ["critério 1", "critério 2", ...],
  "publication_date": "YYYY-MM-DD ou null",
  "start_date": "YYYY-MM-DD ou null",
  "end_date": "YYYY-MM-DD ou null",
  "total_budget": número_em_euros_ou_null
}

REGRAS IMPORTANTES:
1. Retorne APENAS o JSON, sem texto adicional antes ou depois
2. Use valores vazios ([],  "", null) se a informação não estiver disponível
3. CAE codes devem ser strings de 4-5 dígitos (ex: "8413", "47190")
4. company_size só pode conter: "micro", "pme", "grande", ou "não aplicável"
5. Se não mencionar tamanho de empresa, use ["não aplicável"]
6. Seja específico mas conciso nas descrições
7. Para localização, use nomes de cidades/regiões separados por vírgula

ATENÇÃO ESPECIAL - DATAS E ORÇAMENTO:
8. publication_date: Procure ATENTAMENTE por datas de publicação, aviso, ou lançamento do programa
   - Termos comuns: "publicado em", "aviso de", "data de publicação", "lançado em"
   - Formato: YYYY-MM-DD (ex: "2024-03-15")
   
9. start_date: Procure ATENTAMENTE por data de INÍCIO de candidaturas/submissões
   - Termos comuns: "início", "abertura", "candidaturas a partir de", "submissões começam"
   - Formato: YYYY-MM-DD
   
10. end_date: Procure ATENTAMENTE por data de ENCERRAMENTO/LIMITE de candidaturas
    - Termos comuns: "fim", "até", "prazo", "encerramento", "candidaturas até", "limite"
    - Formato: YYYY-MM-DD
    
11. total_budget: Procure ATENTAMENTE por valores de orçamento total, dotação, ou financiamento disponível
    - Termos comuns: "orçamento", "dotação", "milhões €", "milhares €", "verba", "financiamento"
    - Converta SEMPRE para número em euros (ex: "2 milhões €" = 2000000.0)
    - Se mencionar "mil", multiplique por 1000; se mencionar "milhão/milhões", multiplique por 1000000

EXEMPLOS:

Exemplo 1 - Incentivo com informação completa:
Input: "Apoio a PME do setor da construção (CAE 41, 42, 43) localizadas em Lisboa e Porto para eficiência energética. Investimento mínimo: €50.000. Publicado em 15/03/2024, candidaturas de 01/04/2024 a 30/06/2024. Orçamento total: €2.000.000."

Output:
{
  "caes": ["41", "42", "43"],
  "geographic_location": "Lisboa, Porto",
  "company_size": ["pme"],
  "investment_objectives": ["Eficiência energética"],
  "specific_purposes": ["Reabilitação energética de edifícios"],
  "eligibility_criteria": ["Investimento mínimo de €50.000", "Empresas do setor da construção"],
  "publication_date": "2024-03-15",
  "start_date": "2024-04-01",
  "end_date": "2024-06-30",
  "total_budget": 2000000.00
}

Exemplo 2 - Incentivo com informação limitada:
Input: "Financiamento para digitalização empresarial. Abertura de candidaturas em Janeiro."

Output:
{
  "caes": [],
  "geographic_location": "",
  "company_size": ["não aplicável"],
  "investment_objectives": ["Digitalização"],
  "specific_purposes": ["Transformação digital"],
  "eligibility_criteria": [],
  "publication_date": null,
  "start_date": null,
  "end_date": null,
  "total_budget": null
}

Agora processe o documento fornecido."""


class LLMExtractor:
    """Extractor using LLM for structured data extraction."""
    
    def __init__(
        self,
        openai_client: Optional[ManagedOpenAIClient] = None,
        max_retries: int = 2
    ):
        """
        Initialize LLM extractor.
        
        Args:
            openai_client: Managed OpenAI client (or create new one)
            max_retries: Maximum extraction retries on validation errors
        """
        self.client = openai_client or ManagedOpenAIClient(
            max_per_request_eur=0.30
        )
        self.max_retries = max_retries
    
    def extract(
        self,
        title: str,
        description: str,
        document_texts: Optional[List[str]] = None,
        document_urls: Optional[List[str]] = None,
        document_id: Optional[str] = None
    ) -> Optional[AIDescription]:
        """
        Extract structured data from incentive text.
        
        Args:
            title: Incentive title
            description: Incentive description
            document_texts: Optional list of document excerpts (already extracted)
            document_urls: Optional list of document URLs (will extract PDFs)
            
        Returns:
            AIDescription object or None if extraction fails
        """
        # Extract PDFs if URLs provided
        if document_urls and not document_texts:
            from scraper.extractors.pdf_extractor import PDFExtractor
            pdf_extractor = PDFExtractor()
            
            logger.info("extracting_pdfs", urls_count=len(document_urls))
            pdf_texts = pdf_extractor.get_all_pdfs_text_from_pages(
                document_urls,
                max_pdfs_per_page=2  # Limit to avoid too much context
            )
            
            if pdf_texts:
                document_texts = list(pdf_texts.values())
                logger.info("pdfs_extracted", count=len(document_texts))
        # Prepare context
        context_parts = [
            f"TÍTULO: {title}",
            f"DESCRIÇÃO: {description or '(não disponível)'}",
        ]
        
        if document_texts:
            context_parts.append("\nDOCUMENTOS ADICIONAIS:")
            for i, doc_text in enumerate(document_texts[:3], 1):  # Max 3 docs
                # Truncate each doc to 500 chars
                truncated = doc_text[:500] + ("..." if len(doc_text) > 500 else "")
                context_parts.append(f"\nDocumento {i}:\n{truncated}")
        
        context = "\n".join(context_parts)
        
        # Try extraction with retries
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "llm_extraction_attempt",
                    title=title[:50],
                    attempt=attempt,
                    context_length=len(context)
                )
                
                # Call LLM
                result = self.client.chat_completion(
                    messages=[
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": context}
                    ],
                    model="gpt-4o-mini",
                    temperature=0.0,
                    response_format={"type": "json_object"},
                    document_id=document_id
                )
                
                # Parse and validate
                response_text = result["response"]
                
                try:
                    json_data = json.loads(response_text)
                except json.JSONDecodeError as e:
                    logger.error("json_parse_error", error=str(e), response=response_text[:200])
                    
                    # Try to extract JSON from text
                    import re
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        json_data = json.loads(json_match.group(0))
                    else:
                        raise
                
                # Validate with Pydantic
                ai_desc = AIDescription(**json_data)
                
                logger.info(
                    "llm_extraction_success",
                    title=title[:50],
                    cost_eur=result["cost_eur"],
                    from_cache=result["from_cache"],
                    caes_found=len(ai_desc.caes),
                    criteria_found=len(ai_desc.eligibility_criteria)
                )
                
                return ai_desc
                
            except ValidationError as e:
                logger.warning(
                    "validation_error",
                    title=title[:50],
                    attempt=attempt,
                    error=str(e)
                )
                
                if attempt < self.max_retries:
                    # Add validation feedback to context
                    context += f"\n\n[ERRO DE VALIDAÇÃO: {str(e)}. Por favor corrija e retorne JSON válido.]"
                else:
                    logger.error("max_retries_reached", title=title[:50])
                    return None
            
            except BudgetExceededError as e:
                logger.error(
                    "budget_exceeded",
                    title=title[:50],
                    error=str(e)
                )
                # Don't retry on budget errors
                return None
            
            except Exception as e:
                logger.error(
                    "extraction_failed",
                    title=title[:50],
                    attempt=attempt,
                    error=str(e),
                    exc_info=True
                )
                
                if attempt >= self.max_retries:
                    return None
        
        return None
    
    def extract_batch(
        self,
        incentives: List[dict]
    ) -> List[tuple[str, Optional[AIDescription]]]:
        """
        Extract structured data for multiple incentives.
        
        Args:
            incentives: List of incentive dicts with 'incentive_id', 'title', 'description'
            
        Returns:
            List of (incentive_id, AIDescription or None) tuples
        """
        results = []
        
        for inc in incentives:
            incentive_id = inc.get("incentive_id")
            title = inc.get("title", "")
            description = inc.get("description", "")
            
            try:
                ai_desc = self.extract(title, description)
                results.append((incentive_id, ai_desc))
            except Exception as e:
                logger.error(
                    "batch_extraction_failed",
                    incentive_id=incentive_id,
                    error=str(e)
                )
                results.append((incentive_id, None))
        
        return results

