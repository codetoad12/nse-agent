# Dual-Mode Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a long-term (1–3 year, fundamentals-driven) analysis mode alongside the existing short-term mode, and fix rule enforcement in both modes via a code-proposes pattern where signal thresholds are computed in Python and passed to the LLM for confirmation or override.

**Architecture:** Parallel modules — short-term code is updated minimally (signals.py + analyze.py + run.py), long-term lives in new files (fetch_lt.py, signals_lt.py, analyze_lt.py, run_weekly.py). Both modes use the same code-proposes pattern: Python computes `proposed_action` from deterministic rules, the LLM confirms or overrides with logged justification.

**Tech Stack:** Python, anthropic SDK, openbb[technical] + openbb-yfinance, pytest, unittest.mock

---

## File Map

| File | Change | Responsibility |
|---|---|---|
| `agent/signals.py` | Modify | Add `propose_action_short()` and update `format_for_llm()` signature |
| `agent/analyze.py` | Modify | Accept `proposed_action`, update system prompt, parse override fields |
| `agent/run.py` | Modify | Pass `proposed_action` to `analyze()`, update state schema |
| `agent/fetch_lt.py` | Create | Fetch long-term fundamentals via OpenBB |
| `agent/signals_lt.py` | Create | `propose_action_long()` + `format_for_llm_lt()` |
| `agent/analyze_lt.py` | Create | LLM analysis with long-term system prompt |
| `agent/alert.py` | Modify | Add `format_weekly_digest()` |
| `agent/run_weekly.py` | Create | Weekly orchestrator — fetch → propose → analyze → digest |
| `watchlist.json` | Modify | Add optional `long_term_symbols` key |
| `tests/test_signals.py` | Create | Unit tests for `propose_action_short` |
| `tests/test_signals_lt.py` | Create | Unit tests for `propose_action_long` |
| `tests/test_analyze.py` | Create | Unit tests for updated `analyze()` with mocked Anthropic |
| `tests/test_alert.py` | Create | Unit tests for `format_weekly_digest()` |

---

## Task 1: Add `propose_action_short()` to `signals.py`

**Files:**
- Modify: `agent/signals.py`
- Create: `tests/__init__.py`
- Create: `tests/test_signals.py`

- [ ] **Step 1: Create tests directory and write failing tests**

```python
# tests/__init__.py
# (empty)
```

```python
# tests/test_signals.py
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_signals.py -v
```

Expected: `ImportError` or `TypeError` — `propose_action_short` not defined yet.

- [ ] **Step 3: Add `propose_action_short()` and update `format_for_llm()` in `agent/signals.py`**

Add after the `has_actionable_signal` function:

```python
def propose_action_short(bundle: dict) -> str:
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
```

Update `format_for_llm` signature and prepend proposed action:

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_signals.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```
git add agent/signals.py tests/__init__.py tests/test_signals.py
git commit -m "feat: add propose_action_short and update format_for_llm signature"
```

---

## Task 2: Update `analyze.py` for code-proposes pattern

**Files:**
- Modify: `agent/analyze.py`
- Create: `tests/test_analyze.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analyze.py
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

@patch("agent.analyze.anthropic.Anthropic")
def test_analyze_returns_action(mock_anthropic):
    mock_anthropic.return_value = _mock_client(VALID_RESPONSE)
    rec = analyze(_bundle(), "BUY")
    assert rec["action"] == "BUY"
    assert rec["confidence"] == 0.74
    assert rec["override"] is False
    assert rec["override_reason"] is None
    assert rec["proposed_action"] == "BUY"

@patch("agent.analyze.anthropic.Anthropic")
def test_analyze_captures_override(mock_anthropic):
    mock_anthropic.return_value = _mock_client(OVERRIDE_RESPONSE)
    rec = analyze(_bundle(), "BUY")
    assert rec["action"] == "WATCH"
    assert rec["override"] is True
    assert "sector" in rec["override_reason"].lower()

@patch("agent.analyze.anthropic.Anthropic")
def test_analyze_fallback_on_bad_json(mock_anthropic):
    mock_anthropic.return_value = _mock_client("not json at all")
    rec = analyze(_bundle(), "HOLD")
    assert rec["action"] == "WATCH"
    assert rec["confidence"] == 0.3
    assert rec["override"] is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_analyze.py -v
```

