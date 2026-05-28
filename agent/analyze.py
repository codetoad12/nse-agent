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
