# GreekNN Risk System Architecture

## System Overview


The GreekNN Risk System is a portfolio risk management library that processes news events through NLP to generate volatility shocks, applies them to a vol surface, and computes neural network-based Greeks for risk assessment.

**Current Status:** All core Python modules implemented (1-9). REST API server (FastAPI) fully operational with WebSocket support for real-time Greeks visualization.

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
│  │                    MODULE 2: NLP PROCESSING (nlp_engine.py)                                    │ │
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
│  │                    MODULE 3: VOL SHOCK MODEL (vol_shock_model.py)                             │ │
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
│  │                    MODULE 6: ALERT SYSTEM (services/alert_service.py)                            │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  AlertService                                                                             │    │ │
│  │  │  ├── Spot rate movement monitoring (move, spike, trend detection)                        │    │ │
│  │  │  ├── Risk limit monitoring (vega, gamma, delta, rho thresholds)                         │    │ │
│  │  │  ├── Threshold-based alert generation with severity levels                              │    │ │
│  │  │  ├── Alert cooldown and rate limiting                                                    │    │ │
│  │  │  └── Alert acknowledgment and cleanup                                                     │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  └────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                    MODULE 7: FOREX SERVICE (services/forex_service.py)                           │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  ForexService                                                                            │    │ │
│  │  │  ├── Live spot rate fetching via Alpha Vantage/Frankfurter APIs                        │    │ │
│  │  │  ├── Multi-currency support (EURUSD, USDJPY, GBPUSD, USDCHF, AUDUSD, USDCAD, NZDUSD)  │    │ │
│  │  │  ├── Baseline rate tracking and change calculation                                     │    │ │
│  │  │  └── Historical data retrieval                                                          │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  └────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                    MODULE 8: AUDIT SERVICE (services/audit_service.py)                          │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  AuditService                                                                            │    │ │
│  │  │  ├── Full pipeline traceability via SQLite in-memory database                         │    │ │
│  │  │  ├── Trace IDs linking all pipeline stages                                             │    │ │
│  │  │  │     NewsEvent → EventVector → VolShock → VolSurface → GreeksSnapshot              │    │ │
│  │  │  ├── Thread-safe connections using shared cache                                       │    │ │
│  │  │  └── Recent traces listing with status filtering                                       │    │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘    │ │
│  └────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                    MODULE 9: RISK ATTRIBUTION (services/risk_attribution_service.py)             │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐    │ │
│  │  │  RiskAttributionService                                                                  │    │ │
│  │  │  ├── Break down Greek changes into explicit attribution percentages                   │    │ │
│  │  │  ├── News Headlines attribution (NLP → Vol Shock)                                     │    │ │
│  │  │  ├── Historical Vol Drift attribution (natural market movement)                       │    │ │
│  │  │  ├── NN Model Adjustment attribution (neural network corrections)                     │    │ │
│  │  │  ├── Vega spike detection ($10K+ threshold) with special report                       │    │ │
│  │  │  ├── Primary driver identification                                                     │    │ │
│  │  │  └── Confidence scoring for attributions                                               │    │ │
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
│  │  │  ├── GET /api/news - News headlines                                                    │    │ │
│  │  │  ├── GET /api/news-impact - News impact on Greeks                                     │    │ │
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
──────────                    ───────────                    ─────────
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

**All modules 1-5 are now fully implemented.**

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

### Module 6: Alert System (`services/alert_service.py`)
- **Status**: ✅ Implemented
- **Responsibility**: Monitor risk limits and spot rate movements
- **Features**:
  - Spot rate movement monitoring (move, spike, trend detection)
  - Risk limit monitoring (vega, gamma, delta, rho)
  - Threshold-based alert generation with severity levels
  - Alert cooldown and rate limiting
  - Alert acknowledgment and cleanup
- **Alert Types**: SpotRateAlert, RiskAlert

### Module 7: Forex Service (`services/forex_service.py`)
- **Status**: ✅ Implemented
- **Responsibility**: Real-time forex spot rate integration
- **Features**:
  - Live spot rate fetching via Alpha Vantage and Frankfurter APIs
  - Multi-currency support (EURUSD, USDJPY, GBPUSD, USDCHF, AUDUSD, USDCAD, NZDUSD)
  - Baseline rate tracking and change calculation
  - Historical data retrieval
  - Fallback to mock data when APIs unavailable

### Audit Service (`services/audit_service.py`)
- **Status**: ✅ Implemented
- **Responsibility**: Full pipeline traceability via SQLite in-memory database
- **Features**:
  - Trace IDs linking all pipeline stages: NewsEvent → EventVector → VolShock → VolSurface → GreeksSnapshot
  - Thread-safe connections using shared cache for in-memory SQLite
  - Full trace retrieval with all linked data
  - Recent traces listing with status filtering
  - Active traces monitoring
