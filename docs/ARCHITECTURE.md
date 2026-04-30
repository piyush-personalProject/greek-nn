# GreekNN Risk System Architecture

## System Overview

The GreekNN Risk System is a portfolio risk management library that processes news events through NLP to generate volatility shocks, applies them to a vol surface, and computes neural network-based Greeks for risk assessment.

**Current Status:** ✅ All core Python modules implemented (1-5). REST API server (FastAPI) fully operational with WebSocket support for real-time Greeks visualization.

## Project Components

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    GREEK NN RISK SYSTEM                                             │
├─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                                    EXTERNAL DATA SOURCES                                         │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                          │ │
│  │  │  NewsAPI   │  │   MAS RSS   │  │  FED RSS    │  │   ECB RSS   │                          │ │
│  │  │  (REST)    │  │   (Feed)    │  │   (Feed)    │  │   (Feed)    │                          │ │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                          │ │
│  └─────────┼────────────────┼────────────────┼────────────────┼─────────────────────────────────┘ │
│            │                │                │                │                                   │
│            ▼                ▼                ▼                ▼                                   │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                    MODULE 1: NEWS INGESTION (news_ingestion.py)                                │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  NewsIngestionService                                                                  │    │ │
│  │  │  ├── NewsAPISource (NewsAPI.org REST API)                                               │    │ │
│  │  │  ├── RSSFeedSource (MAS, Fed, ECB feeds)                                               │    │ │
│  │  │  ├── BloombergSource (stub implementation)                                              │    │ │
│  │  │  └── Real-time aggregation with deduplication                                            │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  └────────────────────────────────────────────────────────────┬───────────────────────────────────┘ │
│                                                               │                                     │
│                                                               ▼                                     │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                    MODULE 2: NLP PROCESSING (planned)                                        │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  NLPEngine (FinBERT-based sentiment and event extraction)                                 │    │ │
│  │  │  ├── EventVector extraction (type, sentiment, importance, surprise)                    │    │ │
│  │  │  ├── Entity recognition (central banks, currencies, indicators)                        │    │ │
│  │  │  └── Processed event caching in Redis                                                   │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  └────────────────────────────────────────────────────────────┬───────────────────────────────────┘ │
│                                                               │                                     │
│                                                               ▼                                     │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                    MODULE 3: VOL SHOCK MODEL (planned)                                       │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  VolShockModel (Neural network for vol impact prediction)                                │    │ │
│  │  │  Input: EventVector (sentiment_score, importance, surprise_factor, event_type)          │    │ │
│  │  │  Output: VolShock (delta impacts at tenors: 1W, 1M, 3M, 6M, 1Y and 1M 25RR, 25BF)     │    │ │
│  │  │  └── Vol shock application to vol surface                                                │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  └────────────────────────────────────────────────────────────┬───────────────────────────────────┘ │
│                                                               │                                     │
│                                                               ▼                                     │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │               MODULE 4: VOL SURFACE SERVICE (vol_surface_service.py)                         │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  VolSurfaceService                                                                         │    │ │
│  │  │  ├── Baseline surface management                                                          │    │ │
│  │  │  ├── Multi-tier caching (Memory → Redis → Disk)                                         │    │ │
│  │  │  ├── Shock application: Vol_shocked = Vol_base × (1 + Δ)                               │    │ │
│  │  │  └── Version control for audit trail                                                     │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  VolSurfaceSchema                                                                          │    │ │
│  │  │  ├── Tenors: [1W, 1M, 3M, 6M, 1Y]                                                        │    │ │
│  │  │  └── Strikes: [ATM, +25RR, -25RR, +25BF, -25BF]                                         │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  └────────────────────────────────────────────────────────────┬───────────────────────────────────┘ │
│                                                               │                                     │
│                                                               ▼                                     │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │               MODULE 5: NN RISK ENGINE (nn_risk_engine.py)                                   │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  NNRiskEngine                                                                             │    │ │
│  │  │  ├── Compute portfolio Greeks: Δ, Γ, ν, θ, ρ                                             │    │ │
│  │  │  ├── Input: [spot, strike, tenor, vol, rate, option_type]                               │    │ │
│  │  │  ├── Modes: ONNX | PyTorch | Black-Scholes (fallback)                                   │    │ │
│  │  │  ├── Bucketed vega analysis by tenor                                                    │    │ │
│  │  │  └── Position-level and aggregated portfolio Greeks                                     │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  └────────────────────────────────────────────────────────────┬───────────────────────────────────┘ │
│                                                               │                                     │
│                                                               ▼                                     │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                    MODULE 6: ALERT SYSTEM (planned)                                          │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  AlertEngine                                                                             │    │ │
│  │  │  ├── Risk limit monitoring (vega, gamma, delta, rho)                                    │    │ │
│  │  │  ├── Threshold-based alert generation                                                    │    │ │
│  │  │  └── Action recommendations                                                               │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  └────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                              DATA MODELS (schemas.py)                                         │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  NewsEvent, EventVector, VolShock, VolSurface, Portfolio, Greeks, RiskAlert            │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  └────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                              API SERVER (api.py - FastAPI)                                     │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  REST API Endpoints                                                                     │    │ │
│  │  │  ├── GET /api/health - Health check                                                     │    │ │
│  │  │  ├── GET /api/portfolios - List portfolios                                             │    │ │
│  │  │  ├── GET /api/portfolios/{id} - Portfolio details                                      │    │ │
│  │  │  ├── POST /api/portfolios/{id}/greeks - Compute Greeks                                 │    │ │
│  │  │  ├── GET /api/portfolios/{id}/time-ladder - Time ladder view                           │    │ │
│  │  │  ├── GET /api/spot-rates - Current spot rates                                          │    │ │
│  │  │  ├── GET /api/vol-surface - Vol surface summary                                         │    │ │
│  │  │  ├── GET /api/risk-summary - Dashboard risk summary                                     │    │ │
│  │  │  ├── POST /api/trades - Create new trade                                               │    │ │
│  │  │  └── DELETE /api/trades/{id} - Delete trade                                            │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  WebSocket Endpoint                                                                    │    │ │
│  │  │  ├── /ws/greeks - Real-time Greeks tick updates                                        │    │ │
│  │  │  └── Broadcast events: trade_added, trade_removed                                      │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  Frontend UI (templates/, static/)                                                     │    │ │
│  │  │  ├── index.html - Main dashboard                                                       │    │ │
│  │  │  ├── greeks_ui.js - Greeks visualization                                              │    │ │
│  │  │  └── greeks.css - Dashboard styling                                                    │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  └────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
News Headline                    EventVector                    VolShock
───────────                    ───────────                    ─────────
    │                               │                               │
    ▼                               ▼                               ▼
