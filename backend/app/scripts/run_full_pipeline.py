#!/usr/bin/env python3
"""
Pipeline completo para processamento de incentivos.

Este script executa todo o pipeline:
1. Scraping das páginas do Fundo Ambiental
2. Extração determinística (datas, orçamentos)
3. Carregamento para BD
4. Enhancement com LLM (HTML das páginas fonte)
5. Processamento de documentos PDF
6. Geração de embeddings
7. Estatísticas finais

Usage:
    python -m backend.app.scripts.run_full_pipeline [--limit N] [--skip-scraping] [--skip-enhancement]
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

import structlog
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

load_dotenv()

from backend.app.db.session import SessionLocal
from backend.app.models.incentive import Incentive

logger = structlog.get_logger()


def run_scraping(limit: Optional[int] = None) -> bool:
    """Executa o scraping das páginas."""
    print("\n🔄 Fase 1: Scraping das páginas do Fundo Ambiental...")
    
    try:
        import subprocess
        
        cmd = ["python", "-m", "scraper.run"]
        if limit:
            cmd.extend(["--limit", str(limit)])
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent.parent)
        
        if result.returncode == 0:
            print("✅ Scraping concluído com sucesso!")
            return True
        else:
            print(f"❌ Erro no scraping: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao executar scraping: {e}")
        return False


def run_deterministic_extraction() -> bool:
    """Executa a extração determinística (já integrada no scraper)."""
    print("\n🔄 Fase 2: Extração determinística (datas, orçamentos)...")
    print("✅ Extração determinística já integrada no scraper!")
    return True


def run_load_to_database() -> bool:
    """Carrega os incentivos para a base de dados."""
    print("\n🔄 Fase 3: Carregamento para base de dados...")
    
    try:
        import subprocess
        
        result = subprocess.run(
            ["python", "-m", "backend.app.db.load_incentives"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent.parent.parent
        )
        
        if result.returncode == 0:
            print("✅ Carregamento para BD concluído!")
            return True
        else:
            print(f"❌ Erro no carregamento: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao carregar para BD: {e}")
        return False


def run_llm_enhancement() -> bool:
    """Executa o enhancement com LLM usando HTML das páginas fonte."""
    print("\n🔄 Fase 4: Enhancement com LLM (HTML das páginas fonte)...")
    
    try:
        import subprocess
        
        result = subprocess.run(
            ["python", "-m", "backend.app.scripts.enhance_with_source_html"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent.parent.parent
        )
        
        if result.returncode == 0:
            print("✅ Enhancement com LLM concluído!")
            return True
        else:
            print(f"❌ Erro no enhancement: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Erro no enhancement: {e}")
        return False


def run_pdf_processing() -> bool:
    """Processa documentos PDF para incentivos com campos em falta."""
    print("\n🔄 Fase 5: Processamento de documentos PDF...")
    
    try:
        from backend.app.scripts.extract_ai_descriptions import extract_ai_descriptions
        
        with SessionLocal() as db:
            stats = extract_ai_descriptions(db, force=True)
            
            print(f"✅ Processamento de PDFs concluído!")
            print(f"   Total processados: {stats['total']}")
            print(f"   Sucessos: {stats['success']}")
            print(f"   Falhas: {stats['failed']}")
            print(f"   Custo: €{stats['total_cost_eur']:.4f}")
            return True
            
    except Exception as e:
        print(f"❌ Erro no processamento de PDFs: {e}")
        return False


def run_embeddings_generation() -> bool:
    """Gera embeddings para todos os incentivos."""
    print("\n🔄 Fase 6: Geração de embeddings...")
    
    try:
        from backend.app.scripts.extract_ai_descriptions import generate_embeddings
        
        with SessionLocal() as db:
            stats = generate_embeddings(db, force=True)
            
            print(f"✅ Geração de embeddings concluída!")
            print(f"   Total processados: {stats['total']}")
            print(f"   Sucessos: {stats['success']}")
            print(f"   Falhas: {stats['failed']}")
            return True
            
    except Exception as e:
        print(f"❌ Erro na geração de embeddings: {e}")
        return False


def show_final_statistics():
    """Mostra estatísticas finais."""
    print("\n📊 Estatísticas Finais:")
    
    try:
        with SessionLocal() as db:
            total = db.query(Incentive).count()
            pub_dates = db.query(Incentive).filter(Incentive.publication_date.isnot(None)).count()
            start_dates = db.query(Incentive).filter(Incentive.start_date.isnot(None)).count()
            end_dates = db.query(Incentive).filter(Incentive.end_date.isnot(None)).count()
            budgets = db.query(Incentive).filter(Incentive.total_budget.isnot(None)).count()
            ai_descriptions = db.query(Incentive).filter(Incentive.ai_description.isnot(None)).count()
            
            print(f"   Total de incentivos: {total}")
            print(f"   Publication Date: {pub_dates}/{total} ({pub_dates*100//total}%)")
            print(f"   Start Date: {start_dates}/{total} ({start_dates*100//total}%)")
            print(f"   End Date: {end_dates}/{total} ({end_dates*100//total}%)")
            print(f"   Total Budget: {budgets}/{total} ({budgets*100//total}%)")
            print(f"   AI Descriptions: {ai_descriptions}/{total} ({ai_descriptions*100//total}%)")
            
    except Exception as e:
        print(f"❌ Erro ao obter estatísticas: {e}")


def main():
    """Função principal do pipeline."""
    parser = argparse.ArgumentParser(description="Pipeline completo de processamento de incentivos")
    parser.add_argument("--limit", type=int, help="Limitar número de incentivos a processar")
    parser.add_argument("--skip-scraping", action="store_true", help="Pular fase de scraping")
    parser.add_argument("--skip-enhancement", action="store_true", help="Pular fase de enhancement com LLM")
    parser.add_argument("--skip-embeddings", action="store_true", help="Pular geração de embeddings")
    
    args = parser.parse_args()
    
    print("🚀 Iniciando Pipeline Completo de Processamento de Incentivos")
    print("=" * 60)
    
    success = True
    
    # Fase 1: Scraping
    if not args.skip_scraping:
        success = run_scraping(args.limit)
        if not success:
            print("❌ Pipeline interrompido na fase de scraping")
            return
    
    # Fase 2: Extração determinística (já integrada)
    success = run_deterministic_extraction()
    if not success:
        print("❌ Pipeline interrompido na fase de extração determinística")
        return
    
    # Fase 3: Carregamento para BD
    success = run_load_to_database()
    if not success:
        print("❌ Pipeline interrompido no carregamento para BD")
        return
    
    # Fase 4: Enhancement com LLM
    if not args.skip_enhancement:
        success = run_llm_enhancement()
        if not success:
            print("❌ Pipeline interrompido no enhancement com LLM")
            return
    
    # Fase 5: Processamento de documentos PDF
    success = run_pdf_processing()
    if not success:
        print("❌ Pipeline interrompido no processamento de PDFs")
        return
    
    # Fase 6: Geração de embeddings
    if not args.skip_embeddings:
        success = run_embeddings_generation()
        if not success:
            print("❌ Pipeline interrompido na geração de embeddings")
            return
    
    # Estatísticas finais
    show_final_statistics()
    
    print("\n🎉 Pipeline completo executado com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    main()
