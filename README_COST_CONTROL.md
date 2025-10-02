# 💰 OpenAI Cost Control System

Sistema completo de controlo de custos da API OpenAI com **preços dinâmicos** e **feedback visual em tempo real**.

## ✨ Features

### 1. **Preços Dinâmicos**
- 🌍 Taxa de câmbio **EUR/USD em tempo real** (API gratuita)
- 🔄 Cache de 12 horas para taxas de câmbio
- 📊 Preços dos modelos atualizados via web scraping oficial OpenAI
- 💾 Cache de 24 horas para preços dos modelos
- 🛡️ Fallback automático se APIs falharem

### 2. **Controlo por Request**
- 💵 Budget máximo por request (default: €0.30)
- 🚫 Bloqueio automático de requests que excedam o budget
- ✂️ Shrink automático de contexto para caber no budget
- ⚖️ Cálculo preciso com `tiktoken`

### 3. **Cache Inteligente**
- 💾 Cache SQLite de todas as respostas
- 🎯 60-80% de economia esperada
- ⚡ Respostas instantâneas para prompts repetidos
- 📈 Tracking de hit rate e savings

### 4. **Feedback Visual**
- 🎨 Cores no terminal para fácil identificação:
  - ✅ **Verde**: Request barato (<50% do budget)
  - ⚠️ **Amarelo**: Request moderado (50-80% do budget)
  - 🔴 **Vermelho**: Request caro (>80% do budget)
  - 💰 **Cache hit**: Economia visível
- 📊 Info detalhada: tokens, custo, % do budget, modelo

## 📖 Como Usar

### Básico

```python
from backend.app.services.openai_client import ManagedOpenAIClient

# Criar cliente com budget de €0.30 por request
client = ManagedOpenAIClient(max_per_request_eur=0.30)

# Chat completion
result = client.chat_completion(
    messages=[
        {"role": "user", "content": "Explica eficiência energética"}
    ],
    model="gpt-4o-mini"
)

print(result["response"])
print(f"Custo: €{result['cost_eur']:.6f}")
print(f"Cache hit: {result['from_cache']}")
```

**Output no terminal:**
```
  ✅ Cost: €0.000234 (7.8% of €0.30 budget) | 45 in + 120 out = 165 total tokens | Model: gpt-4o-mini
```

### Embeddings

```python
result = client.create_embedding(
    text="Apoio à eficiência energética para PME"
)

embedding = result["embedding"]  # List[float] com 1536 dimensões
```

### JSON Extraction

```python
result = client.chat_completion(
    messages=[
        {"role": "system", "content": "Extract JSON with fields: name, location"},
        {"role": "user", "content": "Empresa ABC está sediada em Lisboa"}
    ],
    model="gpt-4o-mini",
    response_format={"type": "json_object"}
)

data = result["response_json"]  # Already parsed!
```

### Estatísticas

```python
stats = client.get_stats()

print(f"Total hoje: €{stats['total_cost_eur']:.4f}")
print(f"Cache hit rate: {stats['cache']['hits'] / (stats['cache']['hits'] + stats['cache']['misses']) * 100:.1f}%")
```

## 🎯 Exemplo de Output Visual

```bash
# Request normal (barato)
  ✅ Cost: €0.000123 (4.1% of €0.30 budget) | 30 in + 50 out = 80 total tokens | Model: gpt-4o-mini

# Request moderado
  ⚠️ Cost: €0.000187 (62.3% of €0.30 budget) | 150 in + 300 out = 450 total tokens | Model: gpt-4o-mini

# Request caro
  🔴 Cost: €0.000256 (85.3% of €0.30 budget) | 500 in + 400 out = 900 total tokens | Model: gpt-4o-mini

# Cache hit
  💰 CACHE HIT - Saved €0.000187 | 450 tokens
```

## 🔧 Configuração Avançada

### Ajustar Budget

```python
# Budget mais baixo (mais restritivo)
client = ManagedOpenAIClient(max_per_request_eur=0.10)

# Budget mais alto (menos restritivo)
client = ManagedOpenAIClient(max_per_request_eur=0.50)
```

### Forçar Refresh de Preços

