# FX Greeks Risk API Reference

## Base URL

```
http://localhost:8000
```

## API Overview

The FX Greeks Risk API provides real-time Greeks visualization for FX spot and options portfolios. It includes portfolio management, Greeks computation, time ladder analysis, news impact analysis, correlation risk management, and real-time WebSocket updates.

## Endpoints

---

### `GET /`

Serves the main web UI dashboard.

**Response:** HTML page

---

### `GET /api/health`

Health check endpoint for monitoring.

**Response:**
```json
{
    "status": "healthy",
    "timestamp": "2026-04-27T12:00:00.000000",
    "services": {
        "risk_engine": {"nn_risk_engine": "healthy", "model_mode": "blackscholes"},
        "vol_surface": {"status": "healthy"},
        "forex_service": {"status": "healthy"},
        "alert_service": {"status": "healthy"},
        "correlation_service": {"status": "healthy"}
    }
}
```

---

### `GET /api/portfolios`

List all portfolios.

**Response:**
```json
{
    "portfolios": [
        {
            "portfolio_id": "FX-PORTFOLIO-01",
            "timestamp": "2026-04-27T12:00:00.000000",
            "position_count": 5,
            "base_currency": "USD"
        }
    ]
}
```

---

### `GET /api/portfolios/{portfolio_id}`

Get portfolio details including all positions.

**Parameters:**
- `portfolio_id` (path): Portfolio identifier

**Response:**
```json
{
    "portfolio_id": "FX-PORTFOLIO-01",
    "timestamp": "2026-04-27T12:00:00.000000",
    "base_currency": "USD",
    "positions": [
        {
            "position_id": "TRADE-001",
            "instrument": "EURUSD",
            "spot": 1.085,
            "strike": 1.09,
            "tenor": 0.0833,
            "quantity": 1000000,
            "option_type": "CALL",
            "portfolio_id": "FX-PORTFOLIO-01",
            "timestamp": "2026-04-27T12:00:00.000000"
        }
    ]
}
```

---

### `GET /api/portfolios/{portfolio_id}/greeks`

Get Greeks for a portfolio (read-only view).

**Parameters:**
- `portfolio_id` (path): Portfolio identifier

**Response:**
```json
{
    "portfolio_id": "FX-PORTFOLIO-01",
    "timestamp": "2026-04-27T12:00:00.000000",
    "total_greeks": {
        "delta": 450000.0,
        "gamma": 12000.0,
        "vega": 85000.0,
        "theta": -1500.0,
        "rho": 32000.0,
        "vanna": null,
        "volga": null
    },
    "position_greeks": {
        "TRADE-001": {
            "delta": 450000.0,
            "gamma": 12000.0,
            "vega": 85000.0,
            "theta": -1500.0,
            "rho": 32000.0,
            "vanna": null,
            "volga": null
        }
    }
}
```

---

### `POST /api/portfolios/{portfolio_id}/greeks`

Compute Greeks for a portfolio (spot horizon view).

**Parameters:**
- `portfolio_id` (path): Portfolio identifier
- `vol_surface_version` (query, optional): Vol surface version

**Response:**
```json
{
    "portfolio_id": "FX-PORTFOLIO-01",
    "timestamp": "2026-04-27T12:00:00.000000",
    "vol_surface_version": "mock_v1",
    "total_greeks": {
        "delta": 450000.0,
        "gamma": 12000.0,
        "vega": 85000.0,
        "theta": -1500.0,
        "rho": 32000.0,
        "vanna": null,
        "volga": null
    },
    "position_greeks": {
        "TRADE-001": {
            "delta": 450000.0,
            "gamma": 12000.0,
            "vega": 85000.0,
            "theta": -1500.0,
            "rho": 32000.0,
            "vanna": null,
            "volga": null
        }
    }
}
```

---

### `POST /api/portfolios/{portfolio_id}/greeks/impacted`

Compute Greeks impacted by specific news exclusion.

**Parameters:**
- `portfolio_id` (path): Portfolio identifier
- `excluded_news_ids` (body, optional): List of news event IDs to exclude

**Response:** Same structure as `/greeks` endpoint

---

### `GET /api/portfolios/{portfolio_id}/time-ladder`

Get time ladder view (Greeks bucketed by tenor: 1W, 1M, 3M, 6M, 1Y).

**Parameters:**
- `portfolio_id` (path): Portfolio identifier
- `greek_type` (query, optional): Greek type (delta, gamma, vega, theta, rho). Default: "vega"

