# GreekNN Risk System

A real-time neural network-based portfolio risk management system with a FastAPI backend for front-office trader UI. Provides real-time Greeks visualization, spot horizon views, time ladder analysis, and **news-driven risk assessment**.

## Overview

The GreekNN Risk System is a modular Python library designed for financial institutions to perform portfolio risk analysis. It integrates news ingestion, NLP-based event processing, volatility shock modeling, and neural network-based Greeks computation with a web-based UI.

**Status:** All core Python modules implemented (1-9). FastAPI REST API server fully operational with WebSocket support for real-time Greeks visualization and news impact analysis.

## Key Features

- **Real-time News Ingestion**: Aggregates headlines from NewsAPI and RSS feeds (MAS, Fed, ECB)
- **NLP Event Processing**: Extracts structured event vectors using FinBERT sentiment analysis
- **Vol Shock Modeling**: Predicts volatility surface changes from economic events
- **News Impact Analysis**: Calculates which news events impact portfolio Greeks
- **NN Risk Engine**: Computes portfolio Greeks (Delta, Gamma, Vega, Theta, Rho) using ONNX/PyTorch/Black-Scholes
- **Multi-tier Caching**: Memory → Redis → Disk for low-latency surface retrieval
- **FastAPI Backend**: REST API with WebSocket support for real-time updates
- **Web UI**: Dashboard for portfolio management and Greeks visualization
- **Live Forex Integration**: Real-time spot rate fetching via Alpha Vantage/Frankfurter APIs
- **Alert System**: Spot rate movement alerts and risk limit breach monitoring

## News-Driven Risk Assessment

The system provides a complete news-to-risk pipeline:

```
News Headline → NLP Engine → Vol Shock Model → Vol Surface Service → Risk Engine → Greeks Impact
     │               │                │                │                  │              │
     ▼               ▼                ▼                ▼                  ▼              ▼
┌─────────┐   ┌───────────┐   ┌───────────┐   ┌───────────────┐   ┌──────────┐   ┌────────┐
│Reuters  │──▶│FinBERT    │──▶│Neural Net │──▶│Apply Shock    │──▶│Black-    │──▶│Dashboard│
│Bloomberg│   │Sentiment  │   │Vol Impact │   │to Surface     │   │Scholes   │   │Update  │
│MAS/Fed  │   │+ Entities │   │Prediction │   │Vol × (1 + Δ)  │   │Greeks    │   │        │
└─────────┘   └───────────┘   └───────────┘   └───────────────┘   └──────────┘   └────────┘
```

### Example: Fed Rate Decision Impact

```
Headline: "Fed signals potential rate cuts amid cooling inflation data"
         │
         ▼
Event Type: INTEREST_RATE | Sentiment: NEGATIVE (-0.73) | Importance: 0.82
         │
         ▼
Vol Shock: 1M ATM = -0.31% (vol decreases on rate cut expectation)
         │
         ▼
Portfolio Impact:
  - Delta: -$2,000 (currency appreciation expected)
  - Vega: -$3,000 (lower vol reduces option values)
  - Gamma: -$500 (delta exposure reduced)
```

## Project Structure

