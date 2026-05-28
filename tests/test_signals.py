from agent.signals import propose_action_short, format_for_llm

def _bundle(**kwargs):
    base = {"symbol": "TEST.NS", "rsi": None, "macd_signal": None,
            "bollinger_position": None, "price": 100.0, "change_pct": 0.0,
            "pe_ratio": None, "market_cap": None, "sector": None,
            "news_headlines": [], "errors": []}
    base.update(kwargs)
    return base

def test_buy_rsi_and_macd():
    b = _bundle(rsi=32.0, macd_signal="bullish_crossover")
    assert propose_action_short(b) == "BUY"

def test_buy_rsi_and_bollinger():
    b = _bundle(rsi=33.0, bollinger_position="oversold")
    assert propose_action_short(b) == "BUY"

def test_sell_rsi_and_macd():
    b = _bundle(rsi=68.0, macd_signal="bearish_crossover")
    assert propose_action_short(b) == "SELL"

def test_sell_rsi_and_bollinger():
    b = _bundle(rsi=67.0, bollinger_position="overbought")
    assert propose_action_short(b) == "SELL"

def test_watch_rsi_only():
    b = _bundle(rsi=32.0, macd_signal="bearish")
    assert propose_action_short(b) == "WATCH"

def test_watch_macd_crossover_only():
    b = _bundle(rsi=50.0, macd_signal="bullish_crossover")
    assert propose_action_short(b) == "WATCH"

def test_hold_neutral():
    b = _bundle(rsi=50.0, macd_signal="bullish")
    assert propose_action_short(b) == "HOLD"

def test_hold_no_signals():
    b = _bundle()
    assert propose_action_short(b) == "HOLD"

def test_format_for_llm_includes_proposed_action():
    b = _bundle(rsi=32.0, macd_signal="bullish_crossover")
    text = format_for_llm(b, "BUY")
    assert "PROPOSED ACTION: BUY" in text