- **API Endpoints**:
  - `GET /api/audit/trace/{trace_id}` - Retrieve full pipeline trace
  - `GET /api/audit/traces` - List recent traces
  - `POST /api/audit/trace/{trace_id}/end` - Mark trace as completed

### Risk Attribution Service (`services/risk_attribution_service.py`)
- **Status**: ✅ Implemented
- **Responsibility**: Break down Greek changes into explicit attribution percentages
- **Features**:
  - News Headlines attribution (NLP → Vol Shock)
  - Historical Vol Drift attribution (natural market movement)
  - NN Model Adjustment attribution (neural network corrections)
  - Vega spike detection ($10K+ threshold) with special report
  - Primary driver identification
  - Confidence scoring for attributions
- **Attribution Model**:
  - Event-type based weights (INTEREST_RATE: 55% news, 25% drift, 20% NN)
  - Central bank specific sources (Fed, ECB, BoJ, etc.)
  - Human-readable attribution summary
- **API Endpoints**:
  - `GET /api/risk-attribution-report` - Generate full attribution report

### Correlation Service (`services/correlation_service.py`)
- **Status**: ✅ Implemented (Module 10)
- **Responsibility**: Cross-asset correlation risk management for FX portfolios
- **Features**:
  - FX correlation matrix management (EURUSD vs GBPUSD, etc.)
  - Correlation-adjusted Greeks computation
  - Diversification ratio calculation
  - Correlation stress testing with crisis scenarios
  - Diversification opportunity identification
- **Correlation Model**:
  - Default FX correlations (EURUSD-GBPUSD: 0.85, EURUSD-USDJPY: -0.65)
  - Predefined crisis scenarios (2008 Lehman, COVID 2020, EM Stress, Risk-On/Risk-Off)
  - Correlation multipliers for stress testing
- **API Endpoints**:
  - `GET /api/correlation-matrix` - View current FX correlation matrix
  - `GET /api/correlation-risk-report` - Full correlation risk analysis
  - `GET /api/correlation-stress-scenarios` - Available stress scenarios
  - `POST /api/correlation-stress-test` - Run specific scenario

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
  - News ingestion and news impact analysis

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
| Forex APIs | Alpha Vantage, Frankfurter | Live spot rates | ✅ Implemented |
| Alert System | Custom | Risk/spot alerts | ✅ Implemented |
| Logging | structlog | Structured JSON logging | ✅ |
| Testing | pytest | Unit tests | ✅ |
| Monitoring | Prometheus | Metrics | ✅ Available |

## News-Based Wireframes

