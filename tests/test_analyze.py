import os
from unittest.mock import MagicMock, patch
from agent.analyze import analyze

VALID_RESPONSE = """{
  "action": "BUY",
  "confidence": 0.74,
  "override": false,
  "override_reason": null,
  "timeframe": "1-3 weeks",
  "thesis": "Strong oversold signal with MACD confirmation.",
  "key_signals": ["RSI oversold", "MACD bullish crossover"],
  "risks": ["Macro headwinds"]
}"""

OVERRIDE_RESPONSE = """{
  "action": "WATCH",
  "confidence": 0.55,
  "override": true,
  "override_reason": "RSI barely below 35; bearish sector news undermines confidence.",
  "timeframe": "1-3 weeks",
  "thesis": "Downgrading to WATCH due to sector headwinds.",
  "key_signals": ["RSI 34.8"],
  "risks": ["Sector weakness"]
}"""

def _bundle():
    return {"symbol": "SBIN.NS", "price": 970.0, "rsi": 34.5,
            "macd_signal": "bullish_crossover", "bollinger_position": "neutral (35% up band)",
            "pe_ratio": None, "market_cap": 9e12, "sector": "Financial Services",
            "news_headlines": [], "errors": [], "change_pct": -0.5}

def _mock_client(response_text):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    return mock_client

@patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
@patch("agent.analyze.anthropic.Anthropic")
def test_analyze_returns_action(mock_anthropic):
    mock_anthropic.return_value = _mock_client(VALID_RESPONSE)
    rec = analyze(_bundle(), "BUY")
    assert rec["action"] == "BUY"
    assert rec["confidence"] == 0.74
    assert rec["override"] is False
    assert rec["override_reason"] is None
    assert rec["proposed_action"] == "BUY"

@patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
@patch("agent.analyze.anthropic.Anthropic")
def test_analyze_captures_override(mock_anthropic):
    mock_anthropic.return_value = _mock_client(OVERRIDE_RESPONSE)
    rec = analyze(_bundle(), "BUY")
    assert rec["action"] == "WATCH"
    assert rec["override"] is True
    assert "sector" in rec["override_reason"].lower()

@patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
@patch("agent.analyze.anthropic.Anthropic")
def test_analyze_fallback_on_bad_json(mock_anthropic):
    mock_anthropic.return_value = _mock_client("not json at all")
    rec = analyze(_bundle(), "HOLD")
    assert rec["action"] == "WATCH"
    assert rec["confidence"] == 0.3
    assert rec["override"] is False
