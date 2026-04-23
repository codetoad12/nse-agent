"""
Fetch and normalize all signal types for a given NSE/BSE symbol via OpenBB.
Returns a SignalBundle dict consumed by signals.py and analyze.py.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _col(df, *candidates):
    """Return the first matching column value from a DataFrame, or None."""
    for col in candidates:
        if col in df.columns and not df[col].isna().all():
            return float(df[col].iloc[-1])
    return None


def _prev_col(df, *candidates):
    """Return the second-to-last row value for MACD crossover detection."""
    for col in candidates:
        if col in df.columns and len(df) >= 2:
            return float(df[col].iloc[-2])
    return None


def fetch_signals(symbol: str) -> dict:
    """
    Pull all four signal types and return a normalised SignalBundle.
    Errors are captured per-signal rather than crashing the whole fetch.
    """
    from openbb import obb

    bundle = {
        "symbol": symbol,
        "timestamp": datetime.utcnow().isoformat(),
        "price": None,
        "change_pct": None,
        # technicals
        "rsi": None,
        "macd_signal": None,       # bullish_crossover | bearish_crossover | bullish | bearish
        "bollinger_position": None, # overbought | oversold | neutral
        # fundamentals
        "pe_ratio": None,
        "sector": None,
        "market_cap": None,
        # news
        "news_headlines": [],
        "errors": [],
    }

    # ── 1. Live quote ────────────────────────────────────────────────────────
    try:
        q = obb.equity.price.quote(symbol, provider="yfinance").to_dataframe()
        bundle["price"] = _col(q, "last_price", "price", "close")
        bundle["change_pct"] = _col(q, "percent_change", "change_percent", "change_pct")
    except Exception as e:
        bundle["errors"].append(f"quote:{e}")

    # ── 2. Historical prices (60-day window for indicators) ──────────────────
    try:
        end = datetime.utcnow().strftime("%Y-%m-%d")
        start = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
        hist = obb.equity.price.historical(
            symbol, start_date=start, end_date=end, provider="yfinance"
        )
        hist_df = hist.to_dataframe()

        if bundle["price"] is None and not hist_df.empty:
            bundle["price"] = float(hist_df["close"].iloc[-1])

        if len(hist_df) >= 20:
            _compute_technicals(obb, hist, hist_df, bundle)

    except Exception as e:
        bundle["errors"].append(f"history:{e}")

    # ── 3. Fundamentals (profile) ────────────────────────────────────────────
    try:
        prof = obb.equity.profile(symbol, provider="yfinance").to_dataframe()
        if not prof.empty:
            bundle["sector"] = prof.get("sector", [None])[0]
            bundle["market_cap"] = _col(prof, "market_cap", "marketCap")
            bundle["pe_ratio"] = _col(prof, "pe_ratio", "trailingPE", "pe")
    except Exception as e:
        bundle["errors"].append(f"profile:{e}")

    # ── 4. News headlines (yfinance gives 5-10 recent items for .NS) ─────────
    try:
        news = obb.news.company(symbol, limit=5, provider="yfinance").to_dataframe()
        if not news.empty:
            title_col = next((c for c in ["title", "headline", "text"] if c in news.columns), None)
            if title_col:
                bundle["news_headlines"] = news[title_col].dropna().tolist()[:5]
    except Exception as e:
        bundle["errors"].append(f"news:{e}")

    return bundle


def _compute_technicals(obb, hist_obj, hist_df, bundle: dict):
    """Compute RSI, MACD, and Bollinger Band position from historical data."""

    # RSI ─────────────────────────────────────────────────────────────────────
    try:
        rsi_df = obb.technical.rsi(
            data=hist_obj.results, target="close", length=14
        ).to_dataframe()
        bundle["rsi"] = _col(rsi_df, "rsi", "RSI_14", "RSI")
    except Exception as e:
        bundle["errors"].append(f"rsi:{e}")

    # MACD ────────────────────────────────────────────────────────────────────
    try:
        macd_df = obb.technical.macd(
            data=hist_obj.results, target="close", fast=12, slow=26, signal=9
        ).to_dataframe()

        macd_now  = _col(macd_df,  "macd", "MACD")
        sig_now   = _col(macd_df,  "macd_signal", "MACDs_9", "signal")
        macd_prev = _prev_col(macd_df, "macd", "MACD")
        sig_prev  = _prev_col(macd_df, "macd_signal", "MACDs_9", "signal")

        if None not in (macd_now, sig_now, macd_prev, sig_prev):
            if macd_prev < sig_prev and macd_now > sig_now:
                bundle["macd_signal"] = "bullish_crossover"
            elif macd_prev > sig_prev and macd_now < sig_now:
                bundle["macd_signal"] = "bearish_crossover"
            elif macd_now > sig_now:
                bundle["macd_signal"] = "bullish"
            else:
                bundle["macd_signal"] = "bearish"
    except Exception as e:
        bundle["errors"].append(f"macd:{e}")

    # Bollinger Bands ─────────────────────────────────────────────────────────
    try:
        bb_df = obb.technical.bbands(
            data=hist_obj.results, target="close", length=20, std=2.0
        ).to_dataframe()

        upper = _col(bb_df, "bbands_upper", "upper_band", "BBU_20_2.0", "Upper")
        lower = _col(bb_df, "bbands_lower", "lower_band", "BBL_20_2.0", "Lower")
        price = bundle["price"] or float(hist_df["close"].iloc[-1])

        if None not in (upper, lower) and upper != lower:
            if price >= upper:
                bundle["bollinger_position"] = "overbought"
            elif price <= lower:
                bundle["bollinger_position"] = "oversold"
            else:
                pct = (price - lower) / (upper - lower)
                bundle["bollinger_position"] = f"neutral ({pct:.0%} up band)"
    except Exception as e:
        bundle["errors"].append(f"bbands:{e}")