┌─────────┐   ┌─────────────┐   ┌─────────┐   ┌───────────┐   ┌─────────┐
│ Source  │──▶│  NLP Engine │──▶│ Vol Shock│──▶│ Vol Surface│──▶│Risk Eng │
│ (Multi) │   │  (FinBERT)  │   │  Model   │   │  Service   │   │   (NN)  │
└─────────┘   └─────────────┘   └─────────┘   └───────────┘   └─────────┘
                                                                                    │
                                                                                    ▼
                                                                         ┌───────────┐
                                                                         │   API     │
                                                                         │  Server   │
                                                                         └───────────┘
                                                                              │
                                                                              ▼
                                                                    ┌───────────┐
                                                                    │  Web UI   │
                                                                    └───────────┘
```

**Note:** Modules 2 (NLP Engine) and 3 (Vol Shock Model) are now fully implemented. Module 6 (Alert System) is planned.

## Component Responsibilities

### Module 1: News Ingestion (`news_ingestion.py`)
- **File**: `news_ingestion.py`
- **Status**: ✅ Implemented
- **Responsibility**: Real-time headline aggregation from multiple sources
- **Latency Target**: <500ms from headline publish to system ingestion
- **Sources**: NewsAPI, MAS RSS, Fed RSS, Bloomberg (stub)
- **Data**: `NewsEvent` schema with headline, source, url, published_at

### Module 2: NLP Processing (`nlp_engine.py`)
- **File**: `nlp_engine.py`
- **Status**: ✅ Implemented
- **Responsibility**: Extract structured event vectors from headlines using FinBERT
- **Model**: FinBERT (ProsusAI/finbert) for financial sentiment analysis
- **Features**:
  - Sentiment analysis (positive, negative, neutral)
  - Event type classification (interest_rate, inflation, employment, central_bank, macro, unknown)
  - Entity extraction (central banks, currencies, indicators)
  - Importance and surprise factor scoring
  - Redis caching for processed events
- **Output**: `EventVector` with event_type, sentiment, sentiment_score, importance, surprise_factor

### Module 3: Vol Shock Model (`vol_shock_model.py`)
- **File**: `vol_shock_model.py`
- **Status**: ✅ Implemented
- **Responsibility**: Predict vol surface changes from events
- **Features**:
  - Neural network (PyTorch) for vol impact prediction
  - ONNX runtime for production inference
  - Rule-based fallback when models unavailable
  - Redis caching for predicted shocks
  - Training interface for model updates
- **Input**: EventVector features (sentiment_score, importance, surprise_factor, event_type)
- **Output**: VolShock with deltas for each tenor (1W, 1M, 3M, 6M, 1Y ATM) and 1M 25RR, 25BF

### Module 4: Vol Surface Service (`vol_surface_service.py`)
- **File**: `vol_surface_service.py`
- **Status**: ✅ Implemented
- **Responsibility**: Maintain, cache, and serve vol surfaces
- **Caching**: Memory (5min TTL) → Redis (optional) → Backend
- **Versioning**: Each surface has version ID for traceability
- **Dependencies**: QuantLib (optional, falls back gracefully)

### Module 5: NN Risk Engine (`nn_risk_engine.py`)
- **File**: `nn_risk_engine.py`
- **Status**: ✅ Implemented
- **Responsibility**: Compute portfolio Greeks using neural networks or Black-Scholes
- **Input**: Portfolio positions, vol surface, spot rates
- **Output**: Greeks (delta, gamma, vega, theta, rho) per position and total
- **Modes**: 
  - Black-Scholes (default, fully implemented)
  - ONNX (requires `models/risk_nn.onnx`)
  - PyTorch (planned)

### Module 6: Alert System
- **Status**: ⚠️ Planned
- **Responsibility**: Monitor risk limits and generate alerts
- **Limits**: Vega (100K), Gamma (50K), Delta (500K), Rho (100K), Shock (1%)
- **Output**: RiskAlert with exceeded value and recommended action

### API Server (`api.py`)
- **File**: `api.py`
- **Status**: ✅ Implemented
- **Framework**: FastAPI with uvicorn
- **Responsibility**: REST API and WebSocket endpoints for front-office UI
- **Features**:
  - Portfolio management (list, get, create trades, delete trades)
  - Greeks computation (single and batch)
  - Time ladder analysis (Greeks bucketed by tenor)
  - Real-time WebSocket updates
  - Vol surface and spot rates endpoints
  - Risk summary dashboard endpoint

## Technology Stack

| Component | Technology | Purpose | Status |
|-----------|------------|---------|--------|
| Core Language | Python 3.10+ | Application logic | ✅ |
| Web Framework | FastAPI | REST API server | ✅ |
| Data Models | Pydantic | Schema validation | ✅ |
| NLP | FinBERT (Transformers) | Sentiment analysis | ✅ Implemented |
| ML Inference | ONNX Runtime | Production NN inference | ✅ Available |
| Numerical | NumPy, SciPy | Mathematical computations | ✅ |
| Vol Finance | QuantLib, py_vollib | Vol surface modeling | ✅ Available |
| Cache | Redis | Vol surface caching | ✅ Optional |
| Database | PostgreSQL | Persistence | ⚠️ Planned |
| News APIs | NewsAPI, RSS | News ingestion | ✅ |
| Logging | structlog | Structured JSON logging | ✅ |
| Testing | pytest | Unit tests | ✅ |
| Monitoring | Prometheus | Metrics | ✅ Available |

## Configuration Management

All configuration is managed via environment variables with `.env` file support:

```bash
# Environment
ENVIRONMENT=development
DEBUG=false
LOG_LEVEL=INFO