### Wireframe 1: News Impact Dashboard Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    NEWS IMPACT ANALYSIS FLOW                                         │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                         │
│   ┌───────────────────────────────────────┐     ┌───────────────────────────────────────┐            │
│   │          NEWS INGESTION               │     │           NLP PROCESSING                │            │
│   │  ┌─────────────────────────────────┐  │     │  ┌─────────────────────────────────┐  │            │
│   │  │  "Fed signals potential rate   │  │     │  │  Event Type: INTEREST_RATE     │  │            │
│   │  │   cuts amid cooling inflation"  │  │     │  │  Sentiment: NEGATIVE           │  │            │
│   │  │                 │               │  │     │  │  Score: -0.73                  │  │            │
│   │  │                 ▼               │  │     │  │  Importance: 0.82              │  │            │
│   │  │  ┌──────────────────────────┐  │  │     │  │  Entities: [Fed, USD, Rates]  │  │            │
│   │  │  │   Source: Reuters        │  │  │     │  └─────────────────────────────────┘  │            │
│   │  │  │   URL: reuters.com/...   │  │  │     │                 │                    │            │
│   │  │  │   Published: 2026-04-30 │  │  │     │                 ▼                    │            │
│   │  │  └──────────────────────────┘  │  │     │  ┌─────────────────────────────────┐  │            │
│   │  └─────────────────────────────────┘  │     │  │       VOL SHOCK MODEL           │  │            │
│   └───────────────────────────────────────┘     │  │  ┌─────────────────────────────────┐  │            │
│                                                    │  │  │  1W ATM: -0.0023               │  │            │
│                                                    │  │  │  1M ATM: -0.0031               │  │            │
│   ┌───────────────────────────────────────┐     │  │  │  3M ATM: -0.0028               │  │            │
│   │         VOL SURFACE UPDATE             │     │  │  │  6M ATM: -0.0021               │  │            │
│   │  ┌─────────────────────────────────┐  │     │  │  │  1Y ATM: -0.0015               │  │            │
│   │  │  Vol_base ──▶ Vol_shocked      │  │     │  │  └─────────────────────────────────┘  │            │
│   │  │                                 │  │     │  └─────────────────────────────────┘  │            │
│   │  │  1W: 10.0%  ──▶  9.77%         │  │     └───────────────────────────────────────┘            │
│   │  │  1M: 10.0%  ──▶  9.69%         │  │                    │                                   │
│   │  │  3M: 10.0%  ──▶  9.72%         │  │                    ▼                                   │
│   │  │  6M: 10.0%  ──▶  9.79%         │  │     ┌───────────────────────────────────────┐            │
│   │  │  1Y: 10.0%  ──▶  9.85%         │  │     │         GREEKS COMPUTATION             │            │
│   │  └─────────────────────────────────┘  │     │  ┌─────────────────────────────────┐  │            │
│   └───────────────────────────────────────┘     │  │  Baseline    │  Shocked     │  Δ    │  │            │
│                                                    │  ├──────────────┼───────────────┼──────┤  │            │
│   ┌───────────────────────────────────────┐     │  │  Delta: 50K  │  Delta: 48K   │ -2K   │  │            │
│   │            IMPACT SUMMARY              │     │  │  Gamma: 12K  │  Gamma: 11.5K │ -0.5K │  │            │
│   │  ┌─────────────────────────────────┐  │     │  │  Vega: 100K   │  Vega: 97K    │ -3K   │  │            │
│   │  │  Headline: Fed signals rate...  │  │     │  │  Theta: -5K  │  Theta: -4.8K │ +0.2K │  │            │
│   │  │  Source: Reuters                │  │     │  │  Rho: 25K    │  Rho: 23K     │ -2K   │  │            │
│   │  │  Event Type: INTEREST_RATE      │  │     │  └─────────────────────────────────┘  │            │
│   │  │  Sentiment: NEGATIVE (-0.73)    │  │     └───────────────────────────────────────┘            │
│   │  │  ─────────────────────────────   │  │                                                          │
│   │  │  Greeks Impact:                  │  │                                                          │
│   │  │    Δ Delta: -$2,000             │  │                                                          │
│   │  │    Δ Vega: -$3,000              │  │                                                          │
│   │  │    Δ Gamma: -$500               │  │                                                          │
│   │  └─────────────────────────────────┘  │                                                          │
│   └───────────────────────────────────────┘                                                          │
│                                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Wireframe 2: Web UI Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  GREEK NN RISK DASHBOARD                                    [Risk Summary] [News Impact] [Alerts]  │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                         │
│ ┌─────────────────────────────┐ ┌─────────────────────────────┐ ┌─────────────────────────────────┐│
│ │   TOTAL GREEKS              │ │   SPOT RATES                 │ │   VOL SURFACE                    ││
│ │   ───────────────           │ │   ───────────               │ │   ──────────────                 ││
│ │   Delta:    $45,230         │ │   EURUSD:  1.0850           │ │   1W  ████████░░  9.8%         ││
│ │   Gamma:    $12,450         │ │   USDJPY:  149.50           │ │   1M  ███████░░░ 10.1%         ││
│ │   Vega:     $98,520         │ │   GBPUSD:  1.2650           │ │   3M  ██████░░░░ 10.3%         ││
│ │   Theta:    -$5,230         │ │   USDCHF:  0.8850           │ │   6M  █████░░░░░ 10.5%         ││
│ │   Rho:      $25,340         │ │                             │ │   1Y  ████░░░░░░ 10.8%         ││
│ └─────────────────────────────┘ └─────────────────────────────┘ └─────────────────────────────────┘│
│                                                                                                         │
│ ┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐│
│ │  TIME LADDER (VEGA)                                    [Delta] [Gamma] [Vega] [Theta] [Rho]       ││
│ │  ─────────────────────────────────────────────────────────────────────────────────────────────────││
│ │      1W        1M        3M        6M        1Y                                                        ││
│ │  ████████  ████████████████  ████████████████  ██████████████  ████████                              ││
│ │   $15,230    $45,230       $28,450        $12,340       $8,230                                      ││
│ └─────────────────────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                                         │
│ ┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐│
│ │  RECENT NEWS                                               [Filter: All ▼] [Show Impact ☑]        ││
│ │  ─────────────────────────────────────────────────────────────────────────────────────────────────││
│ │  ● Fed signals potential rate cuts amid cooling inflation data                        Reuters 2m ago ││
│ │    Event: INTEREST_RATE | Sentiment: NEGATIVE (-0.73) | Impact: ΔVega -$3,000                       ││
│ │  ─────────────────────────────────────────────────────────────────────────────────────────────────││
│ │  ● ECB maintains cautious stance on monetary policy normalization                    Bloomberg 5m ago ││
│ │    Event: CENTRAL_BANK | Sentiment: NEUTRAL (0.1) | Impact: ΔVega -$500                              ││
│ │  ─────────────────────────────────────────────────────────────────────────────────────────────────││
│ │  ● NFP report shows stronger than expected employment growth                            CNBC 15m ago   ││
│ │    Event: EMPLOYMENT | Sentiment: POSITIVE (0.65) | Impact: ΔVega +$1,200                           ││
│ └─────────────────────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                                         │
│ ┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐│
│ │  PORTFOLIO POSITIONS                                              [+ Add Trade] [Export CSV]       ││
│ │  ─────────────────────────────────────────────────────────────────────────────────────────────────││
│ │  ID       Instrument  Type  Strike   Tenor   Quantity    Delta     Gamma     Vega                 ││
│ │  TRADE-001 EURUSD     CALL  1.0900   1M     1,000,000    $12,340   $2,100    $8,500              ││
│ │  TRADE-002 EURUSD     PUT   1.0800   3M      -500,000   -$8,200   -$1,400   -$5,200              ││
│ │  TRADE-003 USDJPY     CALL  150.00   1W      2,000,000    $25,000   $3,200    $12,000             ││
│ │  TRADE-004 GBPUSD     PUT   1.2600   6M       750,000    -$5,600   -$1,100   -$4,800              ││
│ └─────────────────────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Wireframe 3: News Impact Analysis Sequence

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           NEWS IMPACT ANALYSIS SEQUENCE                                             │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                         │
│  Trader/UI              API                  NLP Engine          Vol Shock      Vol Surface   Risk Eng │
│     │                   │                       │                    │               │            │     │
│     │──GET /news-impact─▶                       │                    │               │            │     │
│     │                   │                       │                    │               │            │     │
│     │                   │──Fetch headlines──────▶                    │               │            │     │
│     │                   │                       │                    │               │            │     │
│     │                   │                       │──FinBERT analyze───▶│               │            │     │
│     │                   │                       │                    │               │            │     │
│     │                   │                       │◀──EventVector───────│               │            │     │
│     │                   │                       │                    │               │            │     │
│     │                   │                       │────Predict shock────▶│               │            │     │
│     │                   │                       │                    │               │            │     │
│     │                   │                       │◀──VolShock─────────│               │            │     │
│     │                   │                       │                    │               │            │     │
│     │                   │                       │                    │──Apply shock─▶│               │     │
│     │                   │                       │                    │               │            │     │
│     │                   │                       │                    │◀─Shocked──────│               │     │
│     │                   │                       │                    │   surface     │            │     │
│     │                   │                       │                    │               │            │     │
│     │                   │                       │                    │               │──Compute───▶│     │
│     │                   │                       │                    │               │   Greeks   │     │
│     │                   │                       │                    │               │            │     │
│     │                   │◀──Impact Report──────────────────────────────────────────────────────────│     │
│     │◀──Dashboard Update│                       │                    │               │            │     │
│     │                   │                       │                    │               │            │     │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Use Cases

