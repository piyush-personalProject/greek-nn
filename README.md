# GreekNN Risk System

A real-time neural network-based portfolio risk management system with a FastAPI backend for front-office trader UI. Provides real-time Greeks visualization, spot horizon views, and time ladder analysis.

## Overview

The GreekNN Risk System is a modular Python library designed for financial institutions to perform portfolio risk analysis. It integrates news ingestion, NLP-based event processing, volatility shock modeling, and neural network-based Greeks computation with a web-based UI.

**Status:** Core Python modules implemented. FastAPI REST API server fully operational with WebSocket support for real-time Greeks visualization.

## Key Features

- **Real-time News Ingestion**: Aggregates headlines from NewsAPI and RSS feeds (MAS, Fed, ECB)
- **NLP Event Processing**: Extracts structured event vectors using FinBERT sentiment analysis (when NLP model available)
- **Vol Shock Modeling**: Predicts volatility surface changes from economic events
- **NN Risk Engine**: Computes portfolio Greeks (Delta, Gamma, Vega, Theta, Rho) using ONNX/PyTorch/Black-Scholes
- **Multi-tier Caching**: Memory → Redis → Disk for low-latency surface retrieval
- **FastAPI Backend**: REST API with WebSocket support for real-time updates
- **Web UI**: Dashboard for portfolio management and Greeks visualization

## Project Structure

```
greek_nn/
├── api.py                    # FastAPI REST API server with WebSocket
├── config.py                 # Configuration management
├── logger.py                 # Structured logging setup
├── schemas.py                # Pydantic models and data classes
├── news_ingestion.py         # Module 1: News Ingestion Service
├── nn_risk_engine.py         # Module 5: Neural Network Risk Engine
├── vol_surface_service.py    # Module 4: Vol Surface Service
├── requirements.txt          # Python dependencies
├── run_tests.py             # Test runner script
├── pytest.ini               # Pytest configuration
├── .env.example             # Environment template
├── templates/               # Web UI templates
│   └── index.html           # Main dashboard HTML
├── static/                  # Static assets
│   ├── css/
│   │   └── greeks.css       # Dashboard styling
│   └── js/
│       └── greeks_ui.js     # Greeks visualization JS
├── docs/                    # Documentation
│   ├── ARCHITECTURE.md      # System architecture
│   ├── API.md               # API reference
│   └── TRACEABILITY.md     # Requirements traceability
└── tests/                   # Unit tests
    ├── __init__.py
    ├── conftest.py          # Pytest fixtures
    ├── test_nn_risk_engine.py
    ├── test_vol_surface.py
    ├── test_news_ingestion.py
    └── test_schemas.py
```

## Installation

### Prerequisites

- Python 3.10+
- Redis (optional, for caching - falls back to memory if unavailable)
- PostgreSQL (optional, for persistence)

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/your-org/greek_nn.git
cd greek_nn
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment** (optional - defaults work for testing)
```bash
cp .env.example .env
# Edit .env with your configuration if needed
```

## Running the API Server

### Start the server

```bash
python api.py
```

The API will be available at `http://localhost:8000`. The web UI dashboard will be served at the root URL.

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Main dashboard UI |
| GET | `/api/health` | Health check |
| GET | `/api/portfolios` | List all portfolios |
| GET | `/api/portfolios/{id}` | Get portfolio details |
| POST | `/api/portfolios/{id}/greeks` | Compute portfolio Greeks |
| GET | `/api/portfolios/{id}/time-ladder` | Time ladder analysis |
| GET | `/api/spot-rates` | Get current spot rates |
| GET | `/api/vol-surface` | Get vol surface summary |
| GET | `/api/risk-summary` | Dashboard risk summary |
| POST | `/api/trades` | Create new trade |
| DELETE | `/api/trades/{id}` | Delete trade |
| WS | `/ws/greeks` | Real-time Greeks WebSocket |

## Running Tests

### Using the test runner script
```bash
python run_tests.py
```

### Using pytest directly
```bash
# Run all tests
pytest -v

# Run with coverage
pytest --cov=. --cov-report=term-missing

# Run specific test file
pytest tests/test_nn_risk_engine.py -v
```

## Usage

### Example: Compute Portfolio Risk via API

```bash
# Get portfolio Greeks
curl -X POST "http://localhost:8000/api/portfolios/FX-PORTFOLIO-01/greeks"

# Get time ladder
curl "http://localhost:8000/api/portfolios/FX-PORTFOLIO-01/time-ladder?greek_type=vega"

# Get risk summary
curl "http://localhost:8000/api/risk-summary?portfolio_id=FX-PORTFOLIO-01"
```

### Example: Compute Portfolio Risk (Python)

