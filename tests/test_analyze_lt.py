import os
from unittest.mock import MagicMock, patch
from agent.analyze_lt import analyze_lt

VALID_RESPONSE = """{
  "action": "BUY",
  "confidence": 0.78,
  "valuation": "fair",
  "override": false,
  "override_reason": null,
  "timeframe": "1-3 years",
  "thesis": "Strong EPS growth and healthy balance sheet with upward trend.",
  "key_signals": ["EPS growth +15%", "Price above 200 DMA"],
  "risks": ["Rate cycle risk"]
}"""

def _bundle():
    return {
        "symbol": "SBIN.NS", "price": 970.0,
        "sma_50": 950.0, "sma_200": 900.0,
        "pe_ratio": 12.0, "market_cap": 9e12, "sector": "Financial Services",
        "eps_growth": 15.0, "revenue_growth": 10.0,
        "debt_to_equity": 0.5, "roe": 14.0, "dividend_yield": 2.0,
        "errors": [],
    }

def _mock_client(response_text):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    return mock_client

@patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
@patch("agent.analyze_lt.anthropic.Anthropic")
def test_analyze_lt_returns_action(mock_anthropic):
    mock_anthropic.return_value = _mock_client(VALID_RESPONSE)
    rec = analyze_lt(_bundle(), "BUY")
    assert rec["action"] == "BUY"
    assert rec["valuation"] == "fair"
    assert rec["override"] is False
    assert rec["proposed_action"] == "BUY"
    assert rec["symbol"] == "SBIN.NS"

@patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
@patch("agent.analyze_lt.anthropic.Anthropic")
def test_analyze_lt_fallback_on_bad_json(mock_anthropic):
    mock_anthropic.return_value = _mock_client("bad json")
    rec = analyze_lt(_bundle(), "HOLD")
    assert rec["action"] == "WATCH"
    assert rec["confidence"] == 0.3
    assert rec["valuation"] == "unavailable"
