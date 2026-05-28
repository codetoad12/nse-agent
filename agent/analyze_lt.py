"""
LLM analysis for long-term (1-3 year) positions.
Uses fundamentals-driven system prompt. Same model as short-term for cost parity.
"""
import json
import logging
import os
import re

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
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": signal_text}],
    )

    raw = msg.content[0].text.strip()
    # Extract the first {...} JSON object, tolerating any surrounding markdown
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        raw = match.group(0)

    try:
        rec = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"LLM returned non-JSON for {bundle['symbol']}: {raw[:300]}")
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