```python
from datetime import datetime
from nn_risk_engine import NNRiskEngine
from vol_surface_service import create_mock_surface
from schemas import Portfolio, PortfolioPosition

# Create sample portfolio
portfolio = Portfolio(
    portfolio_id="PORT-001",
    timestamp=datetime.now(),
    positions=[
        PortfolioPosition(
            position_id="POS-001",
            instrument="EURUSD",
            spot=1.0850,
            strike=1.0900,
            tenor=1/12,  # 1M
            quantity=1000000,
            option_type="CALL",
            portfolio_id="PORT-001"
        )
    ]
)

# Create vol surface
vol_surface = create_mock_surface(datetime.now())

# Compute risk (uses Black-Scholes by default, falls back if ONNX/PyTorch models available)
engine = NNRiskEngine(model_mode="blackscholes")
spot_rates = {"EURUSD": 1.0850}
greeks = engine.compute_portfolio_greeks(portfolio, vol_surface, spot_rates)

print(f"Total Delta: {greeks.total_greeks.delta}")
print(f"Total Vega: {greeks.total_greeks.vega}")
print(f"Total Gamma: {greeks.total_greeks.gamma}")
```

### Example: News Ingestion

```python
import asyncio
from news_ingestion import NewsIngestionService

async def main():
    service = NewsIngestionService()
    headlines = await service.fetch_all_headlines()
    for h in headlines:
        print(f"{h.source}: {h.headline}")

asyncio.run(main())
```

### Example: Vol Surface Service

```python
from datetime import datetime
from vol_surface_service import VolSurfaceService, create_mock_surface

# Create service (Redis optional)
service = VolSurfaceService()

# Create and cache a surface
surface = create_mock_surface(datetime.now())
print(f"Surface version: {surface.version}")
print(f"Tenors: {surface.tenors}")
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | development | Environment (development/staging/production) |
| `DEBUG` | false | Enable debug mode |
| `LOG_LEVEL` | INFO | Logging level |
| `API_HOST` | 0.0.0.0 | API server host |
| `API_PORT` | 8000 | API server port |
| `NEWSAPI_KEY` | - | NewsAPI key for news ingestion |
| `REDIS_HOST` | localhost | Redis host for caching |
| `REDIS_PORT` | 6379 | Redis port |
| `NLP_DEVICE` | cpu | Device for NLP processing |
| `RISK_NN_PATH` | ./models/risk_nn.onnx | Path to ONNX risk model |
| `VOL_MODEL_PATH` | ./models/vol_shock.pkl | Path to vol shock model |
| `VEGA_LIMIT` | 100000 | Vega risk limit |
| `GAMMA_LIMIT` | 50000 | Gamma risk limit |
| `DELTA_LIMIT` | 500000 | Delta risk limit |
| `RHO_LIMIT` | 100000 | Rho risk limit |
| `ENABLE_NEWS` | true | Enable news ingestion |
| `ENABLE_NLP` | true | Enable NLP processing |
| `ENABLE_VOL_SHOCK` | false | Enable vol shock model |
| `ENABLE_ALERTS` | false | Enable alert generation |

## Architecture

The system consists of 6 main modules:

1. **News Ingestion** (`news_ingestion.py`) - Real-time headline aggregation
2. **NLP Processing** - Event vector extraction (requires FinBERT model)
3. **Vol Shock Model** - Predicts vol surface changes from events
4. **Vol Surface Service** (`vol_surface_service.py`) - Surface management and caching
5. **NN Risk Engine** (`nn_risk_engine.py`) - Greeks computation
6. **API Server** (`api.py`) - FastAPI REST API with WebSocket support

### Risk Engine Modes

The risk engine supports multiple computation modes:
- **blackscholes** (default) - Analytical Black-Scholes formulas
- **onnx** - Neural network inference (requires `models/risk_nn.onnx`)
- **pytorch** - PyTorch model (not yet implemented)
- **auto** - Try ONNX → PyTorch → Black-Scholes fallback chain

## Development

### Code Style

This project follows PEP 8:
- `black` for code formatting
- `isort` for import sorting
- `mypy` for type checking

```bash
# Format code
black .
isort .

# Type check
mypy .
```

## Docker

### Build and run with Docker

```bash
# Build image
docker build -t greek_nn:latest .

# Run container
docker run -p 8000:8000 greek_nn:latest
```

### Using Docker Compose

```bash
# Start with Redis and PostgreSQL
docker-compose up -d
```

## Monitoring

### Prometheus Metrics

The system exposes Prometheus metrics via the `prometheus.yml` configuration. Metrics include:
- `risk_computation_duration_seconds`
- `news_ingestion_total`
- `vol_surface_cache_hits_total`
- `alert_triggers_total`

## Troubleshooting

### Common Issues

1. **Redis Connection Failed**
   - The system falls back to memory-only caching automatically
   - Set `REDIS_HOST` correctly or ensure Redis is running

2. **ONNX/PyTorch Model Not Found**
   - The system automatically falls back to Black-Scholes
   - Greeks computation will still work with analytical formulas

3. **NewsAPI Key Missing**
   - News ingestion will be disabled
   - Set `NEWSAPI_KEY` in `.env` to enable

## License

This project is proprietary software. See [LICENSE](LICENSE) for details.

## Support

For issues and questions, contact the Risk Engineering team.