### UC-1: Real-time News Risk Assessment

**Actor:** Risk Manager, Trader

**Preconditions:**
- News ingestion service is running
- NLP engine is initialized (or fallback mode active)
- Vol shock model is available

**Flow:**
1. System continuously ingests news from NewsAPI, RSS feeds
2. News is processed through NLP engine to extract EventVector
3. EventVector is fed to Vol Shock Model to predict surface impact
4. Shocked vol surface is applied
5. Greeks are recomputed and compared to baseline
6. Significant impacts (|ΔGreeks| > threshold) trigger display update

**Postconditions:**
- Dashboard shows updated Greeks with news impact
- Time ladder reflects current risk state

**Example:**
```
Headline: "Fed signals potential rate cuts amid cooling inflation"
→ EventType: INTEREST_RATE
→ Sentiment: NEGATIVE (-0.73)
→ Importance: 0.82
→ Vol Shock: 1M ATM -0.0031
→ Greeks Impact: ΔVega = -$3,000
```

### UC-2: Portfolio Stress Testing via News

**Actor:** Risk Manager

**Preconditions:**
- Portfolio loaded in system
- Historical news or scenario headlines available

**Flow:**
1. Risk manager selects historical news event(s)
2. System replays event through NLP → Vol Shock → Greeks pipeline
3. Shocked portfolio Greeks are computed
4. Risk metrics (VaR equivalent) are calculated

**Example:**
```
Historical Event: "2008 Lehman Brothers Collapse"
→ EventType: MACRO
→ Sentiment: NEGATIVE (-0.95)
→ Vol Shock: 1M ATM +0.15 (extreme stress)
→ Shocked Portfolio: Delta=$250K (vs baseline $45K)
→ Risk Alert: "Delta exceeds limit by $200K"
```

### UC-3: News-Driven Vol Surface Versioning

**Actor:** System (automated)

**Preconditions:**
- News event processed
- Vol shock predicted

