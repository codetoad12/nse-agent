"""
Alert delivery via Telegram bot.
Alert fires when: (a) action changes from previous cycle, OR
                  (b) high-conviction BUY/SELL (confidence >= 0.75).
"""
import logging
import os

import requests

logger = logging.getLogger(__name__)

EMOJI = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡", "WATCH": "🔵"}
TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"


def should_alert(rec: dict, prev_action: str | None) -> bool:
    action_changed  = prev_action is not None and prev_action != rec["action"]
    high_conviction = rec["action"] in ("BUY", "SELL") and rec["confidence"] >= 0.75
    return action_changed or high_conviction


def format_alert(rec: dict, prev_action: str | None = None) -> str:
    symbol = rec["symbol"].replace(".NS", "").replace(".BO", "")
    emoji  = EMOJI.get(rec["action"], "⚪")

    change_note = ""
    if prev_action and prev_action != rec["action"]:
        change_note = f" (was {prev_action})"

    lines = [
        f"{emoji} {symbol} — {rec['action']}{change_note}",
        f"Price: ₹{rec['price']:.2f}" if rec.get("price") else "",
        f"Confidence: {rec['confidence']:.0%}",
        f"RSI: {rec['rsi']:.1f}" if rec.get("rsi") else "",
        f"MACD: {rec['macd']}" if rec.get("macd") else "",
        "",
        rec.get("thesis", ""),
    ]

    risks = rec.get("risks", [])
    if risks:
        lines.append(f"Risk: {', '.join(risks[:2])}")

    return "\n".join(l for l in lines if l is not None)


def send_telegram(text: str):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.info(f"[Telegram not configured] {text}")
        return

    try:
        resp = requests.post(
            TELEGRAM_URL.format(token=token),
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Telegram alert sent.")
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