**Response:**
```json
{
    "portfolio_id": "FX-PORTFOLIO-01",
    "greek_type": "vega",
    "timestamp": "2026-04-27T12:00:00.000000",
    "ladder": [
        {"tenor": "1W", "greeks": {"delta": 0, "gamma": 0, "vega": 15000, "theta": 0, "rho": 0, "vanna": 0, "volga": 0}},
        {"tenor": "1M", "greeks": {"delta": 0, "gamma": 0, "vega": 35000, "theta": 0, "rho": 0, "vanna": 0, "volga": 0}},
        {"tenor": "3M", "greeks": {"delta": 0, "gamma": 0, "vega": 20000, "theta": 0, "rho": 0, "vanna": 0, "volga": 0}},
        {"tenor": "6M", "greeks": {"delta": 0, "gamma": 0, "vega": 10000, "theta": 0, "rho": 0, "vanna": 0, "volga": 0}},
        {"tenor": "1Y", "greeks": {"delta": 0, "gamma": 0, "vega": 5000, "theta": 0, "rho": 0, "vanna": 0, "volga": 0}}
    ],
    "total": {"delta": 0, "gamma": 0, "vega": 85000, "theta": 0, "rho": 0, "vanna": 0, "volga": 0}
}
```

---

### `GET /api/spot-rates`

Get current spot rates.

**Response:**
```json
{
    "timestamp": "2026-04-27T12:00:00.000000",
    "rates": {
        "EURUSD": 1.085,
        "USDJPY": 149.5,
        "GBPUSD": 1.265,
        "USDCHF": 0.885,
        "AUDUSD": 0.655,
        "USDCAD": 1.345,
        "NZDUSD": 0.605
    }
}
```

---

### `GET /api/spot-rates/live`

Get live spot rates fetched from external APIs.

**Response:**
```json
{
    "timestamp": "2026-04-27T12:00:00.000000",
    "source": "frankfurter",
    "rates": {
        "EURUSD": 1.085,
        "USDJPY": 149.5,
        "GBPUSD": 1.265
    }
}
```

---

### `GET /api/spot-rates/history`

Get historical spot rate data.

**Parameters:**
- `pair` (query, optional): Currency pair (e.g., "EURUSD")
- `days` (query, optional): Number of days of history (default: 30)

**Response:**
```json
{
    "pair": "EURUSD",
    "days": 30,
    "history": [
        {"timestamp": "2026-04-27T12:00:00.000000", "rate": 1.085},
        {"timestamp": "2026-04-26T12:00:00.000000", "rate": 1.084}
    ]
}
```

---

### `GET /api/spot-rates/changes`

Get spot rate changes from baseline.

**Response:**
```json
{
    "timestamp": "2026-04-27T12:00:00.000000",
    "changes": {
        "EURUSD": {"change": 0.001, "change_pct": 0.09},
        "USDJPY": {"change": -0.2, "change_pct": -0.13}
    }
}
```

---

### `POST /api/spot-rates/baseline`

Update baseline rates to current rates.

**Response:**
```json
{
    "status": "success",
    "message": "Baseline rates updated"
}
```

---

### `GET /api/vol-surface`

Get current vol surface summary.

**Response:**
```json
{
    "snapshot_id": "surface_20260427",
    "base_date": "2026-04-27T12:00:00.000000",
    "version": "mock_v1",
    "tenors": ["0.0192", "0.0833", "0.2500", "0.5000", "1.0000"],
    "tenor_labels": ["1W", "1M", "3M", "6M", "1Y"],
    "strikes": [100, 102.5, 97.5, 105, 95],
    "vols_atm": [0.08, 0.10, 0.12, 0.11, 0.10]
}
```

---

### `GET /api/risk-summary`

Get comprehensive risk summary for dashboard.

**Parameters:**
- `portfolio_id` (query, optional): Portfolio ID. Default: "FX-PORTFOLIO-01"

**Response:**
```json
{
    "timestamp": "2026-04-27T12:00:00.000000",
    "portfolio_id": "FX-PORTFOLIO-01",
    "spot_rates": {"EURUSD": 1.085, "USDJPY": 149.5, ...},
    "total_greeks": {"delta": 450000, "gamma": 12000, "vega": 85000, "theta": -1500, "rho": 32000, "vanna": 0, "volga": 0},
    "time_ladder": [...],
    "position_count": 5,
    "limits": {
        "vega_limit": 100000,
        "gamma_limit": 50000,
        "delta_limit": 500000
    }
}
```