**Flow:**
1. New news event triggers vol shock
2. New vol surface version created with shock applied
3. Surface version linked to triggering event via EventVector.event_id
4. Greeks recomputed with new surface
5. All computations logged with surface version for audit

**API Usage:**
```
GET /api/vol-surface
Response:
{
  "snapshot_id": "vol-2026-04-30-001",
  "base_date": "2026-04-30T00:00:00Z",
  "version": "shocked-by-event-abc123",
  "tenors": ["1W", "1M", "3M", "6M", "1Y"],
  "vols_atm": [0.0977, 0.0969, 0.0972, 0.0979, 0.0985]
}
```

### UC-4: Time-Ladder Analysis with News Filter

**Actor:** Trader, Risk Manager

**Preconditions:**
- Portfolio has positions across multiple tenors

**Flow:**
1. User requests time ladder for specific Greek type (e.g., vega)
2. User optionally filters by news event type (e.g., INTEREST_RATE only)
3. System computes Greeks bucketed by tenor
4. Only positions affected by filtered news are highlighted

**API Usage:**
```
GET /api/portfolios/FX-PORTFOLIO-01/time-ladder?greek_type=vega

Response:
{
  "portfolio_id": "FX-PORTFOLIO-01",
  "greek_type": "vega",
  "ladder": [
    {"tenor": "1W", "greeks": {"vega": 15230, ...}},
    {"tenor": "1M", "greeks": {"vega": 45230, ...}},
    {"tenor": "3M", "greeks": {"vega": 28450, ...}},
    {"tenor": "6M", "greeks": {"vega": 12340, ...}},
    {"tenor": "1Y", "greeks": {"vega": 8230, ...}}
  ],
  "total": {"vega": 109480, ...}
}
```

### UC-5: WebSocket Real-time Greeks Ticking

**Actor:** Trader (frontend client)

**Preconditions:**
- WebSocket connection established to /ws/greeks

**Flow:**
1. Client connects to WebSocket endpoint
2. Server sends current Greeks state every 1 second
3. Client UI updates Greeks display in real-time
4. Client receives broadcast events (trade_added, trade_removed)

**WebSocket Messages:**
```json
// Periodic tick
{"type": "tick", "timestamp": "2026-04-30T22:47:00Z", "total_greeks": {"delta": 45230, ...}}

// Trade added notification
{"type": "trade_added", "trade_id": "TRADE-006", "instrument": "EURUSD"}

// Trade removed notification
{"type": "trade_removed", "trade_id": "TRADE-003"}
```

### UC-6: Trade Entry with Auto-Risk Assessment

**Actor:** Dealer, Trader

**Preconditions:**
- Portfolio exists
- Vol surface is current

**Flow:**
1. Dealer enters new trade parameters (instrument, strike, tenor, quantity, type)
2. System immediately computes Greeks impact of new trade
3. If Greeks exceed limits, warning displayed before confirmation
4. On confirmation, trade added to portfolio
5. All connected WebSocket clients receive trade_added notification

**API Usage:**
```
POST /api/trades
{
  "instrument": "EURUSD",
  "strike": 1.0900,
  "tenor": 0.0833,
  "quantity": 500000,
  "option_type": "CALL",
  "portfolio_id": "FX-PORTFOLIO-01"
}

Response:
{
  "status": "success",
  "trade_id": "TRADE-006",
  "position": {...}
}
```

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
   - News API unavailable → mock headlines for demo

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
├── services/                 # Service modules
│   ├── alert_service.py      # Module 6: Alert system
│   ├── audit_service.py     # Module 8: Audit service
│   ├── forex_service.py      # Module 7: Forex spot rate service
│   └── risk_attribution_service.py  # Module 9: Risk attribution
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
├── plans/                   # Implementation plans
│   └── live_spot_rate_integration_plan.md
└── tests/
    ├── __init__.py
    ├── conftest.py          # Pytest fixtures
    ├── test_nn_risk_engine.py
    ├── test_vol_surface.py
    ├── test_news_ingestion.py
    ├── test_nlp_engine.py   # Module 2 tests
    ├── test_vol_shock_model.py  # Module 3 tests
    ├── test_alert_service.py    # Module 6 tests
    ├── test_forex_service.py    # Module 7 tests
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
| GET | `/api/news` | Get recent news headlines |
| GET | `/api/news-impact` | Get news with calculated impact on Greeks |
| GET | `/api/risk-attribution-report` | Generate risk attribution report with explicit percentages |
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

**API Endpoint:** `GET /api/news-impact`
- Returns recent news with their calculated impact on Greeks
- Shows baseline Greeks vs shocked Greeks
- Displays vol shocks per tenor (1W, 1M, 3M, 6M, 1Y ATM)
- Shows event type, sentiment, and importance

