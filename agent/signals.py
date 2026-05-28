"""
Signal interpretation and LLM-prompt formatting.

The gate function keeps API costs low: only stocks with at least one
non-neutral signal get forwarded to the LLM each cycle.
"""


# ── Gate: decide whether this symbol warrants LLM analysis ──────────────────

def has_actionable_signal(bundle: dict) -> bool:
    """
    Return True when at least one signal is meaningfully non-neutral.
    Thresholds are intentionally conservative to reduce noise.
    """
    rsi = bundle.get("rsi")
    macd = bundle.get("macd_signal") or ""
    boll = bundle.get("bollinger_position") or ""

    rsi_triggered  = rsi is not None and (rsi < 35 or rsi > 65)
    macd_triggered = "crossover" in macd          # only fresh crossovers
    boll_triggered = boll in ("overbought", "oversold")

    return rsi_triggered or macd_triggered or boll_triggered


# ── Propose action deterministically ─────────────────────────────────────────

def propose_action_short(bundle: dict) -> str:
    """
    Determine a proposed trade action based on signal confluence.
    Returns one of: "BUY", "SELL", "WATCH", "HOLD"

    Rules:
    - BUY: RSI oversold (<35) AND (MACD bullish crossover OR Bollinger oversold)
    - SELL: RSI overbought (>65) AND (MACD bearish crossover OR Bollinger overbought)
    - WATCH: Any single signal fires (RSI extreme, crossover, or Bollinger extreme)
    - HOLD: No signals or weak mix
    """
    rsi = bundle.get("rsi")
    macd = bundle.get("macd_signal") or ""
    boll = bundle.get("bollinger_position") or ""

    rsi_oversold   = rsi is not None and rsi < 35
    rsi_overbought = rsi is not None and rsi > 65
    macd_bullish   = "bullish_crossover" in macd
    macd_bearish   = "bearish_crossover" in macd
    boll_oversold  = boll == "oversold"
    boll_overbought = boll == "overbought"

    if rsi_oversold and (macd_bullish or boll_oversold):
        return "BUY"
    if rsi_overbought and (macd_bearish or boll_overbought):
        return "SELL"
    if rsi_oversold or macd_bullish or boll_oversold or rsi_overbought or macd_bearish or boll_overbought:
        return "WATCH"
    return "HOLD"


# ── Human-readable RSI label ─────────────────────────────────────────────────

def rsi_label(v) -> str:
    if v is None:
        return "unavailable"
    if v < 30:   return f"oversold ({v:.1f})"
    if v < 40:   return f"near oversold ({v:.1f})"
    if v < 60:   return f"neutral ({v:.1f})"
    if v < 70:   return f"near overbought ({v:.1f})"
    return f"overbought ({v:.1f})"


# ── Format bundle as structured text for the LLM prompt ─────────────────────

def format_for_llm(bundle: dict, proposed_action: str) -> str:
    symbol   = bundle["symbol"].replace(".NS", "").replace(".BO", "")
    price    = bundle.get("price")
    chg      = bundle.get("change_pct")
    pe       = bundle.get("pe_ratio")
    mcap     = bundle.get("market_cap")

    price_str = f"₹{price:.2f}" if price else "unavailable"
    if price and chg is not None:
        price_str += f"  ({chg:+.2f}% today)"

    mcap_str = "unavailable"
    if mcap:
        if mcap >= 1e12:
            mcap_str = f"₹{mcap/1e12:.1f}T"
        elif mcap >= 1e9:
            mcap_str = f"₹{mcap/1e9:.0f}B"
        else:
            mcap_str = f"₹{mcap/1e6:.0f}M"

    lines = [
        f"PROPOSED ACTION: {proposed_action}",
        f"SYMBOL: {symbol}",
        f"Price: {price_str}",
        f"RSI (14): {rsi_label(bundle.get('rsi'))}",
        f"MACD signal: {bundle.get('macd_signal') or 'unavailable'}",
        f"Bollinger position: {bundle.get('bollinger_position') or 'unavailable'}",
        f"P/E ratio: {pe:.1f}" if pe else "P/E ratio: unavailable",
        f"Market cap: {mcap_str}",
        f"Sector: {bundle.get('sector') or 'unavailable'}",
    ]

    headlines = bundle.get("news_headlines", [])
    if headlines:
        lines.append("Recent news:")
        for h in headlines:
            lines.append(f"  - {h}")
    else:
        lines.append("Recent news: none available")

    gaps = bundle.get("errors", [])
    if gaps:
        lines.append(f"Data gaps: {', '.join(gaps)}")

    return "\n".join(lines)