---

### `GET /api/news`

Get recent news headlines.

**Parameters:**
- `keyword` (query, optional): Filter by keyword
- `max_results` (query, optional): Maximum number of results (default: 20)

**Response:**
```json
{
    "timestamp": "2026-04-27T12:00:00.000000",
    "news": [
        {
            "headline": "Fed signals potential rate cuts",
            "source": "Reuters",
            "url": "https://reuters.com/...",
            "published_at": "2026-04-27T10:30:00.000000",
            "event_type": "INTEREST_RATE",
            "sentiment": "NEGATIVE",
            "sentiment_score": -0.73
        }
    ]
}
```

---

### `POST /api/news/refresh`

Force refresh of news headlines.

**Response:**
```json
{
    "status": "success",
    "count": 15,
    "timestamp": "2026-04-27T12:00:00.000000"
}
```

---

### `GET /api/news-with-impact`

Get news with calculated impact on Greeks.

**Parameters:**
- `max_results` (query, optional): Maximum number of results (default: 10)
- `portfolio_id` (query, optional): Portfolio ID (default: "FX-PORTFOLIO-01")

**Response:**
```json
{
    "timestamp": "2026-04-27T12:00:00.000000",
    "news_with_impact": [
        {
            "news_event": {...},
            "event_vector": {...},
            "greeks_impact": {"delta": -2000, "gamma": -500, "vega": -3000},
            "vol_shocks": {"1W_ATM": -0.002, "1M_ATM": -0.003}
        }
    ]
}
```

---

### `GET /api/news-impact`

Get news with calculated impact on Greeks (alternative endpoint).

**Parameters:**
- `max_results` (query, optional): Maximum number of results (default: 10)

**Response:** Same structure as `/news-with-impact`

---

### `POST /api/news/exclude`

Compute Greeks with excluded news events.

**Parameters:**
- `excluded_news_ids` (body): List of news event IDs to exclude

**Response:** Greeks computation with partial news impact

---

### `GET /api/risk-attribution-report`

Generate risk attribution report with explicit percentage breakdown.

**Parameters:**
- `portfolio_id` (query, optional): Portfolio ID
- `min_vega_spike` (query, optional): Minimum vega spike threshold

**Response:**
```json
{
    "report": {
        "report_id": "attr-20260513-001",
        "portfolio_id": "FX-PORTFOLIO-01",
        "timestamp": "2026-05-13T12:00:00.000000",
        "baseline_greeks": {...},
        "current_greeks": {...},
        "greeks_delta": {...},
        "delta_attribution": [...],
        "gamma_attribution": [...],
        "vega_attribution": [...],
        "theta_attribution": [...],
        "rho_attribution": [...],
        "primary_driver": "News Headlines",
        "confidence_score": 0.85
    }
}
```

---

### `POST /api/impact/combined`

Get combined spot and vol shock impact on Greeks.

**Parameters:**
- `portfolio_id` (body): Portfolio identifier
- `spot_shock_pct` (body, optional): Spot rate shock percentage
- `vol_shock_ids` (body, optional): List of vol shock IDs

**Response:**
```json
{
    "combined_impact": {
        "spot_impact": {...},
        "vol_impact": {...},
        "total_impact": {...}
    }
}
```

---

### `GET /api/alerts/spot-rates`

Get spot rate alerts.

**Parameters:**
- `since_minutes` (query, optional): Filter alerts within time window

**Response:**
```json
{
    "alerts": [
        {
            "alert_id": "spot-EURUSD-001",
            "alert_type": "SpotRateAlert",
            "pair": "EURUSD",
            "change_pct": 0.5,
            "severity": "medium",
            "message": "EURUSD moved 0.5%",
            "timestamp": "2026-04-27T12:00:00.000000"
        }
    ]
}
```

---

### `GET /api/alerts/all`

Get all active alerts.

**Response:**
```json
{
    "spot_alerts": [...],
    "risk_alerts": [...],
    "total_count": 5
}
```

---

### `POST /api/alerts/{alert_id}/acknowledge`

Acknowledge an alert.

**Parameters:**
- `alert_id` (path): Alert identifier

**Response:**
```json
{
    "status": "success",
    "alert_id": "spot-EURUSD-001"
}
```

---

### `GET /api/correlation-matrix`

Get current FX correlation matrix.

