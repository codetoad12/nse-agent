# NSE Stock Monitoring Agent

Monitors NSE/BSE equities every 15 minutes during market hours using OpenBB for data,
Claude Haiku for analysis, and Telegram for alerts. Runs entirely on GitHub Actions — no server needed.

## How it works

```
Schedule (cron) → Fetch signals (OpenBB/yfinance) → Gate (non-neutral only) →
LLM analyze (Claude Haiku) → Alert (Telegram) → Commit state → repeat
```

State is persisted as `state/last_run.json` committed back to the repo each cycle.
Every recommendation is appended to `logs/decisions.jsonl` for audit/backtesting.

## Setup

### 1. Fork / clone this repo

### 2. Add GitHub Secrets

Go to **Settings → Secrets → Actions** and add:

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | From console.anthropic.com |
| `TELEGRAM_BOT_TOKEN` | From @BotFather on Telegram |
| `TELEGRAM_CHAT_ID` | Your chat ID (send any msg to @userinfobot) |

### 3. Edit your watchlist

Edit `watchlist.json` — use NSE symbols with `.NS` suffix, or BSE with `.BO`.

```json
{
  "symbols": ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
}
```

### 4. Enable Actions

Go to **Actions** tab → enable workflows. The cron will kick in automatically.
Use **workflow_dispatch** to trigger a manual test run first.

## Signal logic

| Signal | Actionable threshold |
|--------|---------------------|
| RSI (14) | < 35 (oversold) or > 65 (overbought) |
| MACD | Fresh bullish or bearish crossover |
| Bollinger Bands | Price touching upper or lower band |

All three are computed from 90-day price history via OpenBB + yfinance (free, no API key).

## Alert logic

A Telegram alert fires when:
- Recommendation **changes** from the previous cycle (e.g. HOLD → BUY)
- OR action is BUY/SELL with confidence ≥ 75%

## Cost estimate

- OpenBB/yfinance: free
- Claude Haiku: ~$0.10/day (15 stocks × 26 cycles × partial gating)
- Telegram: free

## Project structure

```
.github/workflows/market_monitor.yml   # cron schedule
agent/
  run.py        # entry point
  fetch.py      # OpenBB data fetching
  signals.py    # gate + LLM formatting
  analyze.py    # Claude Haiku analysis
  alert.py      # Telegram delivery
watchlist.json  # symbols to monitor
state/          # persisted state (committed each cycle)
logs/           # JSONL decision log
requirements.txt
```