```
greek_nn/
├── api.py                    # FastAPI REST API server with WebSocket
├── config.py                 # Configuration management
├── logger.py                 # Structured logging setup
├── schemas.py                # Pydantic models and data classes
├── news_ingestion.py         # Module 1: News Ingestion Service
├── nlp_engine.py            # Module 2: NLP Processing with FinBERT
├── vol_shock_model.py       # Module 3: Volatility Shock Prediction
├── nn_risk_engine.py         # Module 5: Neural Network Risk Engine
├── vol_surface_service.py    # Module 4: Vol Surface Service
├── services/                 # Service modules
│   ├── alert_service.py      # Module 6: Alert System (spot rate & risk alerts)
│   ├── audit_service.py     # Module 8: Audit Service (pipeline traceability)
│   ├── forex_service.py      # Module 7: Live forex spot rate integration
│   └── risk_attribution_service.py  # Module 9: Risk Attribution (explicit percentage breakdown)
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
│   ├── ARCHITECTURE.md      # System architecture (with wireframes)
│   ├── API.md               # API reference
│   └── TRACEABILITY.md     # Requirements traceability
├── plans/                   # Implementation plans
│   └── live_spot_rate_integration_plan.md
└── tests/                   # Unit tests
    ├── __init__.py
    ├── conftest.py          # Pytest fixtures
    ├── test_nn_risk_engine.py
    ├── test_vol_surface.py
    ├── test_news_ingestion.py
    ├── test_nlp_engine.py
    ├── test_vol_shock_model.py
    ├── test_alert_service.py
    ├── test_forex_service.py
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
| GET | `/api/news` | Get recent news headlines |
| GET | `/api/news-impact` | **Get news with calculated impact on Greeks** |
| GET | `/api/audit/trace/{trace_id}` | Get full audit trace for pipeline execution |
| GET | `/api/audit/traces` | List recent audit traces |
| GET | `/api/risk-attribution-report` | Generate risk attribution report with explicit percentages |
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

### Example: News Impact Analysis via API

```bash
# Get news with impact on Greeks
curl "http://localhost:8000/api/news-impact?max_results=5"

# Response includes:
# - headline, source, url, published_at
# - event_type, sentiment, sentiment_score, importance
# - greeks_impact: {delta, gamma, vega, theta, rho}
# - vol_shocks: {1W_ATM, 1M_ATM, 3M_ATM, 6M_ATM, 1Y_ATM}
```

### Example: Get Recent News

```bash
# Get all recent headlines
curl "http://localhost:8000/api/news"

# Filter by keyword
curl "http://localhost:8000/api/news?keyword=fed"
```

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

### Example: News Ingestion (Python)

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

### Example: NLP Processing (Python)

```python
from nlp_engine import NLPEngine
from schemas import NewsEvent
from datetime import datetime

# Initialize engine (uses FinBERT if available, else rule-based fallback)
engine = NLPEngine()

# Process a news event
event = NewsEvent(
    headline="Fed signals potential rate cuts amid cooling inflation",
    source="Reuters",
    url="https://reuters.com",
    published_at=datetime.now(),
    content="Federal Reserve officials indicate openness to rate reductions."
)

event_vector = engine.process_news_event(event)

print(f"Event Type: {event_vector.event_type.value}")
print(f"Sentiment: {event_vector.sentiment.value} ({event_vector.sentiment_score})")
print(f"Importance: {event_vector.importance}")
print(f"Entities: {event_vector.entities}")
```

### Example: News-to-Risk Pipeline (Python)

```python
import asyncio
from news_ingestion import NewsIngestionService
from nlp_engine import NLPEngine
from vol_shock_model import VolShockModel
from vol_surface_service import VolSurfaceService, create_mock_surface
from nn_risk_engine import NNRiskEngine
from schemas import Portfolio
from datetime import datetime

async def assess_news_impact():
    # Initialize services
    news_service = NewsIngestionService()
    nlp_engine = NLPEngine()
    vol_shock_model = VolShockModel()
    vol_surface_service = VolSurfaceService()
    risk_engine = NNRiskEngine()
    
    # Fetch news
    headlines = await news_service.fetch_all_headlines()
    
    # Get baseline Greeks
    portfolio = Portfolio(...)
    baseline_surface = create_mock_surface(datetime.now())
    baseline_greeks = risk_engine.compute_portfolio_greeks(
        portfolio, baseline_surface, {"EURUSD": 1.0850}
    )
    
    # Process each headline and calculate impact
    for headline in headlines[:5]:
        # NLP processing
        event_vector = nlp_engine.process_news_event(headline)
        
        # Predict vol shock
        vol_shock = vol_shock_model.predict_shock(event_vector)
        
        # Apply shock
        shocked_surface, _ = vol_surface_service.get_shocked_surface(
            baseline_surface, vol_shock
        )
        
        # Compute impacted Greeks
        shocked_greeks = risk_engine.compute_portfolio_greeks(
            portfolio, shocked_surface, {"EURUSD": 1.0850}
        )
        
        # Calculate delta
        delta_vega = shocked_greeks.total_greeks.vega - baseline_greeks.total_greeks.vega
        
        print(f"{headline.headline[:50]}...")
        print(f"  → ΔVega: {delta_vega:.2f}")

