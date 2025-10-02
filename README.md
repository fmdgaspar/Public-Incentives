# AI Challenge | Public Incentives

Automatic matching system between companies and public incentives from Environmental Fund using LLM.

## What does it do?

- **Scrapes** incentives from "Apoios PRR" tab of Environmental Fund
- **Structured extraction** with GPT-4o-mini (CAE codes, location, eligibility criteria)
- **Intelligent matching** between companies and incentives (vectors + BM25 + LLM re-ranking)
- **REST API** for querying and top-5 recommendations per incentive

## Architecture

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
[ Matching Service (rules + vectors + BM25 + re-rank LLM) ]
     |
   [ FastAPI ] ----> [ Chatbot RAG ] (optional)
     |
[ Observability: Logs JSON | Prometheus | Grafana ]
```

## Quick Start

```bash
# 1. Setup environment
cp env.example .env
# Edit .env and add your OPENAI_API_KEY

# 2. Start the stack
docker-compose up -d

# 3. Access API
open http://localhost:8000/docs
```

## Tech Stack

- **Backend**: Python 3.11, FastAPI, Pydantic
- **Database**: PostgreSQL 16 + pgvector
- **LLM**: OpenAI (gpt-4o-mini + text-embedding-3-small)
- **Scraping**: Playwright + BeautifulSoup
- **Matching**: Cosine similarity + BM25 + LLM re-ranking
- **Observability**: Prometheus + Grafana

## Structure

```
backend/        # FastAPI API
scraper/        # Web scraping & LLM extraction
infra/          # Prometheus, Grafana configs
tests/          # Unit, integration, E2E
data/           # Raw data & CSVs
```

## Development

```bash
# Local setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Tests
pytest

# Linting
ruff check .
black .
```
