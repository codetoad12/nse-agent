"""
Long-term signal proposal and LLM prompt formatting.
Fundamentals-driven: EPS/revenue growth, balance sheet, price vs 200 DMA.
"""


def propose_action_long(bundle: dict) -> str:
    eps_growth   = bundle.get("eps_growth")
    rev_growth   = bundle.get("revenue_growth")
    debt_eq      = bundle.get("debt_to_equity")
    price        = bundle.get("price")
    sma_200      = bundle.get("sma_200")

    price_above_200 = price is not None and sma_200 is not None and price > sma_200
    price_below_200 = price is not None and sma_200 is not None and price < sma_200

    strong_growth   = (eps_growth is not None and eps_growth > 10
                       and rev_growth is not None and rev_growth > 8)
    healthy_balance = debt_eq is not None and debt_eq < 1.0
    deteriorating   = eps_growth is not None and eps_growth < 0
    has_fundamentals = (eps_growth is not None or rev_growth is not None or
                        debt_eq is not None or bundle.get("roe") is not None)

    if strong_growth and healthy_balance and price_above_200:
        return "BUY"
    if deteriorating and price_below_200:
        return "SELL"
    if strong_growth or (price_above_200 and has_fundamentals):
        return "WATCH"
    return "HOLD"


def _pct(v) -> str:
    if v is None:
        return "unavailable"
    return f"{v:+.1f}%"


def _price_vs_dma(price, dma, label) -> str:
    if price is None or dma is None:
        return f"{label}: unavailable"
    diff = ((price - dma) / dma) * 100
    direction = "above" if price > dma else "below"
    return f"{label}: ₹{dma:.0f} (price {direction} by {abs(diff):.1f}%)"


def format_for_llm_lt(bundle: dict, proposed_action: str) -> str:
    symbol = bundle["symbol"].replace(".NS", "").replace(".BO", "")
    price  = bundle.get("price")
    mcap   = bundle.get("market_cap")

    mcap_str = "unavailable"
    if mcap:
        if mcap >= 1e12:
            mcap_str = f"₹{mcap/1e12:.1f}T"
        elif mcap >= 1e9:
            mcap_str = f"₹{mcap/1e9:.0f}B"

    pe = bundle.get("pe_ratio")
    roe = bundle.get("roe")
    dte = bundle.get("debt_to_equity")
    div = bundle.get("dividend_yield")

    lines = [
        f"PROPOSED ACTION: {proposed_action}",
        f"SYMBOL: {symbol}",
        f"Price: ₹{price:.2f}" if price else "Price: unavailable",
        _price_vs_dma(price, bundle.get("sma_50"),  "50 DMA"),
        _price_vs_dma(price, bundle.get("sma_200"), "200 DMA"),
        f"P/E ratio: {pe:.1f}" if pe else "P/E ratio: unavailable",
        f"EPS growth (YoY): {_pct(bundle.get('eps_growth'))}",
        f"Revenue growth (YoY): {_pct(bundle.get('revenue_growth'))}",
        f"Debt-to-equity: {dte:.2f}" if dte is not None else "Debt-to-equity: unavailable",
        f"ROE: {_pct(roe)}",
        f"Dividend yield: {div:.1f}%" if div else "Dividend yield: unavailable",
        f"Market cap: {mcap_str}",
        f"Sector: {bundle.get('sector') or 'unavailable'}",
    ]

    gaps = bundle.get("errors", [])
    if gaps:
        lines.append(f"Data gaps: {', '.join(gaps)}")

    return "\n".join(lines)
