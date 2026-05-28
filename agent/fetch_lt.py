"""
Fetch long-term fundamental signals for a given NSE/BSE symbol via yfinance.
Uses a 2-year price history window for SMA computation. RSI/MACD/Bollinger excluded.

yfinance unit conventions (applied here so callers see consistent units):
  debtToEquity   → percentage (36.65 = 0.37x) — divided by 100 before storing
  returnOnEquity → decimal (0.15 = 15%)       — multiplied by 100 before storing
  earningsGrowth → decimal (0.18 = 18%)       — multiplied by 100 before storing
  revenueGrowth  → decimal (0.08 = 8%)        — multiplied by 100 before storing
  dividendYield  → decimal (0.01 = 1%)        — multiplied by 100 before storing
"""
import logging
from datetime import datetime

import yfinance as yf

logger = logging.getLogger(__name__)


def _safe(val):
    """Return float or None; filters out NaN and inf."""
    try:
        f = float(val)
        if f != f or abs(f) == float("inf"):
            return None
        return f
    except (TypeError, ValueError):
        return None


def fetch_signals_lt(symbol: str) -> dict:
    bundle = {
        "symbol": symbol,
        "timestamp": datetime.utcnow().isoformat(),
        "price": None,
        "sma_50": None,
        "sma_200": None,
        "pe_ratio": None,
        "market_cap": None,
        "sector": None,
        "eps_growth": None,
        "revenue_growth": None,
        "debt_to_equity": None,
        "roe": None,
        "dividend_yield": None,
        "errors": [],
    }

    try:
        ticker = yf.Ticker(symbol)
    except Exception as e:
        bundle["errors"].append(f"ticker_init:{e}")
        return bundle

    # ── 1. Fundamentals from ticker.info ─────────────────────────────────────
    try:
        info = ticker.info or {}

        bundle["price"]      = _safe(info.get("currentPrice") or info.get("regularMarketPrice"))
        bundle["pe_ratio"]   = _safe(info.get("trailingPE"))
        bundle["market_cap"] = _safe(info.get("marketCap"))
        bundle["sector"]     = info.get("sector")

        roe = _safe(info.get("returnOnEquity"))
        if roe is not None:
            bundle["roe"] = roe * 100  # decimal → percentage

        dte = _safe(info.get("debtToEquity"))
        if dte is not None:
            bundle["debt_to_equity"] = dte / 100  # percentage → ratio

        eg = _safe(info.get("earningsGrowth"))
        if eg is not None:
            bundle["eps_growth"] = eg * 100  # decimal → percentage

        rg = _safe(info.get("revenueGrowth"))
        if rg is not None:
            bundle["revenue_growth"] = rg * 100  # decimal → percentage

        dy = _safe(info.get("trailingAnnualDividendYield"))
        if dy is not None:
            bundle["dividend_yield"] = dy * 100  # decimal → percentage

    except Exception as e:
        bundle["errors"].append(f"info:{e}")

    # ── 2. 2-year price history + SMAs ───────────────────────────────────────
    try:
        hist = ticker.history(period="2y")
        if hist.empty:
            bundle["errors"].append("history:empty_dataframe")
        else:
            close = hist["Close"]
            if bundle["price"] is None and not close.empty:
                bundle["price"] = _safe(close.iloc[-1])
            if len(close) >= 50:
                bundle["sma_50"] = _safe(close.rolling(50).mean().iloc[-1])
            if len(close) >= 200:
                bundle["sma_200"] = _safe(close.rolling(200).mean().iloc[-1])
    except Exception as e:
        bundle["errors"].append(f"history:{e}")

    return bundle
