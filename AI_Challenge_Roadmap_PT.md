# AI Challenge | Public Incentives — Roadmap Técnico Detalhado
**Versão:** 1.0  
**Data:** 2025-10-02


> Este documento descreve, com elevado nível de detalhe, a arquitetura, tarefas, tecnologias, testes, Docker, logs/observabilidade, métricas de eficácia e operação para entregar o desafio técnico. Todo o stack é gratuito (infra & libs) exceto chamadas à OpenAI (controladas por teto de custo).

---

## Índice
1. [Visão Geral do Produto](#visão-geral-do-produto)
2. [Requisitos Funcionais](#requisitos-funcionais)
3. [Requisitos Não Funcionais](#requisitos-não-funcionais)
4. [Arquitetura (Detalhada)](#arquitetura-detalhada)
5. [Esquema de Dados e DDL](#esquema-de-dados-e-ddl)
6. [Scraper & ETL](#scraper--etl)
7. [Extração Estruturada com LLM](#extração-estruturada-com-llm)
8. [Integração de Empresas (CSV)](#integração-de-empresas-csv)
9. [Matching: Regras, Vectores, BM25 e Re-ranking LLM](#matching-regras-vectores-bm25-e-re-ranking-llm)
10. [API (FastAPI) & Contratos](#api-fastapi--contratos)
11. [UI (Opcional)](#ui-opcional)
12. [Observabilidade: Logs, Métricas, Traces](#observabilidade-logs-métricas-traces)
13. [Testes e Qualidade](#testes-e-qualidade)
14. [Docker, Compose e DevOps](#docker-compose-e-devops)
15. [Operação: Schedulers, Backup, Retenção](#operação-schedulers-backup-retenção)
16. [Segurança e Privacidade](#segurança-e-privacidade)
17. [Avaliação de Eficácia (Métricas)](#avaliação-de-eficácia-métricas)
18. [Controlo de Custos OpenAI](#controlo-de-custos-openai)
19. [Riscos & Mitigação](#riscos--mitigação)
20. [Roadmap e Cronograma](#roadmap-e-cronograma)
21. [Definition of Done (Checklist)](#definition-of-done-checklist)
22. [Apêndice A: Exemplos de Código/Config](#apêndice-a-exemplos-de-códigoconfig)

---

## Visão Geral do Produto
Sistema que:
- Faz scraping do separador **“Apoios PRR”** do **Fundo Ambiental**.
- Estrutura os incentivos com ajuda de LLM (JSON validado).
- Carrega empresas do ficheiro **`companies_sample.csv`**.
- Gera **top-5 empresas** por incentivo com **score objetivo** e **explicação**.
- Expõe API (e UI opcional) + chatbot RAG (opcional).
- Entrega com **testes**, **Docker/Compose**, **observabilidade** e **documentação**.

**Tecnologias principais (grátis):** Python 3.11, Playwright/Requests+BS4, Pydantic, FastAPI, PostgreSQL (+pgvector) ou FAISS, Great Expectations, Prometheus+Grafana, pytest.  
**LLM (pago):** OpenAI (gpt-4o-mini/4.1-mini + text-embedding-3-small) — com **teto diário**.

---

## Requisitos Funcionais
- RF1: Scraping de todos os incentivos do separador “Apoios PRR” (paginado).
- RF2: Extração de campos: título, descrição, links, datas (pub/início/fim), orçamento, fonte.
- RF3: **`ai_description`** em JSON (CAE aplicáveis, localização, tamanho da empresa, objetivos, finalidades, critérios).
- RF4: Base de dados com **tabela `incentives`** (estrutura pedida) e **`companies`** (upload do CSV).
- RF5: Matching automático → **top-5** empresas por incentivo com `score` e **justificação**.
- RF6: API pública para listar incentivos, ver detalhe e pedir matches.
- RF7 (Opcional): Chatbot que responde sobre incentivos e empresas.
- RF8: Export/seed de dados de demonstração para revisão rápida.

## Requisitos Não Funcionais
- RNF1: Reprodutibilidade total via Docker/Compose.
- RNF2: Logs estruturados e métricas Prometheus.
- RNF3: Testes (unit, integração, e2e) + lint + tipagem.
- RNF4: Controlo de custo OpenAI com teto diário e cache.
- RNF5: Documentação completa e OpenAPI gerada automaticamente.

---

## Arquitetura (Detalhada)
### Diagrama (ASCII)
```
[ Scheduler ]                   [ OpenAI ]
     |                              ^
     v                              |
[ Scraper ] -> [ Parser ] -> [ LLM Extractor ] -> [ ai_description JSON ]
     |                                         \-> [ Embeddings ]
     v
[ DB: Postgres (+pgvector) ] <---- [ Companies Loader (CSV) ]
     ^            ^
     |            |
[ Matching Service (regras + vetores + BM25 + re-rank LLM) ]
     |
   [ FastAPI ] ----> [ Chatbot RAG ] (opcional)
     |
[ Observabilidade: Logs JSON | Prometheus | Grafana ]
```

### Componentes e responsabilidades
- **Scraper**: coleta páginas do “Apoios PRR”; respeita robots; salva raw + normalizado.
- **Parser/Extractor**: transforma HTML para objetos internos.
- **LLM Extractor**: aplica prompt com schema; valida via Pydantic; reintenta se necessário.
- **Embeddings**: cria vetores para incentivos e empresas (para busca semântica).
- **Matching Service**: filtra por regras determinísticas, calcula similaridade vetorial e BM25, reordena com LLM barato.
- **API**: endpoints REST (FastAPI); autenticação simples (token opcional).
- **Chatbot**: RAG sobre incentivos/empresas com citations (opcional).
- **Observabilidade**: métricas, logs, dashboards.
- **Scheduler**: atualizações automáticas (diário/semana).

---

## Esquema de Dados e DDL
```sql
CREATE EXTENSION IF NOT EXISTS vector; -- pgvector, quando Postgres

CREATE TABLE IF NOT EXISTS incentives (
  incentive_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT,
  ai_description JSONB,
  document_urls TEXT[],
  publication_date DATE,
  start_date DATE,
  end_date DATE,
  total_budget NUMERIC,
  source_link TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS incentive_embeddings (
  incentive_id TEXT PRIMARY KEY
    REFERENCES incentives(incentive_id) ON DELETE CASCADE,
  embedding VECTOR(1536)
);

CREATE TABLE IF NOT EXISTS companies (
  company_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  cae_codes TEXT[],
  size TEXT CHECK (size IN ('micro','pme','grande','unknown')),
  district TEXT,
  county TEXT,
  parish TEXT,
  website TEXT,
  raw JSONB
);

CREATE TABLE IF NOT EXISTS company_embeddings (
  company_id TEXT PRIMARY KEY
    REFERENCES companies(company_id) ON DELETE CASCADE,
  embedding VECTOR(1536)
);

CREATE TABLE IF NOT EXISTS awarded_cases (
  id BIGSERIAL PRIMARY KEY,
  source TEXT,
  incentive_id TEXT,
  company_name TEXT,
  amount NUMERIC,
  year INT,
  raw JSONB
);

CREATE INDEX IF NOT EXISTS idx_incentives_pubdate ON incentives(publication_date);
CREATE INDEX IF NOT EXISTS idx_incentives_dates ON incentives(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name);
```

**Observações:**
- Em SQLite/FAISS: substituir `VECTOR` por tabela separada com blob e usar FAISS para busca.
- Em Postgres: `pgvector` permite `cosine_distance(embedding, query)`.

---

## Scraper & ETL
### Bibliotecas
- **Playwright** (ou `requests` + `BeautifulSoup` se estático), `selectolax/lxml`, `tenacity` para retries.

### Estratégia
1. Respeitar `robots.txt` e adicionar cabeçalhos `User-Agent` claros.
2. Descoberta de páginas via paginação/links do separador **“Apoios PRR”**.
3. Coleta para cada incentivo:
   - `title`, `description`, `source_link`,
   - `document_urls` (PDFs ou páginas),
   - tentativa determinística de `publication_date`, `start_date`, `end_date`, `total_budget` via regexes e heurísticas.
4. Guardar **raw HTML** (hash + timestamp) numa pasta/coluna auxiliar para auditoria.
5. ETL transforma para schema `incentives`.

### Anti-fragilidade
- Backoff exponencial, limite de paralelismo (ex.: 4 páginas simultâneas).
- **Idempotência**: `incentive_id` = hash estável (ex.: `sha1(source_link)`).
- **Testes VCR**: fixtures com 2–3 páginas reais e um PDF de exemplo (para regressão).

### Normalização de campos
- Datas: `dd/mm/yyyy` → `YYYY-MM-DD` (timezone naive).
- Orçamento: capturar números com separadores PT; converter para decimal.
- URLs: absolutizar links relativos.

---

## Extração Estruturada com LLM
### Modelo & custos
- **gpt-4o-mini** (ou 4.1-mini) para extração; **text-embedding-3-small** para embeddings.
- Cache local obrigatório: `{sha1(text)} -> (json, tokens, custo)`.

### Schema Pydantic (exemplo)
```python
from pydantic import BaseModel, Field
from typing import List, Literal

class AIDescription(BaseModel):
    caes: List[str] = Field(default_factory=list)
    geographic_location: str = ""
    company_size: List[Literal["micro","pme","grande","não aplicável"]] = Field(default_factory=list)
    investment_objectives: List[str] = Field(default_factory=list)
    specific_purposes: List[str] = Field(default_factory=list)
    eligibility_criteria: List[str] = Field(default_factory=list)
```

### Prompt de extração (resumo)
- Incluir instrução de **retornar apenas JSON válido** e aderir ao schema.
- Fornecer exemplo POSITIVO e NEGATIVO.
- Reintentar com “repair prompt” quando JSON inválido.

### Política de retries
- 1ª tentativa normal → se inválido: `json_repair` → se falhar: fallback para regex/heurística minimal e marcar `ai_description_validation_error=true`.

### Embeddings
- Gerar para: `title + description + ai_description serializado`.
- Normalizar vetores (L2) antes de armazenar.

---

## Integração de Empresas (CSV)
### Carregamento
- Endpoint `POST /companies/upload` ou comando `python -m tools.load_companies path=companies_sample.csv`.
- Deduplicação por `company_id` ou (`name`,`district`).

### Normalização
- **CAE**: manter apenas dígitos; zero-pad conforme necessário (4–5 dígitos). Criar coluna `cae_codes` (array).
- **Localização**: mapear para `district`, `county`, `parish` (quando possível a partir do CSV).
- **Tamanho**: mapear regras (ex.: `employees` ou `turnover`) → `micro|pme|grande|unknown`.

### Embeddings de empresas
- Texto base: `"{name}. CAE: {codes}. Localização: {district}/{county}. {optional_description}"`.

---

## Matching: Regras, Vectores, BM25 e Re-ranking LLM
### Pipeline de Scoring
1. **Filtros/penalizações determinísticas**  
   - `size`: se `ai_description.company_size` não contém o tamanho da empresa e não inclui “não aplicável” → `penalty *= 0.6`  
   - `cae`: se não há interseção → `penalty *= 0.5`  
   - `geo`: se `geographic_location` não cobre a localização da empresa → `penalty *= 0.7`
2. **Similaridade vetorial (cosine)** entre incentivo e empresa.
3. **BM25** (lib `rank-bm25`) sobre termos (`title`, `description`, CAE como tokens).
4. **Re-ranking LLM** nos top-20 (contexto curto, barato).

**Score final (0–1):**
```
score = (0.55 * cosine + 0.25 * bm25_norm + 0.20 * llm_rerank) * penalty
```
- Guardar **explicação**: quais critérios cumpriu/falhou e razões do LLM (2–3 bullets).

### Pseudocódigo (simplificado)
```python
candidates = vector_search(incentive_vec, top=50)
candidates = bm25_boost(candidates, incentive_text)
candidates = apply_rule_penalties(candidates, ai_desc)
reranked = llm_rerank(incentive, candidates[:20])
return top_k(reranked, k=5)
```

---

## API (FastAPI) & Contratos
### Endpoints principais
- `GET /health` → 200 (status & versões).
- `GET /incentives?query=&page=&size=` → paginação, filtros por datas.
- `GET /incentives/{id}` → detalhe + `ai_description` + documentos.
- `GET /incentives/{id}/matches?top_k=5` → top-K com score e explicação.
- `POST /companies/upload` (CSV) → 201.
- `GET /companies/{id}` → detalhe.

### Modelos de resposta (exemplo)
```json
{
  "incentive_id": "fa_123",
  "title": "...",
  "ai_description": { "...": "..." },
  "matches": [
    { "company_id":"c1", "name":"Empresa A", "score":0.82,
      "explanation":[ "CAE compatível", "Localização elegível" ] }
  ]
}
```

### Segurança
- Token simples via header `X-API-Key` para endpoints de escrita.
- CORS restrito.

---

## UI (Opcional)
- React + Vite + Tailwind **ou** templates Jinja no FastAPI.
- Páginas:
  - Lista de incentivos (busca e filtros).
  - Detalhe do incentivo com top-5 empresas (tabela com motivos).
  - Upload do CSV.
  - Chat (se ativado).

---

## Observabilidade: Logs, Métricas, Traces
### Logs
- **structlog** → JSON: `{ts, level, service, route, duration_ms, request_id, tokens_in, tokens_out, openai_cost_eur}`.
- Correlation-ID via middleware.

### Métricas Prometheus (exemplos)
- `scraper_pages_total`
- `scraper_failures_total`
- `llm_tokens_total{type="prompt|completion|embedding"}`
- `llm_cost_eur_total`
- `match_requests_total`
- `match_latency_seconds` (histogram)
- `api_requests_total{route,code}`

### Traces (opcional)
- OpenTelemetry com export `otlp` para Grafana Tempo/Jaeger (opcional).

---

## Testes e Qualidade
### Unit
- Parsers/regex, normalização CAE/datas, penalizações de regras, score final.
- Validação Pydantic de `ai_description`.
### Integração
- ETL completo contra Postgres ephemeral (pytest-docker).
- Upload CSV → verificação de contagens e normalização.
### E2E
- Subir stack com `docker-compose` e bater na API.
- Fluxo: scrape → extract → embed → matches.
### API Contract
- **Schemathesis** em `openapi.json`.
### Dados
- **Great Expectations**: unicidade, limites de datas, schema de JSON, orçamentos não negativos.
### Qualidade de código
- `ruff`, `black`, `mypy` no CI.
### LLM “goldens”
- 10 incentivos com saídas aprovadas; snapshot tests com tolerância.

---

## Docker, Compose e DevOps
### Serviços no `docker-compose.yml`
- `db`: postgres + pgvector (volume persistente).
- `api`: FastAPI (porta 8000).
- `scraper`: job ou sidecar com APScheduler.
- `prometheus` e `grafana` (opcionais).
- `frontend` (opcional).

### Variáveis de ambiente (exemplo)
```
OPENAI_API_KEY=...
MAX_DAILY_OPENAI_EUR=20
DB_DSN=postgresql+psycopg://postgres:postgres@db:5432/ai_challenge
LOG_LEVEL=INFO
```

### CI (GitHub Actions)
- Jobs: `lint → test → build → push → e2e`.
- Publicação da imagem no GHCR com tag `git-sha`.

---

## Operação: Schedulers, Backup, Retenção
- **APScheduler**: `cron` diário às 03:00 UTC para atualizar incentivos.
- Retentativa automática para falhas (3 tentativas).
- Backups Postgres (dump diário para volume/artefato local).
- Retenção de logs 14 dias; rotação via Docker.

---

## Segurança e Privacidade
- Respeitar `robots.txt` e rate limit.
- Sanitização de HTML/URLs, nofollow para links de saída.
- Secrets fora do repo (`.env`, Docker secrets).
- Se CSV tiver PII, cifrar volume (opcional) e mascarar logs.

---

## Avaliação de Eficácia (Métricas)
### Ground-truth de “apoios atribuídos”
- Scrapar/exportar casos financiados (mesma fonte).
- Normalizar nomes e *fuzzy match* com `companies.name` (Levenshtein + limiar 0.9).
- Criar pares positivos `(incentive_id, company_name)`.

### Métricas de ranking
- **P@K**, **R@K**, **MRR**, **nDCG@5**.
- **Ablation**: Vetores; Vetores+Regras; +Re-rank LLM.

### Protocolo
- Separar por tempo (train/val/test).
- Reportar curva Precision-Recall e tabela de métricas.

---

## Controlo de Custos OpenAI
- **Cache** de prompts e embeddings (SQLite).
- **Teto diário**: `MAX_DAILY_OPENAI_EUR`. Ao atingir, as chamadas são negadas e o job aguarda o dia seguinte.
- **Batching** para embeddings.
- **Top-K** reduzido para re-rank (20 ou menos).

Pseudo-código:
```python
if today_cost_eur() + estimated_cost(call) > MAX_DAILY_OPENAI_EUR:
    raise BudgetExceeded
```

---

## Riscos & Mitigação
- Mudança do HTML → testes VCR + Playwright como fallback.
- Custo LLM acima do esperado → cache + teto + “dry-run” sem LLM.
- Dados ruidosos (CAE/nome) → normalização + *fuzzy match* com revisão manual amostral.
- Ground-truth incompleto → combinar avaliação humana rápida (20 pares).

---

## Roadmap e Cronograma (7 dias úteis)
| Dia | Entregas |
|---|---|
| 1 | Repo, Docker/Compose, DB, Scraper MVP |
| 2 | Parser + LLM extração + cache + DDL |
| 3 | Upload CSV + normalização + embeddings |
| 4 | Matching (regras + vetores) |
| 5 | Re-ranking LLM + API + UI mínima |
| 6 | Avaliação (nDCG/P@5) + dashboards |
| 7 | Hardening (testes, docs, custos, tuning) |

---

## Definition of Done (Checklist)
- [ ] Scraper cobre 100% do separador *Apoios PRR*.
- [ ] `incentives` conforme especificação + `ai_description` válido.
- [ ] Upload `companies_sample.csv` → `companies` populada.
- [ ] `/incentives/{id}/matches` devolve **top-5** com score e explicações.
- [ ] Avaliação com **P@5** e **nDCG@5** reportadas.
- [ ] Controlo de custo e cache ativos; custo diário ≤ teto.
- [ ] Testes unit/integração/e2e; Schemathesis OK; lint/tipo OK.
- [ ] Docker/Compose “up” em < 10 min; README completo.
- [ ] Logs estruturados + `/metrics` Prometheus funcionais.
- [ ] (Opcional) Chatbot RAG com citações de fonte.

---

## Apêndice A: Exemplos de Código/Config

### A1. `docker-compose.yml` (exemplo mínimo)
```yaml
version: "3.9"
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: ai_challenge
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  api:
    build:
      context: ./backend
      dockerfile: api.Dockerfile
    environment:
      DB_DSN: postgresql+psycopg://postgres:postgres@db:5432/ai_challenge
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      MAX_DAILY_OPENAI_EUR: "20"
    depends_on: [db]
    ports: ["8000:8000"]
  scraper:
    build:
      context: ./scraper
      dockerfile: scraper.Dockerfile
    environment:
      DB_DSN: postgresql+psycopg://postgres:postgres@db:5432/ai_challenge
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    depends_on: [db]
  prometheus:
    image: prom/prometheus
    volumes: ["./infra/prometheus.yml:/etc/prometheus/prometheus.yml"]
    ports: ["9090:9090"]
  grafana:
    image: grafana/grafana
    ports: ["3000:3000"]
volumes:
  pgdata: {}
```

### A2. `api.Dockerfile`
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY backend/pyproject.toml backend/poetry.lock* ./
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic psycopg[binary]     structlog prometheus-client openai numpy scikit-learn rank-bm25     python-dotenv tenacity pgvector
COPY backend/. .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### A3. `scraper.Dockerfile`
```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy
WORKDIR /app
COPY scraper/requirements.txt .
RUN pip install -r requirements.txt
COPY scraper/. .
CMD ["python", "-m", "scraper.run", "--once"]
```

### A4. Pydantic models (FastAPI)
```python
class MatchItem(BaseModel):
    company_id: str
    name: str
    score: float
    explanation: list[str]

class IncentiveResponse(BaseModel):
    incentive_id: str
    title: str
    ai_description: dict
    matches: list[MatchItem] | None = None
```

### A5. Prompt de re-ranking (resumo)
```
Sistema: Classifica de 0 a 100 a compatibilidade entre o incentivo e a empresa.
Considera CAE, localização, tamanho, objetivos e critérios. Responde JSON:
{"score":0-100, "bullets":["...","..."]}. Usa apenas informação fornecida.
```

### A6. Scoring (código simplificado)
```python
def rule_penalty(ai, company):
    p = 1.0
    if ai.company_size and company.size not in ai.company_size and "não aplicável" not in ai.company_size:
        p *= 0.6
    if ai.caes and not set(ai.caes).intersection(set(company.cae_codes or [])):
        p *= 0.5
    if ai.geographic_location and not covers(ai.geographic_location, company):
        p *= 0.7
    return p
```

### A7. Métricas de ranking (Python)
```python
def precision_at_k(y_true, y_pred, k=5):
    return len(set(y_true) & set(y_pred[:k])) / k
```

### A8. Prometheus no FastAPI
```python
from prometheus_client import Counter, Histogram
REQUESTS = Counter("api_requests_total","requests",["route","code"])
LATENCY = Histogram("match_latency_seconds","latency")

@app.middleware("http")
async def metrics_middleware(request, call_next):
    start = time.perf_counter()
    resp = await call_next(request)
    LATENCY.observe(time.perf_counter()-start)
    REQUESTS.labels(request.url.path, resp.status_code).inc()
    return resp
```

### A9. Great Expectations (exemplo de expectativas)
```yaml
expect_table_row_count_to_be_between:
  min_value: 1
expect_column_values_to_not_be_null:
  column: incentive_id
expect_column_values_to_match_regex_list:
  column: total_budget
  regex_list: ["^$","^[0-9,.]+$"]
```

---

**FIM** — Este ficheiro serve como guia de implementação e como anexo de entrega técnica.
