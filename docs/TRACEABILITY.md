# Traceability Matrix

## Requirement to Test Traceability

This document maps system requirements to implementation components and test cases.

### Module 1: News Ingestion

| Requirement ID | Requirement Description | Component | Test File | Test Cases |
|----------------|------------------------|-----------|-----------|------------|
| NI-001 | Real-time headline aggregation | `NewsIngestionService` | `test_news_ingestion.py` | `test_service_initialization`, `test_health_check` |
| NI-002 | Multi-source support (NewsAPI, RSS, Bloomberg) | `NewsAPISource`, `RSSFeedSource`, `BloombergSource` | `test_news_ingestion.py` | `test_newsapi_source`, `test_rss_source`, `test_bloomberg_mock_mode` |
| NI-003 | <500ms latency target | Async implementation | `test_news_ingestion.py` | N/A (performance test) |
| NI-004 | Deduplication by headline | `NewsIngestionService.recent_headlines` | `test_news_ingestion.py` | `test_deduplication_by_headline` |
| NI-005 | Keyword-based filtering | `get_recent_by_keyword()` | `test_news_ingestion.py` | `test_get_recent_by_keyword_*` |

### Module 2: NLP Processing

| Requirement ID | Requirement Description | Component | Test File | Test Cases |
|----------------|------------------------|-----------|-----------|------------|
| NLP-001 | Event extraction from headlines | `EventVector` schema | `test_schemas.py` | `test_event_vector_*` |
| NLP-002 | Sentiment classification (positive/neutral/negative) | `Sentiment` enum | `test_schemas.py` | `test_all_sentiments_defined` |
| NLP-003 | Event type classification | `EventType` enum | `test_schemas.py` | `test_all_event_types_defined` |
| NLP-004 | Importance scoring (0-1) | `EventVector.importance` | `test_schemas.py` | `test_importance_range` |
| NLP-005 | Surprise factor (0-1) | `EventVector.surprise_factor` | `test_schemas.py` | `test_surprise_factor_range` |

### Module 3: Vol Shock Model

| Requirement ID | Requirement Description | Component | Test File | Test Cases |
|----------------|------------------------|-----------|-----------|------------|
| VS-001 | Predict vol deltas for 1W, 1M, 3M, 6M, 1Y | `VolShock` schema | `test_schemas.py` | `test_valid_vol_shock` |
| VS-002 | 25Delta Risk Reversal prediction | `VolShock.delta_1M_25RR` | `test_schemas.py` | `test_valid_vol_shock` |
| VS-003 | 25Delta Butterfly prediction | `VolShock.delta_1M_25BF` | `test_schemas.py` | `test_valid_vol_shock` |
| VS-004 | Support negative shocks (vol decrease) | `VolShock` deltas | `test_schemas.py` | `test_vol_shock_negative_deltas` |

### Module 4: Vol Surface Service

| Requirement ID | Requirement Description | Component | Test File | Test Cases |
|----------------|------------------------|-----------|-----------|------------|
| VSS-001 | Multi-tier caching (Memory → Redis → Disk) | `VolSurfaceService._memory_cache` | `test_vol_surface.py` | `test_memory_cache_storage`, `test_cache_key_generation` |
| VSS-002 | Cache TTL management | `_cache_ttl` | `test_vol_surface.py` | `test_memory_cache_ttl` |
| VSS-003 | Shock application to baseline surface | `get_shocked_surface()` | `test_vol_surface.py` | `test_get_shocked_surface`, `test_shocked_surface_volumes_increased` |
| VSS-004 | Surface versioning for audit | `VolSurface.version` | `test_vol_surface.py` | `test_surface_version` |
| VSS-005 | Bilinear interpolation | `QuantLibVolSurfaceBackend.interpolate_at_strike()` | `test_vol_surface.py` | `test_interpolate_at_strike`, `test_interpolate_bounds_check` |

### Module 5: NN Risk Engine

| Requirement ID | Requirement Description | Component | Test File | Test Cases |
|----------------|------------------------|-----------|-----------|------------|
| RE-001 | Portfolio Greeks computation | `compute_portfolio_greeks()` | `test_nn_risk_engine.py` | `test_compute_greeks_with_blackscholes`, `test_greeks_addition` |
| RE-002 | Delta calculation | `BlackScholesGreeksCPU.delta()` | `test_nn_risk_engine.py` | `test_delta_call_option`, `test_delta_put_option`, `test_delta_itm_call`, `test_delta_otm_call` |
| RE-003 | Gamma calculation | `BlackScholesGreeksCPU.gamma()` | `test_nn_risk_engine.py` | `test_gamma_positive`, `test_gamma_decreases_with_time` |
| RE-004 | Vega calculation | `BlackScholesGreeksCPU.vega()` | `test_nn_risk_engine.py` | `test_vega_positive`, `test_vega_decreases_with_time` |
| RE-005 | Theta calculation | `BlackScholesGreeksCPU.theta()` | `test_nn_risk_engine.py` | `test_theta_call_negative` |
| RE-006 | Rho calculation | `BlackScholesGreeksCPU.rho()` | `test_nn_risk_engine.py` | `test_rho_call_positive`, `test_rho_put_negative` |
| RE-007 | ONNX inference mode | `_compute_greeks_onnx()` | `test_nn_risk_engine.py` | N/A (requires ONNX model) |
| RE-008 | PyTorch inference mode | `_compute_greeks_pytorch()` | `test_nn_risk_engine.py` | N/A (requires PyTorch model) |
| RE-009 | Black-Scholes fallback | `_compute_greeks_blackscholes()` | `test_nn_risk_engine.py` | All Black-Scholes tests |
| RE-010 | Bucketed vega analysis | `compute_bucketed_vega()` | `test_nn_risk_engine.py` | `test_bucketed_vega` |
| RE-011 | Zero vol handling | `BlackScholesGreeksCPU` | `test_nn_risk_engine.py` | `test_zero_volatility_handling` |
| RE-012 | Zero time handling | `BlackScholesGreeksCPU` | `test_nn_risk_engine.py` | `test_zero_time_handling` |

