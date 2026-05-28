from agent.alert import format_weekly_digest


def _rec(symbol, action, confidence, valuation="fair", override=False, override_reason=None, risks=None):
    return {
        "symbol": symbol, "action": action, "confidence": confidence,
        "valuation": valuation, "override": override,
        "override_reason": override_reason,
        "thesis": "Test thesis for this stock.",
        "risks": risks or ["market risk"],
    }


def test_digest_contains_buy_stocks():
    recs = [_rec("SBIN.NS", "BUY", 0.74), _rec("MARUTI.NS", "HOLD", 0.60)]
    text = format_weekly_digest(recs, "28 May 2026")
    assert "SBIN" in text
    assert "BUY" in text
    assert "28 May 2026" in text


def test_digest_groups_by_action():
    recs = [
        _rec("SBIN.NS", "BUY", 0.74),
        _rec("TCS.NS", "HOLD", 0.60),
        _rec("ITC.NS", "WATCH", 0.62),
    ]
    text = format_weekly_digest(recs, "28 May 2026")
    buy_pos   = text.index("BUY")
    hold_pos  = text.index("HOLD")
    assert buy_pos < hold_pos


def test_digest_shows_override():
    recs = [
        _rec("MARUTI.NS", "WATCH", 0.55, override=True,
             override_reason="RSI not oversold despite MACD crossover")
    ]
    text = format_weekly_digest(recs, "28 May 2026")
    assert "Override" in text or "override" in text.lower()
    assert "MARUTI" in text


def test_digest_no_overrides_message():
    recs = [_rec("SBIN.NS", "BUY", 0.74)]
    text = format_weekly_digest(recs, "28 May 2026")
    assert "none" in text.lower() or "0" in text
