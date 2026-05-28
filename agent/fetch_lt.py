"""
Fetch long-term fundamental signals for a given NSE/BSE symbol via OpenBB.
Uses a 2-year price history window. RSI/MACD/Bollinger are excluded.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _col(df, *candidates):
    for col in candidates:
        if col in df.columns and not df[col].isna().all():
            return float(df[col].iloc[-1])
    return None


def fetch_signals_lt(symbol: str) -> dict:
    from openbb import obb

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

    # ── 1. Live quote ────────────────────────────────────────────────────────
    try:
        q = obb.equity.price.quote(symbol, provider="yfinance").to_dataframe()
        bundle["price"] = _col(q, "last_price", "price", "close")
    except Exception as e:
        bundle["errors"].append(f"quote:{e}")

    # ── 2. 2-year price history + SMAs ───────────────────────────────────────
    try:
        end   = datetime.utcnow().strftime("%Y-%m-%d")
        start = (datetime.utcnow() - timedelta(days=730)).strftime("%Y-%m-%d")
        hist  = obb.equity.price.historical(
            symbol, start_date=start, end_date=end, provider="yfinance"
        )
        hist_df = hist.to_dataframe()

        if bundle["price"] is None and not hist_df.empty:
            bundle["price"] = float(hist_df["close"].iloc[-1])

        if len(hist_df) >= 50:
            sma50_df = obb.technical.sma(
                data=hist_df, target="close", length=50
            ).to_dataframe()
            bundle["sma_50"] = _col(sma50_df, "close_SMA_50")

        if len(hist_df) >= 200:
            sma200_df = obb.technical.sma(
                data=hist_df, target="close", length=200
            ).to_dataframe()
            bundle["sma_200"] = _col(sma200_df, "close_SMA_200")

    except Exception as e:
        bundle["errors"].append(f"history:{e}")

    # ── 3. Profile (P/E, sector, market cap) ────────────────────────────────
    try:
        prof = obb.equity.profile(symbol, provider="yfinance").to_dataframe()
        if not prof.empty:
            bundle["sector"]     = prof.get("sector", [None])[0]
            bundle["market_cap"] = _col(prof, "market_cap", "marketCap")
            bundle["pe_ratio"]   = _col(prof, "pe_ratio", "trailingPE", "pe")
    except Exception as e:
        bundle["errors"].append(f"profile:{e}")

    # ── 4. Fundamental metrics (ROE, debt-to-equity) ────────────────────────
    try:
        metrics = obb.equity.fundamental.metrics(
            symbol, provider="yfinance"
        ).to_dataframe()
        if not metrics.empty:
            bundle["roe"]            = _col(metrics, "roe", "returnOnEquity")
            bundle["debt_to_equity"] = _col(metrics, "debt_to_equity", "debtToEquity")
    except Exception as e:
        bundle["errors"].append(f"metrics:{e}")

    # ── 5. Income statement (EPS + revenue growth) ──────────────────────────
    try:
        income = obb.equity.fundamental.income(
            symbol, provider="yfinance", limit=2
        ).to_dataframe()
        if len(income) >= 2:
            eps_now  = _col(income.iloc[[0]], "eps", "basicEPS", "dilutedEPS")
            eps_prev = _col(income.iloc[[1]], "eps", "basicEPS", "dilutedEPS")
            rev_now  = _col(income.iloc[[0]], "revenue", "totalRevenue")
            rev_prev = _col(income.iloc[[1]], "revenue", "totalRevenue")
            if eps_now and eps_prev and eps_prev != 0:
                bundle["eps_growth"] = ((eps_now - eps_prev) / abs(eps_prev)) * 100
            if rev_now and rev_prev and rev_prev != 0:
                bundle["revenue_growth"] = ((rev_now - rev_prev) / abs(rev_prev)) * 100
    except Exception as e:
        bundle["errors"].append(f"income:{e}")

    # ── 6. Dividend yield ────────────────────────────────────────────────────
    try:
        divs = obb.equity.fundamental.dividends(
            symbol, provider="yfinance"
        ).to_dataframe()
        if not divs.empty and bundle["price"]:
            div_col = next((c for c in ["amount", "dividend", "value"] if c in divs.columns), None)
            if div_col:
                annual_div = float(divs[div_col].dropna().head(4).sum())
                bundle["dividend_yield"] = (annual_div / bundle["price"]) * 100
    except Exception as e:
        bundle["errors"].append(f"dividends:{e}")

    return bundle
