import os
from datetime import date
from functools import lru_cache

try:
    from py_vollib.black_scholes import black_scholes
    from py_vollib.black_scholes.greeks.analytical import delta, gamma, vega, theta
    from py_vollib.black_scholes.implied_volatility import implied_volatility
    PY_VOLLIB_AVAILABLE = True
except ImportError:
    PY_VOLLIB_AVAILABLE = False


RISK_FREE_RATE = float(os.getenv("RISK_FREE_RATE", "0.05"))


def _time_to_expiry(expiration: date) -> float:
    days = (expiration - date.today()).days
    return max(days / 365.0, 1e-6)


def calculate_greeks(
    price: float,
    strike: float,
    expiration: date,
    put_call: str,
    underlying_price: float,
) -> dict:
    """Return IV and Greeks for one options contract. Returns zeros if py_vollib unavailable."""
    if not PY_VOLLIB_AVAILABLE or underlying_price <= 0 or price <= 0:
        return {"iv": 0.0, "delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}

    flag = "c" if put_call.upper() in ("CALL", "C") else "p"
    t = _time_to_expiry(expiration)
    r = RISK_FREE_RATE

    try:
        iv = implied_volatility(price, underlying_price, strike, t, r, flag)
        d = delta(flag, underlying_price, strike, t, r, iv)
        g = gamma(flag, underlying_price, strike, t, r, iv)
        v = vega(flag, underlying_price, strike, t, r, iv)
        th = theta(flag, underlying_price, strike, t, r, iv)
        return {"iv": iv, "delta": d, "gamma": g, "vega": v, "theta": th}
    except Exception:
        return {"iv": 0.0, "delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}
