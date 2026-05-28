from agent.signals_lt import propose_action_long, format_for_llm_lt

def _bundle(**kwargs):
    base = {
        "symbol": "SBIN.NS", "price": 970.0,
        "sma_50": 950.0, "sma_200": 900.0,
        "pe_ratio": 12.0, "market_cap": 9e12, "sector": "Financial Services",
        "eps_growth": None, "revenue_growth": None,
        "debt_to_equity": None, "roe": None, "dividend_yield": 2.0,
        "errors": [],
    }
    base.update(kwargs)
    return base

def test_buy_strong_fundamentals_above_200dma():
    b = _bundle(eps_growth=15.0, revenue_growth=10.0, debt_to_equity=0.5)
    assert propose_action_long(b) == "BUY"

def test_sell_deteriorating_below_200dma():
    b = _bundle(eps_growth=-5.0, price=800.0, sma_200=900.0)
    assert propose_action_long(b) == "SELL"

def test_watch_good_fundamentals_bad_trend():
    b = _bundle(eps_growth=12.0, revenue_growth=9.0, debt_to_equity=0.4,
                price=800.0, sma_200=900.0)
    assert propose_action_long(b) == "WATCH"

def test_watch_good_trend_weak_fundamentals():
    b = _bundle(eps_growth=3.0, revenue_growth=4.0)
    assert propose_action_long(b) == "WATCH"

def test_hold_missing_data():
    b = _bundle()
    assert propose_action_long(b) == "HOLD"

def test_format_includes_proposed_action():
    b = _bundle(eps_growth=15.0, revenue_growth=10.0, debt_to_equity=0.5)
    text = format_for_llm_lt(b, "BUY")
    assert "PROPOSED ACTION: BUY" in text
    assert "EPS growth" in text
    assert "200 DMA" in text
