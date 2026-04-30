# Tests

This directory contains unit tests for the GreekNN Risk System.

## Structure

```
tests/
├── __init__.py
├── conftest.py              # Pytest fixtures and configuration
├── test_nn_risk_engine.py   # Tests for NN Risk Engine
├── test_vol_surface.py      # Tests for Vol Surface Service
├── test_news_ingestion.py   # Tests for News Ingestion
└── test_schemas.py          # Tests for Pydantic schemas
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html --cov-report=term

# Run specific test file
pytest tests/test_nn_risk_engine.py -v

# Run with verbose output
pytest -vv --tb=long

# Run tests matching a pattern
pytest -k "test_delta"

# Using the test runner script
python run_tests.py
```

## Test Configuration

Tests use fixtures defined in `conftest.py`:
- `sample_portfolio` - Mock portfolio for testing
- `mock_vol_surface` - Mock vol surface for testing
- `sample_news_event` - Mock news event for testing
- `mock_redis` - Mock Redis client for caching tests
- `risk_limits` - Risk limit configuration

## Fixtures

```python
# conftest.py provides:
@pytest.fixture
def sample_portfolio():
    """Creates a sample portfolio for testing."""
    ...

@pytest.fixture
def mock_vol_surface():
    """Creates a mock vol surface."""
    ...

@pytest.fixture
def sample_event_vector():
    """Creates a sample event vector."""
    ...

@pytest.fixture
def risk_limits():
    """Creates risk limit configuration."""
    ...
```

## Writing Tests

When adding new tests:

1. Use descriptive test names: `test_<method>_<scenario>_<expected>`
2. Add docstrings explaining what is being tested
3. Use fixtures for common test data
4. Assert specific values, not just "truthy" checks
5. Test both success and failure paths

```python
def test_compute_greeks_with_valid_inputs(sample_portfolio, mock_vol_surface):
    """Test that compute_greeks returns correct values for valid inputs."""
    engine = NNRiskEngine(model_mode="blackscholes")
    result = engine.compute_portfolio_greeks(
        sample_portfolio,
        mock_vol_surface,
        {"EURUSD": 1.085}
    )
    
    assert result.total_greeks.delta != 0
    assert result.portfolio_id == sample_portfolio.portfolio_id
```

## Test Coverage

| Module | Test File | Test Count |
|--------|-----------|------------|
| NN Risk Engine | `test_nn_risk_engine.py` | 25+ |
| Vol Surface | `test_vol_surface.py` | 15 |
| News Ingestion | `test_news_ingestion.py` | 14 |
| Schemas | `test_schemas.py` | 22 |
| **Total** | | **76+** |

## API Testing

The API server (`api.py`) is tested via manual testing or integration tests. Key endpoints to test:

- `GET /api/health` - Health check
- `GET /api/portfolios` - List portfolios
- `GET /api/portfolios/{id}` - Get portfolio details
- `POST /api/portfolios/{id}/greeks` - Compute Greeks
- `GET /api/portfolios/{id}/time-ladder` - Time ladder
- `GET /api/spot-rates` - Get spot rates
- `GET /api/vol-surface` - Get vol surface
- `GET /api/risk-summary` - Risk summary
- `POST /api/trades` - Create trade
- `DELETE /api/trades/{id}` - Delete trade
- `WS /ws/greeks` - WebSocket real-time updates

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2024-01 | 1.0.0 | Initial test documentation |
| 2026-04 | 2.0.0 | Added API testing section, updated structure |