**UI Feature:** "Show Impact" button in News panel toggles between news list and news-with-impact view

### Audit & Traceability

The system provides full audit trail for the news-to-Greeks pipeline through the **Audit Service**:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         AUDIT SERVICE (SQLite In-Memory)                           │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                            PIPELINE TRACE FLOW                                │   │
│  │                                                                              │   │
│  │  NewsEvent ──▶ EventVector ──▶ VolShock ──▶ VolSurface ──▶ GreeksSnapshot   │   │
│  │      │              │             │            │              │              │   │
│  │      ▼              ▼             ▼            ▼              ▼              │   │
│  │  ┌─────────┐   ┌───────────┐   ┌────────┐   ┌──────────┐   ┌───────────┐      │   │
│  │  │  news_  │   │  event_   │   │  vol_  │   │  vol_    │   │  greeks_  │      │   │
│  │  │ events  │   │  vectors  │   │ shocks │   │ surfaces │   │ snapshots │      │   │
│  │  └─────────┘   └───────────┘   └────────┘   └──────────┘   └───────────┘      │   │
│  │                                                                              │   │
│  │                         All linked by trace_id                                │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                            DATABASE SCHEMA                                     │   │
│  │                                                                              │   │
│  │  traces(id, trace_id, created_at, status, completed_at, metadata)            │   │
│  │       │                                                                       │   │
│  │       ├──▶ news_events(trace_id, headline, source, url, published_at, ...)  │   │
│  │       ├──▶ event_vectors(trace_id, event_id, event_type, sentiment, ...)   │   │
│  │       ├──▶ vol_shocks(trace_id, shock_id, event_id, delta_1W_ATM, ...)     │   │
│  │       ├──▶ vol_surfaces(trace_id, snapshot_id, shock_id, tenors, ...)       │   │
│  │       └──▶ greeks_snapshots(trace_id, snapshot_id, portfolio_id, delta, ...)│   │
│  │                                                                              │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Trace ID Format:** `news-batch-{YYYYMMDD-HHMMSS}` (e.g., `news-batch-20260504-070551`)

**API Endpoints for Audit:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/audit/trace/{trace_id}` | Get full pipeline trace with all stages |
| GET | `/api/audit/traces` | List recent traces (supports `?status=active`) |
| POST | `/api/audit/trace/{trace_id}/end` | Mark trace as completed |
| GET | `/api/risk-attribution-report` | Generate risk attribution report with explicit percentages |

**Example Trace Retrieval:**

```bash
curl "http://localhost:8000/api/audit/trace/news-batch-20260504-070551"
```

Returns:
```json
{
  "trace": {
    "trace_id": "news-batch-20260504-070551",
    "created_at": "2026-05-04T07:05:51",
    "status": "active",
    "completed_at": null
  },
  "news_events": [...],
  "event_vectors": [...],
  "vol_shocks": [...],
  "vol_surfaces": [...],
  "greeks_snapshots": [...]
}
```

**Distributed Tracing Integration:**

Every API request automatically receives a `X-Trace-ID` response header for correlation:
- Request can include `X-Trace-ID` header to continue an existing trace
- Middleware generates new trace ID if not provided
- All log messages include trace context

## Vega Impact Calculation: News Sentiment to Greeks

The system calculates vega impact from positive/negative news through a multi-stage pipeline. This section explains the complete flow with detailed examples.

### Stage 1: Sentiment Analysis

**File:** [`nlp_engine.py:216-238`](nlp_engine.py:216)

News headlines are processed through FinBERT to extract sentiment:

| Sentiment | Score Range | Example Headline |
|-----------|-------------|------------------|
| POSITIVE | +0.5 to +1.0 | "Fed signals rate cuts amid cooling inflation" → +0.73 |
| NEGATIVE | -1.0 to -0.5 | "Recession fears mount as GDP contracts" → -0.82 |
| NEUTRAL | -0.5 to +0.5 | "ECB holds rates steady as expected" → +0.05 |

The sentiment score directly influences the volatility shock magnitude.

### Stage 2: Volatility Shock Prediction

**File:** [`vol_shock_model.py:407-467`](vol_shock_model.py:407)

The rule-based model computes volatility shocks using:

```python
base_impact = sentiment_score * importance * 0.3
surprise_boost = 1.0 + surprise_factor * 0.5
delta_ATM = base_impact * tenor_multiplier * surprise_boost
```

**Key insight:** `sentiment_score` directly multiplies the shock magnitude.

- **Negative sentiment** → Negative vol shocks (vol surface decreases)
- **Positive sentiment** → Positive vol shocks (vol surface increases)

**Tenor Multipliers** (for INTEREST_RATE events):

| Tenor | Multiplier | Rationale |
|-------|------------|-----------|
| 1W | 1.5 | Short-term vol most sensitive to rate decisions |
| 1M | 1.8 | Immediate market reaction |
| 3M | 1.5 | Medium-term adjustment |
| 6M | 1.2 | Longer-term normalization |
| 1Y | 1.0 | Baseline reference |

### Stage 3: Vol Surface Application

**File:** [`vol_surface_service.py:263-266`](vol_surface_service.py:263)

```python
shocked_vol[tenor_idx][:] = shocked_vol[tenor_idx][:] * (1.0 + shock_amount)
```

| News Sentiment | Shock Direction | Vol Surface Effect |
|----------------|------------------|-------------------|
| Negative | Negative | Vol decreases (markets expect calmer conditions) |
| Positive | Positive | Vol increases (markets expect higher activity) |

### Stage 4: Vega Calculation

**File:** [`nn_risk_engine.py:95-101`](nn_risk_engine.py:95)

Vega is computed via Black-Scholes:

```python
def vega(S, K, T, r, sigma):
    d1 = (log(S/K) + (r + 0.5*sigma²)*T) / (sigma*sqrt(T))
    return S * norm.pdf(d1) * sqrt(T) / 100  # Per 1% vol change