```python
from backend.app.services.budget_guard import (
    get_gpt4o_mini_prices_cached,
    get_exchange_rate_cached
)

# Refresh exchange rate
rate = get_exchange_rate_cached(force_refresh=True)

# Refresh model prices
prices = get_gpt4o_mini_prices_cached(force_refresh=True)
```

### Tratar Budget Exceeded

```python
from backend.app.services.openai_client import BudgetExceededError

try:
    result = client.chat_completion(messages=[...])
except BudgetExceededError as e:
    print(f"Request too expensive: {e}")
    # Fallback logic here
```

## 📊 Tabela de Preços (Exemplo Atual)

Com taxa **1 USD = 0.93 EUR**:

| Modelo | Input (€/1M tokens) | Output (€/1M tokens) |
|--------|---------------------|----------------------|
| gpt-4o-mini | €0.1395 | €0.558 |
| text-embedding-3-small | €0.0186 | - |

*Preços atualizados automaticamente a cada 24h*

## 🎬 Demo Completa

Execute o script de demonstração:

```bash
python examples/demo_cost_tracking.py
```

Demonstra:
1. ✅ Taxa de câmbio dinâmica
2. ✅ Request simples com custo
3. ✅ Cache hits e savings
4. ✅ Warnings para requests caros
5. ✅ Budget enforcement
6. ✅ Embeddings
7. ✅ Estatísticas diárias

## 🧪 Testes

```bash
python examples/test_openai_client.py
```

## 💡 Dicas de Economia

1. **Use cache ao máximo**: Requests idênticos são grátis!
2. **Mantenha prompts concisos**: Menos tokens = menor custo
3. **Use `temperature=0.0`** para comportamento determinístico (melhor cache hit rate)
4. **Monitore o budget**: Verifique stats regularmente
5. **Batch embeddings**: Processe múltiplos textos de uma vez

## 🔍 Arquitetura

```
Request
  ↓
Check Cache ────────────→ HIT → Return (€0)
  ↓ MISS
Get Exchange Rate (cached 12h)
  ↓
Get Model Prices (cached 24h)
  ↓
Check Budget ───────────→ EXCEEDED → Error
  ↓ OK
Estimate Cost
  ↓
Shrink if Needed
  ↓
Call OpenAI API
  ↓
Calculate Actual Cost
  ↓
Save to Cache
  ↓
Track Cost
  ↓
Print Visual Feedback
  ↓
Return Response
```

## 📝 Logs Estruturados

Todos os eventos são logged com `structlog`:

```json
{
  "event": "openai_response",
  "timestamp": "2024-10-02T10:30:00Z",
  "model": "gpt-4o-mini",
  "tokens_in": 45,
  "tokens_out": 120,
  "cost_eur": 0.000234,
  "from_cache": false
}
```

## ⚡ Performance

- **Cache hit**: < 1ms
- **Cache miss + API call**: ~500-2000ms
- **Exchange rate fetch**: ~200ms (cached 12h)
- **Price scraping**: ~1000ms (cached 24h)

## 🛡️ Segurança

- ✅ Validação de inputs
- ✅ Rate limiting via budget
- ✅ Secrets via env vars
- ✅ SQL injection protection (parametrized queries)
- ✅ Fallback em caso de falhas

## 📚 Scripts Úteis

```bash
# Extrair AI descriptions de incentivos
python -m backend.app.scripts.extract_ai_descriptions --limit 10

# Gerar embeddings
python -m backend.app.scripts.extract_ai_descriptions --skip-embeddings

# Ver estatísticas
python -c "from backend.app.services.openai_client import ManagedOpenAIClient; \
  print(ManagedOpenAIClient().get_stats())"
```

## 🎓 Conceitos-Chave

### Token
Unidade mínima de texto (~4 caracteres). "Lisboa" ≈ 2 tokens.

### Cache Hit
Request idêntico a um anterior → resposta instantânea e grátis.

### Budget per Request
Limite máximo de custo para uma única chamada à API.

### Shrink
Redução automática do contexto para caber no budget.

---

**Desenvolvido com ❤️ para o AI Challenge | Public Incentives**