asyncio.run(assess_news_impact())
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

The system consists of 8 main modules:

1. **News Ingestion** (`news_ingestion.py`) - Real-time headline aggregation from NewsAPI, RSS feeds
2. **NLP Processing** (`nlp_engine.py`) - Event vector extraction using FinBERT sentiment analysis
3. **Vol Shock Model** (`vol_shock_model.py`) - Predicts vol surface changes from events
4. **Vol Surface Service** (`vol_surface_service.py`) - Surface management, caching, and shock application
5. **NN Risk Engine** (`nn_risk_engine.py`) - Greeks computation (ONNX/PyTorch/Black-Scholes)
6. **Alert System** (`services/alert_service.py`) - Risk limit monitoring and spot rate alerts
7. **Forex Service** (`services/forex_service.py`) - Live forex spot rate integration with Alpha Vantage/Frankfurter APIs
8. **Audit Service** (`services/audit_service.py`) - Full pipeline traceability via SQLite in-memory database
9. **Risk Attribution Service** (`services/risk_attribution_service.py`) - Break down Greek changes into explicit attribution percentages

### Logging System

The project includes a comprehensive structured logging system with the following features:

- **Distributed Tracing**: Correlation IDs, trace IDs, and span IDs for request tracing
- **Context Propagation**: Automatic propagation of request context through all operations
- **Performance Logging**: `PerformanceLogger` context manager and `@log_performance` decorator
- **Structured Output**: JSON logging in production, colored output in development
- **Thread-Safe**: Thread-safe ID generation for concurrent operations

**Usage:**

```python
from logger import get_logger, log_performance, PerformanceLogger

# Simple logging
logger = get_logger(__name__)
logger.info("Processing request", extra_fields={"request_id": "123"})

# Performance context manager
with PerformanceLogger("model_inference", logger) as perf:
    result = model.predict(data)
    perf.add_metric("input_size", len(data))

# Decorator for functions
@log_performance("database_query")
def fetch_positions():
    ...
```

### Auditability & Traceability

The system provides full audit trail for the news-to-Greeks pipeline through the **Audit Service**:

- **SQLite In-Memory Database**: Persists all pipeline stages with thread-safe access
- **Trace IDs**: Each news batch processing run gets a unique trace ID (e.g., `news-batch-20260504-070551`)
- **Full Lineage**: Links NewsEvent → EventVector → VolShock → VolSurface → GreeksSnapshot
- **API Integration**: All audit data retrievable via REST endpoints

**Pipeline Trace Flow:**

```
NewsEvent → EventVector → VolShock → VolSurface → GreeksSnapshot
     │            │            │            │              │
     ▼            ▼            ▼            ▼              ▼
┌─────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────┐
│ news_   │ │ event_   │ │ vol_     │ │ vol_      │ │ greeks_  │
│ events  │ │ vectors  │ │ shocks   │ │ surfaces  │ │ snapshots│
└─────────┘ └──────────┘ └──────────┘ └───────────┘ └──────────┘
     │            │            │            │              │
     └────────────┴─────────────┴────────────┴──────────────┘
                          trace_id
```

**Audit API Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/audit/trace/{trace_id}` | Get full trace with all pipeline stages |
| GET | `/api/audit/traces` | List recent traces |
| POST | `/api/audit/trace/{trace_id}/end` | Mark trace as completed |

**Example: Retrieve Trace**

```bash
# Get full pipeline trace
curl "http://localhost:8000/api/audit/trace/news-batch-20260504-070551"