**Response:**
```json
{
    "matrix_id": "fx-default",
    "pairs": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"],
    "correlations": {
        "EURUSD-GBPUSD": 0.85,
        "EURUSD-USDJPY": -0.65,
        "EURUSD-USDCHF": 0.70
    },
    "last_updated": "2026-04-27T12:00:00.000000"
}
```

---

### `GET /api/correlation-risk-report`

Get full correlation risk analysis report.

**Parameters:**
- `portfolio_id` (query, optional): Portfolio ID

**Response:**
```json
{
    "report": {
        "portfolio_id": "FX-PORTFOLIO-01",
        "timestamp": "2026-04-27T12:00:00.000000",
        "correlation_matrix": {...},
        "diversification_ratio": 1.25,
        "correlation_risk_score": 0.45,
        "positions_correlation_info": [...],
        "risk_contribution_by_pair": {...},
        "warnings": []
    }
}
```

---

### `GET /api/correlation-adjusted`

Get correlation-adjusted Greeks for the portfolio.

**Parameters:**
- `portfolio_id` (query, optional): Portfolio ID

**Response:**
```json
{
    "portfolio_id": "FX-PORTFOLIO-01",
    "correlation_adjusted_greeks": {
        "delta": 420000,
        "gamma": 11500,
        "vega": 78000,
        "theta": -1450,
        "rho": 30000
    },
    "adjustment_explanation": "Correlations reduced delta by 6.7%"
}
```

---

### `POST /api/correlation-adjusted-with-event`

Get correlation-adjusted Greeks with a specific event applied.

**Parameters:**
- `portfolio_id` (body): Portfolio ID
- `event_vector` (body): Event vector to simulate

**Response:** Same as `/correlation-adjusted` with event applied

---

### `GET /api/correlation-change-report`

Get report of correlation changes caused by news events.

**Response:**
```json
{
    "changes": [
        {
            "pair": "EURUSD-GBPUSD",
            "old_correlation": 0.85,
            "new_correlation": 0.82,
            "change": -0.03,
            "triggered_by": "ECB policy divergence headline",
            "timestamp": "2026-04-27T12:00:00.000000"
        }
    ]
}
```

---

### `GET /api/correlation-stress-scenarios`

Get available correlation stress test scenarios.

**Response:**
```json
{
    "scenarios": [
        {"id": "lehman_2008", "name": "2008 Lehman Crisis", "description": "Extreme correlation during 2008 financial crisis"},
        {"id": "covid_2020", "name": "COVID 2020", "description": "Pandemic-driven correlation shifts"},
        {"id": "em_stress", "name": "EM Stress", "description": "Emerging market correlation spike"},
        {"id": "risk_on_risk_off", "name": "Risk-On/Risk-Off", "description": "Flight to safety correlation pattern"}
    ]
}
```

---

### `POST /api/correlation-stress-test`

Run correlation stress test with a specific scenario.

**Parameters:**
- `scenario_id` (body): Scenario ID to apply
- `portfolio_id` (body, optional): Portfolio ID

**Response:**
```json
{
    "scenario": "lehman_2008",
    "portfolio_id": "FX-PORTFOLIO-01",
    "correlation_multiplier": 1.5,
    "stressed_correlations": {...},
    "impact_on_greeks": {
        "delta_change": -15000,
        "gamma_change": -800,
        "vega_change": -5000
    }
}
```

---

### `WebSocket /ws/greeks`

WebSocket endpoint for real-time Greeks updates. Sends periodic tick updates every second.

**Response (tick):**
```json
{
    "type": "tick",
    "timestamp": "2026-04-27T12:00:01.000000",
    "portfolio_id": "FX-PORTFOLIO-01",
    "total_greeks": {"delta": 450000, "gamma": 12000, "vega": 85000, "theta": -1500, "rho": 32000, "vanna": 0, "volga": 0},
    "spot_rates": {"EURUSD": 1.085, "USDJPY": 149.5, ...}
}
```

**Events broadcast:**
- `tick`: Periodic Greeks update (every 1 second)
- `trade_added`: When a new trade is added
- `trade_removed`: When a trade is deleted
- `spot_rate_alert`: When spot rate movement triggers alert

---

### `POST /api/trades`

Create a new trade (maker/dealer function).

**Request Body:**
- `instrument` (required): Trading instrument (e.g., EURUSD)
- `strike` (required): Strike price
- `tenor` (required): Time to expiration in years
- `quantity` (required): Position size
- `option_type` (required): CALL or PUT
- `portfolio_id` (optional): Portfolio ID. Default: "FX-PORTFOLIO-01"