```

**Why lower vol = lower vega:** Vega is proportional to `norm.pdf(d1) * sqrt(T)`. When volatility decreases due to negative news, the vega exposure of each option reduces.

### Complete Example: Negative News Impact on Vega

**Input:**
```
Headline: "Fed signals potential rate cuts amid cooling inflation"
Event Type: INTEREST_RATE
Sentiment: NEGATIVE (-0.73)
Importance: 0.82
Surprise Factor: 0.6
```

**Calculation:**

| Step | Formula | Value |
|------|---------|-------|
| Base Impact | sentiment × importance × 0.3 | -0.73 × 0.82 × 0.3 = **-0.180** |
| Surprise Boost | 1 + surprise × 0.5 | 1 + 0.6 × 0.5 = **1.30** |
| 1M ATM Delta | base × 1.8 × boost | -0.180 × 1.8 × 1.30 = **-0.421** |
| Baseline Vol | 10.0% | 10.0% |
| Shocked Vol | 10.0% × (1 + (-0.421)) | **9.58%** |

**Resulting Vega Change:**

| Greek | Baseline | Shocked | Δ Change |
|-------|----------|---------|----------|
| Delta | $50,000 | $48,000 | -$2,000 |
| Gamma | $12,000 | $11,500 | -$500 |
| **Vega** | **$100,000** | **$97,000** | **-$3,000** |

### Complete Example: Positive News Impact on Vega

**Input:**
```
Headline: "NFP report shows stronger than expected employment growth"
Event Type: EMPLOYMENT
Sentiment: POSITIVE (+0.68)
Importance: 0.75
Surprise Factor: 0.4
```

**Calculation:**

| Step | Formula | Value |
|------|---------|-------|
| Base Impact | sentiment × importance × 0.3 | 0.68 × 0.75 × 0.3 = **+0.153** |
| Surprise Boost | 1 + surprise × 0.5 | 1 + 0.4 × 0.5 = **1.20** |
| 1M ATM Delta | base × 1.2 × boost | 0.153 × 1.2 × 1.20 = **+0.220** |
| Baseline Vol | 10.0% | 10.0% |
| Shocked Vol | 10.0% × (1 + 0.220) | **12.20%** |

**Resulting Vega Change:**

| Greek | Baseline | Shocked | Δ Change |
|-------|----------|---------|----------|
| Delta | $50,000 | $51,500 | +$1,500 |
| Gamma | $12,000 | $12,300 | +$300 |
| **Vega** | **$100,000** | **$103,500** | **+$3,500** |

### Intuition Summary

| Scenario | News Sentiment | Vol Impact | Vega Impact |
|----------|----------------|------------|-------------|
| Rate cut signals | Negative | Decreases | **Lowers** vega exposure |
| Strong employment | Positive | Increases | **Raises** vega exposure |
| Central bank hawkishness | Negative | Increases | **Raises** vega exposure |
| Peaceful geopolitical news | Positive | Decreases | **Lowers** vega exposure |

**Core Principle:** Negative news (e.g., recession fears) typically causes markets to expect calmer conditions → lower implied volatility → lower vega. Positive news (e.g., strong economic data) suggests higher market activity → higher implied vol → higher vega.

## Risk Attribution Reports

The system provides **Risk Attribution Reports** that explicitly break down what drives Greek changes with attribution percentages.

### File: [`services/risk_attribution_service.py`](services/risk_attribution_service.py)

### Attribution Model

The attribution model breaks down Greek changes into three factors:

| Factor | Description | Example |
|--------|-------------|---------|
| **News Headlines** | Attribution to specific news events (NLP → Vol Shock) | "50% of this move is attributed to the ECB interest rate headline" |
| **Historical Vol Drift** | Natural market volatility changes not from news | "30% to historical vol drift" |
| **NN Model Adjustment** | Neural network's learned adjustments beyond rule-based | "20% to NN model adjustment" |

### Event-Type Based Attribution Weights

Different event types have different attribution weightings:

| Event Type | News Weight | Vol Drift Weight | NN Adjustment Weight |
|------------|-------------|------------------|---------------------|
| INTEREST_RATE | 55% | 25% | 20% |
| INFLATION | 50% | 30% | 20% |
| EMPLOYMENT | 45% | 35% | 20% |
| CENTRAL_BANK | 50% | 30% | 20% |
| MACRO | 40% | 40% | 20% |
| UNKNOWN | 30% | 50% | 20% |

### Vega Spike Detection

When a Vega spike of $10K+ (5% change) is detected, a special `VegaSpikeAttribution` report is generated:

```json
{
  "vega_spike_report": {
    "vega_spike_amount": 10000,
    "vega_spike_percentage": 10.5,
    "headline": "ECB announces unexpected rate cut amid cooling inflation",
    "event_type": "INTEREST_RATE",
    "attribution_factors": [
      {
        "factor_type": "news_headline",
        "source": "ECB interest rate headline",
        "percentage": 50.0,
        "description": "Vol spike driven by NEGATIVE sentiment news"
      },
      {
        "factor_type": "historical_vol_drift",
        "source": "historical vol drift",
        "percentage": 30.0,
        "description": "Market volatility adjustment not from news"
      },
      {
        "factor_type": "nn_model_adjustment",
        "source": "onnx model adjustment",
        "percentage": 20.0,
        "description": "NN model learned correction beyond rule-based"
      }
    ],
    "total_attributed_percentage": 100.0,
    "attribution_summary": "50% of this move is attributed to ECB interest rate headline, 30% to historical vol drift, and 20% to NN model adjustment"
  }
}
```

### API Endpoint

**GET `/api/risk-attribution-report`**

Returns a full `RiskAttributionReport` with:
- Baseline and current Greeks
- Attribution breakdown for each Greek (delta, gamma, vega, theta, rho)
- Vega spike report when applicable
- Primary driver identification
- Confidence score

### Usage Example

```bash
curl "http://localhost:8000/api/risk-attribution-report?portfolio_id=FX-PORTFOLIO-01&min_vega_spike=10000"
```

### Report Schema

**File:** [`schemas.py`](schemas.py)

```python
class RiskAttributionReport(BaseModel):
    """Complete Risk Attribution Report for portfolio Greeks."""
    report_id: str
    portfolio_id: str
    timestamp: datetime
    baseline_greeks: Greeks
    current_greeks: Greeks
    greeks_delta: Greeks
    
    # Attributions by Greek type
    delta_attribution: List[RiskAttributionFactor]
    gamma_attribution: List[RiskAttributionFactor]
    vega_attribution: List[RiskAttributionFactor]
    theta_attribution: List[RiskAttributionFactor]
    rho_attribution: List[RiskAttributionFactor]
    
    # Special Vega spike report
    vega_spike_report: Optional[VegaSpikeAttribution]
    
    primary_driver: str
    confidence_score: float