### Module 6: Alert System

| Requirement ID | Requirement Description | Component | Test File | Test Cases |
|----------------|------------------------|-----------|-----------|------------|
| AL-001 | Risk limit monitoring | `RiskAlert` schema | `test_schemas.py` | `test_valid_risk_alert` |
| AL-002 | Alert with exceeded value | `RiskAlert.exceeded_by` | `test_schemas.py` | `test_valid_risk_alert` |
| AL-003 | Action recommendations | `RiskAlert.action_recommended` | `test_schemas.py` | `test_valid_risk_alert` |

### API Server (api.py)

| Requirement ID | Requirement Description | Endpoint | Test Coverage |
|----------------|------------------------|---------|--------------|
| API-001 | Health check endpoint | `GET /api/health` | Manual testing |
| API-002 | List portfolios | `GET /api/portfolios` | Manual testing |
| API-003 | Get portfolio details | `GET /api/portfolios/{id}` | Manual testing |
| API-004 | Compute portfolio Greeks | `POST /api/portfolios/{id}/greeks` | Manual testing |
| API-005 | Time ladder analysis | `GET /api/portfolios/{id}/time-ladder` | Manual testing |
| API-006 | Get spot rates | `GET /api/spot-rates` | Manual testing |
| API-007 | Get vol surface | `GET /api/vol-surface` | Manual testing |
| API-008 | Risk summary dashboard | `GET /api/risk-summary` | Manual testing |
| API-009 | Create trade | `POST /api/trades` | Manual testing |
| API-010 | Delete trade | `DELETE /api/trades/{id}` | Manual testing |
| API-011 | WebSocket real-time updates | `WS /ws/greeks` | Manual testing |
| API-012 | Serve web UI | `GET /` | Manual testing |
| API-013 | News impact analysis | `GET /api/news-impact` | Manual testing |

### Data Schemas

| Schema | Validation | Test File | Test Cases |
|--------|-----------|-----------|------------|
| `NewsEvent` | Required fields, URL format | `test_schemas.py` | `test_valid_news_event`, `test_news_event_optional_content` |
| `EventVector` | Score ranges (0-1, -1 to 1) | `test_schemas.py` | `test_sentiment_score_range`, `test_importance_range` |
| `VolSurface` | Shape validation | `test_schemas.py` | `test_vol_surface_shape_validation` |
| `Portfolio` | Default currency, position list | `test_schemas.py` | `test_valid_portfolio`, `test_portfolio_default_currency` |
| `PortfolioPosition` | Positive values for spot, strike, tenor | `test_schemas.py` | `test_position_spot_must_be_positive` |
| `Greeks` | Addition operator, to_dict() | `test_schemas.py` | `test_greeks_addition`, `test_greeks_to_dict` |

### Configuration

| Config Item | Default | Test Coverage |
|-------------|---------|---------------|
| `VEGA_LIMIT` | 100,000 | Via `risk_limits` fixture |
| `GAMMA_LIMIT` | 50,000 | Via `risk_limits` fixture |
| `DELTA_LIMIT` | 500,000 | Via `risk_limits` fixture |
| `RHO_LIMIT` | 100,000 | Via `risk_limits` fixture |
| `SHOCK_THRESHOLD` | 0.01 | Via `risk_limits` fixture |

---

## Test Coverage Summary

| Module | Files | Test Count | Coverage |
|--------|-------|------------|----------|
| NN Risk Engine | `test_nn_risk_engine.py` | 25+ | Black-Scholes formulas, engine initialization, edge cases |
| Vol Surface | `test_vol_surface.py` | 15 | Caching, shock application, interpolation |
| News Ingestion | `test_news_ingestion.py` | 14 | Source aggregation, keyword search, health checks |
| Schemas | `test_schemas.py` | 22 | Validation, enums, edge cases |
| **Total** | | **76+** | |

---

## Integration Points

```
NewsEvent → EventVector → VolShock → VolSurface (shocked) → PortfolioGreeks
    ↑           ↑            ↑              ↑                    ↓
    └───────────┴────────────┴──────────────┴────────────────────┘
                           NLP Module

API Server (FastAPI):
    GET /api/portfolios → NNRiskEngine.compute_portfolio_greeks → PortfolioGreeks
    GET /api/portfolios/{id}/time-ladder → NNRiskEngine.compute_portfolio_greeks (bucketed) → TimeLadder
    WS /ws/greeks → NNRiskEngine.compute_portfolio_greeks → Real-time tick
```

---

## Version Control

| Date | Version | Changes |
|------|---------|---------|
| 2024-01 | 1.0.0 | Initial traceability matrix |
| 2026-04 | 2.0.0 | Added API server traceability, updated test counts |