Expected: `TypeError` — `analyze()` takes 1 argument, 2 given.

- [ ] **Step 3: Update `agent/analyze.py`**

Replace the entire file with:

```python
"""
LLM analysis step: send signal bundle to Claude, receive structured recommendation.
Uses claude-haiku for cost efficiency (~$0.10/day at 15-min intervals, 15 stocks).
"""
import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a quantitative analyst covering Indian equity markets (NSE/BSE).

You receive a signal snapshot for one stock and a rule-based proposed action.
Your job is to confirm the proposed action or override it with evidence.

RULES:
- Base your recommendation ONLY on the provided signals.
- SHORT_TERM means 1–3 weeks, driven by technical momentum.
- Confirm the proposed action unless you have specific signal evidence to override.
- If you override, you MUST set "override": true and explain concisely in "override_reason".
- Do NOT override based on general market sentiment or missing data alone.
- If key data is unavailable, lower your confidence accordingly.
- Indian macro/regulatory risk is always a background consideration.

RESPOND ONLY with valid JSON — no preamble, no markdown fences:
{
  "action": "BUY" | "HOLD" | "SELL" | "WATCH",
  "confidence": <float 0.0–1.0>,
  "override": <bool>,
  "override_reason": <string or null>,
  "timeframe": "1–3 weeks",
  "thesis": "<2 sentence explanation>",
  "key_signals": ["<signal 1>", "<signal 2>"],
  "risks": ["<risk 1>", "<risk 2>"]
}"""


def analyze(bundle: dict, proposed_action: str) -> dict:
    from agent.signals import format_for_llm

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    signal_text = format_for_llm(bundle, proposed_action)

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": signal_text}],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json\n"):
            raw = raw[5:]

    try:
        rec = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"LLM returned non-JSON for {bundle['symbol']}: {raw[:200]}")
        rec = {
            "action": "WATCH",
            "confidence": 0.3,
            "override": False,
            "override_reason": None,
            "timeframe": "1–3 weeks",
            "thesis": "LLM response could not be parsed. Manual review needed.",
            "key_signals": [],
            "risks": ["parse error"],
        }

    rec.setdefault("override", False)
    rec.setdefault("override_reason", None)

    rec["symbol"]          = bundle["symbol"]
    rec["price"]           = bundle.get("price")
    rec["rsi"]             = bundle.get("rsi")
    rec["macd"]            = bundle.get("macd_signal")
    rec["bollinger"]       = bundle.get("bollinger_position")
    rec["proposed_action"] = proposed_action

    return rec
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_analyze.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```
git add agent/analyze.py tests/test_analyze.py
git commit -m "feat: code-proposes pattern for short-term analysis"
```

---

## Task 3: Wire `proposed_action` through `run.py`

**Files:**
- Modify: `agent/run.py`

- [ ] **Step 1: Update imports and the main loop in `agent/run.py`**

Change the import line at the top:

```python
from agent.signals import has_actionable_signal, propose_action_short
```

In the main loop, after the gate check (after `skipped.append(symbol); continue`), add the proposal before the LLM call:

```python
        # 2.5 Propose action from signal rules
        proposed_action = propose_action_short(bundle)

        # 3. LLM analysis
        try:
            rec = analyze(bundle, proposed_action)
```

Update the state save at line 124 to include new fields:

```python
        state["recommendations"][symbol] = {
            "action":          rec["action"],
            "confidence":      rec["confidence"],
            "proposed_action": rec.get("proposed_action"),
            "override":        rec.get("override", False),
            "ts":              now_ist,
        }
```

Update the log line to capture override:

```python
        logger.info(
            f"{symbol}: {rec['action']} "
            f"(conf={rec['confidence']:.0%}  RSI={rec.get('rsi') or 'n/a'}"
            f"  proposed={proposed_action}"
            f"{'  OVERRIDE' if rec.get('override') else ''})"
        )