**Response:**
```json
{
    "status": "success",
    "trade_id": "TRADE-006",
    "position": {
        "position_id": "TRADE-006",
        "instrument": "EURUSD",
        "spot": 1.085,
        "strike": 1.09,
        "tenor": 0.0833,
        "quantity": 500000,
        "option_type": "CALL",
        "portfolio_id": "FX-PORTFOLIO-01"
    }
}
```

---

### `DELETE /api/trades/{trade_id}`

Delete a trade from portfolio.

**Parameters:**
- `trade_id` (path): Trade/Position ID to delete
- `portfolio_id` (query, optional): Portfolio ID. Default: "FX-PORTFOLIO-01"

**Response:**
```json
{
    "status": "success",
    "trade_id": "TRADE-001"
}
```

---

### `GET /api/audit/trace/{trace_id}`

Get full pipeline trace with all stages.

**Parameters:**
- `trace_id` (path): Trace identifier

**Response:**
```json
{
    "trace": {
        "trace_id": "news-batch-20260504-070551",
        "created_at": "2026-05-04T07:05:51",
        "status": "completed",
        "completed_at": "2026-05-04T07:05:52"
    },
    "news_events": [...],
    "event_vectors": [...],
    "vol_shocks": [...],
    "vol_surfaces": [...],
    "greeks_snapshots": [...]
}
```

---

### `GET /api/audit/traces`

List recent audit traces.

**Parameters:**
- `limit` (query, optional): Maximum number of traces (default: 20)
- `status` (query, optional): Filter by status (active, completed)

**Response:**
```json
{
    "traces": [
        {
            "trace_id": "news-batch-20260504-070551",
            "created_at": "2026-05-04T07:05:51",
            "status": "completed"
        }
    ],
    "total_count": 15
}
```

---

### `POST /api/audit/trace/{trace_id}/end`

Mark trace as completed.

**Parameters:**
- `trace_id` (path): Trace identifier
- `status` (query, optional): Final status (default: "completed")

**Response:**
```json
{
    "status": "success",
    "trace_id": "news-batch-20260504-070551"
}
```

---

## Error Responses

### 400 Bad Request
```json
{
    "detail": "Validation error message"
}
```

### 404 Not Found
```json
{
    "detail": "Portfolio not found"
}
```

### 500 Internal Server Error
```json
{
    "detail": "Failed to compute Greeks: error message"
}
```

### 503 Service Unavailable
```json
{
    "detail": "Vol surface not available"
}
```

---

## CORS

The API has CORS enabled for all origins to support local development.

---

## Schemas

### PortfolioPosition Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| position_id | string | Yes | Unique position identifier (e.g., TRADE-001) |
| instrument | string | Yes | Trading instrument (e.g., EURUSD, USDJPY) |
| spot | float | Yes | Current spot rate |
| strike | float | Yes | Strike price |
| tenor | float | Yes | Time to expiration in years (e.g., 1/12 for 1M) |
| quantity | float | Yes | Position size |
| option_type | string | Yes | CALL or PUT |
| portfolio_id | string | Yes | Parent portfolio ID |

### Greeks Schema

| Field | Type | Description |
|-------|------|-------------|
| delta | float | Delta risk measure |
| gamma | float | Gamma risk measure |
| vega | float | Vega risk measure (per 1% vol change) |
| theta | float | Theta risk measure (per day) |
| rho | float | Rho risk measure (per 1% rate change) |
| vanna | float | Vanna measure (optional) |
| volga | float | Volga measure (optional) |

### Tenor Bucket Mapping

| Tenor Range | Bucket Name |
|-------------|-------------|
| <= 1 week (1/52 years) | 1W |
| <= 1 month (1/12 years) | 1M |
| <= 3 months (3/12 years) | 3M |
| <= 6 months (6/12 years) | 6M |
| > 6 months | 1Y |

---

## Rate Limits

Rate limits are not currently enforced. The API is designed for internal front-office use.

---

## Authentication

Currently open. Auth implementation planned for future release.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-04-27 | Initial API implementation with portfolio management, Greeks computation, time ladder, and WebSocket updates |
| 1.1.0 | 2026-05-13 | Added correlation risk endpoints (Module 10), live spot rates, enhanced alerts, news exclusion, and combined impact endpoints |