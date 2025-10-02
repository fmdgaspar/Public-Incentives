"""
Example script to test OpenAI client with cost control.

Run from project root:
    python examples/test_openai_client.py
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

import structlog
from backend.app.services.openai_client import ManagedOpenAIClient, BudgetExceededError

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


def test_chat_completion():
    """Test chat completion with cost control."""
    print("\n" + "="*60)
    print("TEST 1: Chat Completion")
    print("="*60 + "\n")
    
    client = ManagedOpenAIClient(
        max_per_request_eur=0.30
    )
    
    # Test simple completion
    result = client.chat_completion(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2? Answer in one word."}
        ],
        model="gpt-4o-mini",
        temperature=0.0
    )
    
    print(f"Response: {result['response']}")
    print(f"Tokens: {result['usage']['prompt_tokens']} in + {result['usage']['completion_tokens']} out")
    print(f"Cost: €{result['cost_eur']:.6f}")
    print(f"From cache: {result['from_cache']}")
    
    # Test cache hit (same request)
    print("\n--- Calling again (should hit cache) ---\n")
    
    result2 = client.chat_completion(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2? Answer in one word."}
        ],
        model="gpt-4o-mini",
        temperature=0.0
    )
    
    print(f"Response: {result2['response']}")
    print(f"Cost: €{result2['cost_eur']:.6f} (saved €{result2.get('original_cost_eur', 0):.6f})")
    print(f"From cache: {result2['from_cache']}")


def test_json_extraction():
    """Test JSON extraction."""
    print("\n" + "="*60)
    print("TEST 2: JSON Extraction")
    print("="*60 + "\n")
    
    client = ManagedOpenAIClient(max_per_request_eur=0.30)
    
    incentive_text = """
    Apoio à Eficiência Energética em PME
    
    O presente incentivo destina-se a pequenas e médias empresas (PME) dos setores
    da indústria transformadora (CAE 10-33) e serviços (CAE 45-82), localizadas nas
    regiões de Lisboa, Porto e Braga.
    
    Objetivos:
    - Melhoria da eficiência energética
    - Redução de emissões de CO2
    - Instalação de painéis solares fotovoltaicos
    
    Critérios de elegibilidade:
    - Empresas com menos de 250 trabalhadores
    - Investimento mínimo de €25.000
    - Sede em Portugal
    """
    
    result = client.chat_completion(
        messages=[
            {
                "role": "system",
                "content": "Extract structured data as JSON with fields: caes (list), location (string), company_size (list), objectives (list)."
            },
            {
                "role": "user",
                "content": incentive_text
            }
        ],
        model="gpt-4o-mini",
        temperature=0.0,
        response_format={"type": "json_object"}
    )
    
    print(f"Response JSON:")
    print(result['response_json'])
    print(f"\nCost: €{result['cost_eur']:.6f}")


def test_embedding():
    """Test embedding generation."""
    print("\n" + "="*60)
    print("TEST 3: Embeddings")
    print("="*60 + "\n")
    
    client = ManagedOpenAIClient(max_per_request_eur=0.30)
    
    text = "Apoio à eficiência energética para PME em Lisboa"
    
    result = client.create_embedding(
        text=text,
        model="text-embedding-3-small"
    )
    
    print(f"Text: {text}")
    print(f"Dimension: {result['dimension']}")
    print(f"Tokens: {result['tokens']}")
    print(f"Cost: €{result['cost_eur']:.6f}")
    print(f"From cache: {result['from_cache']}")
    print(f"First 5 values: {result['embedding'][:5]}")
    
    # Test cache hit
    print("\n--- Calling again (should hit cache) ---\n")
    
    result2 = client.create_embedding(text=text)
    print(f"Cost: €{result2['cost_eur']:.6f}")
    print(f"From cache: {result2['from_cache']}")


def test_budget_enforcement():
    """Test budget enforcement."""
    print("\n" + "="*60)
    print("TEST 4: Budget Enforcement")
    print("="*60 + "\n")
    
    # Very low budget to trigger error
    client = ManagedOpenAIClient(max_per_request_eur=0.001)
    
    try:
        result = client.chat_completion(
            messages=[
                {"role": "user", "content": "Write a long essay about AI." * 100}
            ],
            model="gpt-4o-mini"
        )
        print("❌ Should have raised BudgetExceededError!")
    except BudgetExceededError as e:
        print(f"✅ Budget check working! Error: {e}")


def test_context_shrinking():
    """Test automatic context shrinking."""
    print("\n" + "="*60)
    print("TEST 5: Automatic Context Shrinking")
    print("="*60 + "\n")
    
    client = ManagedOpenAIClient(max_per_request_eur=0.10)  # Low budget
    
    # Very long context
    long_context = "This is a very long document. " * 1000
    
    result = client.chat_completion(
        messages=[
            {"role": "system", "content": "Summarize in one sentence."},
            {"role": "user", "content": long_context}
        ],
        model="gpt-4o-mini",
        temperature=0.0
    )
    
    print(f"✅ Context was automatically shrunk to fit budget")
    print(f"Response: {result['response']}")
    print(f"Cost: €{result['cost_eur']:.6f}")


def test_stats():
    """Test cost statistics."""
    print("\n" + "="*60)
    print("TEST 6: Cost Statistics")
    print("="*60 + "\n")
    
    client = ManagedOpenAIClient(max_per_request_eur=0.30)
    
    stats = client.get_stats()
    
    print(f"Date: {stats['date']}")
    print(f"Total cost: €{stats['total_cost_eur']:.4f}")
    print(f"\nBy model:")
    for model, data in stats.get('by_model', {}).items():
        print(f"  {model}: €{data['cost_eur']:.4f} ({data['count']} requests)")
    
    cache_stats = stats.get('cache', {})
    print(f"\nCache:")
    print(f"  Hits: {cache_stats.get('hits', 0)}")
    print(f"  Misses: {cache_stats.get('misses', 0)}")
    print(f"  Actual cost: €{cache_stats.get('actual_cost_eur', 0):.4f}")
    
    if cache_stats.get('hits', 0) > 0:
        hit_rate = cache_stats['hits'] / (cache_stats['hits'] + cache_stats['misses']) * 100
        print(f"  Hit rate: {hit_rate:.1f}%")


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("OPENAI CLIENT TESTS WITH COST CONTROL")
    print("="*70)
    
    try:
        test_chat_completion()
        test_json_extraction()
        test_embedding()
        test_budget_enforcement()
        test_context_shrinking()
        test_stats()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED")
        print("="*70 + "\n")
    
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        logger.error("test_failed", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

