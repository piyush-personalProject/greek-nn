# FX Greeks Risk API Reference

## Base URL

```
http://localhost:8000
```

## API Overview

The FX Greeks Risk API provides real-time Greeks visualization for FX spot and options portfolios. It includes portfolio management, Greeks computation, time ladder analysis, and real-time WebSocket updates.

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
        "vol_surface": {"status": "healthy"}
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
- `trade_added`: When a new trade is added
- `trade_removed`: When a trade is deleted

---

### `POST /api/trades`

Create a new trade (maker/dealer function).

**Request Body (query parameters):**
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

## Authentication

Currently open. Auth implementation planned for future release.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-04-27 | Initial API implementation with portfolio management, Greeks computation, time ladder, and WebSocket updates |