```

- [ ] **Step 2: Verify no import errors**

```
python -c "from agent.run import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```
git add agent/run.py
git commit -m "feat: wire proposed_action through run.py and update state schema"
```

---

## Task 4: Create `fetch_lt.py`

**Files:**
- Create: `agent/fetch_lt.py`

- [ ] **Step 1: Create `agent/fetch_lt.py`**

```python
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
            bundle["roe"]           = _col(metrics, "roe", "returnOnEquity")
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
```

- [ ] **Step 2: Verify import works**

```
python -c "from agent.fetch_lt import fetch_signals_lt; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```
git add agent/fetch_lt.py
git commit -m "feat: add fetch_signals_lt for long-term fundamental data"
```

---

## Task 5: Create `signals_lt.py`

**Files:**
- Create: `agent/signals_lt.py`
- Create: `tests/test_signals_lt.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_signals_lt.py
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_signals_lt.py -v
```

Expected: `ModuleNotFoundError` — `agent.signals_lt` not found.

- [ ] **Step 3: Create `agent/signals_lt.py`**

```python
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

    if strong_growth and healthy_balance and price_above_200:
        return "BUY"
    if deteriorating and price_below_200:
        return "SELL"
    if strong_growth or (price_above_200 and rev_growth is not None and rev_growth > 5):
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_signals_lt.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```
git add agent/signals_lt.py tests/test_signals_lt.py
git commit -m "feat: add propose_action_long and format_for_llm_lt"
```

---

## Task 6: Create `analyze_lt.py`

**Files:**
- Create: `agent/analyze_lt.py`
- Create: `tests/test_analyze_lt.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analyze_lt.py
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

@patch("agent.analyze_lt.anthropic.Anthropic")
def test_analyze_lt_returns_action(mock_anthropic):
    mock_anthropic.return_value = _mock_client(VALID_RESPONSE)
    rec = analyze_lt(_bundle(), "BUY")
    assert rec["action"] == "BUY"
    assert rec["valuation"] == "fair"
    assert rec["override"] is False
    assert rec["proposed_action"] == "BUY"
    assert rec["symbol"] == "SBIN.NS"

@patch("agent.analyze_lt.anthropic.Anthropic")
def test_analyze_lt_fallback_on_bad_json(mock_anthropic):
    mock_anthropic.return_value = _mock_client("bad json")
    rec = analyze_lt(_bundle(), "HOLD")
    assert rec["action"] == "WATCH"
    assert rec["confidence"] == 0.3
    assert rec["valuation"] == "unavailable"
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_analyze_lt.py -v
```

Expected: `ModuleNotFoundError` — `agent.analyze_lt` not found.

- [ ] **Step 3: Create `agent/analyze_lt.py`**

