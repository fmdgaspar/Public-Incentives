"""
Testes para o serviço de matching.
"""

import pytest
import os
from unittest.mock import Mock, patch
import numpy as np

# Set dummy OpenAI API key for tests
os.environ["OPENAI_API_KEY"] = "test-key"

from backend.app.services.matching_service import MatchingService, MatchResult
from backend.app.models.incentive import Incentive
from backend.app.models.company import Company


@pytest.fixture
def mock_openai_client():
    """Mock do cliente OpenAI."""
    client = Mock()
    return client


@pytest.fixture
def matching_service(mock_openai_client):
    """Instância do serviço de matching."""
    return MatchingService(openai_client=mock_openai_client)


@pytest.fixture
def sample_incentive():
    """Incentivo de exemplo."""
    incentive = Mock(spec=Incentive)
    incentive.incentive_id = "test_incentive"
    incentive.title = "Test Incentive"
    incentive.description = "Test description"
    incentive.ai_description = {
        "investment_objectives": ["sustainability", "renewable energy"],
        "caes": ["12345"],
        "company_size": ["pme"],
        "geographic_location": "Portugal"
    }
    return incentive


@pytest.fixture
def sample_company():
    """Empresa de exemplo."""
    company = Mock(spec=Company)
    company.company_id = "test_company"
    company.name = "Test Company"
    company.cae_codes = ["12345", "67890"]
    company.size = "pme"
    company.district = "Lisboa"
    company.county = None
    company.parish = None
    company.raw = {"description": "Test company description"}
    return company


def test_matching_service_initialization(mock_openai_client):
    """Testa a inicialização do serviço de matching."""
    service = MatchingService(openai_client=mock_openai_client)
    
    assert service.client == mock_openai_client
    assert service.weights['vector'] == 0.50
    assert service.weights['bm25'] == 0.20
    assert service.weights['llm'] == 0.30
    assert service.penalties['size_mismatch'] == 0.8
    assert service.penalties['cae_mismatch'] == 0.7
    assert service.penalties['geo_mismatch'] == 0.9


def test_calculate_cosine_similarity(matching_service):
    """Testa o cálculo de similaridade coseno."""
    vec1 = np.array([1.0, 0.0, 0.0])
    vec2 = np.array([1.0, 0.0, 0.0])
    
    similarity = matching_service._calculate_cosine_similarity(vec1, vec2)
    assert similarity == 1.0
    
    vec3 = np.array([0.0, 1.0, 0.0])
    similarity = matching_service._calculate_cosine_similarity(vec1, vec3)
    # Vectors are orthogonal, so cosine similarity is 0, but our function normalizes to [0,1]
    assert similarity == 0.5  # (0 + 1) / 2 = 0.5


def test_tokenize_text(matching_service):
    """Testa a tokenização de texto."""
    text = "Energias renováveis e sustentabilidade ambiental"
    tokens = matching_service._tokenize_text(text)
    
    assert "energias" in tokens
    assert "renováveis" in tokens
    assert "sustentabilidade" in tokens
    assert "ambiental" in tokens
    assert "de" not in tokens  # Stop word removida
    assert "e" not in tokens   # Stop word removida


def test_calculate_bm25_score(matching_service, sample_incentive, sample_company):
    """Testa o cálculo do score BM25."""
    score = matching_service._calculate_bm25_score(sample_incentive, sample_company)
    
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_apply_deterministic_filters_no_penalties(matching_service, sample_incentive, sample_company):
    """Testa filtros determinísticos sem penalizações."""
    penalty, penalties_applied = matching_service._apply_deterministic_filters(
        sample_incentive, sample_company
    )
    
    assert penalty == 1.0
    assert penalties_applied == {}


