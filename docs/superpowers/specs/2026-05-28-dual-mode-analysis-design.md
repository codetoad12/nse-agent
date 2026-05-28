# Dual-Mode Analysis Design
**Date:** 2026-05-28  
**Status:** Approved

---

## Problem

The current agent is purely short-term (1–3 weeks, technical momentum). There is no support for longer-horizon investing. Additionally, the LLM silently breaks signal rules — MARUTI received a BUY with RSI 51.5 despite the prompt requiring RSI < 35. Confidence scores anchor to round numbers (0.55, 0.58, 0.62, 0.72) and are not trustworthy.

---

## Goals

1. Add a parallel long-term analysis mode (1–3 year, fundamentals-driven)
2. Fix rule enforcement: code proposes the action, LLM confirms or overrides with justification
3. Apply the code-proposes pattern to both short-term and long-term

---

## Architecture: Parallel Modules (Option A)

Short-term and long-term are kept entirely separate. Existing short-term code is not modified structurally — only `analyze.py` and `signals.py` are updated to support the code-proposes pattern.

```
Short-term (existing, updated)       Long-term (new)
──────────────────────────────       ───────────────────────────────
fetch.py         (unchanged)         fetch_lt.py
signals.py       (+ propose fn)      signals_lt.py
analyze.py       (+ proposed_action) analyze_lt.py
run.py           (unchanged)         run_weekly.py
alert.py         (+ digest fn)       ← shared
state/last_run.json                  state/last_run_lt.json
```

---

## Code-Proposes Pattern (both modes)

Instead of asking the LLM to decide the action, the code computes a `proposed_action` deterministically from signal thresholds and passes it to the LLM. The LLM can confirm or override — but must explicitly state if overriding and why.

### Short-term proposal logic (in `signals.py`)

```
proposed_action:
  BUY   → RSI < 35 AND (macd == bullish_crossover OR bollinger == oversold)
  SELL  → RSI > 65 AND (macd == bearish_crossover OR bollinger == overbought)
  WATCH → one signal triggered, missing confirmation
  HOLD  → no signals triggered
```

### Long-term proposal logic (in `signals_lt.py`)

```
proposed_action:
  BUY   → EPS growth > 10% AND revenue growth > 8% AND debt_equity < 1.0
           AND price > 200 DMA
  SELL  → EPS growth < 0% AND price < 200 DMA AND PE > sector_avg * 1.2
  WATCH → strong fundamentals but price trend against, OR good trend but weak fundamentals
  HOLD  → mixed or insufficient signals
```

### LLM prompt change (both modes)

The system prompt receives a `proposed_action` field and a new instruction:

> "A rule-based system has proposed: **{proposed_action}**. You may confirm this or override it. If you override, you MUST set `override: true` and explain in `override_reason`. Do not override without a specific, evidence-based reason from the signals provided."

The LLM response gains two new optional fields:
```json
{
  "action": "BUY|SELL|HOLD|WATCH",
  "confidence": 0.0–1.0,
  "override": false,
  "override_reason": null,
  "thesis": "...",
  "key_signals": [...],
  "risks": [...]
}
```

Overrides are logged in `decisions.jsonl` for audit.

---

## Long-Term Data: `fetch_lt.py`

Uses OpenBB with yfinance provider throughout. Same error-capture pattern as `fetch.py`.

| Signal | OpenBB Endpoint | Notes |
|---|---|---|
| 2-year price history | `obb.equity.price.historical` | For DMA computation |
| 50 DMA, 200 DMA | `obb.technical.sma` | Trend direction |
| P/E ratio, market cap, sector | `obb.equity.profile` | Valuation context |
| EPS, revenue (TTM + prior year) | `obb.equity.fundamental.income` | Growth rate |
| Debt-to-equity, ROE | `obb.equity.fundamental.metrics` | Balance sheet health |
| Dividend yield | `obb.equity.fundamental.dividends` | Income signal |

Returns a `LongTermBundle` dict. RSI/MACD/Bollinger are excluded — irrelevant at this horizon.

---

## Long-Term Analysis: `analyze_lt.py`

- Same model: `claude-haiku-4-5-20251001`
- System prompt focuses on: business quality, valuation, earnings trajectory, balance sheet
- Timeframe label: `"1–3 years"`
- Additional output field: `"valuation": "cheap|fair|expensive"` — shown in digest
- Receives `proposed_action` from `signals_lt.py`

---

## Weekly Orchestrator: `run_weekly.py`

1. Load `state/last_run_lt.json`
2. Read watchlist — uses `long_term_symbols` key from `watchlist.json` if present, otherwise falls back to `symbols`
3. For each symbol: `fetch_lt` → `signals_lt.propose_action` → `analyze_lt`
4. Log each result to `logs/decisions_lt.jsonl`
5. Save updated state to `state/last_run_lt.json`
6. Format and send one Telegram digest message

Runs independently of `run.py` — triggered via a separate cron job or manual invocation.

---

## Watchlist Customization

`watchlist.json` gains an optional key:

```json
{
  "symbols": ["RELIANCE.NS", "TCS.NS", ...],
  "long_term_symbols": ["RELIANCE.NS", "HDFCBANK.NS", "MARUTI.NS"]
}
```

If `long_term_symbols` is absent, `symbols` is used for both modes.

---

## Weekly Digest Format (`alert.py`)

Single Telegram message sent at end of `run_weekly.py`:

```
📊 Weekly Long-Term Review — 28 May 2026

🟢 BUY
  SBIN — 74% | Fair | EPS +18% YoY, price > 200 DMA
  MARUTI — 71% | Cheap | Revenue recovery, strong capex

🟡 HOLD
  TCS — Expensive but quality business
  RELIANCE — Mixed fundamentals

🔵 WATCH
  HDFCBANK — Strong ROE, P/E elevated

⚠️ Overrides this week: none

Risks: rate sensitivity (SBIN), EV transition (MARUTI)
```

Overrides are surfaced explicitly in the digest so they are easy to spot and audit.

---

## State Schema

`state/last_run_lt.json` mirrors `last_run.json` but adds signal snapshot:

```json
{
  "last_updated": "2026-05-28T...",
  "recommendations": {
    "SBIN.NS": {
      "action": "BUY",
      "confidence": 0.74,
      "valuation": "fair",
      "proposed_action": "BUY",
      "override": false,
      "ts": "2026-05-28T..."
    }
  }
}
```

The same signal snapshot improvement will be applied to `last_run.json` (short-term state) as part of this work.

---

## Files Changed

| File | Change |
|---|---|
| `agent/signals.py` | Add `propose_action_short()` |
| `agent/analyze.py` | Accept + pass `proposed_action` to LLM prompt |
| `agent/fetch_lt.py` | New — long-term signal fetching |
| `agent/signals_lt.py` | New — long-term proposal logic |
| `agent/analyze_lt.py` | New — long-term LLM analysis |
| `agent/run_weekly.py` | New — weekly orchestrator |
| `agent/alert.py` | Add `format_weekly_digest()` |
| `watchlist.json` | Add optional `long_term_symbols` key |
| `state/last_run_lt.json` | New state file (auto-created) |
| `logs/decisions_lt.jsonl` | New log file (auto-created) |
