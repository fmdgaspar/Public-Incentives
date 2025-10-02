"""
Demonstration of cost tracking with dynamic exchange rates and visual feedback.

Features demonstrated:
1. Dynamic EUR/USD exchange rate fetching
2. Real-time cost display with colors
3. Cache hit savings visualization
4. Budget enforcement

Run from project root:
    python examples/demo_cost_tracking.py
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

from backend.app.services.openai_client import ManagedOpenAIClient, BudgetExceededError
from backend.app.services.budget_guard import get_exchange_rate_cached, Colors


def print_header(title: str):
    """Print formatted header."""
    print("\n" + "="*70)
    print(f"{Colors.BOLD}{title}{Colors.RESET}")
    print("="*70 + "\n")


def demo_exchange_rate():
    """Demo 1: Show current exchange rate."""
    print_header("1️⃣  DYNAMIC EXCHANGE RATE")
    
    try:
        rate = get_exchange_rate_cached()
        print(f"{Colors.GREEN}✓{Colors.RESET} Exchange rate fetched successfully!")
        print(f"  1 USD = {Colors.BOLD}{rate:.4f} EUR{Colors.RESET}")
        print(f"  (Cached for 12 hours, updates automatically)\n")
    except Exception as e:
        print(f"{Colors.RED}✗{Colors.RESET} Failed to fetch rate: {e}\n")


def demo_simple_request():
    """Demo 2: Simple chat completion with cost display."""
    print_header("2️⃣  SIMPLE REQUEST WITH COST TRACKING")
    
    client = ManagedOpenAIClient(max_per_request_eur=0.30)
    
    print("Asking: 'What is 2+2?'\n")
    
    result = client.chat_completion(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2? Answer in one word."}
        ],
        model="gpt-4o-mini",
        temperature=0.0
    )
    
    print(f"\nResponse: {Colors.CYAN}{result['response']}{Colors.RESET}\n")


def demo_cache_hit():
    """Demo 3: Demonstrate cache hit savings."""
    print_header("3️⃣  CACHE HIT DEMONSTRATION")
    
    client = ManagedOpenAIClient(max_per_request_eur=0.30)
    
    print("First request (will hit API):")
    result1 = client.chat_completion(
        messages=[
            {"role": "user", "content": "Say hello in Portuguese"}
        ],
        model="gpt-4o-mini"
    )
    
    print(f"\nResponse: {result1['response'][:50]}...\n")
    
    print("\nSecond request (SAME prompt, should hit cache):")
    result2 = client.chat_completion(
        messages=[
            {"role": "user", "content": "Say hello in Portuguese"}
        ],
        model="gpt-4o-mini"
    )
    
    print(f"\nResponse: {result2['response'][:50]}...\n")


def demo_expensive_request():
    """Demo 4: Show warning for expensive requests."""
    print_header("4️⃣  EXPENSIVE REQUEST WARNING")
    
    client = ManagedOpenAIClient(max_per_request_eur=0.30)
    
    long_prompt = "Explain quantum computing in detail. " * 20
    
    print(f"Making request with ~{len(long_prompt)} characters...\n")
    
    result = client.chat_completion(
        messages=[
            {"role": "user", "content": long_prompt}
        ],
        model="gpt-4o-mini",
        max_tokens=500
    )
    
    print(f"\nResponse length: {len(result['response'])} chars")
    print(f"Notice the {Colors.YELLOW}yellow warning{Colors.RESET} if cost > 50% of budget!\n")


def demo_budget_exceeded():
    """Demo 5: Budget enforcement."""
    print_header("5️⃣  BUDGET ENFORCEMENT")
    
    # Very low budget to trigger error
    client = ManagedOpenAIClient(max_per_request_eur=0.001)
    
    print(f"Budget set to: {Colors.RED}€0.001{Colors.RESET} (very low!)")
    print("Attempting expensive request...\n")
    
    try:
        result = client.chat_completion(
            messages=[
                {"role": "user", "content": "Write a long essay." * 100}
            ],
            model="gpt-4o-mini"
        )
        print(f"{Colors.RED}❌ Should have been blocked!{Colors.RESET}")
    except BudgetExceededError as e:
        print(f"{Colors.GREEN}✅ Budget check working!{Colors.RESET}")
        print(f"   Error: {str(e)[:100]}...\n")


def demo_embedding():
    """Demo 6: Embedding with cost tracking."""
    print_header("6️⃣  EMBEDDING GENERATION")
    
    client = ManagedOpenAIClient(max_per_request_eur=0.30)
    
    text = "Apoio à eficiência energética para PME em Lisboa"
    print(f"Text: '{text}'\n")
    
    result = client.create_embedding(text=text)
    
    print(f"\nEmbedding generated:")
    print(f"  Dimension: {result['dimension']}")
    print(f"  First 3 values: {result['embedding'][:3]}\n")


def demo_statistics():
    """Demo 7: Daily statistics."""
    print_header("7️⃣  DAILY COST STATISTICS")
    
    client = ManagedOpenAIClient(max_per_request_eur=0.30)
    stats = client.get_stats()
    
    print(f"Date: {Colors.BOLD}{stats['date']}{Colors.RESET}")
    print(f"Total cost: {Colors.BOLD}€{stats['total_cost_eur']:.4f}{Colors.RESET}\n")
    
    if stats.get('by_model'):
        print("By model:")
        for model, data in stats['by_model'].items():
            print(f"  {Colors.BLUE}{model}{Colors.RESET}: "
                  f"€{data['cost_eur']:.4f} ({data['count']} requests)")
    
    cache = stats.get('cache', {})
    if cache.get('hits', 0) > 0 or cache.get('misses', 0) > 0:
        total_requests = cache['hits'] + cache['misses']
        hit_rate = (cache['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        print(f"\n{Colors.BOLD}Cache Performance:{Colors.RESET}")
        print(f"  Hits: {Colors.GREEN}{cache['hits']}{Colors.RESET}")
        print(f"  Misses: {cache['misses']}")
        print(f"  Hit rate: {Colors.GREEN}{hit_rate:.1f}%{Colors.RESET}")
        print(f"  Actual cost (excluding cache): €{cache.get('actual_cost_eur', 0):.4f}")
        
        if cache.get('hits', 0) > 0:
            # Estimate savings
            avg_cost = cache['actual_cost_eur'] / cache['misses'] if cache['misses'] > 0 else 0
            estimated_savings = avg_cost * cache['hits']
            print(f"  {Colors.BOLD}Estimated savings: €{estimated_savings:.4f}{Colors.RESET} 💰")
    
    print()


def main():
    """Run all demonstrations."""
    print("\n" + "="*70)
    print(f"{Colors.BOLD}{Colors.CYAN}OPENAI COST TRACKING DEMO{Colors.RESET}")
    print(f"Demonstrates dynamic pricing and visual cost feedback")
    print("="*70)
    
    try:
        demo_exchange_rate()
        
        input(f"{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}\n")
        demo_simple_request()
        
        input(f"{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}\n")
        demo_cache_hit()
        
        input(f"{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}\n")
        demo_expensive_request()
        
        input(f"{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}\n")
        demo_budget_exceeded()
        
        input(f"{Colors.YELLOW}Press ENTER to continue...{Colors.RESET}\n")
        demo_embedding()
        
        input(f"{Colors.YELLOW}Press ENTER to see statistics...{Colors.RESET}\n")
        demo_statistics()
        
        print("="*70)
        print(f"{Colors.GREEN}✅ ALL DEMOS COMPLETED{Colors.RESET}")
        print("="*70 + "\n")
        
        print(f"{Colors.BOLD}Key takeaways:{Colors.RESET}")
        print(f"  1. Exchange rates update automatically every 12 hours")
        print(f"  2. {Colors.GREEN}Green{Colors.RESET} = cheap request (<50% budget)")
        print(f"  3. {Colors.YELLOW}Yellow{Colors.RESET} = moderate request (50-80% budget)")
        print(f"  4. {Colors.RED}Red{Colors.RESET} = expensive request (>80% budget)")
        print(f"  5. Cache hits save money automatically!")
        print(f"  6. Budget enforcement prevents runaway costs\n")
    
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}⚠️  Demo interrupted{Colors.RESET}\n")
        sys.exit(0)
    
    except Exception as e:
        print(f"\n\n{Colors.RED}❌ Error: {e}{Colors.RESET}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

