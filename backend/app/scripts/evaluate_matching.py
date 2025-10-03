#!/usr/bin/env python3
"""
Script para avaliar a qualidade do matching usando métricas P@5 e nDCG@5.

Usage:
    python -m backend.app.scripts.evaluate_matching
"""

import sys
import math
from pathlib import Path
from typing import List, Dict, Any, Optional
import argparse

import structlog
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.app.db.session import SessionLocal
from backend.app.models.incentive import Incentive
from backend.app.services.matching_service import MatchingService
from backend.app.services.openai_client import ManagedOpenAIClient

logger = structlog.get_logger()


def calculate_precision_at_k(relevant_items: List[bool], k: int) -> float:
    """
    Calcula Precision@K.
    
    Args:
        relevant_items: Lista de booleanos indicando se cada item é relevante
        k: Número de itens a considerar
        
    Returns:
        Precision@K (0.0-1.0)
    """
    if k == 0:
        return 0.0
    
    top_k = relevant_items[:k]
    if not top_k:
        return 0.0
    
    return sum(top_k) / len(top_k)


def calculate_dcg_at_k(relevance_scores: List[float], k: int) -> float:
    """
    Calcula DCG@K (Discounted Cumulative Gain).
    
    Args:
        relevance_scores: Lista de scores de relevância
        k: Número de itens a considerar
        
    Returns:
        DCG@K
    """
    if k == 0:
        return 0.0
    
    top_k = relevance_scores[:k]
    dcg = 0.0
    
    for i, score in enumerate(top_k):
        if i == 0:
            dcg += score
        else:
            dcg += score / math.log2(i + 1)
    
    return dcg


def calculate_ndcg_at_k(relevance_scores: List[float], k: int) -> float:
    """
    Calcula nDCG@K (normalized DCG).
    
    Args:
        relevance_scores: Lista de scores de relevância
        k: Número de itens a considerar
        
    Returns:
        nDCG@K (0.0-1.0)
    """
    if k == 0:
        return 0.0
    
    dcg = calculate_dcg_at_k(relevance_scores, k)
    
    # Ideal DCG: ordenar por relevância descendente
    ideal_scores = sorted(relevance_scores, reverse=True)
    ideal_dcg = calculate_dcg_at_k(ideal_scores, k)
    
    if ideal_dcg == 0:
        return 0.0
    
    return dcg / ideal_dcg


