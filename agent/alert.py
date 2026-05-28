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


_MAX_TG = 4096


def _split_message(text: str) -> list[str]:
    """Split text into ≤4096-char chunks, breaking at blank lines."""
    if len(text) <= _MAX_TG:
        return [text]
    chunks, current = [], []
    current_len = 0
    for para in text.split("\n\n"):
        block = para + "\n\n"
        if current_len + len(block) > _MAX_TG and current:
            chunks.append("\n\n".join(current).rstrip())
            current, current_len = [], 0
        current.append(para)
        current_len += len(block)
    if current:
        chunks.append("\n\n".join(current).rstrip())
    return chunks


def send_telegram(text: str):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.info(f"[Telegram not configured] {text}")
        return

    for chunk in _split_message(text):
        try:
            resp = requests.post(
                TELEGRAM_URL.format(token=token),
                json={"chat_id": chat_id, "text": chunk},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return
    logger.info("Telegram alert sent.")


def format_weekly_digest(recommendations: list, date_str: str) -> str:
    by_action: dict = {}
    overrides = []

    for rec in recommendations:
        action = rec.get("action", "HOLD")
        by_action.setdefault(action, []).append(rec)
        if rec.get("override"):
            overrides.append(rec)

    action_label = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "WATCH": "🔵 WATCH", "HOLD": "🟡 HOLD"}
    lines = [f"📊 Weekly Long-Term Review — {date_str}", ""]

    for action in ["BUY", "SELL", "WATCH", "HOLD"]:
        stocks = by_action.get(action, [])
        if not stocks:
            continue
        lines.append(action_label[action])
        for rec in stocks:
            symbol = rec["symbol"].replace(".NS", "").replace(".BO", "")
            conf = rec.get("confidence", 0)
            val  = rec.get("valuation", "")
            thesis = rec.get("thesis") or ""
            val_str = f" | {val.capitalize()}" if val and val != "unavailable" else ""
            lines.append(f"  {symbol} — {conf:.0%}{val_str}")
            if thesis:
                lines.append(f"  {thesis}")
        lines.append("")

    if overrides:
        lines.append(f"⚠️ Overrides this week: {len(overrides)}")
        for rec in overrides:
            symbol = rec["symbol"].replace(".NS", "").replace(".BO", "")
            reason = rec.get("override_reason") or ""
            lines.append(f"  {symbol}: {reason}")
    else:
        lines.append("⚠️ Overrides this week: none")

    # Top risk per BUY/WATCH symbol only — actionable ones
    actionable = [r for r in recommendations if r.get("action") in ("BUY", "SELL", "WATCH")]
    top_risks = []
    for rec in actionable:
        risks = rec.get("risks") or []
        if risks:
            symbol = rec["symbol"].replace(".NS", "").replace(".BO", "")
            top_risks.append(f"• {symbol}: {risks[0]}")

    if top_risks:
        lines.append("")
        lines.append("Key risks:")
        lines.extend(top_risks)

    return "\n".join(l for l in lines if l is not None)
