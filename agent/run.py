"""
Main agent loop — called by GitHub Actions every 15 minutes.

Flow per cycle:
  load state → check market open → foreach symbol:
    fetch signals → gate (actionable?) → LLM analyze →
    alert if needed → update state → commit state
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pytz

from agent.alert import format_alert, send_telegram, should_alert
from agent.analyze import analyze
from agent.fetch import fetch_signals
from agent.signals import has_actionable_signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

IST          = pytz.timezone("Asia/Kolkata")
STATE_PATH   = Path("state/last_run.json")
LOG_PATH     = Path("logs/decisions.jsonl")
WATCHLIST    = Path("watchlist.json")


# ── Market calendar ──────────────────────────────────────────────────────────

def is_market_open() -> bool:
    """NSE regular hours: 09:15 – 15:30 IST, Mon–Fri."""
    now = datetime.now(IST)
    if now.weekday() > 4:  # Saturday / Sunday
        return False
    open_t  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_t <= now <= close_t


# ── State persistence ────────────────────────────────────────────────────────

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


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    # if not is_market_open():
    #     logger.info("Market is closed — nothing to do.")
    #     sys.exit(0)

    state     = load_state()
    watchlist = json.loads(WATCHLIST.read_text())["symbols"]
    now_ist   = datetime.now(IST).isoformat()

    logger.info(f"Cycle start — {len(watchlist)} symbols in watchlist")
    alerted: list[str] = []
    skipped: list[str] = []

    for symbol in watchlist:
        logger.info(f"--- {symbol} ---")

        # 1. Fetch
        try:
            bundle = fetch_signals(symbol)
        except Exception as e:
            logger.error(f"{symbol}: fetch crashed — {e}")
            continue

        if bundle.get("errors"):
            logger.warning(f"{symbol}: partial data — {bundle['errors']}")

        # 2. Gate — skip neutral signals to save API cost
        if not has_actionable_signal(bundle):
            logger.info(f"{symbol}: no actionable signal, skipping LLM")
            skipped.append(symbol)
            continue

        # 3. LLM analysis
        try:
            rec = analyze(bundle)
        except Exception as e:
            logger.error(f"{symbol}: LLM failed — {e}")
            continue

        logger.info(
            f"{symbol}: {rec['action']} "
            f"(conf={rec['confidence']:.0%}  RSI={rec.get('rsi') or 'n/a'})"
        )

        # 4. Alert
        prev = state["recommendations"].get(symbol, {})
        prev_action = prev.get("action")

        if should_alert(rec, prev_action):
            msg = format_alert(rec, prev_action)
            send_telegram(msg)
            alerted.append(symbol)

        # 5. Log (always) + update state
        append_log({"cycle_ts": now_ist, **rec})
        state["recommendations"][symbol] = {
            "action":     rec["action"],
            "confidence": rec["confidence"],
            "ts":         now_ist,
        }

    # 6. Persist state
    state["last_updated"] = now_ist
    save_state(state)

    logger.info(
        f"Cycle done — analyzed: {len(watchlist) - len(skipped)}, "
        f"skipped (neutral): {len(skipped)}, "
        f"alerted: {alerted or 'none'}"
    )


if __name__ == "__main__":
    main()