def test_apply_deterministic_filters_size_penalty(matching_service, sample_incentive):
    """Testa filtros determinísticos com penalização de tamanho."""
    # Empresa com tamanho diferente
    company = Mock(spec=Company)
    company.company_id = "test_company"
    company.name = "Test Company"
    company.cae_codes = ["12345"]
    company.size = "grande"  # Diferente do exigido "pme"
    company.district = "Lisboa"
    company.county = None
    company.parish = None
    company.raw = {}
    
    penalty, penalties_applied = matching_service._apply_deterministic_filters(
        sample_incentive, company
    )
    
    assert penalty == 0.8  # size_mismatch penalty
    assert "size" in penalties_applied
    assert penalties_applied["size"] == 0.8


def test_apply_deterministic_filters_cae_penalty(matching_service, sample_incentive):
    """Testa filtros determinísticos com penalização de CAE."""
    # Empresa com CAE diferente
    company = Mock(spec=Company)
    company.company_id = "test_company"
    company.name = "Test Company"
    company.cae_codes = ["99999"]  # Diferente do exigido "12345"
    company.size = "pme"
    company.district = "Lisboa"
    company.county = None
    company.parish = None
    company.raw = {}
    
    penalty, penalties_applied = matching_service._apply_deterministic_filters(
        sample_incentive, company
    )
    
    assert penalty == 0.7  # cae_mismatch penalty
    assert "cae" in penalties_applied
    assert penalties_applied["cae"] == 0.7


def test_apply_deterministic_filters_geo_penalty(matching_service):
    """Testa filtros determinísticos com penalização geográfica."""
    # Incentivo com localização específica
    incentive = Mock(spec=Incentive)
    incentive.ai_description = {
        "geographic_location": "Algarve"
    }
    
    # Empresa em localização diferente
    company = Mock(spec=Company)
    company.company_id = "test_company"
    company.name = "Test Company"
    company.cae_codes = []
    company.size = None
    company.district = "Lisboa"  # Diferente do exigido "Algarve"
    company.county = None
    company.parish = None
    company.raw = {}
    
    penalty, penalties_applied = matching_service._apply_deterministic_filters(
        incentive, company
    )
    
    assert penalty == 0.9  # geo_mismatch penalty
    assert "geo" in penalties_applied
    assert penalties_applied["geo"] == 0.9


@patch('backend.app.services.matching_service.MatchingService._llm_rerank')
def test_find_matches_no_llm(mock_llm_rerank, matching_service):
    """Testa busca de matches sem LLM."""
    # Mock do LLM rerank
    mock_llm_rerank.return_value = {}
    
    # Mock da sessão de BD
    mock_db = Mock()
    
    # Mock do incentivo
    mock_incentive = Mock()
    mock_incentive.incentive_id = "test_incentive"
    mock_incentive.title = "Test Incentive"
    mock_incentive.description = "Test description"
    mock_incentive.ai_description = {"test": "data"}
    
    # Mock do embedding do incentivo
    mock_embedding = Mock()
    mock_embedding.embedding = np.array([0.1, 0.2, 0.3])
    
    # Mock das queries
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_incentive,  # Primeira query: incentivo
        mock_embedding   # Segunda query: embedding
    ]
    
    # Mock da query SQL para candidatos
    mock_result = Mock()
    mock_row = Mock()
    mock_row.company_id = "test_company"
    mock_row.name = "Test Company"
    mock_row.cae_codes = ["12345"]
    mock_row.size = "pme"
    mock_row.district = "Lisboa"
    mock_row.county = None
    mock_row.parish = None
    mock_row.website = None
    mock_row.raw = {}
    mock_row.embedding = np.array([0.1, 0.2, 0.3])
    mock_row.vector_similarity = 0.8
    
    mock_result.__iter__ = Mock(return_value=iter([mock_row]))
    mock_db.execute.return_value = mock_result
    
    # Executar teste
    matches = matching_service.find_matches(mock_db, "test_incentive", top_k=1, use_llm=False)
    
    assert len(matches) == 1
    assert isinstance(matches[0], MatchResult)
    assert matches[0].company_id == "test_company"
    assert matches[0].company_name == "Test Company"
    assert 0.0 <= matches[0].score <= 1.0
