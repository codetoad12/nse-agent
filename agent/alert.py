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
