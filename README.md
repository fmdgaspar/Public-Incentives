# 🚀 AI Challenge | Public Incentives

Sistema de matching automático entre incentivos públicos portugueses e empresas, utilizando LLMs e RAG.

---

## 📋 Índice

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Quick Start](#quick-start)
- [API Documentation](#api-documentation)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Development](#development)
- [Testing](#testing)
- [Cost Control](#cost-control)
- [Roadmap](#roadmap)

---

## 🎯 Visão Geral

Este projeto implementa um sistema completo de:
1. **Scraping** de incentivos públicos do Fundo Ambiental
2. **Extração estruturada** usando LLMs (GPT-4o-mini)
3. **Matching automático** entre incentivos e empresas
4. **Chatbot RAG** para consultas sobre incentivos e empresas
5. **API REST** para integração

### Funcionalidades Principais

- ✅ Scraper completo de incentivos PRR
- ✅ Extração de dados estruturados com IA
- ✅ Matching top-5 empresas por incentivo
- ✅ Embeddings vetoriais para busca semântica
- ✅ Chatbot RAG com citações de fonte
- ✅ Controlo de custos OpenAI (€0.30/documento)
- ✅ Cache inteligente de respostas LLM
- ✅ Métricas Prometheus
- ✅ Testes automatizados

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                        API REST (FastAPI)                        │
│  /health | /incentives | /companies | /matching | /chat        │
└─────────────────┬───────────────────────────────────────────────┘
                  │
        ┌─────────┴──────────┐
        │                    │
┌───────▼──────┐    ┌────────▼────────┐    ┌──────────────┐
│   Matching   │    │   RAG Service   │    │   OpenAI     │
│   Service    │◄───┤   (Chatbot)     │◄───┤   Client     │
└───────┬──────┘    └────────┬────────┘    └──────┬───────┘
        │                    │                     │
        │         ┌──────────┴─────────┐          │
        │         │                    │          │
        │    ┌────▼─────┐      ┌───────▼──────┐  │
        │    │  Vector  │      │  Embeddings  │  │
        └────►  Search  │      │   Service    │◄─┘
             └────┬─────┘      └───────┬──────┘
                  │                    │
        ┌─────────▼────────────────────▼─────────┐
        │     PostgreSQL + pgvector               │
        │  incentives | companies | embeddings   │
        └────────────────────────────────────────┘
                         ▲
                         │
        ┌────────────────┴─────────────────┐
        │         Data Pipeline             │
        │  Scraper → Parser → LLM → DB     │
        └──────────────────────────────────┘
```

### Componentes

1. **Scraper** (`scraper/`):
   - Playwright para web scraping
   - Parsers para extração determinística
   - PDF extractor para documentos

2. **LLM Services** (`backend/app/services/`):
   - OpenAI client com cache
   - Budget guard para controlo de custos
   - LLM extractor para dados estruturados
   - Embedding service para vetorização

3. **Matching** (`backend/app/services/matching_service.py`):
   - Vector similarity (50%)
   - BM25 text search (20%)
   - LLM re-ranking (30%)
   - Filtros determinísticos

4. **RAG Chatbot** (`backend/app/services/rag_service.py`):
   - Retrieval de documentos relevantes
   - Generation com citações
   - Controlo de custos

5. **Database** (`backend/app/models/`):
   - PostgreSQL com pgvector
   - Incentivos, empresas, embeddings

---

## 🚀 Quick Start

### Pré-requisitos

- Docker & Docker Compose
- OpenAI API Key

### Setup

1. **Clone o repositório**:
```bash
git clone <repo-url>
cd Public-Incentives
```

2. **Configure variáveis de ambiente**:
```bash
cp env.example .env
# Edite .env e adicione sua OPENAI_API_KEY
```

3. **Inicie os serviços**:
```bash
make setup
```

4. **Execute a pipeline completa**:
```bash
make pipeline
```

Isso irá:
- Scrape incentivos do Fundo Ambiental
- Extrair dados estruturados com LLM
- Gerar embeddings
- Carregar empresas do CSV
- Popular a base de dados

5. **Inicie a API**:
```bash
make start
```

A API estará disponível em `http://localhost:8000`

---

## 📚 API Documentation

### Endpoints Principais

#### Health Check
```bash
GET /health
```

#### Listar Incentivos
```bash
GET /api/v1/incentives?page=1&page_size=10
```

#### Obter Incentivo
```bash
GET /api/v1/incentives/{id}
```

#### Matching (Top 5 Empresas)
```bash
GET /api/v1/matching/{incentive_id}?limit=5
```

**Resposta**:
```json
{
  "incentive_id": "...",
  "matches": [
    {
      "company": { "id": "...", "name": "...", ... },
      "score": 0.85,
      "components": { "vector": 0.7, "bm25": 0.3, "llm": 0.9 },
      "penalties": { "size_mismatch": 0.8 },
      "explanation": "Alta compatibilidade..."
    }
  ]
}
```

#### Chatbot RAG
```bash
GET /api/v1/chat?question=eficiencia+energetica
```

**Resposta**:
```json
{
  "answer": "Existem vários incentivos...",
  "sources": [
    {
      "type": "incentive",
      "id": "...",
      "title": "Eficiência Energética...",
      "similarity": 0.89
    }
  ],
  "confidence": 0.85,
  "cost_eur": 0.0005
}
```

### Documentação Interativa

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

---

## 🛠️ Tech Stack

### Backend
- **FastAPI** - API REST framework
- **PostgreSQL + pgvector** - Base de dados vetorial
- **SQLAlchemy** - ORM
- **Pydantic** - Validação de dados

### AI/ML
- **OpenAI GPT-4o-mini** - Extração e re-ranking
- **text-embedding-3-small** - Embeddings (1536 dim)
- **rank-bm25** - Text search

### Scraping
- **Playwright** - Web automation
- **BeautifulSoup4** - HTML parsing
- **PyPDF2 / pdfplumber** - PDF extraction

### DevOps
- **Docker / Docker Compose** - Containerização
- **Prometheus** - Métricas
- **Grafana** - Dashboards
- **pytest** - Testing

---

## 📁 Project Structure

```
Public-Incentives/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routes & models
│   │   ├── db/               # Database setup & loaders
│   │   ├── models/           # SQLAlchemy models
│   │   ├── scripts/          # CLI scripts & pipeline
│   │   └── services/         # Business logic
│   ├── Dockerfile
│   └── requirements.txt
│
├── scraper/
│   ├── extractors/           # LLM & PDF extractors
│   ├── parsers/              # HTML parsers
│   ├── scraper.py           # Main scraper
│   └── requirements.txt
│
├── data/
│   ├── processed/           # incentives.json
│   └── raw/                 # Raw scraped data
│
├── tests/
│   ├── test_api.py
│   ├── test_matching_service.py
│   └── unit/
│
├── infra/
│   ├── init.sql            # PostgreSQL setup
│   ├── prometheus.yml
│   └── grafana/
│
├── docker-compose.yml
├── Makefile
└── README.md
```

---

## 💻 Development

### Comandos Úteis (Makefile)

```bash
# Setup inicial
make setup              # Inicia DB e cria schema

# Pipeline
make pipeline           # Pipeline completa (scraping + LLM + embeddings)
make pipeline-quick     # Pipeline com limite de documentos

# Serviços
make start              # Inicia todos os serviços
make stop               # Para todos os serviços
make restart            # Reinicia serviços

# Logs
make logs               # Logs de todos os serviços
make logs-api           # Logs da API
make logs-db            # Logs do PostgreSQL

# Database
make db-shell           # Shell PostgreSQL
make backup-db          # Backup da base de dados

# API
make api-shell          # Shell do container da API
make api-docs           # Abre documentação da API
make api-test           # Testa endpoints da API

# Matching
make search-matches     # Script de matching interativo
make evaluate-matching  # Avaliação P@5 e nDCG@5

# Cleanup
make clean              # Remove containers e volumes
make status             # Status dos serviços
```

### Desenvolvimento Local

```bash
# Criar virtual environment
python -m venv venv
source venv/bin/activate  # ou `venv\Scripts\activate` no Windows

# Instalar dependências
pip install -r requirements.txt
pip install -r backend/requirements.txt
pip install -r scraper/requirements.txt

# Instalar Playwright browsers
playwright install chromium

# Configurar DB local (opcional)
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_challenge"
```

---

## 🧪 Testing

### Executar Testes

```bash
# Todos os testes
make test

# Testes específicos
pytest tests/test_api.py
pytest tests/test_matching_service.py -v

# Com coverage
pytest --cov=backend --cov-report=html
```

### Estrutura de Testes

- **Unit tests**: `tests/unit/` - Funções isoladas
- **Integration tests**: `tests/integration/` - Serviços integrados
- **E2E tests**: `tests/e2e/` - Fluxos completos
- **API tests**: `tests/test_api.py` - Endpoints

---

## 💰 Cost Control

### Limites de Custo

- **Por documento**: €0.30 máximo
- **Por request API**: €0.30 máximo
- **Cache**: Respostas LLM em cache por 30 dias

### Custos Típicos

| Operação | Custo Médio | Tokens |
|----------|-------------|--------|
| Extração LLM (incentivo) | €0.0005 | ~2000 |
| Embedding (incentivo) | €0.00001 | ~500 |
| Matching (5 empresas) | €0.0004 | ~1500 |
| Chat RAG (query) | €0.0005 | ~2000 |

### Monitorização

```bash
# Ver estatísticas de custos
make stats

# Métricas Prometheus
http://localhost:9090

# Dashboard Grafana
http://localhost:3000
```

Documentação detalhada: [README_COST_CONTROL.md](README_COST_CONTROL.md)

---