class VegaSpikeAttribution(BaseModel):
    """Attribution breakdown for a Vega spike event."""
    vega_spike_amount: float
    vega_spike_percentage: float
    attribution_factors: List[RiskAttributionFactor]
    total_attributed_percentage: float
    headline: str
    event_type: str
    timestamp: datetime
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024-01 | Initial architecture |
| 1.1.0 | 2026-04 | Updated to reflect actual implementation state including FastAPI server |
| 2.0.0 | 2026-04 | Added WebSocket support, portfolio management, time ladder analysis |
| 2.1.0 | 2026-04 | Implemented Module 2 (NLP Engine with FinBERT) and Module 3 (Vol Shock Model) |
| 2.2.0 | 2026-04 | Added news-based wireframes, use cases, and UI layouts |
| 2.3.0 | 2026-05 | Added mobile-friendly UI, sort by category/sentiment, Greeks display at booking, spot movement alerts |
| 2.4.0 | 2026-05 | Added Vega Impact Calculation section with detailed examples |
| 2.5.0 | 2026-05 | Added Risk Attribution Report feature with explicit attribution percentages |
| 2.6.0 | 2026-05 | Updated to reflect Risk Attribution Service (Module 9) |
| 2.7.0 | 2026-05 | Added Module 10: Correlation Service for cross-asset correlation risk |
| 2.8.0 | 2026-05 | Added Enterprise Module: retry, circuit breaker, rate limiter, exceptions |