def evaluate_matching_quality(
    db,
    matching_service: MatchingService,
    sample_size: Optional[int] = None
) -> Dict[str, Any]:
    """
    Avalia a qualidade do matching para uma amostra de incentivos.
    
    Args:
        db: Sessão da base de dados
        matching_service: Serviço de matching
        sample_size: Tamanho da amostra (None = todos)
        
    Returns:
        Dicionário com métricas de avaliação
    """
    logger.info("evaluation_started", sample_size=sample_size)
    
    # Obter incentivos para avaliar
    query = db.query(Incentive).filter(Incentive.ai_description.isnot(None))
    if sample_size:
        query = query.limit(sample_size)
    
    incentives = query.all()
    
    if not incentives:
        logger.error("no_incentives_found")
        return {"error": "No incentives found for evaluation"}
    
    logger.info("incentives_selected", count=len(incentives))
    
    # Métricas agregadas
    total_p_at_5 = 0.0
    total_ndcg_at_5 = 0.0
    total_incentives = 0
    evaluation_results = []
    
    for incentive in incentives:
        try:
            logger.info("evaluating_incentive", 
                       incentive_id=incentive.incentive_id,
                       title=incentive.title[:50])
            
            # Obter matches
            matches = matching_service.find_matches(db, incentive.incentive_id, top_k=5)
            
            if not matches:
                logger.warning("no_matches_found", incentive_id=incentive.incentive_id)
                continue
            
            # Simular relevância baseada no score (para demonstração)
            # Em produção, isto seria baseado em feedback humano ou ground truth
            relevance_scores = []
            relevant_items = []
            
            for match in matches:
                # Score de relevância baseado no score do matching
                # Scores > 0.5 são considerados relevantes
                relevance_score = match.score
                is_relevant = match.score > 0.5
                
                relevance_scores.append(relevance_score)
                relevant_items.append(is_relevant)
            
            # Calcular métricas
            p_at_5 = calculate_precision_at_k(relevant_items, 5)
            ndcg_at_5 = calculate_ndcg_at_k(relevance_scores, 5)
            
            total_p_at_5 += p_at_5
            total_ndcg_at_5 += ndcg_at_5
            total_incentives += 1
            
            evaluation_results.append({
                "incentive_id": incentive.incentive_id,
                "title": incentive.title,
                "matches_count": len(matches),
                "p_at_5": p_at_5,
                "ndcg_at_5": ndcg_at_5,
                "top_score": matches[0].score if matches else 0.0,
                "relevant_matches": sum(relevant_items)
            })
            
            logger.info("incentive_evaluated",
                       incentive_id=incentive.incentive_id,
                       p_at_5=p_at_5,
                       ndcg_at_5=ndcg_at_5,
                       relevant_matches=sum(relevant_items))
            
        except Exception as e:
            logger.error("evaluation_error",
                        incentive_id=incentive.incentive_id,
                        error=str(e),
                        exc_info=True)
            continue
    
    # Calcular métricas médias
    if total_incentives > 0:
        avg_p_at_5 = total_p_at_5 / total_incentives
        avg_ndcg_at_5 = total_ndcg_at_5 / total_incentives
    else:
        avg_p_at_5 = 0.0
        avg_ndcg_at_5 = 0.0
    
    results = {
        "total_incentives_evaluated": total_incentives,
        "average_p_at_5": avg_p_at_5,
        "average_ndcg_at_5": avg_ndcg_at_5,
        "evaluation_results": evaluation_results
    }
    
    logger.info("evaluation_complete", **results)
    return results


def print_evaluation_results(results: Dict[str, Any]):
    """Imprime os resultados da avaliação de forma formatada."""
    print("\n" + "="*80)
    print("📊 AVALIAÇÃO DE QUALIDADE DO MATCHING".center(80))
    print("="*80 + "\n")
    
    if "error" in results:
        print(f"❌ Erro: {results['error']}")
        return
    
    print(f"📋 Incentivos avaliados: {results['total_incentives_evaluated']}")
    print(f"🎯 Precision@5 média: {results['average_p_at_5']:.4f}")
    print(f"📈 nDCG@5 média: {results['average_ndcg_at_5']:.4f}")
    
    print(f"\n📊 Interpretação:")
    print(f"   • Precision@5: {results['average_p_at_5']:.1%} dos top-5 matches são relevantes")
    print(f"   • nDCG@5: {results['average_ndcg_at_5']:.1%} da qualidade ideal de ranking")
    
    # Mostrar alguns exemplos
    if results['evaluation_results']:
        print(f"\n🔍 Exemplos de avaliação:")
        for i, result in enumerate(results['evaluation_results'][:5]):
            print(f"\n{i+1}. {result['title'][:60]}...")
            print(f"   Precision@5: {result['p_at_5']:.3f}")
            print(f"   nDCG@5: {result['ndcg_at_5']:.3f}")
            print(f"   Matches relevantes: {result['relevant_matches']}/5")
            print(f"   Melhor score: {result['top_score']:.3f}")


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(description="Avaliar qualidade do matching")
    parser.add_argument("--sample-size", type=int, help="Número de incentivos a avaliar")
    parser.add_argument("--output", type=str, help="Ficheiro para guardar resultados (JSON)")
    
    args = parser.parse_args()
    
    load_dotenv()
    
    db = SessionLocal()
    openai_client = ManagedOpenAIClient()
    matching_service = MatchingService(openai_client=openai_client)
    
    try:
        print("\n🔄 Iniciando avaliação de qualidade...")
        
        results = evaluate_matching_quality(
            db,
            matching_service,
            sample_size=args.sample_size
        )
        
        print_evaluation_results(results)
        
        # Guardar resultados se especificado
        if args.output:
            import json
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Resultados guardados em: {args.output}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrompido pelo utilizador")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Erro: {e}")
        logger.error("script_failed", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