# API Server
API_HOST=0.0.0.0
API_PORT=8000

# Database (for future use)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=risk_system

# Redis (optional - falls back to memory)
REDIS_HOST=localhost
REDIS_PORT=6379

# News API
NEWSAPI_KEY=your_api_key

# ML Configuration
NLP_DEVICE=cpu
RISK_NN_PATH=./models/risk_nn.onnx
VOL_MODEL_PATH=./models/vol_shock.pkl

# Risk Limits
VEGA_LIMIT=100000
GAMMA_LIMIT=50000
DELTA_LIMIT=500000
RHO_LIMIT=100000

# Feature Flags
ENABLE_NEWS=true
ENABLE_NLP=true
ENABLE_VOL_SHOCK=false
ENABLE_ALERTS=false
```

## Error Handling & Resilience

1. **Fallback Chain**: ONNX → PyTorch → Black-Scholes
2. **Cache Miss Handling**: Memory → Redis → Backend
3. **Graceful Degradation**: 
   - Redis unavailable → memory-only caching
   - QuantLib unavailable → numpy-based calculations
   - NLP unavailable → manual event input
   - ONNX/PyTorch unavailable → Black-Scholes analytical

## File Structure

```
greek_nn/
├── api.py                    # FastAPI REST API server
├── config.py                 # Configuration management
├── logger.py                 # Structured logging setup  
├── schemas.py                # Pydantic models and data classes
├── news_ingestion.py         # Module 1: News ingestion service
├── nlp_engine.py            # Module 2: NLP processing with FinBERT
├── vol_shock_model.py       # Module 3: Volatility shock prediction
├── nn_risk_engine.py         # Module 5: Risk engine with Greeks computation
├── vol_surface_service.py    # Module 4: Vol surface management
├── requirements.txt          # Python dependencies
├── run_tests.py             # Test runner
├── pytest.ini               # Pytest configuration
├── .env.example             # Environment template
├── templates/               # Web UI templates
│   └── index.html           # Main dashboard HTML
├── static/                  # Static assets
│   ├── css/
│   │   └── greeks.css       # Dashboard styling
│   └── js/
│       └── greeks_ui.js     # Greeks visualization JS
├── docs/
│   ├── ARCHITECTURE.md       # This file
│   ├── API.md               # API reference
│   └── TRACEABILITY.md      # Requirements traceability
└── tests/
    ├── __init__.py
    ├── conftest.py          # Pytest fixtures
    ├── test_nn_risk_engine.py
    ├── test_vol_surface.py
    ├── test_news_ingestion.py
    ├── test_nlp_engine.py   # Module 2 tests
    ├── test_vol_shock_model.py  # Module 3 tests
    └── test_schemas.py