```python
"""
LLM analysis for long-term (1-3 year) positions.
Uses fundamentals-driven system prompt. Same model as short-term for cost parity.
"""
import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a fundamental analyst covering Indian equity markets (NSE/BSE).

You receive a fundamental snapshot for one stock and a rule-based proposed action.
Your job is to assess the long-term investment case and confirm or override the proposal.

RULES:
- Base your recommendation ONLY on the provided signals.
- LONG_TERM means 1–3 years, driven by earnings growth, valuation, and balance sheet quality.
- BUY  → strong earnings trajectory + reasonable valuation + healthy balance sheet + upward trend.
- SELL → deteriorating fundamentals + downward price trend.
- HOLD → mixed signals; no strong directional case.
- WATCH → one strong signal present but missing confirmation.
- Confirm the proposed action unless you have specific evidence to override.
- If you override, set "override": true and explain in "override_reason".
- If key data is unavailable, lower your confidence and note it in risks.
- Indian macro/regulatory risk is always a background consideration.

RESPOND ONLY with valid JSON — no preamble, no markdown fences:
{
  "action": "BUY" | "HOLD" | "SELL" | "WATCH",
  "confidence": <float 0.0–1.0>,
  "valuation": "cheap" | "fair" | "expensive",
  "override": <bool>,
  "override_reason": <string or null>,
  "timeframe": "1–3 years",
  "thesis": "<2 sentence explanation>",
  "key_signals": ["<signal 1>", "<signal 2>"],
  "risks": ["<risk 1>", "<risk 2>"]
}"""


def analyze_lt(bundle: dict, proposed_action: str) -> dict:
    from agent.signals_lt import format_for_llm_lt

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    signal_text = format_for_llm_lt(bundle, proposed_action)

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": signal_text}],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json\n"):
            raw = raw[5:]

    try:
        rec = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"LLM returned non-JSON for {bundle['symbol']}: {raw[:200]}")
        rec = {
            "action": "WATCH",
            "confidence": 0.3,
            "valuation": "unavailable",
            "override": False,
            "override_reason": None,
            "timeframe": "1–3 years",
            "thesis": "LLM response could not be parsed. Manual review needed.",
            "key_signals": [],
            "risks": ["parse error"],
        }

    rec.setdefault("override", False)
    rec.setdefault("override_reason", None)
    rec.setdefault("valuation", "unavailable")

    rec["symbol"]          = bundle["symbol"]
    rec["price"]           = bundle.get("price")
    rec["proposed_action"] = proposed_action
    rec["eps_growth"]      = bundle.get("eps_growth")
    rec["revenue_growth"]  = bundle.get("revenue_growth")
    rec["sma_200"]         = bundle.get("sma_200")

    return rec
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_analyze_lt.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```
git add agent/analyze_lt.py tests/test_analyze_lt.py
git commit -m "feat: add analyze_lt for long-term LLM analysis"
```

---

## Task 7: Add `format_weekly_digest()` to `alert.py`

**Files:**
- Modify: `agent/alert.py`
- Create: `tests/test_alert.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_alert.py
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
    buy_pos  = text.index("BUY")
    hold_pos = text.index("HOLD")
    watch_pos = text.index("WATCH")
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_alert.py -v
```

Expected: `ImportError` — `format_weekly_digest` not defined.

- [ ] **Step 3: Add `format_weekly_digest()` to `agent/alert.py`**

Append to the end of the file:

```python
def format_weekly_digest(recommendations: list, date_str: str) -> str:
    by_action = {"BUY": [], "SELL": [], "WATCH": [], "HOLD": []}
    overrides = []

    for rec in recommendations:
        action = rec.get("action", "HOLD")
        by_action.setdefault(action, []).append(rec)
        if rec.get("override"):
            overrides.append(rec)

    action_emoji = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "WATCH": "🔵 WATCH", "HOLD": "🟡 HOLD"}
    lines = [f"📊 Weekly Long-Term Review — {date_str}", ""]

    for action in ["BUY", "SELL", "WATCH", "HOLD"]:
        stocks = by_action.get(action, [])
        if not stocks:
            continue
        lines.append(action_emoji[action])
        for rec in stocks:
            symbol = rec["symbol"].replace(".NS", "").replace(".BO", "")
            conf = rec.get("confidence", 0)
            val  = rec.get("valuation", "")
            thesis = (rec.get("thesis") or "")[:80]
            val_str = f" | {val.capitalize()}" if val and val != "unavailable" else ""
            lines.append(f"  {symbol} — {conf:.0%}{val_str} | {thesis}")
        lines.append("")

    if overrides:
        lines.append(f"⚠️ Overrides this week: {len(overrides)}")
        for rec in overrides:
            symbol = rec["symbol"].replace(".NS", "").replace(".BO", "")
            reason = (rec.get("override_reason") or "")[:80]
            lines.append(f"  {symbol}: {reason}")
    else:
        lines.append("⚠️ Overrides this week: none")

    all_risks = []
    for rec in recommendations:
        risks = rec.get("risks") or []
        if risks:
            symbol = rec["symbol"].replace(".NS", "").replace(".BO", "")
            all_risks.append(f"{symbol}: {risks[0][:40]}")

    if all_risks:
        lines.append("")
        lines.append("Risks: " + " | ".join(all_risks[:3]))

    return "\n".join(l for l in lines if l is not None)
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_alert.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```
git add agent/alert.py tests/test_alert.py
git commit -m "feat: add format_weekly_digest to alert.py"
```

