#!/usr/bin/env python3
"""
Script para pesquisar matches entre incentivos e empresas.

Usage:
    python -m backend.app.scripts.search_matches --incentive-id <ID> [--limit 5]
    python -m backend.app.scripts.search_matches --list-incentives
"""

import sys
import argparse
from pathlib import Path
from typing import List, Optional

import structlog
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.app.db.session import SessionLocal
from backend.app.models.incentive import Incentive
from backend.app.services.matching_service import MatchingService
from backend.app.services.openai_client import ManagedOpenAIClient

logger = structlog.get_logger()


def list_incentives(db, limit: int = 10) -> List[Incentive]:
    """Lista incentivos disponíveis."""
    incentives = db.query(Incentive).filter(
        Incentive.ai_description.isnot(None)
    ).limit(limit).all()
    return incentives


def print_incentive_summary(incentive: Incentive):
    """Imprime resumo de um incentivo."""
    print(f"\n📋 {incentive.title}")
    print(f"   ID: {incentive.incentive_id}")
    if incentive.ai_description:
        ai_desc = incentive.ai_description
        if ai_desc.get("geographic_location"):
            print(f"   🌍 Localização: {ai_desc['geographic_location']}")
        if ai_desc.get("company_size"):
            print(f"   🏢 Tamanho: {', '.join(ai_desc['company_size'])}")
        if ai_desc.get("investment_objectives"):
            print(f"   🎯 Objetivos: {', '.join(ai_desc['investment_objectives'][:3])}")
    if incentive.total_budget:
        print(f"   💰 Orçamento: €{incentive.total_budget:,.2f}")


def print_matches(matches):
    """Imprime os resultados do matching."""
    if not matches:
        print("   ❌ Nenhum match encontrado.")
        return

    print(f"\n✅ Encontrados {len(matches)} matches:\n")
    
    for i, match in enumerate(matches, 1):
        print(f"{i}. {match.company_name}")
        print(f"   Company ID: {match.company_id}")
        print(f"   Score: {match.score:.4f}")
        print(f"   Explicação: {match.explanation}")
        print(f"   Componentes:")
        for comp, val in match.component_scores.items():
            print(f"     - {comp}: {val:.4f}")
        if match.penalties_applied:
            print(f"   Penalizações: {match.penalties_applied}")
        print()


def search_matches_for_incentive(incentive_id: str, limit: int = 5):
    """Pesquisa matches para um incentivo específico."""
    load_dotenv()
    
    db = SessionLocal()
    openai_client = ManagedOpenAIClient()
    matching_service = MatchingService(openai_client=openai_client)

    try:
        print("\n" + "="*80)
        print("🔍 PESQUISA DE MATCHES - INCENTIVOS vs EMPRESAS".center(80))
        print("="*80 + "\n")

        # Buscar o incentivo
        incentive = db.query(Incentive).filter(Incentive.incentive_id == incentive_id).first()
        if not incentive:
            print(f"❌ Incentivo não encontrado: {incentive_id}")
            return

        print_incentive_summary(incentive)
        print(f"\n🔍 Procurando {limit} melhores matches...")
        
        matches = matching_service.find_matches(
            db,
            incentive.incentive_id,
            top_k=limit
        )
        
        print_matches(matches)

    except Exception as e:
        print(f"\n\n❌ Erro: {e}")
        logger.error("script_failed", error=str(e), exc_info=True)
    finally:
        db.close()


def list_available_incentives(limit: int = 20):
    """Lista incentivos disponíveis."""
    load_dotenv()
    
    db = SessionLocal()
    try:
        print("\n" + "="*80)
        print("📋 INCENTIVOS DISPONÍVEIS".center(80))
        print("="*80 + "\n")

        incentives = list_incentives(db, limit=limit)
        
        if not incentives:
            print("❌ Nenhum incentivo encontrado com AI description.")
            return
        
        for i, incentive in enumerate(incentives, 1):
            print(f"{i:2d}. {incentive.title}")
            print(f"    ID: {incentive.incentive_id}")
            if incentive.ai_description:
                ai_desc = incentive.ai_description
                if ai_desc.get("geographic_location"):
                    print(f"    🌍 Localização: {ai_desc['geographic_location']}")
                if ai_desc.get("investment_objectives"):
                    print(f"    🎯 Objetivos: {', '.join(ai_desc['investment_objectives'][:2])}")
            print()

    except Exception as e:
        print(f"\n\n❌ Erro: {e}")
        logger.error("script_failed", error=str(e), exc_info=True)
    finally:
        db.close()


def main():
    """Função principal com argumentos de linha de comando."""
    parser = argparse.ArgumentParser(description="Pesquisar matches entre incentivos e empresas")
    parser.add_argument("--incentive-id", type=str, help="ID do incentivo para pesquisar matches")
    parser.add_argument("--limit", type=int, default=5, help="Número de matches a retornar (padrão: 5)")
    parser.add_argument("--list-incentives", action="store_true", help="Listar incentivos disponíveis")
    
    args = parser.parse_args()
    
    if args.list_incentives:
        list_available_incentives()
    elif args.incentive_id:
        search_matches_for_incentive(args.incentive_id, args.limit)
    else:
        parser.print_help()
        print("\n💡 Exemplos:")
        print("  python -m backend.app.scripts.search_matches --list-incentives")
        print("  python -m backend.app.scripts.search_matches --incentive-id 50dd62777b4a6de6ec2315de7be89dce4fc449ed --limit 3")


if __name__ == "__main__":
    main()
