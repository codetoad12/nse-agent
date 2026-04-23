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

You receive a signal snapshot for one stock and must return a short-term recommendation.

RULES:
- Base your recommendation ONLY on the provided signals.
- SHORT_TERM means 1–3 weeks, driven by technical momentum.
- BUY  → clear oversold reading (RSI < 35) + at least one confirming signal.
- SELL → clear overbought reading (RSI > 65) + at least one confirming signal.
- HOLD → signals are mixed or neutral; no strong directional case.
- WATCH → one strong signal but missing confirmation; flag for next cycle.
- If key data is unavailable, lower your confidence accordingly.
- Indian macro/regulatory risk is always a background consideration.

RESPOND ONLY with valid JSON — no preamble, no markdown fences:
{
  "action": "BUY" | "HOLD" | "SELL" | "WATCH",
  "confidence": <float 0.0–1.0>,
  "timeframe": "1–3 weeks",
  "thesis": "<2 sentence explanation>",
  "key_signals": ["<signal 1>", "<signal 2>"],
  "risks": ["<risk 1>", "<risk 2>"]
}"""


def analyze(bundle: dict) -> dict:
    from agent.signals import format_for_llm

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    signal_text = format_for_llm(bundle)

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": signal_text}],
    )

    raw = msg.content[0].text.strip()
    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json\n"):
            raw = raw[5:]

    try:
        rec = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"LLM returned non-JSON for {bundle['symbol']}: {raw[:200]}")
        # Graceful fallback — treat as WATCH with low confidence
        rec = {
            "action": "WATCH",
            "confidence": 0.3,
            "timeframe": "1–3 weeks",
            "thesis": "LLM response could not be parsed. Manual review needed.",
            "key_signals": [],
            "risks": ["parse error"],
        }

    # Attach raw signal values so the log is self-contained
    rec["symbol"]   = bundle["symbol"]
    rec["price"]    = bundle.get("price")
    rec["rsi"]      = bundle.get("rsi")
    rec["macd"]     = bundle.get("macd_signal")
    rec["bollinger"] = bundle.get("bollinger_position")

    return rec
