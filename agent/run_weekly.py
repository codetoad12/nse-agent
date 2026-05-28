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
    symbols = wl.get("long_term_symbols") or wl.get("symbols") or []
    if not symbols:
        logger.error("No symbols found in watchlist.json — aborting")
        sys.exit(1)
    state   = load_state()
    now_ist = datetime.now(IST).isoformat()
    date_str = datetime.now(IST).strftime("%d %b %Y").lstrip("0")

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
