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

### Module 7: Forex Service

| Requirement ID | Requirement Description | Component | Test File | Test Cases |
|----------------|------------------------|-----------|-----------|------------|
| FX-001 | Live spot rate fetching | `ForexService.fetch_rates()` | `test_forex_service.py` | `test_fetch_rates_*` |
| FX-002 | Multi-currency support | ForexService.supported_pairs | `test_forex_service.py` | `test_supported_pairs` |
| FX-003 | Baseline rate tracking | `update_baseline()` | `test_forex_service.py` | `test_update_baseline` |
| FX-004 | Rate change calculation | `get_rate_change()` | `test_forex_service.py` | `test_get_rate_change_*` |
| FX-005 | Mock mode fallback | `_get_mock_rate()` | `test_forex_service.py` | `test_fetch_rates_no_api_key` |

### Module 8: Audit Service (SQLite In-Memory)

| Requirement ID | Requirement Description | Component | Test File | Test Cases |
|----------------|------------------------|-----------|-----------|------------|
| AU-001 | SQLite in-memory persistence | `AuditService` | `test_audit_service.py` | `test_audit_service_init`, `test_trace_lifecycle` |
| AU-002 | News event persistence | `persist_news_event()` | `test_audit_service.py` | `test_persist_news_event` |
| AU-003 | Event vector persistence | `persist_event_vector()` | `test_audit_service.py` | `test_persist_event_vector` |
| AU-004 | Vol shock persistence | `persist_vol_shock()` | `test_audit_service.py` | `test_persist_vol_shock` |
| AU-005 | Vol surface persistence | `persist_vol_surface()` | `test_audit_service.py` | `test_persist_vol_surface` |
| AU-006 | Greeks snapshot persistence | `persist_greeks()` | `test_audit_service.py` | `test_persist_greeks` |
| AU-007 | Full trace retrieval | `get_trace()` | `test_audit_service.py` | `test_get_trace` |
| AU-008 | Thread-safe connections | `_get_connection()` | `test_audit_service.py` | `test_concurrent_access` |

### Module 10: Correlation Service

| Requirement ID | Requirement Description | Component | Test File | Test Cases |
|----------------|------------------------|-----------|-----------|------------|
| CORR-001 | FX correlation matrix management | `CorrelationService` | `test_correlation_service.py` | `test_initialization`, `test_default_matrix` |
| CORR-002 | Correlation-adjusted Greeks | `get_correlation_adjusted_greeks()` | `test_correlation_service.py` | `test_correlation_adjusted_greeks_*` |
| CORR-003 | Diversification ratio calculation | `calculate_diversification_ratio()` | `test_correlation_service.py` | `test_diversification_ratio_*` |
| CORR-004 | Correlation stress testing | `run_stress_test()` | `test_correlation_service.py` | `test_stress_scenarios_*` |
| CORR-005 | Predefined crisis scenarios | Crisis scenarios | `test_correlation_service.py` | `test_lehman_scenario`, `test_covid_scenario` |
| CORR-006 | Correlation update | `update_correlation()` | `test_correlation_service.py` | `test_update_correlation_*` |
| CORR-007 | Position correlation analysis | `analyze_position_correlations()` | `test_correlation_service.py` | `test_position_correlations_*` |
| CORR-008 | Correlation risk report | `get_correlation_risk_report()` | `test_correlation_service.py` | `test_risk_report_*` |

### API Server (api.py)

| Requirement ID | Requirement Description | Endpoint | Test Coverage |
|----------------|------------------------|---------|--------------|
| API-001 | Health check endpoint | `GET /api/health` | Manual testing |
| API-002 | List portfolios | `GET /api/portfolios` | Manual testing |
| API-003 | Get portfolio details | `GET /api/portfolios/{id}` | Manual testing |
| API-004 | Compute portfolio Greeks | `POST /api/portfolios/{id}/greeks` | Manual testing |
| API-005 | Time ladder analysis | `GET /api/portfolios/{id}/time-ladder` | Manual testing |
| API-006 | Get spot rates | `GET /api/spot-rates` | Manual testing |
| API-007 | Get live spot rates | `GET /api/spot-rates/live` | Manual testing |
| API-008 | Get vol surface | `GET /api/vol-surface` | Manual testing |
| API-009 | Risk summary dashboard | `GET /api/risk-summary` | Manual testing |
| API-010 | Create trade | `POST /api/trades` | Manual testing |
| API-011 | Delete trade | `DELETE /api/trades/{id}` | Manual testing |
| API-012 | WebSocket real-time updates | `WS /ws/greeks` | Manual testing |
| API-013 | News impact analysis | `GET /api/news-impact` | Manual testing |
| API-014 | Audit trace retrieval | `GET /api/audit/trace/{trace_id}` | Manual testing |
| API-015 | List recent traces | `GET /api/audit/traces` | Manual testing |
| API-016 | End trace | `POST /api/audit/trace/{trace_id}/end` | Manual testing |
| API-017 | Correlation matrix | `GET /api/correlation-matrix` | Manual testing |
| API-018 | Correlation risk report | `GET /api/correlation-risk-report` | Manual testing |
| API-019 | Correlation stress scenarios | `GET /api/correlation-stress-scenarios` | Manual testing |
| API-020 | Run correlation stress test | `POST /api/correlation-stress-test` | Manual testing |
| API-021 | Risk attribution report | `GET /api/risk-attribution-report` | Manual testing |
| API-022 | Spot rate alerts | `GET /api/alerts/spot-rates` | Manual testing |
| API-023 | News exclusion | `POST /api/news/exclude` | Manual testing |
| API-024 | Combined impact | `POST /api/impact/combined` | Manual testing |