# Response includes:
# - trace: {trace_id, created_at, status, completed_at}
# - news_events: [{headline, source, url, published_at}]
# - event_vectors: [{event_type, sentiment, sentiment_score, importance}]
# - vol_shocks: [{delta_1W_ATM, delta_1M_ATM, ...}]
# - vol_surfaces: [{tenors, strikes, volatilities}]
# - greeks_snapshots: [{delta, gamma, vega, theta, rho}]
```

**Trace ID in UI:**

The system automatically includes `X-Trace-ID` in response headers for every API request. When fetching news impact, the trace ID is displayed in the UI allowing users to look up the full pipeline execution.

**Trace ID Display in News Impact Panel:**

When viewing news with impact, each news item shows its associated `trace_id` at the bottom of the news card. Clicking the trace ID opens the full audit trail for that specific news-to-Greeks execution.

```javascript
// The UI displays trace ID for each news impact
<div class="news-trace-id">
    Trace: <a href="/api/audit/trace/{trace_id}" target="_blank">{trace_id}</a>
</div>
```

### Risk Engine Modes

The risk engine supports multiple computation modes:
- **blackscholes** (default) - Analytical Black-Scholes formulas
- **onnx** - Neural network inference (requires `models/risk_nn.onnx`)
- **pytorch** - PyTorch model (not yet implemented)
- **auto** - Try ONNX → PyTorch → Black-Scholes fallback chain

### News Impact Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                       NEWS IMPACT FLOW                                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  News Sources ──▶ News Ingestion ──▶ NLP Engine ──▶ Vol Shock Model    │
│                                                                         │
│                        │                          │                    │
│                        ▼                          ▼                    │
│                   NewsEvent ─────────────▶ EventVector                 │
│                                              │                         │
│                                              ▼                         │
│                                       VolShock ──────────────────┐     │
│                                              │                    │     │
│                                              ▼                    ▼     │
│                                    Vol Surface ──────▶ Shocked Surface  │
│                                                              │          │
│                                                              ▼          │
│                                                       Risk Engine       │
│                                                              │          │
│                                                              ▼          │
│                                                       Greeks Impact     │
│                                                              │          │
│                                                              ▼          │
│                                                         Dashboard       │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
```

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
   - News ingestion will use mock headlines for demo
   - Set `NEWSAPI_KEY` in `.env` to enable real news

4. **NLP Model Loading Failed**
   - System uses rule-based fallback for sentiment analysis
   - FinBERT model will load automatically when available

5. **WebSocket Connection Issues**
   - Ensure `DEBUG=false` in production
   - Check CORS settings if connecting from different origin

## Wireframes

The system includes detailed wireframes in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md):

1. **News Impact Dashboard Flow** - Complete pipeline from news to Greeks impact
2. **Web UI Dashboard Layout** - Real-time risk dashboard with news panel
3. **News Impact Analysis Sequence** - API sequence diagram for news impact

## Use Cases

### UC-1: Real-time News Risk Assessment
Risk Manager monitors portfolio as news flows in. System automatically processes news through NLP → Vol Shock → Greeks pipeline and updates dashboard.

### UC-2: Portfolio Stress Testing via News
Replays historical news events to calculate portfolio impact under stress scenarios.

### UC-3: News-Driven Vol Surface Versioning
Each news event creates a new vol surface version linked to the triggering event for audit trail.

### UC-4: Time-Ladder Analysis with News Filter
Trader filters time ladder to show only positions affected by specific event types (e.g., interest rate news).

### UC-5: WebSocket Real-time Greeks Ticking
Trader receives live Greeks updates every second via WebSocket connection.

### UC-6: Trade Entry with Auto-Risk Assessment
Dealer enters new trade and immediately sees Greeks impact before confirmation.

## License

This project is proprietary software. See [LICENSE](LICENSE) for details.

## Support

For issues and questions, contact the Risk Engineering team.

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024-01 | Initial architecture |
| 1.1.0 | 2026-04 | Updated to reflect actual implementation state including FastAPI server |
| 2.0.0 | 2026-04 | Added WebSocket support, portfolio management, time ladder analysis |
| 2.1.0 | 2026-04 | Implemented Module 2 (NLP Engine with FinBERT) and Module 3 (Vol Shock Model) |
| 2.2.0 | 2026-04 | Added news-based wireframes, use cases, and UI layouts |
| 2.3.0 | 2026-05 | Added mobile-friendly UI, sort by category/sentiment, Greeks display at booking, spot movement alerts |