```

## API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serve main UI |
| GET | `/api/health` | Health check |
| GET | `/api/portfolios` | List all portfolios |
| GET | `/api/portfolios/{id}` | Get portfolio details |
| POST | `/api/portfolios/{id}/greeks` | Compute portfolio Greeks |
| GET | `/api/portfolios/{id}/time-ladder` | Get time ladder view |
| GET | `/api/spot-rates` | Get current spot rates |
| GET | `/api/vol-surface` | Get vol surface summary |
| GET | `/api/risk-summary` | Get dashboard risk summary |
| POST | `/api/trades` | Create new trade |
| DELETE | `/api/trades/{id}` | Delete trade |
| WS | `/ws/greeks` | Real-time Greeks WebSocket |

### News Impact Tracking

The system tracks which news impacted Greeks through:

```
NewsEvent → EventVector → VolShock → VolSurface (shocked) → PortfolioGreeks (new)
                                                        → PortfolioGreeks (old, baseline)
                                                            ↓
                                                    Greeks Impact (Δdelta, Δgamma, etc.)
```

**New API Endpoint:** `GET /api/news-impact`
- Returns recent news with their calculated impact on Greeks
- Shows baseline Greeks vs shocked Greeks
- Displays vol shocks per tenor (1W, 1M, 3M, 6M, 1Y ATM)
- Shows event type, sentiment, and importance

**UI Feature:** "Show Impact" button in News panel toggles between news list and news-with-impact view

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024-01 | Initial architecture |
| 1.1.0 | 2026-04 | Updated to reflect actual implementation state including FastAPI server |
| 2.0.0 | 2026-04 | Added WebSocket support, portfolio management, time ladder analysis |
| 2.1.0 | 2026-04 | Implemented Module 2 (NLP Engine with FinBERT) and Module 3 (Vol Shock Model) |
