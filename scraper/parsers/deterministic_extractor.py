"""
Extrator determinístico de informação de incentivos.

Tenta extrair datas e orçamentos usando regex e parsing de HTML,
antes de recorrer à LLM.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, Any
import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger()


class DeterministicExtractor:
    """Extrai informação de forma determinística de HTML."""
    
    # Padrões de data em português
    DATE_PATTERNS = [
        # DD/MM/YYYY ou DD-MM-YYYY
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
        # YYYY-MM-DD
        r'(\d{4})-(\d{1,2})-(\d{1,2})',
        # DD de MMMM de YYYY
        r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',
    ]
    
    # Mapeamento de meses em português
    MONTHS_PT = {
        'janeiro': 1, 'fevereiro': 2, 'março': 3, 'abril': 4,
        'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8,
        'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12
    }
    
    # Padrões para orçamento
    BUDGET_PATTERNS = [
        # X milhões de euros
        r'(\d+(?:[.,]\d+)?)\s*(?:milhões?|M)\s*(?:de\s*)?(?:euros?|€)',
        # X mil euros
        r'(\d+(?:[.,]\d+)?)\s*mil\s*(?:de\s*)?(?:euros?|€)',
        # €X.XXX.XXX ou € X XXX XXX
        r'€\s*(\d+(?:[.,\s]\d{3})*(?:[.,]\d{2})?)',
        # X.XXX.XXX € ou X XXX XXX €
        r'(\d+(?:[.,\s]\d{3})*(?:[.,]\d{2})?)\s*€',
        # Dotação: X
        r'(?:dotação|orçamento|verba)[\s:]+(\d+(?:[.,]\d+)?)\s*(?:milhões?|mil|€)',
    ]
    
    def __init__(self):
        """Initialize extractor."""
        pass
    
    def extract_dates_from_text(self, text: str) -> Dict[str, Optional[date]]:
        """
        Extrai datas de um texto.
        
        Args:
            text: Texto para extrair datas
            
        Returns:
            Dict com publication_date, start_date, end_date
        """
        result = {
            'publication_date': None,
            'start_date': None,
            'end_date': None
        }
        
        # Procurar por contexto de publicação
        pub_patterns = [
            r'publicado\s+(?:em|a|no|na)\s+([^.\n]{5,30})',
            r'data\s+de\s+publicação[\s:]+([^.\n]{5,30})',
            r'aviso\s+de\s+abertura[\s:]*([^.\n]{5,30})',
        ]
        
        for pattern in pub_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                extracted_date = self._parse_date_string(date_str)
                if extracted_date:
                    result['publication_date'] = extracted_date
                    logger.debug("extracted_publication_date", date=extracted_date.isoformat())
                    break
        
        # Procurar por datas de início
        start_patterns = [
            r'(?:início|abertura|começa(?:m)?)\s+(?:das?\s+)?(?:candidaturas?|submissões?)[\s:]+([^.\n]{5,30})',
            r'(?:candidaturas?|submissões?)\s+(?:a\s+)?(?:partir\s+)?de[\s:]+([^.\n]{5,30})',
            r'prazo\s+de\s+candidatura(?:s)?[\s:]+de\s+([^.\n]{5,30})\s+até',
        ]
        
        for pattern in start_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                extracted_date = self._parse_date_string(date_str)
                if extracted_date:
                    result['start_date'] = extracted_date
                    logger.debug("extracted_start_date", date=extracted_date.isoformat())
                    break
        
        # Procurar por datas de fim
        end_patterns = [
            r'(?:fim|encerramento|prazo|término|limite)\s+(?:das?\s+)?(?:candidaturas?|submissões?)[\s:]+([^.\n]{5,30})',
            r'(?:candidaturas?|submissões?)\s+até[\s:]+([^.\n]{5,30})',
            r'até[\s:]+([^.\n]{5,30})',
            r'prazo\s+de\s+candidatura(?:s)?[\s:]+.*?até[\s:]+([^.\n]{5,30})',
        ]
        
        for pattern in end_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                extracted_date = self._parse_date_string(date_str)
                if extracted_date:
                    result['end_date'] = extracted_date
                    logger.debug("extracted_end_date", date=extracted_date.isoformat())
                    break
        
        return result
    
    def _parse_date_string(self, date_str: str) -> Optional[date]:
        """
        Parse uma string de data.
        
        Args:
            date_str: String com data
            
        Returns:
            date object ou None
        """
        date_str = date_str.strip()
        
        # Tentar padrões numéricos
        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, date_str)
            if match:
                try:
                    groups = match.groups()
                    
                    # DD/MM/YYYY ou DD-MM-YYYY
                    if len(groups) == 3 and len(groups[2]) == 4:
                        if len(groups[0]) <= 2:  # Começa com dia
                            day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                        else:  # YYYY-MM-DD
                            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                        
                        return date(year, month, day)
                    
                except (ValueError, IndexError) as e:
                    logger.debug("date_parse_failed", date_str=date_str, error=str(e))
                    continue
        
        # Tentar formato com mês por extenso
        for month_name, month_num in self.MONTHS_PT.items():
            if month_name in date_str.lower():
                # Procurar dia e ano
                day_match = re.search(r'(\d{1,2})', date_str)
                year_match = re.search(r'(\d{4})', date_str)
                
                if day_match and year_match:
                    try:
                        day = int(day_match.group(1))
                        year = int(year_match.group(1))
                        return date(year, month_num, day)
                    except ValueError:
                        continue
        
        return None
    
    def extract_budget_from_text(self, text: str) -> Optional[Decimal]:
        """
        Extrai orçamento/budget de um texto.
        
        Args:
            text: Texto para extrair orçamento
            
        Returns:
            Decimal com valor em euros ou None
        """
        for pattern in self.BUDGET_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            
            for match in matches:
                try:
                    value_str = match.group(1)
                    
                    # Normalizar número (remover espaços, trocar vírgulas)
                    value_str = value_str.replace(' ', '').replace('.', '').replace(',', '.')
                    value = Decimal(value_str)
                    
                    # Verificar se está em milhões ou milhares
                    context = text[max(0, match.start()-50):match.end()+50].lower()
                    
                    if 'milhões' in context or 'milhão' in context or ' m ' in context:
                        value = value * 1_000_000
                    elif 'mil' in context and 'milhões' not in context:
                        value = value * 1_000
                    
                    logger.debug("extracted_budget", value=float(value))
                    return value
                    
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def extract_from_html(self, html: str) -> Dict[str, Any]:
        """
        Extrai informação completa de HTML.
        
        Args:
            html: HTML da página
            
        Returns:
            Dict com campos extraídos
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extrair texto limpo
        text = soup.get_text()
        
        # Extrair datas
        dates = self.extract_dates_from_text(text)
        
        # Extrair orçamento
        budget = self.extract_budget_from_text(text)
        
        result = {
            **dates,
            'total_budget': budget
        }
        
        logger.info("deterministic_extraction_complete",
                   has_pub_date=result['publication_date'] is not None,
                   has_start_date=result['start_date'] is not None,
                   has_end_date=result['end_date'] is not None,
                   has_budget=result['total_budget'] is not None)
        
        return result

