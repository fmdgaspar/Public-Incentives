#!/usr/bin/env python3
"""
Script to enhance incentive data using source HTML pages.

For incentives with missing fields (dates, budget), this script:
1. Loads the original HTML from data/raw/
2. Passes it to the LLM for extraction
3. Updates the database with extracted information
"""

import sys
import json
import re
from pathlib import Path
from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any

import structlog
from sqlalchemy import or_
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

load_dotenv()

from backend.app.db.session import SessionLocal
from backend.app.models.incentive import Incentive
from scraper.extractors.llm_extractor import LLMExtractor
from backend.app.services.openai_client import ManagedOpenAIClient
from backend.app.services.document_cost_tracker import document_cost_tracker

logger = structlog.get_logger()


def find_html_file(incentive_id: str, data_dir: Path = Path("data/raw")) -> Optional[Path]:
    """
    Find the HTML file for a given incentive ID.
    
    Args:
        incentive_id: The incentive ID
        data_dir: Directory containing raw HTML files
        
    Returns:
        Path to HTML file or None
    """
    # Look for files matching the pattern: {incentive_id}_*.html
    pattern = f"{incentive_id}_*.html"
    matching_files = list(data_dir.glob(pattern))
    
    if matching_files:
        # Return the most recent file (highest timestamp)
        return max(matching_files, key=lambda p: p.stat().st_mtime)
    
    return None


def extract_text_from_html(html_path: Path) -> str:
    """
    Extract clean text from HTML file.
    
    Args:
        html_path: Path to HTML file
        
    Returns:
        Extracted text
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style tags
    for script in soup(["script", "style", "nav", "footer", "header"]):
        script.decompose()
    
    # Get text
    text = soup.get_text()
    
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = '\n'.join(chunk for chunk in chunks if chunk)
    
    return text


def enhance_incentive(
    incentive: Incentive,
    llm_extractor: LLMExtractor,
    db: Session
) -> bool:
    """
    Enhance a single incentive with data from source HTML.
    
    Args:
        incentive: Incentive object to enhance
        llm_extractor: LLM extractor instance
        db: Database session
        
    Returns:
        True if any field was updated
    """
    # Find HTML file
    html_file = find_html_file(incentive.incentive_id)
    
    if not html_file:
        logger.warning("html_not_found", incentive_id=incentive.incentive_id)
        return False
    
    logger.info("processing_html", 
                incentive_id=incentive.incentive_id,
                html_file=str(html_file))
    
    # Extract text from HTML
    try:
        html_text = extract_text_from_html(html_file)
    except Exception as e:
        logger.error("html_extraction_failed",
                    incentive_id=incentive.incentive_id,
                    error=str(e))
        return False
    
    # Prepare document ID for cost tracking
    document_id = f"html_enhance_{incentive.incentive_id}"
    document_cost_tracker.reset_document(document_id)
    
    # Call LLM with HTML context
    try:
        ai_desc = llm_extractor.extract(
            title=incentive.title,
            description=incentive.description or "",
            document_texts=[html_text],  # Pass HTML as document text
            document_id=document_id
        )
        
        if not ai_desc:
            logger.warning("llm_extraction_failed", incentive_id=incentive.incentive_id)
            return False
        
        # Update only missing fields
        updated = False
        
        if not incentive.publication_date and ai_desc.publication_date:
            incentive.publication_date = ai_desc.publication_date
            updated = True
            logger.info("updated_publication_date",
                       incentive_id=incentive.incentive_id,
                       date=ai_desc.publication_date.isoformat())
        
        if not incentive.start_date and ai_desc.start_date:
            incentive.start_date = ai_desc.start_date
            updated = True
            logger.info("updated_start_date",
                       incentive_id=incentive.incentive_id,
                       date=ai_desc.start_date.isoformat())
        
        if not incentive.end_date and ai_desc.end_date:
            incentive.end_date = ai_desc.end_date
            updated = True
            logger.info("updated_end_date",
                       incentive_id=incentive.incentive_id,
                       date=ai_desc.end_date.isoformat())
        
        if not incentive.total_budget and ai_desc.total_budget is not None:
            incentive.total_budget = ai_desc.total_budget
            updated = True
            logger.info("updated_total_budget",
                       incentive_id=incentive.incentive_id,
                       budget=float(ai_desc.total_budget))
        
        # Update ai_description if not present
        if not incentive.ai_description:
            incentive.ai_description = ai_desc.model_dump(mode='json')
            updated = True
        
        if updated:
            db.commit()
        
        cost = document_cost_tracker.get_document_cost(document_id)
        logger.info("enhancement_complete",
                   incentive_id=incentive.incentive_id,
                   updated=updated,
                   cost_eur=cost)
        
        return updated
        
    except Exception as e:
        logger.error("enhancement_failed",
                    incentive_id=incentive.incentive_id,
                    error=str(e))
        db.rollback()
        return False


def main():
    """Main function."""
    print("\n🔄 Melhorando incentivos com HTML das páginas fonte...\n")
    
    # Initialize OpenAI client and extractor
    openai_client = ManagedOpenAIClient()
    llm_extractor = LLMExtractor(openai_client=openai_client)
    
    with SessionLocal() as db:
        # Query incentives with missing fields
        incentives_to_enhance = db.query(Incentive).filter(
            or_(
                Incentive.publication_date.is_(None),
                Incentive.start_date.is_(None),
                Incentive.end_date.is_(None),
                Incentive.total_budget.is_(None)
            )
        ).all()
        
        total = len(incentives_to_enhance)
        enhanced_count = 0
        total_cost = 0.0
        
        print(f"📊 Total de incentivos a processar: {total}\n")
        
        for i, incentive in enumerate(incentives_to_enhance, 1):
            print(f"[{i}/{total}] {incentive.title[:70]}...")
            
            try:
                was_enhanced = enhance_incentive(incentive, llm_extractor, db)
                
                if was_enhanced:
                    enhanced_count += 1
                    cost = document_cost_tracker.get_document_cost(
                        f"html_enhance_{incentive.incentive_id}"
                    )
                    total_cost += cost
                    print(f"  ✅ Atualizado! Custo: €{cost:.6f}")
                else:
                    print(f"  ⚠️  Nenhuma atualização necessária")
                
            except Exception as e:
                print(f"  ❌ Erro: {e}")
                logger.error("processing_error",
                           incentive_id=incentive.incentive_id,
                           error=str(e))
        
        print(f"\n✅ Processamento concluído!")
        print(f"   Total processados: {total}")
        print(f"   Com melhorias: {enhanced_count}")
        print(f"   Custo total: €{total_cost:.6f}")
        
        # Show updated statistics
        print(f"\n📊 Estatísticas finais:")
        total_incentives = db.query(Incentive).count()
        pub_dates = db.query(Incentive).filter(Incentive.publication_date.isnot(None)).count()
        start_dates = db.query(Incentive).filter(Incentive.start_date.isnot(None)).count()
        end_dates = db.query(Incentive).filter(Incentive.end_date.isnot(None)).count()
        budgets = db.query(Incentive).filter(Incentive.total_budget.isnot(None)).count()
        
        print(f"   Publication Date: {pub_dates}/{total_incentives} ({pub_dates*100//total_incentives}%)")
        print(f"   Start Date: {start_dates}/{total_incentives} ({start_dates*100//total_incentives}%)")
        print(f"   End Date: {end_dates}/{total_incentives} ({end_dates*100//total_incentives}%)")
        print(f"   Total Budget: {budgets}/{total_incentives} ({budgets*100//total_incentives}%)")


if __name__ == "__main__":
    main()

