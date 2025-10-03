"""
Testes para a API FastAPI.
"""

import pytest
import os
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

# Set dummy OpenAI API key for tests
os.environ["OPENAI_API_KEY"] = "test-key"

from backend.app.main import app

client = TestClient(app)


def test_root_endpoint():
    """Testa o endpoint raiz."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Public Incentives API"
    assert data["version"] == "1.0.0"
    assert "/docs" in data["docs"]
    assert "/api/v1/health" in data["health"]


def test_metrics_endpoint():
    """Testa o endpoint de métricas Prometheus."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "version=0.0.4" in response.headers["content-type"]
    
    # Verifica se contém métricas básicas
    content = response.text
    assert "http_requests_total" in content
    assert "http_request_duration_seconds" in content


@patch('backend.app.api.routes.get_db')
def test_health_endpoint(mock_get_db):
    """Testa o endpoint de health check."""
    # Mock da sessão de BD
    mock_db = Mock()
    mock_get_db.return_value = mock_db
    
    # Mock das queries
    mock_db.query.return_value.count.return_value = 10
    
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"
    assert data["database_connected"] is True


@patch('backend.app.api.routes.get_db')
def test_list_incentives(mock_get_db):
    """Testa o endpoint de listagem de incentivos."""
    # Mock da sessão de BD
    mock_db = Mock()
    mock_get_db.return_value = mock_db
    
    # Mock dos incentivos
    mock_incentive = Mock()
    mock_incentive.incentive_id = "test_id"
    mock_incentive.title = "Test Incentive"
    mock_incentive.description = "Test Description"
    mock_incentive.ai_description = {"test": "data"}
    mock_incentive.document_urls = []
    mock_incentive.publication_date = None
    mock_incentive.start_date = None
    mock_incentive.end_date = None
    mock_incentive.total_budget = None
    mock_incentive.source_link = None
    
    mock_db.query.return_value.filter.return_value.limit.return_value.offset.return_value.all.return_value = [mock_incentive]
    mock_db.query.return_value.filter.return_value.count.return_value = 1
    
    response = client.get("/api/v1/incentives?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert "incentives" in data
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 10


@patch('backend.app.api.routes.get_db')
def test_get_incentive_not_found(mock_get_db):
    """Testa o endpoint de obtenção de incentivo inexistente."""
    # Mock da sessão de BD
    mock_db = Mock()
    mock_get_db.return_value = mock_db
    
    # Mock de incentivo não encontrado
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    response = client.get("/api/v1/incentives/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


@patch('backend.app.api.routes.get_db')
def test_list_companies(mock_get_db):
    """Testa o endpoint de listagem de empresas."""
    # Mock da sessão de BD
    mock_db = Mock()
    mock_get_db.return_value = mock_db
    
    # Mock das empresas
    mock_company = Mock()
    mock_company.company_id = "test_company"
    mock_company.name = "Test Company"
    mock_company.cae_codes = ["12345"]
    mock_company.size = "pme"
    mock_company.district = "Lisboa"
    mock_company.county = None
    mock_company.parish = None
    mock_company.website = None
    mock_company.raw = {}
    
    mock_db.query.return_value.limit.return_value.offset.return_value.all.return_value = [mock_company]
    mock_db.query.return_value.count.return_value = 1
    
    response = client.get("/api/v1/companies?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert "companies" in data
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 10


def test_matching_endpoint_invalid_id():
    """Testa o endpoint de matching com ID inválido."""
    response = client.get("/api/v1/matching/invalid-id")
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


def test_api_docs_available():
    """Testa se a documentação da API está disponível."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_openapi_schema():
    """Testa se o schema OpenAPI está disponível."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "info" in data
    assert "paths" in data