### Data Schemas

| Schema | Validation | Test File | Test Cases |
|--------|-----------|-----------|------------|
| `NewsEvent` | Required fields, URL format | `test_schemas.py` | `test_valid_news_event`, `test_news_event_optional_content` |
| `EventVector` | Score ranges (0-1, -1 to 1) | `test_schemas.py` | `test_sentiment_score_range`, `test_importance_range` |
| `VolSurface` | Shape validation | `test_schemas.py` | `test_vol_surface_shape_validation` |
| `Portfolio` | Default currency, position list | `test_schemas.py` | `test_valid_portfolio`, `test_portfolio_default_currency` |
| `PortfolioPosition` | Positive values for spot, strike, tenor | `test_schemas.py` | `test_position_spot_must_be_positive` |
| `Greeks` | Addition operator, to_dict() | `test_schemas.py` | `test_greeks_addition`, `test_greeks_to_dict` |
| `CorrelationMatrix` | Matrix symmetry, bounds [-1,1] | `test_schemas.py` | `test_correlation_matrix_*` |
| `CorrelationAdjustedGreeks` | Greeks with correlation adjustments | `test_schemas.py` | `test_correlation_adjusted_greeks_*` |
| `RiskAttributionReport` | Attribution breakdown validation | `test_schemas.py` | `test_risk_attribution_report_*` |

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
| NLP Engine | `test_nlp_engine.py` | 10+ | Sentiment analysis, event extraction |
| Vol Shock Model | `test_vol_shock_model.py` | 15+ | Rule-based predictions, NN forward pass, batch processing |
| Alert Service | `test_alert_service.py` | 20+ | Risk alerts, spot alerts, rate limiting |
| Forex Service | `test_forex_service.py` | 15+ | Rate fetching, baseline tracking |
| Audit Service | `test_audit_service.py` | 10+ | Trace lifecycle, persistence |
| Correlation Service | `test_correlation_service.py` | 20+ | Correlation matrix, stress testing, adjusted Greeks |
| Enterprise Module | `test_enterprise.py` | 30+ | Retry, circuit breaker, rate limiter, exceptions |
| Schemas | `test_schemas.py` | 22 | Validation, enums, edge cases |
| **Total** | | **200+** | |

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
    GET /api/news-with-impact → News → NLP → VolShock → Greeks (with audit persistence)
    GET /api/audit/trace/{trace_id} → Full pipeline trace from SQLite
    GET /api/correlation-matrix → CorrelationService.get_correlation_matrix()
    GET /api/correlation-adjusted → CorrelationService.get_correlation_adjusted_greeks()
```

### Audit Persistence (SQLite In-Memory)

The audit service persists the full news-to-Greeks pipeline using SQLite in-memory database:

| Table | Purpose | Link Key |
|-------|---------|----------|
| `traces` | Trace metadata | `trace_id` |
| `news_events` | Raw news headlines | `trace_id` |
| `event_vectors` | NLP output | `trace_id`, `event_id` |
| `vol_shocks` | Vol predictions | `trace_id`, `event_id` |
| `vol_surfaces` | Shocked surfaces | `trace_id`, `shock_id` |
| `greeks_snapshots` | Final Greeks | `trace_id`, `vol_surface_snapshot_id` |

### Correlation Service Integration

The correlation service integrates with the risk engine to provide correlation-adjusted Greeks:

```
Portfolio Positions → CorrelationService.analyze_position_correlations()
                              ↓
              CorrelationService.get_correlation_adjusted_greeks()
                              ↓
                    CorrelationAdjustedGreeks
                              ↓
                    Dashboard Display
```

---

## Version Control

| Date | Version | Changes |
|------|---------|---------|
| 2024-01 | 1.0.0 | Initial traceability matrix |
| 2026-04 | 2.0.0 | Added API server traceability, updated test counts |
| 2026-05 | 3.0.0 | Added Module 10 (Correlation Service) traceability, updated total test count to 166+ |
| 2026-05 | 4.0.0 | Added Enterprise Module traceability (retry, circuit breaker, rate limiter), total test count 200+ |