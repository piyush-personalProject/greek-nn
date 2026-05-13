# Plan: Fix Vol Surface to Use RR and Butterfly Vols

## Issue Identified

The `_get_vol_for_position()` method in [`nn_risk_engine.py:469`](nn_risk_engine.py:469) always uses `vol_surface.volatilities[tenor_idx][0]` which is **ATM vol only**. This ignores the position's strike, meaning:

- **RR (Risk Reversal)** and **BF (Butterfly)** volatilities are computed by the shock model
- But they are **never actually used** when computing portfolio Greeks
- All positions, regardless of strike, use ATM vol

## ✅ FIXED: Implementation Complete

The issue has been fixed with the following changes:

### Files Modified

1. **`vol_surface_service.py`**
   - Added `get_vol_at_strike()` method to `VolSurfaceService` for strike-aware volatility lookup

2. **`nn_risk_engine.py`**
   - Modified `_get_vol_for_position()` to use strike-based vol lookup based on moneyness
   - ATM (|moneyness - 1| ≤ 0.01): uses index 0
   - OTM Call (moneyness > 1): uses index 1 (+25RR)
   - OTM Put (moneyness < 1): uses index 2 (-25RR)

3. **`tests/test_nn_risk_engine.py`**
   - Added `test_get_vol_for_position_otm_call`
   - Added `test_get_vol_for_position_otm_put`
   - Added `test_get_vol_for_position_atm_uses_atm_vol`
   - Added `test_get_vol_for_position_with_spot_parameter`

4. **`tests/test_vol_surface.py`**
   - Added `test_get_vol_at_strike_atm`
   - Added `test_get_vol_at_strike_otm_call`
   - Added `test_get_vol_at_strike_otm_put`

### How the Fix Works

The [`_get_vol_for_position()`](nn_risk_engine.py:469) method now:
1. Takes an optional `spot` parameter
2. Calculates moneyness = strike / spot
3. Selects the appropriate vol index:
   - moneyness ≈ 1.0 (ATM) → index 0 (ATM vol)
   - moneyness > 1.0 (OTM Call) → index 1 (+25RR vol)
   - moneyness < 1.0 (OTM Put) → index 2 (-25RR vol)

### Tests

All new tests pass:
- `test_get_vol_for_position_otm_call` ✅
- `test_get_vol_for_position_otm_put` ✅
- `test_get_vol_for_position_atm_uses_atm_vol` ✅
- `test_get_vol_for_position_with_spot_parameter` ✅
- `test_get_vol_at_strike_atm` ✅
- `test_get_vol_at_strike_otm_call` ✅
- `test_get_vol_at_strike_otm_put` ✅