---

## Task 8: Create `run_weekly.py`

**Files:**
- Create: `agent/run_weekly.py`

- [ ] **Step 1: Create `agent/run_weekly.py`**

```python
"""
Weekly long-term analysis cycle.
Run once per week (e.g. Friday after market close or Saturday morning).
Sends a single digest Telegram message summarising all long-term positions.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pytz

from agent.alert import format_weekly_digest, send_telegram
from agent.analyze_lt import analyze_lt
from agent.fetch_lt import fetch_signals_lt
from agent.signals_lt import propose_action_long

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

IST            = pytz.timezone("Asia/Kolkata")
STATE_PATH     = Path("state/last_run_lt.json")
LOG_PATH       = Path("logs/decisions_lt.jsonl")
WATCHLIST_PATH = Path("watchlist.json")


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"last_updated": None, "recommendations": {}}


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def append_log(entry: dict):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    wl      = json.loads(WATCHLIST_PATH.read_text())
    symbols = wl.get("long_term_symbols") or wl["symbols"]
    state   = load_state()
    now_ist = datetime.now(IST).isoformat()
    date_str = datetime.now(IST).strftime("%-d %b %Y")

    logger.info(f"Weekly cycle start — {len(symbols)} symbols")
    results = []

    for symbol in symbols:
        logger.info(f"--- {symbol} ---")

        try:
            bundle = fetch_signals_lt(symbol)
        except Exception as e:
            logger.error(f"{symbol}: fetch crashed — {e}")
            continue

        if bundle.get("errors"):
            logger.warning(f"{symbol}: partial data — {bundle['errors']}")

        proposed_action = propose_action_long(bundle)
        logger.info(f"{symbol}: proposed={proposed_action}")

        try:
            rec = analyze_lt(bundle, proposed_action)
        except Exception as e:
            logger.error(f"{symbol}: LLM failed — {e}")
            continue

        logger.info(
            f"{symbol}: {rec['action']} (conf={rec['confidence']:.0%}"
            f"  valuation={rec.get('valuation')}"
            f"{'  OVERRIDE' if rec.get('override') else ''})"
        )

        append_log({"cycle_ts": now_ist, **rec})
        state["recommendations"][symbol] = {
            "action":          rec["action"],
            "confidence":      rec["confidence"],
            "valuation":       rec.get("valuation"),
            "proposed_action": rec.get("proposed_action"),
            "override":        rec.get("override", False),
            "ts":              now_ist,
        }
        results.append(rec)

    state["last_updated"] = now_ist
    save_state(state)

    if results:
        digest = format_weekly_digest(results, date_str)
        send_telegram(digest)
        logger.info("Weekly digest sent.")
    else:
        logger.warning("No results to digest — Telegram not called.")

    logger.info("Weekly cycle done.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify import**

```
python -c "from agent.run_weekly import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```
git add agent/run_weekly.py
git commit -m "feat: add run_weekly.py for long-term weekly analysis cycle"
```

---

## Task 9: Update `watchlist.json` and run full test suite

**Files:**
- Modify: `watchlist.json`

- [ ] **Step 1: Add `long_term_symbols` key to `watchlist.json`**

```json
{
  "symbols": [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "BAJFINANCE.NS", "SBIN.NS", "WIPRO.NS",
    "AXISBANK.NS", "KOTAKBANK.NS", "MARUTI.NS", "TITAN.NS", "ULTRACEMCO.NS"
  ],
  "long_term_symbols": [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "MARUTI.NS", "TITAN.NS", "BAJFINANCE.NS"
  ]
}
```

- [ ] **Step 2: Run the full test suite**

```
pytest tests/ -v
```

Expected: all tests PASS with no errors.

- [ ] **Step 3: Final commit**

```
git add watchlist.json
git commit -m "config: add long_term_symbols to watchlist"
```
